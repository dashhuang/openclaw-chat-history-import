#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import zipfile
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from archive_contract import (
    build_archive_entry,
    normalize_timestamp_ms,
    synthetic_message_id,
    write_archive_entries,
)


TELEGRAM_MESSAGES_HTML_RE = re.compile(r"^messages(?:\d+)?\.html$")
TELEGRAM_EXPORT_ID_RE = re.compile(r"^message-?(\d+)$")
VOID_HTML_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


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
    parser.add_argument(
        "--chat-type",
        choices=["direct", "group", "channel"],
        help="Override chat type when the source format does not encode one.",
    )
    parser.add_argument("--peer-id", help="Override peer/chat id when the source format does not encode one.")
    parser.add_argument("--conversation-label", help="Override human-readable conversation label.")
    parser.add_argument(
        "--assistant-name",
        action="append",
        default=[],
        help="Speaker name to treat as assistant. Repeatable.",
    )
    parser.add_argument("--out-jsonl", help="Write normalized canonical entries to a JSONL file.")
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


def detect_chatgpt_export_names(names: set[str]) -> bool:
    return "conversations.json" in names and not detect_claude_export(names)


def detect_chatgpt_sharded_export_names(names: set[str]) -> bool:
    return any(name.startswith("conversations-") and name.endswith(".json") for name in names)


def list_chatgpt_conversation_filenames(names: Iterable[str]) -> list[str]:
    unique = {PurePosixPath(name).name for name in names}
    return sorted(
        name
        for name in unique
        if name == "conversations.json" or (name.startswith("conversations-") and name.endswith(".json"))
    )


def detect_telegram_desktop_export(names: Iterable[str]) -> bool:
    return any(TELEGRAM_MESSAGES_HTML_RE.match(PurePosixPath(name).name) for name in names)


class TelegramHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.messages: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.div_depth = 0
        self.active_capture: dict[str, Any] | None = None
        self.last_from_name: str | None = None

    def _start_capture(self, target: str) -> None:
        self.active_capture = {"target": target, "depth": 1, "buffer": []}

    def _finish_capture(self) -> None:
        if self.active_capture is None or self.current is None:
            self.active_capture = None
            return
        target = self.active_capture["target"]
        text = "".join(self.active_capture["buffer"]).replace("\xa0", " ")
        text = re.sub(r"\s+\n", "\n", text)
        text = re.sub(r"\n\s+", "\n", text)
        text = re.sub(r"[ \t]+", " ", text).strip()
        if target == "from_name":
            if text:
                self.current["from_name"] = text
        elif target == "text":
            if text:
                self.current.setdefault("texts", []).append(text)
        elif target == "reply_to":
            if text:
                self.current["reply_to"] = text
        elif target == "media_title":
            if text:
                self.current.setdefault("media_titles", []).append(text)
        elif target == "media_description":
            if text:
                self.current.setdefault("media_descriptions", []).append(text)
        elif target == "media_status":
            if text:
                self.current.setdefault("media_statuses", []).append(text)
        self.active_capture = None

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs_list)
        classes = attrs.get("class", "").split()

        if self.current is None and tag == "div" and "message" in classes:
            self.current = {"classes": classes, "id": attrs.get("id"), "texts": []}
            self.div_depth = 1
            return

        if self.current is not None and tag == "div":
            self.div_depth += 1

        if self.active_capture is not None:
            if tag == "br":
                self.active_capture["buffer"].append("\n")
                return
            if tag not in VOID_HTML_TAGS:
                self.active_capture["depth"] += 1
            return

        if self.current is None:
            return

        if tag == "div":
            class_name = attrs.get("class", "")
            if class_name == "from_name":
                self._start_capture("from_name")
                return
            if class_name == "text":
                self._start_capture("text")
                return
            if class_name == "reply_to details":
                self._start_capture("reply_to")
                return
            if class_name == "title bold":
                self._start_capture("media_title")
                return
            if class_name == "description":
                self._start_capture("media_description")
                return
            if class_name == "status details":
                self._start_capture("media_status")
                return

        if "date" in classes and "details" in classes and attrs.get("title") and not self.current.get("date_title"):
            self.current["date_title"] = attrs["title"]

    def handle_data(self, data: str) -> None:
        if self.active_capture is not None:
            self.active_capture["buffer"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.active_capture is not None:
            if tag not in VOID_HTML_TAGS:
                self.active_capture["depth"] -= 1
                if self.active_capture["depth"] == 0:
                    self._finish_capture()

        if self.current is None:
            return

        if tag == "div":
            self.div_depth -= 1

        if self.div_depth == 0:
            message = self.current
            self.current = None
            if "service" in message.get("classes", []):
                return
            if not message.get("from_name") and "joined" in message.get("classes", []) and self.last_from_name:
                message["from_name"] = self.last_from_name
            if message.get("from_name"):
                self.last_from_name = message["from_name"]
            self.messages.append(message)


def natural_html_key(path: Path) -> tuple[int, int]:
    if path.name == "messages.html":
        return (0, 0)
    match = re.fullmatch(r"messages(\d+)\.html", path.name)
    return (1, int(match.group(1)) if match else 10**9)


def normalize_telegram_export_message_id(raw_id: object) -> str | None:
    match = TELEGRAM_EXPORT_ID_RE.fullmatch(str(raw_id or "").strip())
    return match.group(1) if match else None


def parse_telegram_export_timestamp(raw_value: object) -> int | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    for fmt in ("%d.%m.%Y %H:%M:%S UTC%z", "%d.%m.%Y %H:%M:%S %z"):
        try:
            return int(datetime.strptime(value, fmt).timestamp() * 1000)
        except ValueError:
            continue
    return None


def normalize_telegram_media_text(message: dict[str, Any]) -> str:
    titles = [str(item).strip() for item in message.get("media_titles") or [] if str(item).strip()]
    descriptions = [
        str(item).strip()
        for item in message.get("media_descriptions") or []
        if str(item).strip() and "Not included, change data exporting settings to download." not in str(item)
    ]
    statuses = [str(item).strip() for item in message.get("media_statuses") or [] if str(item).strip()]
    title = titles[0] if titles else "Media"
    details = descriptions + statuses
    if details:
        return f"[Media] {title} | {', '.join(details)}"
    return f"[Media] {title}"


def extract_telegram_export_title(source: Path) -> str | None:
    first_page = source / "messages.html"
    if not first_page.exists():
        return None
    match = re.search(
        r'<div class="text bold">\s*(.*?)\s*</div>',
        first_page.read_text(encoding="utf-8", errors="ignore"),
        re.S,
    )
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip() or None


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
    rendered: list[str] = []

    parts = content.get("parts")
    if isinstance(parts, list):
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

    content_text = str(content.get("text") or "").strip()
    if content_text:
        return content_text

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


def load_chatgpt_conversations_from_zip(source: Path) -> tuple[list[dict[str, Any]], str]:
    with zipfile.ZipFile(source) as zf:
        member_names = [name for name in zf.namelist() if not name.endswith("/")]
        base_names = list_chatgpt_conversation_filenames(member_names)
        selected_members: list[str] = []

        if "conversations.json" in base_names:
            for name in member_names:
                if PurePosixPath(name).name == "conversations.json":
                    selected_members = [name]
                    break
        else:
            for base_name in base_names:
                for name in member_names:
                    if PurePosixPath(name).name == base_name:
                        selected_members.append(name)
                        break

        if not selected_members:
            raise SystemExit(f"unsupported zip format: {source}")

        conversations: list[dict[str, Any]] = []
        for member in selected_members:
            raw = json.loads(zf.read(member).decode("utf-8"))
            if isinstance(raw, list):
                conversations.extend(item for item in raw if isinstance(item, dict))
        return conversations, ("chatgpt-account-export" if len(selected_members) == 1 and PurePosixPath(selected_members[0]).name == "conversations.json" else "chatgpt-account-export-sharded")


def load_chatgpt_conversations_from_directory(source: Path) -> tuple[list[dict[str, Any]], str]:
    files = [p for p in source.rglob("*.json") if p.is_file()]
    selected_files: list[Path] = []

    standard = sorted(p for p in files if p.name == "conversations.json")
    if standard:
        selected_files = [standard[0]]
    else:
        selected_files = sorted(p for p in files if p.name.startswith("conversations-") and p.name.endswith(".json"))

    if not selected_files:
        raise SystemExit(f"unsupported source format: {source}")

    conversations: list[dict[str, Any]] = []
    for file_path in selected_files:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            conversations.extend(item for item in raw if isinstance(item, dict))
    detected = "chatgpt-directory-export" if len(selected_files) == 1 and selected_files[0].name == "conversations.json" else "chatgpt-directory-export-sharded"
    return conversations, detected


def normalize_chatgpt_conversations(
    conversations: list[dict[str, Any]],
    *,
    source: Path,
    detected_format: str,
    workspace: str,
    agent_id: str,
    provider_override: str | None,
) -> tuple[list[dict], dict[str, Any]]:
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
        "detected_format": detected_format,
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
    conversations, detected_format = load_chatgpt_conversations_from_zip(source)
    return normalize_chatgpt_conversations(
        conversations,
        source=source,
        detected_format=detected_format,
        workspace=workspace,
        agent_id=agent_id,
        provider_override=provider_override,
    )


def normalize_chatgpt_directory(
    source: Path,
    *,
    workspace: str,
    agent_id: str,
    provider_override: str | None,
) -> tuple[list[dict], dict[str, Any]]:
    conversations, detected_format = load_chatgpt_conversations_from_directory(source)
    return normalize_chatgpt_conversations(
        conversations,
        source=source,
        detected_format=detected_format,
        workspace=workspace,
        agent_id=agent_id,
        provider_override=provider_override,
    )


def normalize_telegram_desktop_export(
    source: Path,
    *,
    workspace: str,
    agent_id: str,
    provider_override: str | None,
    chat_type_override: str | None,
    peer_id_override: str | None,
    conversation_label_override: str | None,
    assistant_names: Iterable[str],
) -> tuple[list[dict], dict[str, Any]]:
    if not peer_id_override:
        raise SystemExit("telegram desktop import requires --peer-id")

    html_files = sorted(
        (path for path in source.iterdir() if path.is_file() and TELEGRAM_MESSAGES_HTML_RE.match(path.name)),
        key=natural_html_key,
    )
    if not html_files:
        raise SystemExit(f"unsupported source format: {source}")

    import_run_id = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-chat-import")
    provider = provider_override or "telegram"
    chat_type = chat_type_override or "group"
    peer_id = str(peer_id_override)
    export_title = extract_telegram_export_title(source)
    conversation_label = conversation_label_override or export_title or f"telegram:{chat_type}:{peer_id}"
    assistant_name_set = {name.strip() for name in assistant_names if str(name).strip()}
    entries: list[dict] = []
    skipped_messages = 0

    for html_file in html_files:
        parser = TelegramHTMLParser()
        parser.feed(html_file.read_text(encoding="utf-8", errors="ignore"))
        for ordinal, message in enumerate(parser.messages):
            raw_message_id = normalize_telegram_export_message_id(message.get("id"))
            from_name = str(message.get("from_name") or "").strip()
            role = "assistant" if from_name and from_name in assistant_name_set else "user"
            speaker_name = from_name or ("Assistant" if role == "assistant" else "User")
            texts = [str(item).strip() for item in message.get("texts") or [] if str(item).strip()]
            text = "\n\n".join(texts).strip() if texts else normalize_telegram_media_text(message)
            if not text:
                skipped_messages += 1
                continue
            timestamp_ms = parse_telegram_export_timestamp(message.get("date_title"))
            message_id = raw_message_id or synthetic_message_id(
                html_file.name, ordinal, from_name, message.get("date_title"), text[:80]
            )
            entries.append(
                build_archive_entry(
                    timestamp_ms=timestamp_ms,
                    channel="telegram",
                    chat_type=chat_type,
                    role=role,
                    text=text,
                    workspace=workspace,
                    agent_id=agent_id,
                    peer_id=peer_id,
                    conversation_label=conversation_label,
                    speaker_name=speaker_name,
                    speaker_id=None,
                    source_provider=provider,
                    source_type="telegram-desktop-html-export",
                    source_archive=source.name,
                    source_conversation_id=peer_id,
                    source_message_id=raw_message_id,
                    import_run_id=import_run_id,
                    message_id=message_id,
                )
            )

    manifest = {
        "source": str(source),
        "detected_format": "telegram-desktop-html-directory",
        "source_provider": provider,
        "import_run_id": import_run_id,
        "html_file_count": len(html_files),
        "entry_count": len(entries),
        "skipped_messages": skipped_messages,
        "archive_root": None,
        "conversation_label": conversation_label,
        "peer_id": peer_id,
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


def normalize(
    source: Path,
    *,
    workspace: str,
    agent_id: str,
    provider_override: str | None,
    chat_type_override: str | None = None,
    peer_id_override: str | None = None,
    conversation_label_override: str | None = None,
    assistant_names: Iterable[str] = (),
) -> tuple[list[dict], dict[str, Any]]:
    if source.is_dir():
        rel_names = {str(path.relative_to(source)) for path in source.rglob("*") if path.is_file()}
        base_names = {Path(name).name for name in rel_names}
        if detect_telegram_desktop_export(rel_names):
            return normalize_telegram_desktop_export(
                source,
                workspace=workspace,
                agent_id=agent_id,
                provider_override=provider_override,
                chat_type_override=chat_type_override,
                peer_id_override=peer_id_override,
                conversation_label_override=conversation_label_override,
                assistant_names=assistant_names,
            )
        if detect_chatgpt_export_names(base_names) or detect_chatgpt_sharded_export_names(base_names):
            return normalize_chatgpt_directory(
                source,
                workspace=workspace,
                agent_id=agent_id,
                provider_override=provider_override,
            )
        raise SystemExit(f"unsupported source format: {source}")

    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as zf:
            names = {PurePosixPath(name).name for name in zf.namelist() if not name.endswith("/")}
            if detect_claude_export(names):
                return normalize_claude_export(
                    source,
                    workspace=workspace,
                    agent_id=agent_id,
                    provider_override=provider_override,
                )
            if detect_chatgpt_export_names(names) or detect_chatgpt_sharded_export_names(names):
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
                return normalize_chatgpt_conversations(
                    [item for item in raw if isinstance(item, dict)],
                    source=source,
                    detected_format="chatgpt-conversations-json",
                    workspace=workspace,
                    agent_id=agent_id,
                    provider_override=provider_override,
                )

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
        chat_type_override=args.chat_type,
        peer_id_override=args.peer_id,
        conversation_label_override=args.conversation_label,
        assistant_names=args.assistant_name,
    )
    if args.out_jsonl:
        out_path = Path(args.out_jsonl).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
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
