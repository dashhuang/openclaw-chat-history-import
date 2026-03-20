#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = [
    "timestamp_utc",
    "timestamp_local",
    "local_date",
    "local_time",
    "channel",
    "chat_type",
    "role",
    "text",
]

VALID_CHAT_TYPES = {"direct", "group", "channel"}
VALID_ROLES = {"user", "assistant"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
TIMESTAMP_LOCAL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that imported archive files stay compatible with conversation-archive."
    )
    parser.add_argument(
        "archive_root",
        nargs="?",
        default="logs/message-archive-raw",
        help="Archive root to validate.",
    )
    parser.add_argument(
        "--import-run-id",
        help="Only validate entries written by this import_run_id.",
    )
    parser.add_argument(
        "--source-archive",
        help="Only validate entries whose source_archive matches this exact value.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser.parse_args()


def validate_entry(entry: dict[str, Any], path: Path, line_no: int) -> list[str]:
    errors: list[str] = []
    missing = [field for field in REQUIRED_FIELDS if field not in entry]
    if missing:
        errors.append(f"{path}:{line_no}: missing required fields: {', '.join(missing)}")
        return errors

    if entry.get("chat_type") not in VALID_CHAT_TYPES:
        errors.append(f"{path}:{line_no}: invalid chat_type={entry.get('chat_type')!r}")
    if entry.get("role") not in VALID_ROLES:
        errors.append(f"{path}:{line_no}: invalid role={entry.get('role')!r}")
    if not isinstance(entry.get("text"), str):
        errors.append(f"{path}:{line_no}: text must be a string")
    if not DATE_RE.match(str(entry.get("local_date") or "")):
        errors.append(f"{path}:{line_no}: invalid local_date={entry.get('local_date')!r}")
    if not TIME_RE.match(str(entry.get("local_time") or "")):
        errors.append(f"{path}:{line_no}: invalid local_time={entry.get('local_time')!r}")
    if not TIMESTAMP_LOCAL_RE.match(str(entry.get("timestamp_local") or "")):
        errors.append(f"{path}:{line_no}: invalid timestamp_local={entry.get('timestamp_local')!r}")
    if not str(entry.get("channel") or "").strip():
        errors.append(f"{path}:{line_no}: channel must be non-empty")
    if "conversation_slug" in entry and not str(entry.get("conversation_slug") or "").strip():
        errors.append(f"{path}:{line_no}: conversation_slug must be non-empty when present")
    return errors


def validate_path_shape(path: Path, archive_root: Path) -> list[str]:
    errors: list[str] = []
    rel = path.relative_to(archive_root)
    parts = rel.parts
    if len(parts) != 4:
        errors.append(
            f"{path}: expected path shape <channel>/<chat_type>/<conversation_slug>/<YYYY-MM-DD>.jsonl"
        )
        return errors
    _, chat_type, conversation_slug, filename = parts
    if chat_type not in VALID_CHAT_TYPES:
        errors.append(f"{path}: invalid chat_type path segment {chat_type!r}")
    if not conversation_slug.strip():
        errors.append(f"{path}: empty conversation_slug path segment")
    if not filename.endswith(".jsonl"):
        errors.append(f"{path}: expected .jsonl file")
    else:
        stem = filename[:-6]
        if not DATE_RE.match(stem):
            errors.append(f"{path}: filename stem must be YYYY-MM-DD")
    return errors


def entry_matches(entry: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.import_run_id and str(entry.get("import_run_id") or "") != args.import_run_id:
        return False
    if args.source_archive and str(entry.get("source_archive") or "") != args.source_archive:
        return False
    return True


def validate_archive(archive_root: Path, args: argparse.Namespace) -> dict[str, Any]:
    files = sorted(p for p in archive_root.rglob("*.jsonl") if p.is_file())
    errors: list[str] = []
    checked_entries = 0
    matched_files: set[str] = set()

    if not archive_root.exists():
        errors.append(f"missing archive root: {archive_root}")
        return {
            "archive_root": str(archive_root),
            "file_count": 0,
            "matched_file_count": 0,
            "entry_count": 0,
            "status": "error",
            "filters": {
                "import_run_id": args.import_run_id,
                "source_archive": args.source_archive,
            },
            "errors": errors,
        }

    if not files:
        errors.append(f"no jsonl files under: {archive_root}")

    for path in files:
        path_shape_errors = validate_path_shape(path, archive_root)
        path_had_match = False
        for line_no, raw in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError as exc:
                if not args.import_run_id and not args.source_archive:
                    errors.append(f"{path}:{line_no}: invalid json: {exc}")
                continue
            if not isinstance(entry, dict):
                if not args.import_run_id and not args.source_archive:
                    errors.append(f"{path}:{line_no}: entry must be a JSON object")
                continue
            if not entry_matches(entry, args):
                continue
            path_had_match = True
            checked_entries += 1
            matched_files.add(str(path))
            if path_shape_errors:
                errors.extend(path_shape_errors)
                path_shape_errors = []
            errors.extend(validate_entry(entry, path, line_no))

        if not args.import_run_id and not args.source_archive and path_shape_errors:
            errors.extend(path_shape_errors)

    if (args.import_run_id or args.source_archive) and checked_entries == 0:
        errors.append("no matching entries for supplied filters")

    return {
        "archive_root": str(archive_root),
        "file_count": len(files),
        "matched_file_count": len(matched_files),
        "entry_count": checked_entries,
        "status": "ok" if not errors else "error",
        "filters": {
            "import_run_id": args.import_run_id,
            "source_archive": args.source_archive,
        },
        "errors": errors,
    }


def main() -> int:
    args = parse_args()
    report = validate_archive(Path(args.archive_root).expanduser(), args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"archive_root={report['archive_root']}")
        print(f"file_count={report['file_count']}")
        print(f"matched_file_count={report['matched_file_count']}")
        print(f"entry_count={report['entry_count']}")
        print(f"status={report['status']}")
        if args.import_run_id:
            print(f"import_run_id={args.import_run_id}")
        if args.source_archive:
            print(f"source_archive={args.source_archive}")
        for error in report["errors"]:
            print(f"error={error}")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
