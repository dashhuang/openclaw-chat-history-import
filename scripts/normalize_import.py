#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from archive_contract import (
    build_archive_entry,
    normalize_timestamp_ms,
    synthetic_message_id,
    write_archive_entries,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize an external chat archive into conversation-archive-compatible JSONL."
    )
    parser.add_argument("source", help="Path to the source archive or canonical JSONL.")
    parser.add_argument(
        "--archive-root",
        default="logs/message-archive-raw",
        help="Archive root to write under.",
    )
    parser.add_argument("--workspace", default="workspace", help="Workspace label to embed in archive entries.")
    parser.add_argument("--agent-id", default="main", help="Agent id to embed in archive entries.")
    parser.add_argument("--provider", help="Override source provider when auto-detection is weak.")
    parser.add_argument("--apply", action="store_true", help="Write archive files instead of dry-run only.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser.parse_args()


def detect_claude_export(names: set[str]) -> bool:
    return {
        "users.json",
        "projects.json",
        "memories.json",
        "conversations.json",
    }.issubset(names)


def detect_chatgpt_export(names: set[str]) -> bool:
    return "conversations.json" in names and not detect_claude_export(names)


def render_message_text(message: dict[str, Any]) -> str:
    parts = []
    for part in message.get("content", []) or []:
        if part.get("type") == "text":
            text = str(part.get("text") or "").strip()
            if text:
                parts.append(text)
    if parts:
        return "\n\n".join(parts).strip()
    return str(message.get("text") or "").strip()


def parse_chatgpt_message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    parts = content.get("parts")
    if isinstance(parts, list):
        rendered = []
        for part in parts:
            if isinstance(part, str):
                text = part.strip()
                if text:
                    rendered.append(text)
            elif isinstance(part, dict):
                text = str(part.get("text") or "").strip()
                if text:
                    rendered.append(text)
        if rendered:
            return "\n\n".join(rendered).strip()
    text = str(message.get("text") or "").strip()
    if text:
        return text
    return ""


def iter_chatgpt_linear_messages(conversation: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = conversation.get("mapping") or {}
    current_node = conversation.get("current_node")
    if not isinstance(mapping, dict) or not current_node:
        return []

    chain = []
    seen = set()
    node_id = current_node
    while node_id and node_id not in seen:
        seen.add(node_id)
        node = mapping.get(node_id)
        if not isinstance(node, dict):
            break
        chain.append(node)
        node_id = node.get("parent")
    chain.reverse()

    messages = []
    for node in chain:
        message = node.get("message")
        if not isinstance(message, dict):
            continue
        author = message.get("author") or {}
        role = str(author.get("role") or "")
        if role not in {"user", "assistant"}:
            continue
        text = parse_chatgpt_message_text(message)
        if not text:
            continue
        messages.append(
            {
                "role": role,
                "text": text,
                "message_id": message.get("id") or node.get("id"),
                "timestamp_ms": normalize_timestamp_ms(message.get("create_time") or node.get("create_time")),
                "author_name": author.get("name"),
            }
        )
    return messages


def normalize_claude_export(
    source: Path,
    *,
    workspace: str,
    agent_id: str,
    provider_override: str | None,
) -> tuple[list[dict], dict[str, Any]]:
    with zipfile.ZipFile(source) as zf:
        conversations = json.loads(zf.read("conversations.json").decode("utf-8"))
        users = json.loads(zf.read("users.json").decode("utf-8"))

    user = users[0] if users else {}
    account_uuid = str(user.get("uuid") or "unknown-account")
    account_name = str(user.get("full_name") or "User")
    import_run_id = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-chat-import")
    provider = provider_override or "claude"
    source_name = source.name

    entries: list[dict] = []
    skipped_messages = 0

    for conv_index, conversation in enumerate(conversations):
        conversation_id = str(conversation.get("uuid") or f"conversation-{conv_index}")
        conversation_label = str(
            conversation.get("name")
            or conversation.get("summary")
            or f"{provider}-conversation-{conv_index + 1}"
        )
        peer_id = f"{provider}:account:{account_uuid}"
        ordinal = 0
        for message in conversation.get("chat_messages", []) or []:
            sender = str(message.get("sender") or "unknown")
            if sender not in {"human", "assistant"}:
                skipped_messages += 1
                continue
            role = "user" if sender == "human" else "assistant"
            speaker_name = account_name if role == "user" else "Assistant"
            speaker_id = account_uuid if role == "user" else None
            text = render_message_text(message)
            if not text:
                skipped_messages += 1
                continue
            created_at = message.get("created_at")
            timestamp_ms = None
            if created_at:
                try:
                    timestamp_ms = int(
                        datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).timestamp() * 1000
                    )
                except ValueError:
                    timestamp_ms = normalize_timestamp_ms(created_at)
            raw_message_id = message.get("uuid")
            message_id = str(raw_message_id) if raw_message_id else synthetic_message_id(
                conversation_id, created_at, role, ordinal
            )
            entries.append(
                build_archive_entry(
                    timestamp_ms=timestamp_ms,
                    channel=provider,
                    chat_type="direct",
                    role=role,
                    text=text,
                    workspace=workspace,
                    agent_id=agent_id,
                    peer_id=peer_id,
                    conversation_label=conversation_label,
                    speaker_name=speaker_name,
                    speaker_id=speaker_id,
                    source_provider=provider,
                    source_type="account-export",
                    source_archive=source_name,
                    source_conversation_id=conversation_id,
                    source_message_id=str(raw_message_id) if raw_message_id else None,
                    import_run_id=import_run_id,
                    message_id=message_id,
                )
            )
            ordinal += 1

    manifest = {
        "source": str(source),
        "detected_format": "claude-account-export",
        "source_provider": provider,
        "import_run_id": import_run_id,
        "conversation_count": len(conversations),
        "entry_count": len(entries),
        "skipped_messages": skipped_messages,
        "archive_root": None,
    }
    return entries, manifest


def normalize_chatgpt_export(
    source: Path,
    *,
    workspace: str,
    agent_id: str,
    provider_override: str | None,
) -> tuple[list[dict], dict[str, Any]]:
    with zipfile.ZipFile(source) as zf:
        conversations = json.loads(zf.read("conversations.json").decode("utf-8"))

    import_run_id = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-chat-import")
    provider = provider_override or "chatgpt"
    source_name = source.name
    entries: list[dict] = []
    skipped_messages = 0

    for conv_index, conversation in enumerate(conversations):
        conversation_id = str(
            conversation.get("id")
            or conversation.get("conversation_id")
            or conversation.get("uuid")
            or f"conversation-{conv_index}"
        )
        conversation_label = str(
            conversation.get("title")
            or conversation.get("name")
            or f"{provider}-conversation-{conv_index + 1}"
        )
        peer_id = f"{provider}:conversation:{conversation_id}"
        linear_messages = iter_chatgpt_linear_messages(conversation)
        if not linear_messages:
            skipped_messages += 1
            continue
        for ordinal, message in enumerate(linear_messages):
            role = str(message["role"])
            raw_message_id = message.get("message_id")
            message_id = str(raw_message_id) if raw_message_id else synthetic_message_id(
                conversation_id, message.get("timestamp_ms"), role, ordinal
            )
            speaker_name = "User" if role == "user" else "Assistant"
            author_name = message.get("author_name")
            if isinstance(author_name, str) and author_name.strip():
                speaker_name = author_name.strip()
            entries.append(
                build_archive_entry(
                    timestamp_ms=message.get("timestamp_ms"),
                    channel=provider,
                    chat_type="direct",
                    role=role,
                    text=str(message["text"]),
                    workspace=workspace,
                    agent_id=agent_id,
                    peer_id=peer_id,
                    conversation_label=conversation_label,
                    speaker_name=speaker_name,
                    source_provider=provider,
                    source_type="account-export",
                    source_archive=source_name,
                    source_conversation_id=conversation_id,
                    source_message_id=str(raw_message_id) if raw_message_id else None,
                    import_run_id=import_run_id,
                    message_id=message_id,
                )
            )

    manifest = {
        "source": str(source),
        "detected_format": "chatgpt-account-export",
        "source_provider": provider,
        "import_run_id": import_run_id,
        "conversation_count": len(conversations),
        "entry_count": len(entries),
        "skipped_messages": skipped_messages,
        "archive_root": None,
    }
    return entries, manifest


def normalize_canonical_jsonl(
    source: Path,
    *,
    workspace: str,
    agent_id: str,
    provider_override: str | None,
) -> tuple[list[dict], dict[str, Any]]:
    entries: list[dict] = []
    import_run_id = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-chat-import")
    for ordinal, raw in enumerate(source.read_text(encoding="utf-8", errors="ignore").splitlines()):
        raw = raw.strip()
        if not raw:
            continue
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            continue
        obj.setdefault("workspace", workspace)
        obj.setdefault("agent_id", agent_id)
        obj.setdefault("source", "import")
        obj.setdefault("source_provider", provider_override or obj.get("channel") or "imported")
        obj.setdefault("source_type", "canonical-jsonl")
        obj.setdefault("source_archive", source.name)
        obj.setdefault("import_run_id", import_run_id)
        if not obj.get("message_id"):
            obj["message_id"] = synthetic_message_id(obj.get("conversation_slug"), obj.get("timestamp_utc"), ordinal)
        entries.append(obj)
    manifest = {
        "source": str(source),
        "detected_format": "canonical-jsonl",
        "source_provider": provider_override or "imported",
        "import_run_id": import_run_id,
        "entry_count": len(entries),
        "archive_root": None,
    }
    return entries, manifest


def normalize(source: Path, *, workspace: str, agent_id: str, provider_override: str | None) -> tuple[list[dict], dict[str, Any]]:
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as zf:
            names = set(zf.namelist())
            if detect_claude_export(names):
                return normalize_claude_export(
                    source,
                    workspace=workspace,
                    agent_id=agent_id,
                    provider_override=provider_override,
                )
            if detect_chatgpt_export(names):
                return normalize_chatgpt_export(
                    source,
                    workspace=workspace,
                    agent_id=agent_id,
                    provider_override=provider_override,
                )
        raise SystemExit(f"unsupported zip format: {source}")

    if source.suffix.lower() == ".json":
        raw = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            sample = raw[0]
            if "mapping" in sample and ("current_node" in sample or "title" in sample):
                tmp_zip_like = source
                import_run_id = None
                # Reuse the same logic with a local shim.
                conversations = raw
                import_run_id = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-chat-import")
                provider = provider_override or "chatgpt"
                source_name = source.name
                entries: list[dict] = []
                skipped_messages = 0
                for conv_index, conversation in enumerate(conversations):
                    conversation_id = str(
                        conversation.get("id")
                        or conversation.get("conversation_id")
                        or conversation.get("uuid")
                        or f"conversation-{conv_index}"
                    )
                    conversation_label = str(
                        conversation.get("title")
                        or conversation.get("name")
                        or f"{provider}-conversation-{conv_index + 1}"
                    )
                    peer_id = f"{provider}:conversation:{conversation_id}"
                    linear_messages = iter_chatgpt_linear_messages(conversation)
                    if not linear_messages:
                        skipped_messages += 1
                        continue
                    for ordinal, message in enumerate(linear_messages):
                        role = str(message["role"])
                        raw_message_id = message.get("message_id")
                        message_id = str(raw_message_id) if raw_message_id else synthetic_message_id(
                            conversation_id, message.get("timestamp_ms"), role, ordinal
                        )
                        speaker_name = "User" if role == "user" else "Assistant"
                        author_name = message.get("author_name")
                        if isinstance(author_name, str) and author_name.strip():
                            speaker_name = author_name.strip()
                        entries.append(
                            build_archive_entry(
                                timestamp_ms=message.get("timestamp_ms"),
                                channel=provider,
                                chat_type="direct",
                                role=role,
                                text=str(message["text"]),
                                workspace=workspace,
                                agent_id=agent_id,
                                peer_id=peer_id,
                                conversation_label=conversation_label,
                                speaker_name=speaker_name,
                                source_provider=provider,
                                source_type="account-export",
                                source_archive=source_name,
                                source_conversation_id=conversation_id,
                                source_message_id=str(raw_message_id) if raw_message_id else None,
                                import_run_id=import_run_id,
                                message_id=message_id,
                            )
                        )
                manifest = {
                    "source": str(tmp_zip_like),
                    "detected_format": "chatgpt-conversations-json",
                    "source_provider": provider,
                    "import_run_id": import_run_id,
                    "conversation_count": len(conversations),
                    "entry_count": len(entries),
                    "skipped_messages": skipped_messages,
                    "archive_root": None,
                }
                return entries, manifest

    if source.suffix.lower() == ".jsonl":
        return normalize_canonical_jsonl(
            source,
            workspace=workspace,
            agent_id=agent_id,
            provider_override=provider_override,
        )

    raise SystemExit(f"unsupported source format: {source}")


def render_text(manifest: dict[str, Any]) -> str:
    return "\n".join(f"{key}={value}" for key, value in manifest.items())


def main() -> int:
    args = parse_args()
    source = Path(args.source).expanduser()
    archive_root = Path(args.archive_root).expanduser()
    entries, manifest = normalize(
        source,
        workspace=args.workspace,
        agent_id=args.agent_id,
        provider_override=args.provider,
    )
    if args.apply:
        result = write_archive_entries(archive_root, entries)
        manifest.update(result)
        manifest["archive_root"] = str(archive_root)
        manifest["status"] = "applied"
    else:
        manifest["archive_root"] = str(archive_root)
        manifest["status"] = "dry-run"

    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(render_text(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
