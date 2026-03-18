#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


IMPORT_MARKER_PREFIX = "<!-- imported-memory "
MEMORY_MD_FALLBACK_MARKER = "## 导入补充"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage or apply model-authored daily memory and MEMORY.md merge payloads."
    )
    parser.add_argument("payload_json", help="JSON payload authored by the model for memory merge.")
    parser.add_argument(
        "--memory-root",
        default="memory",
        help="Daily memory root containing YYYY-MM-DD.md files.",
    )
    parser.add_argument(
        "--memory-file",
        default="MEMORY.md",
        help="MEMORY.md file path.",
    )
    parser.add_argument(
        "--review-root",
        default="tmp/chat-history-import-review",
        help="Directory for staging review artifacts.",
    )
    parser.add_argument("--apply-daily", action="store_true", help="Write daily memory blocks into memory/YYYY-MM-DD.md.")
    parser.add_argument("--apply-long-term", action="store_true", help="Write approved MEMORY.md candidates into MEMORY.md.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser.parse_args()


def render_import_comment(provider: str, archive: str | None = None) -> str:
    provider = str(provider or "imported").strip().lower()
    parts = [f"provider={provider}"]
    if archive:
        parts.append(f"archive={archive}")
    return f"{IMPORT_MARKER_PREFIX}{' '.join(parts)} -->"


def payload_memory_md_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries = payload.get("memory_md")
    if entries is None:
        entries = payload.get("long_term_memory")
    return list(entries or [])


def render_daily_block(entry: dict[str, Any]) -> str:
    provider = str(entry.get("source_provider") or "imported")
    archive = str(entry.get("source_archive") or "").strip() or None
    lines = [render_import_comment(provider, archive)]
    for bullet in entry.get("bullets") or []:
        lines.append(f"- {bullet}")
    return "\n".join(lines).rstrip()


def normalize_section_heading(section: str | None) -> str | None:
    if not section:
        return None
    text = str(section).strip()
    if not text:
        return None
    if text.startswith("#"):
        return text
    return f"## {text}"


def find_footer_start(lines: list[str]) -> int:
    for idx, line in enumerate(lines):
        if line.strip() == "---":
            return idx
    return len(lines)


def line_starts_new_block(stripped: str) -> bool:
    return (
        stripped.startswith(IMPORT_MARKER_PREFIX)
        or stripped.startswith("#")
        or stripped == "---"
    )


def merge_daily_block(existing: str, entry: dict[str, Any]) -> str:
    provider = str(entry.get("source_provider") or "imported").strip().lower()
    new_block = render_daily_block(entry)
    lines = existing.splitlines()
    start = None
    end = None

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(IMPORT_MARKER_PREFIX) and f"provider={provider}" in stripped:
            start = idx
            end = idx + 1
            while end < len(lines):
                next_line = lines[end].strip()
                if line_starts_new_block(next_line):
                    break
                end += 1
            break

    if start is not None and end is not None:
        merged_lines = lines[:start] + [new_block] + lines[end:]
        return "\n".join(merged_lines).rstrip() + "\n"

    footer_start = find_footer_start(lines)
    if footer_start < len(lines):
        prefix = lines[:footer_start]
        suffix = lines[footer_start:]
        while prefix and not prefix[-1].strip():
            prefix = prefix[:-1]
        merged_lines = prefix + ["", new_block, ""] + suffix
        return "\n".join(merged_lines).rstrip() + "\n"

    trimmed = existing.rstrip()
    if trimmed:
        return trimmed + "\n\n" + new_block + "\n"
    return new_block + "\n"


def render_memory_md_block(entry: dict[str, Any]) -> str:
    provider = str(entry.get("source_provider") or "imported")
    archive = str(entry.get("source_archive") or "").strip() or None
    lines = [render_import_comment(provider, archive)]
    for bullet in entry.get("bullets") or []:
        lines.append(f"- {bullet}")
    return "\n".join(lines).rstrip()


def split_section_bounds(lines: list[str], heading: str) -> tuple[int, int] | None:
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == heading:
            start = idx
            break
    if start is None:
        return None
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("## ") or stripped == "---":
            end = idx
            break
    return start, end


def replace_or_append_import_block(lines: list[str], start: int, end: int, entry: dict[str, Any]) -> list[str]:
    provider = str(entry.get("source_provider") or "imported").strip().lower()
    new_block = render_memory_md_block(entry)
    block_start = None
    block_end = None

    for idx in range(start + 1, end):
        stripped = lines[idx].strip()
        if stripped.startswith(IMPORT_MARKER_PREFIX) and f"provider={provider}" in stripped:
            block_start = idx
            block_end = idx + 1
            while block_end < end:
                next_line = lines[block_end].strip()
                if line_starts_new_block(next_line):
                    break
                block_end += 1
            break

    if block_start is not None and block_end is not None:
        return lines[:block_start] + [new_block] + lines[block_end:]

    insert_at = end
    prefix = lines[:insert_at]
    while prefix and not prefix[-1].strip():
        prefix = prefix[:-1]
        insert_at -= 1
    suffix = lines[insert_at:]
    addition = ["", new_block]
    return prefix + addition + suffix


def merge_memory_md(existing: str, entry: dict[str, Any]) -> str:
    heading = normalize_section_heading(entry.get("section"))
    lines = existing.rstrip().splitlines()

    if not lines:
        lines = ["# 长期记忆"]

    if heading:
        bounds = split_section_bounds(lines, heading)
        if bounds is None:
            block = render_memory_md_block(entry)
            footer_start = find_footer_start(lines)
            prefix = lines[:footer_start]
            suffix = lines[footer_start:]
            while prefix and not prefix[-1].strip():
                prefix = prefix[:-1]
            merged_lines = prefix + ["", heading, block]
            if suffix:
                merged_lines += [""] + suffix
            return "\n".join(merged_lines).rstrip() + "\n"
        start, end = bounds
        merged_lines = replace_or_append_import_block(lines, start, end, entry)
        return "\n".join(merged_lines).rstrip() + "\n"

    block = render_memory_md_block(entry)
    if MEMORY_MD_FALLBACK_MARKER in existing:
        base, _, tail = existing.partition(MEMORY_MD_FALLBACK_MARKER)
        existing = base.rstrip()
        tail_lines = tail.splitlines()
        filtered_tail = []
        provider = str(entry.get("source_provider") or "imported").strip().lower()
        skip = False
        for line in tail_lines:
            stripped = line.strip()
            if stripped.startswith(IMPORT_MARKER_PREFIX) and f"provider={provider}" in stripped:
                skip = True
                continue
            if skip and (stripped.startswith(IMPORT_MARKER_PREFIX) or stripped.startswith("## ")):
                skip = False
            if not skip:
                filtered_tail.append(line)
        tail_body = "\n".join(filtered_tail).strip()
        if tail_body:
            return existing + f"\n\n{MEMORY_MD_FALLBACK_MARKER}\n\n{tail_body}\n\n{block}\n"
        return existing + f"\n\n{MEMORY_MD_FALLBACK_MARKER}\n\n{block}\n"
    footer_start = find_footer_start(lines)
    prefix = lines[:footer_start]
    suffix = lines[footer_start:]
    while prefix and not prefix[-1].strip():
        prefix = prefix[:-1]
    merged_lines = prefix + ["", MEMORY_MD_FALLBACK_MARKER, "", block]
    if suffix:
        merged_lines += [""] + suffix
    return "\n".join(merged_lines).rstrip() + "\n"


def write_review_files(review_root: Path, payload: dict[str, Any]) -> dict[str, str]:
    review_root.mkdir(parents=True, exist_ok=True)
    daily_file = review_root / "daily-memory-candidates.json"
    memory_md_file = review_root / "memory-md-candidates.md"

    daily_file.write_text(
        json.dumps(payload.get("daily_memory") or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    blocks: list[str] = []
    for entry in payload_memory_md_entries(payload):
        heading = normalize_section_heading(entry.get("section"))
        if heading:
            blocks.append(heading)
        blocks.append(render_memory_md_block(entry))
        blocks.append("")
    memory_md_file.write_text("\n".join(blocks).rstrip() + "\n", encoding="utf-8")

    return {
        "daily_review_file": str(daily_file),
        "memory_md_review_file": str(memory_md_file),
    }


def apply_daily(memory_root: Path, payload: dict[str, Any]) -> list[str]:
    written: list[str] = []
    memory_root.mkdir(parents=True, exist_ok=True)
    for entry in payload.get("daily_memory") or []:
        date = str(entry.get("date") or "").strip()
        if not date:
            continue
        path = memory_root / f"{date}.md"
        existing = path.read_text(encoding="utf-8") if path.exists() else f"# {date}\n"
        merged = merge_daily_block(existing, entry)
        path.write_text(merged, encoding="utf-8")
        written.append(str(path))
    return written


def apply_long_term(memory_file: Path, payload: dict[str, Any]) -> str:
    existing = memory_file.read_text(encoding="utf-8") if memory_file.exists() else "# 长期记忆\n"
    merged = existing
    for entry in payload_memory_md_entries(payload):
        merged = merge_memory_md(merged, entry)
    memory_file.write_text(merged, encoding="utf-8")
    return str(memory_file)


def main() -> int:
    args = parse_args()
    payload = json.loads(Path(args.payload_json).expanduser().read_text(encoding="utf-8"))
    review_files = write_review_files(Path(args.review_root).expanduser(), payload)

    daily_written: list[str] = []
    long_term_written: str | None = None

    if args.apply_daily:
        daily_written = apply_daily(Path(args.memory_root).expanduser(), payload)
    if args.apply_long_term:
        long_term_written = apply_long_term(Path(args.memory_file).expanduser(), payload)

    report = {
        "review_root": str(Path(args.review_root).expanduser()),
        **review_files,
        "daily_written": daily_written,
        "long_term_written": long_term_written,
        "status": "ok",
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for key, value in report.items():
            print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
