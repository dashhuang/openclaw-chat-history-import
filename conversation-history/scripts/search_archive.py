#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ARCHIVE_DIRS = [Path("logs/message-archive-raw")]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search workspace-local conversation archive JSONL.")
    parser.add_argument("--query", help="Case-insensitive substring to search in message text.")
    parser.add_argument("--sender", help="Case-insensitive substring filter for speaker name.")
    parser.add_argument("--channel", help="Channel filter, e.g. telegram, bluebubbles, feishu.")
    parser.add_argument("--chat-type", dest="chat_type", choices=["direct", "group", "channel"], help="Chat type filter.")
    parser.add_argument("--peer", help="Substring filter for peer ID or conversation label.")
    parser.add_argument("--date", help="Filter local_date (YYYY-MM-DD).")
    parser.add_argument("--from-date", dest="from_date", help="Lower bound local_date (YYYY-MM-DD).")
    parser.add_argument("--to-date", dest="to_date", help="Upper bound local_date (YYYY-MM-DD).")
    parser.add_argument("--role", choices=["user", "assistant"], help="Role filter.")
    parser.add_argument("--limit", type=int, default=8, help="Max hits to print (default: 8).")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser.parse_args()


def iter_entries(roots: list[Path]):
    for archive_root in roots:
        if not archive_root.exists():
            continue
        for path in sorted(archive_root.rglob("*.jsonl")):
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for raw_line in handle:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        entry = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    entry["_path"] = str(path)
                    yield entry


def matches(entry: dict, args: argparse.Namespace) -> bool:
    if args.role and entry.get("role") != args.role:
        return False
    if args.channel and entry.get("channel") != args.channel.lower():
        return False
    if args.chat_type and entry.get("chat_type") != args.chat_type:
        return False

    local_date = entry.get("local_date") or ""
    if args.date and local_date != args.date:
        return False
    if args.from_date and local_date < args.from_date:
        return False
    if args.to_date and local_date > args.to_date:
        return False

    if args.sender:
        speaker = (entry.get("speaker_name") or "").lower()
        if args.sender.lower() not in speaker:
            return False

    if args.peer:
        peer_text = " ".join(
            filter(
                None,
                [
                    str(entry.get("peer_id") or ""),
                    str(entry.get("conversation_label") or ""),
                    str(entry.get("conversation_slug") or ""),
                ],
            )
        ).lower()
        if args.peer.lower() not in peer_text:
            return False

    if args.query:
        text = (entry.get("text") or "").lower()
        if args.query.lower() not in text:
            return False

    return True


def render_text(results: list[dict]) -> str:
    lines: list[str] = []
    for entry in results:
        header = (
            f"[{entry.get('local_date')} {entry.get('local_time')}] "
            f"{entry.get('channel')}/{entry.get('chat_type')} "
            f"{entry.get('role')} {entry.get('speaker_name') or 'unknown'}"
        )
        lines.append(header)
        lines.append(
            f"conversation={entry.get('conversation_label') or entry.get('peer_id') or entry.get('conversation_slug')}"
        )
        if entry.get("message_id"):
            lines.append(f"message_id={entry['message_id']} session={entry.get('session_id')}")
        snippet = str(entry.get("text") or "").strip()
        lines.append(snippet)
        lines.append(f"path={entry.get('_path')}")
        lines.append("")
    return "\n".join(lines).rstrip()


def dedupe_results(results: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for entry in results:
        timestamp = entry.get("timestamp_utc") or entry.get("timestamp_local") or ""
        key = (
            entry.get("channel"),
            entry.get("chat_type"),
            entry.get("peer_id"),
            entry.get("role"),
            entry.get("message_id") or timestamp,
            entry.get("_path") or "",
            entry.get("text") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def sort_key(item: dict) -> tuple[str, str, str]:
    return (
        str(item.get("timestamp_utc") or item.get("timestamp_local") or ""),
        str(item.get("session_id") or ""),
        str(item.get("event_id") or ""),
    )


def main() -> int:
    args = parse_args()
    roots = [root for root in ARCHIVE_DIRS if root.exists()]
    if not roots:
        print(
            "archive directory missing: logs/message-archive-raw.",
            file=sys.stderr,
        )
        return 2

    results = [entry for entry in iter_entries(roots) if matches(entry, args)]
    results.sort(key=sort_key)
    results = dedupe_results(results)
    results = results[-max(args.limit, 1) :]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(render_text(results) if results else "No archive hits.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
