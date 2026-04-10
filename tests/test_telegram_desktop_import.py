#!/usr/bin/env python3

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from archive_contract import write_archive_entries  # noqa: E402
from inspect_import import inspect  # noqa: E402
from normalize_import import normalize  # noqa: E402


MESSAGES_HTML = """<!DOCTYPE html>
<html>
  <body>
    <div class="page_header">
      <div class="content">
        <div class="text bold">饭要吃饱</div>
      </div>
    </div>
    <div class="page_body chat_page">
      <div class="history">
        <div class="message service" id="message-1">
          <div class="body details">15 March 2026</div>
        </div>
        <div class="message default clearfix" id="message-999981572">
          <div class="body">
            <div class="pull_right date details" title="06.03.2018 15:24:36 UTC+10:00">15:24</div>
            <div class="from_name">Dash</div>
            <div class="text">上一条<br>带换行<br>不应该污染下一条</div>
          </div>
        </div>
        <div class="message default clearfix" id="message-999981571">
          <div class="body">
            <div class="pull_right date details" title="06.03.2018 15:25:36 UTC+10:00">15:25</div>
            <div class="from_name">Kros Dai</div>
            <div class="media_wrap clearfix">
              <div class="media clearfix pull_left media_sticker">
                <div class="body">
                  <div class="title bold">Sticker</div>
                  <div class="status details">🙊, 11.4 KB</div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="message default clearfix" id="message10620">
          <div class="body">
            <div class="pull_right date details" title="15.03.2026 18:21:51 UTC+10:00">18:21</div>
            <div class="from_name">Cindy</div>
            <div class="text">第一行<br>第二行</div>
          </div>
        </div>
        <div class="message default clearfix joined" id="message10621">
          <div class="body">
            <div class="pull_right date details" title="15.03.2026 18:22:01 UTC+10:00">18:22</div>
            <div class="reply_to details">In reply to <a href="messages263.html#go_to_message10613">this message</a></div>
            <div class="text">继续说</div>
          </div>
        </div>
      </div>
    </div>
  </body>
</html>
"""


MESSAGES2_HTML = """<!DOCTYPE html>
<html>
  <body>
    <div class="page_header">
      <div class="content">
        <div class="text bold">饭要吃饱</div>
      </div>
    </div>
    <div class="page_body chat_page">
      <div class="history">
        <div class="message default clearfix" id="message10622">
          <div class="body">
            <div class="pull_right date details" title="15.03.2026 18:23:03 UTC+10:00">18:23</div>
            <div class="from_name">Dash</div>
            <div class="media_wrap clearfix">
              <div class="media clearfix pull_left media_photo">
                <div class="fill pull_left"></div>
                <div class="body">
                  <div class="title bold">Photo</div>
                  <div class="description">Not included, change data exporting settings to download.</div>
                  <div class="status details">818×824, 73.0 KB</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </body>
</html>
"""


class TelegramDesktopImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.export_dir = Path(self.temp_dir.name) / "ChatExport"
        self.export_dir.mkdir(parents=True, exist_ok=True)
        (self.export_dir / "messages.html").write_text(MESSAGES_HTML, encoding="utf-8")
        (self.export_dir / "messages2.html").write_text(MESSAGES2_HTML, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_inspect_detects_telegram_desktop_export(self) -> None:
        report = inspect(self.export_dir)
        self.assertEqual(report["detected_format"], "telegram-desktop-html-directory")
        self.assertEqual(report["html_file_count"], 2)
        self.assertEqual(report["chat_title"], "饭要吃饱")

    def test_normalize_telegram_desktop_export_handles_old_and_new_message_ids(self) -> None:
        entries, manifest = normalize(
            self.export_dir,
            workspace="workspace-food-group",
            agent_id="food-group",
            provider_override=None,
            chat_type_override="group",
            peer_id_override="-1003778432310",
            conversation_label_override=None,
            assistant_names=["Cindy"],
        )

        self.assertEqual(manifest["entry_count"], 5)
        self.assertEqual(entries[0]["source_message_id"], "999981572")
        self.assertEqual(entries[0]["text"], "上一条\n带换行\n不应该污染下一条")

        self.assertEqual(entries[1]["source_message_id"], "999981571")
        self.assertEqual(entries[1]["message_id"], "999981571")
        self.assertEqual(entries[1]["speaker_name"], "Kros Dai")
        self.assertEqual(entries[1]["text"], "[Media] Sticker | 🙊, 11.4 KB")

        self.assertEqual(entries[2]["role"], "assistant")
        self.assertEqual(entries[2]["speaker_name"], "Cindy")
        self.assertEqual(entries[2]["text"], "第一行\n第二行")

        self.assertEqual(entries[3]["speaker_name"], "Cindy")
        self.assertEqual(entries[3]["role"], "assistant")
        self.assertEqual(entries[3]["message_id"], "10621")

        self.assertEqual(entries[4]["text"], "[Media] Photo | 818×824, 73.0 KB")
        self.assertEqual(entries[4]["peer_id"], "-1003778432310")
        self.assertEqual(entries[4]["conversation_slug"], "1003778432310")

    def test_write_archive_entries_is_idempotent_for_same_source_message_id(self) -> None:
        entries, _manifest = normalize(
            self.export_dir,
            workspace="workspace-food-group",
            agent_id="food-group",
            provider_override=None,
            chat_type_override="group",
            peer_id_override="-1003778432310",
            conversation_label_override=None,
            assistant_names=["Cindy"],
        )
        archive_root = Path(self.temp_dir.name) / "archive"

        first = write_archive_entries(archive_root, entries)
        second = write_archive_entries(archive_root, entries)

        self.assertEqual(first["entries_written"], 5)
        self.assertEqual(second["entries_written"], 0)
        self.assertEqual(second["entries_skipped"], 5)


if __name__ == "__main__":
    unittest.main()
