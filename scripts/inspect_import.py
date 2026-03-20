#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".txt"}
CHATGPT_METADATA_FILES = {
    "user.json",
    "user_settings.json",
    "shared_conversations.json",
    "group_chats.json",
    "message_feedback.json",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect an external chat archive before import."
    )
    parser.add_argument("path", help="Path to a zip, json/jsonl file, text file, or directory.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser.parse_args()


def read_json_bytes(raw: bytes) -> Any:
    return json.loads(raw.decode("utf-8"))


def detect_claude_export(names: set[str]) -> bool:
    return {
        "users.json",
        "projects.json",
        "memories.json",
        "conversations.json",
    }.issubset(names)


def detect_chatgpt_export_names(names: set[str]) -> bool:
    return "conversations.json" in names and not detect_claude_export(names)


def detect_chatgpt_sharded_export_names(names: set[str]) -> bool:
    return any(name.startswith("conversations-") and name.endswith(".json") for name in names)


def list_chatgpt_conversation_files(names: Iterable[str]) -> list[str]:
    return sorted(
        name
        for name in names
        if name == "conversations.json" or (name.startswith("conversations-") and name.endswith(".json"))
    )


def summarize_claude_zip(path: Path, zf: zipfile.ZipFile) -> dict[str, Any]:
    names = set(zf.namelist())
    conversations = read_json_bytes(zf.read("conversations.json"))
    memories = read_json_bytes(zf.read("memories.json"))
    projects = read_json_bytes(zf.read("projects.json"))
    users = read_json_bytes(zf.read("users.json"))

    content_types: Counter[str] = Counter()
    senders: Counter[str] = Counter()
    attachments = 0
    files = 0
    message_count = 0

    for conv in conversations:
        for message in conv.get("chat_messages", []) or []:
            message_count += 1
            senders[str(message.get("sender") or "unknown")] += 1
            attachments += len(message.get("attachments") or [])
            files += len(message.get("files") or [])
            for part in message.get("content", []) or []:
                content_types[str(part.get("type") or "unknown")] += 1

    return {
        "path": str(path),
        "type": "zip",
        "detected_format": "claude-account-export",
        "files": sorted(names),
        "conversation_count": len(conversations),
        "message_count": message_count,
        "memory_entry_count": len(memories),
        "project_count": len(projects),
        "user_count": len(users),
        "senders": dict(senders),
        "content_types": dict(content_types),
        "attachment_count": attachments,
        "file_reference_count": files,
    }


def summarize_chatgpt_file_set(path: Path, *, names: list[str], source_type: str) -> dict[str, Any]:
    conversation_files = list_chatgpt_conversation_files(names)
    top_level_names = sorted(
        name
        for name in names
        if "/" not in name.strip("/")
    )
    metadata_files = sorted(name for name in top_level_names if name in CHATGPT_METADATA_FILES)

    if "conversations.json" in conversation_files:
        detected = f"chatgpt-{source_type}-export"
    else:
        detected = f"chatgpt-{source_type}-export-sharded"

    return {
        "path": str(path),
        "type": source_type,
        "detected_format": detected,
        "conversation_json_file_count": len(conversation_files),
        "conversation_json_files_sample": conversation_files[:20],
        "top_level_files": top_level_names[:60],
        "metadata_files_present": metadata_files,
    }


def summarize_generic_zip(path: Path, zf: zipfile.ZipFile) -> dict[str, Any]:
    names = sorted(name for name in zf.namelist() if not name.endswith("/"))
    name_set = set(names)
    if detect_chatgpt_export_names(name_set) or detect_chatgpt_sharded_export_names(name_set):
        return summarize_chatgpt_file_set(path, names=names, source_type="zip")
    return {
        "path": str(path),
        "type": "zip",
        "detected_format": "unknown-zip",
        "files": names,
    }


def summarize_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    summary: dict[str, Any] = {
        "path": str(path),
        "type": "json",
        "detected_format": "unknown-json",
        "top_level": type(raw).__name__,
    }
    if isinstance(raw, list):
        summary["item_count"] = len(raw)
        if raw and isinstance(raw[0], dict):
            sample_keys = sorted(raw[0].keys())
            summary["sample_keys"] = sample_keys
            if "chat_messages" in raw[0]:
                summary["detected_format"] = "claude-conversations-json"
            elif "mapping" in raw[0] and ("current_node" in raw[0] or "title" in raw[0]):
                summary["detected_format"] = "chatgpt-conversations-json"
    elif isinstance(raw, dict):
        summary["top_level_keys"] = sorted(raw.keys())
    return summary


def summarize_jsonl(path: Path) -> dict[str, Any]:
    count = 0
    sample_keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        count += 1
        if not sample_keys:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                obj = None
            if isinstance(obj, dict):
                sample_keys.update(obj.keys())
    return {
        "path": str(path),
        "type": "jsonl",
        "detected_format": "jsonl",
        "line_count": count,
        "sample_keys": sorted(sample_keys),
    }


def summarize_text(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="ignore")
    return {
        "path": str(path),
        "type": "text",
        "detected_format": "plain-text-log",
        "line_count": len(content.splitlines()),
        "char_count": len(content),
    }


def summarize_directory(path: Path) -> dict[str, Any]:
    files = [p for p in path.rglob("*") if p.is_file()]
    rel_names = sorted(str(p.relative_to(path)) for p in files)
    suffixes = Counter(p.suffix.lower() or "<none>" for p in files)
    name_set = set(rel_names)
    if detect_chatgpt_export_names(name_set) or detect_chatgpt_sharded_export_names(name_set):
        report = summarize_chatgpt_file_set(path, names=rel_names, source_type="directory")
        report["file_count"] = len(files)
        report["suffixes"] = dict(sorted(suffixes.items()))
        return report
    return {
        "path": str(path),
        "type": "directory",
        "detected_format": "directory",
        "file_count": len(files),
        "suffixes": dict(sorted(suffixes.items())),
    }


def inspect(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing path: {path}")

    if path.is_dir():
        return summarize_directory(path)

    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = set(name for name in zf.namelist() if not name.endswith("/"))
            if detect_claude_export(names):
                return summarize_claude_zip(path, zf)
            return summarize_generic_zip(path, zf)

    if path.suffix.lower() == ".json":
        return summarize_json(path)

    if path.suffix.lower() == ".jsonl":
        return summarize_jsonl(path)

    if path.suffix.lower() in TEXT_SUFFIXES:
        return summarize_text(path)

    return {
        "path": str(path),
        "type": "file",
        "detected_format": "unknown-file",
        "suffix": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"path={report.get('path')}",
        f"type={report.get('type')}",
        f"detected_format={report.get('detected_format')}",
    ]
    for key in [
        "conversation_count",
        "message_count",
        "memory_entry_count",
        "project_count",
        "user_count",
        "attachment_count",
        "file_reference_count",
        "item_count",
        "line_count",
        "file_count",
        "conversation_json_file_count",
    ]:
        if key in report:
            lines.append(f"{key}={report[key]}")
    if "content_types" in report:
        lines.append(f"content_types={json.dumps(report['content_types'], ensure_ascii=False)}")
    if "senders" in report:
        lines.append(f"senders={json.dumps(report['senders'], ensure_ascii=False)}")
    if "sample_keys" in report:
        lines.append(f"sample_keys={json.dumps(report['sample_keys'], ensure_ascii=False)}")
    if "suffixes" in report:
        lines.append(f"suffixes={json.dumps(report['suffixes'], ensure_ascii=False)}")
    if "conversation_json_files_sample" in report:
        lines.append(
            f"conversation_json_files_sample={json.dumps(report['conversation_json_files_sample'], ensure_ascii=False)}"
        )
    if "top_level_files" in report:
        lines.append(f"top_level_files={json.dumps(report['top_level_files'], ensure_ascii=False)}")
    if "metadata_files_present" in report:
        lines.append(f"metadata_files_present={json.dumps(report['metadata_files_present'], ensure_ascii=False)}")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = inspect(Path(args.path).expanduser())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
