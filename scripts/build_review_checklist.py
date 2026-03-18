#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a date-by-date review checklist for imported chat history."
    )
    parser.add_argument(
        "archive_root",
        nargs="?",
        default="logs/message-archive-raw",
        help="Archive root or subdirectory to scan.",
    )
    parser.add_argument(
        "--source-archive",
        help="Only include entries whose source_archive matches this exact value.",
    )
    parser.add_argument(
        "--import-run-id",
        help="Only include entries whose import_run_id matches this exact value.",
    )
    parser.add_argument(
        "--source-provider",
        help="Only include entries whose source_provider matches this exact value.",
    )
    parser.add_argument(
        "--json-out",
        help="Write the checklist report as JSON to this path.",
    )
    parser.add_argument(
        "--md-out",
        help="Write the checklist report as Markdown to this path.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON to stdout instead of text summary.",
    )
    return parser.parse_args()


def entry_matches(entry: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.source_archive and str(entry.get("source_archive") or "") != args.source_archive:
        return False
    if args.import_run_id and str(entry.get("import_run_id") or "") != args.import_run_id:
        return False
    if args.source_provider and str(entry.get("source_provider") or "") != args.source_provider:
        return False
    return True


def build_report(archive_root: Path, args: argparse.Namespace) -> dict[str, Any]:
    files = sorted(p for p in archive_root.rglob("*.jsonl") if p.is_file())
    days: list[dict[str, Any]] = []
    total_entries = 0
    total_user = 0
    total_assistant = 0

    for path in files:
        matched_entries: list[dict[str, Any]] = []
        user_count = 0
        assistant_count = 0

        for line_no, raw in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            if not entry_matches(entry, args):
                continue
            matched_entries.append(entry)
            role = str(entry.get("role") or "")
            if role == "user":
                user_count += 1
            elif role == "assistant":
                assistant_count += 1

        if not matched_entries:
            continue

        total_entries += len(matched_entries)
        total_user += user_count
        total_assistant += assistant_count

        sample = matched_entries[0]
        days.append(
            {
                "date": path.stem,
                "path": str(path),
                "relative_path": str(path.relative_to(archive_root)),
                "entry_count": len(matched_entries),
                "user_count": user_count,
                "assistant_count": assistant_count,
                "channel": sample.get("channel"),
                "chat_type": sample.get("chat_type"),
                "conversation_slug": sample.get("conversation_slug"),
                "source_provider": sample.get("source_provider"),
                "source_archive": sample.get("source_archive"),
                "import_run_id": sample.get("import_run_id"),
                "reviewed": False,
                "decision": None,
                "reason": None,
            }
        )

    return {
        "archive_root": str(archive_root),
        "filters": {
            "source_archive": args.source_archive,
            "import_run_id": args.import_run_id,
            "source_provider": args.source_provider,
        },
        "dates_total": len(days),
        "entries_total": total_entries,
        "user_entries_total": total_user,
        "assistant_entries_total": total_assistant,
        "days": days,
    }


def render_markdown(report: dict[str, Any]) -> str:
    filters = report.get("filters") or {}
    lines = [
        "# Import Review Checklist",
        "",
        f"- archive_root: `{report['archive_root']}`",
        f"- dates_total: {report['dates_total']}",
        f"- entries_total: {report['entries_total']}",
        f"- user_entries_total: {report['user_entries_total']}",
        f"- assistant_entries_total: {report['assistant_entries_total']}",
    ]
    active_filters = {k: v for k, v in filters.items() if v}
    if active_filters:
        lines.append("- filters:")
        for key, value in active_filters.items():
            lines.append(f"  - {key}: `{value}`")
    lines.extend(["", "## Dates", ""])

    for day in report.get("days") or []:
        lines.append(
            "- [ ] "
            f"{day['date']} — {day['entry_count']} entries "
            f"({day['user_count']} user / {day['assistant_count']} assistant) — "
            f"`{day['relative_path']}`"
        )

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    archive_root = Path(args.archive_root).expanduser()
    report = build_report(archive_root, args)

    if args.json_out:
        json_path = Path(args.json_out).expanduser()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.md_out:
        md_path = Path(args.md_out).expanduser()
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(report), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"archive_root={report['archive_root']}")
        print(f"dates_total={report['dates_total']}")
        print(f"entries_total={report['entries_total']}")
        print(f"user_entries_total={report['user_entries_total']}")
        print(f"assistant_entries_total={report['assistant_entries_total']}")
        for day in report.get("days") or []:
            print(
                "day="
                f"{day['date']}|{day['entry_count']}|{day['user_count']}|{day['assistant_count']}|{day['relative_path']}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
