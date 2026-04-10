#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


NON_ALNUM_RE = re.compile(r"[^a-z0-9._+-]+")


def pad2(value: int) -> str:
    return str(value).zfill(2)


def sanitize_slug(value: str) -> str:
    slug = NON_ALNUM_RE.sub("-", str(value or "").strip().lower()).strip("-")
    return slug or "unknown"


def normalize_text(text: str) -> str:
    lines = (
        str(text or "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u2028", "\n")
        .replace("\u2029", "\n")
        .replace("\x85", "\n")
        .split("\n")
    )
    return "\n".join(line.rstrip() for line in lines).strip()


def normalize_timestamp_ms(value: object) -> int | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    if numeric < 1e11:
        return int(numeric * 1000)
    return int(numeric)


def format_local_date(dt: datetime) -> str:
    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"


def format_local_time(dt: datetime) -> str:
    return f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"


def format_local_timestamp(dt: datetime) -> str:
    offset = dt.utcoffset()
    offset_minutes = 0 if offset is None else int(offset.total_seconds() // 60)
    sign = "+" if offset_minutes >= 0 else "-"
    abs_minutes = abs(offset_minutes)
    hours = abs_minutes // 60
    minutes = abs_minutes % 60
    return f"{format_local_date(dt)}T{format_local_time(dt)}{sign}{pad2(hours)}:{pad2(minutes)}"


def synthetic_message_id(*parts: object) -> str:
    payload = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return f"import-{digest[:20]}"


def build_archive_entry(
    *,
    timestamp_ms: int | None,
    channel: str,
    chat_type: str,
    role: str,
    text: str,
    workspace: str,
    agent_id: str,
    peer_id: str,
    conversation_label: str,
    speaker_name: str,
    source_provider: str,
    source_type: str,
    source_archive: str,
    import_run_id: str,
    message_id: str | None = None,
    speaker_id: str | None = None,
    source_conversation_id: str | None = None,
    source_message_id: str | None = None,
    imported_at: str | None = None,
) -> dict:
    effective_ts = timestamp_ms if timestamp_ms is not None else int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    utc_dt = datetime.fromtimestamp(effective_ts / 1000, tz=timezone.utc)
    local_dt = utc_dt.astimezone()
    conversation_slug = sanitize_slug(peer_id or conversation_label)
    clean_text = normalize_text(text)
    return {
        "source": "import",
        "timestamp_utc": utc_dt.isoformat().replace("+00:00", "Z"),
        "timestamp_local": format_local_timestamp(local_dt),
        "local_date": format_local_date(local_dt),
        "local_time": format_local_time(local_dt),
        "workspace": workspace,
        "agent_id": agent_id,
        "channel": str(channel).lower(),
        "chat_type": chat_type,
        "peer_id": peer_id,
        "conversation_label": conversation_label,
        "conversation_slug": conversation_slug,
        "message_id": message_id,
        "role": role,
        "speaker_name": speaker_name,
        "speaker_id": speaker_id,
        "text": clean_text,
        "source_provider": source_provider,
        "source_type": source_type,
        "source_archive": source_archive,
        "source_conversation_id": source_conversation_id,
        "source_message_id": source_message_id,
        "import_run_id": import_run_id,
        "imported_at": imported_at or format_local_timestamp(datetime.now().astimezone()),
    }


def archive_relative_path(entry: dict) -> Path:
    return Path(entry["channel"]) / entry["chat_type"] / entry["conversation_slug"] / f"{entry['local_date']}.jsonl"


def dedupe_identity(entry: dict) -> str:
    if entry.get("source_message_id"):
        return f"smid:{entry['source_message_id']}"
    if entry.get("message_id"):
        return f"mid:{entry['message_id']}"
    timestamp = str(entry.get("timestamp_utc") or entry.get("timestamp_local") or "")
    text = normalize_text(str(entry.get("text") or ""))
    return f"fallback:{timestamp}|{text}"


def dedupe_key(entry: dict) -> tuple[str, str, str, str, str]:
    peer = str(entry.get("peer_id") or entry.get("conversation_slug") or entry.get("conversation_label") or "")
    return (
        str(entry.get("channel") or ""),
        str(entry.get("chat_type") or ""),
        peer,
        str(entry.get("role") or ""),
        dedupe_identity(entry),
    )


def write_archive_entries(archive_root: Path, entries: Iterable[dict]) -> dict[str, int]:
    files_written = 0
    entries_written = 0
    entries_skipped = 0
    grouped: dict[Path, list[dict]] = {}
    for entry in entries:
        rel = archive_relative_path(entry)
        grouped.setdefault(rel, []).append(entry)

    for rel, rel_entries in grouped.items():
        full_path = archive_root / rel
        full_path.parent.mkdir(parents=True, exist_ok=True)
        existing_keys = set()
        if full_path.exists():
            for raw_line in full_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    existing = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if isinstance(existing, dict):
                    existing_keys.add(dedupe_key(existing))
        lines_to_write = []
        for entry in rel_entries:
            key = dedupe_key(entry)
            if key in existing_keys:
                entries_skipped += 1
                continue
            existing_keys.add(key)
            lines_to_write.append(json.dumps(entry, ensure_ascii=False))
            entries_written += 1
        if not lines_to_write:
            continue
        with full_path.open("a", encoding="utf-8") as handle:
            for line in lines_to_write:
                handle.write(line + "\n")
        files_written += 1

    return {
        "files_written": files_written,
        "entries_written": entries_written,
        "entries_skipped": entries_skipped,
    }
