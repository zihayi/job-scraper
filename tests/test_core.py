from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from chat_markdown import render_markdown
from chat_store import ChatStore
from clean import clean_html
from config import SettingsStore
from extract import _normalize_location, chat_about_jobs
from store import JobStore


class CleanHtmlTests(unittest.TestCase):
    def test_removes_noise_and_keeps_job_text(self):
        html = "<nav>菜单</nav><main><h1>后端工程师</h1><script>bad()</script><p>负责 API</p></main>"
        self.assertEqual(clean_html(html), "后端工程师\n负责 API")


class ExtractTests(unittest.TestCase):
    def test_normalizes_city_names_and_delimiters(self):
        self.assertEqual(_normalize_location("深圳市，上海市、深圳市"), "深圳、上海")
        self.assertEqual(_normalize_location("北京市海淀区/重庆市渝北区"), "北京、重庆")
        self.assertEqual(_normalize_location("广东省深圳市南山区"), "深圳")

    def test_streams_reasoning_and_final_answer(self):
        class FakeStream(list):
            def close(self):
                self.closed = True

        stream = FakeStream([
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                content=None, reasoning_content="先比较", model_extra={}
            ))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                content="推荐岗位", reasoning_content=None, model_extra={}
            ))]),
        ])
        create = Mock(return_value=stream)
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
            close=Mock(),
        )
        with patch("extract._client", return_value=client):
            reply = chat_about_jobs(
                "哪个岗位更合适？",
                [{"title": "后端工程师", "requirements": []}],
                [],
                "test-key",
            )
        self.assertEqual(reply, {"content": "推荐岗位", "reasoning": "先比较"})
        self.assertTrue(create.call_args.kwargs["stream"])
        self.assertTrue(stream.closed)
        client.close.assert_called_once()


class JobStoreTests(unittest.TestCase):
    def test_add_deduplicate_update_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory) / "jobs.json")
            source = {"title": "工程师", "location": "深圳", "source_url": "https://example.com/job"}
            added = store.add([source, source])
            self.assertEqual(len(added), 1)
            job_id = added[0]["id"]
            updated = store.update(
                job_id,
                {"title": "高级工程师", "company": "示例公司", "location": "上海", "status": "已投递", "starred": True},
            )
            self.assertEqual(updated["title"], "高级工程师")
            self.assertEqual(updated["company"], "示例公司")
            self.assertEqual(updated["location"], "上海")
            self.assertEqual(updated["status"], "已投递")
            self.assertTrue(updated["starred"])
            store.delete(job_id)
            self.assertEqual(store.list(), [])

    def test_rejects_invalid_tracking_value(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory) / "jobs.json")
            job_id = store.add([{"title": "工程师", "source_url": "https://example.com"}])[0]["id"]
            with self.assertRaises(ValueError):
                store.update(job_id, {"status": "未知状态"})
            with self.assertRaises(ValueError):
                store.update(job_id, {"title": "  "})


class ChatStoreTests(unittest.TestCase):
    def test_persists_exchange_and_provides_model_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chat.json"
            store = ChatStore(path)
            messages = store.add_exchange("比较岗位", "岗位 A 更匹配。", "先比较技术要求。")
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[1]["reasoning"], "先比较技术要求。")
            self.assertEqual(ChatStore(path).context(), [
                {"role": "user", "content": "比较岗位"},
                {"role": "assistant", "content": "岗位 A 更匹配。"},
            ])
            store.clear()
            self.assertEqual(store.list(), [])


class ChatMarkdownTests(unittest.TestCase):
    def test_renders_markdown_and_escapes_raw_html(self):
        html = render_markdown("## 推荐\n\n- **岗位 A**\n\n<script>alert(1)</script>")
        self.assertIn("<h2>推荐</h2>", html)
        self.assertIn("<strong>岗位 A</strong>", html)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_renders_reasoning_markdown_separately(self):
        from chat_markdown import render_chat_messages

        messages = render_chat_messages([
            {"role": "assistant", "content": "结论", "reasoning": "1. **比较要求**"}
        ])
        self.assertIn("<strong>比较要求</strong>", messages[0]["reasoning_html"])


class SettingsStoreTests(unittest.TestCase):
    def test_saves_model_port_and_masks_key(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            public = store.update(
                {
                    "api_key": "test-key",
                    "extraction_model": "deepseek-chat",
                    "chat_model": "deepseek-reasoner",
                    "port": 8001,
                }
            )
            self.assertTrue(public["has_api_key"])
            self.assertNotIn("example-secret", public["api_key_masked"])
            self.assertEqual(public["extraction_model"], "deepseek-chat")
            self.assertEqual(public["chat_model"], "deepseek-reasoner")
            self.assertEqual(public["port"], 8001)

    def test_uses_legacy_model_as_extraction_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"model":"deepseek-reasoner"}', encoding="utf-8")
            values = SettingsStore(path).effective()
            self.assertEqual(values["extraction_model"], "deepseek-reasoner")
            self.assertEqual(values["chat_model"], "deepseek-reasoner")


if __name__ == "__main__":
    unittest.main()
