from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as webapp
from chat_store import ChatStore
from config import SettingsStore
from store import JobStore


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        directory = Path(self.temp_dir.name)
        webapp.app.config.update(TESTING=True)
        webapp.job_store = JobStore(directory / "jobs.json")
        webapp.settings_store = SettingsStore(directory / "settings.json")
        webapp.chat_store = ChatStore(directory / "chat.json")
        self.client = webapp.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_index_and_public_settings(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Job Scraper", page)
        self.assertIn('id="companyFilter"', page)
        self.assertIn('id="locationFilter"', page)
        self.assertIn('id="recruitTypeFilter"', page)
        self.assertIn('id="statusFilter"', page)
        self.assertIn('aria-label="职位名称"', page)
        self.assertIn('aria-label="公司名称"', page)
        self.assertIn('aria-label="所在地"', page)
        self.assertIn('id="chatBtn"', page)
        self.assertIn('id="chatModal"', page)
        self.assertIn('id="chatDockBtn"', page)
        self.assertIn('id="chatFullBtn"', page)
        self.assertIn('id="chatSettingsBtn"', page)
        self.assertIn('id="chatQuestionBtn"', page)
        self.assertIn('id="chatQuestionList"', page)
        self.assertIn('id="addJobBtn"', page)
        self.assertIn('id="addJobModal"', page)
        self.assertIn('id="confirmModal"', page)
        self.assertIn('function askConfirm(', page)
        self.assertNotIn("!confirm(", page)
        self.assertIn('id="contextStatus"', page)
        self.assertIn('class="status-date"', page)
        self.assertIn('class="status-history"', page)
        self.assertIn('data-detail-field="description"', page)
        self.assertIn('data-detail-field="requirements"', page)
        self.assertIn('onclick="saveJobDetails', page)
        self.assertIn('onclick="startEditJobDetails', page)
        self.assertNotIn('data-detail-field="salary"', page)
        self.assertIn('id="browserUseEnabledInput"', page)
        self.assertIn('id="browserMaxStepsInput"', page)
        self.assertIn('data-settings-tab="browser"', page)
        self.assertIn('data-settings-tab="about"', page)
        self.assertIn('id="aboutVersion"', page)

        settings = self.client.get("/api/settings").get_json()
        self.assertFalse(settings["has_api_key"])
        self.assertEqual(settings["extraction_model"], "deepseek-chat")
        self.assertEqual(settings["chat_model"], "deepseek-reasoner")
        self.assertFalse(settings["browser_use_enabled"])
        self.assertEqual(settings["browser_max_steps"], 20)
        self.assertIn('id="extractionModelSelect"', page)
        self.assertIn('id="chatModelSelect"', page)

    def test_settings_never_returns_plain_api_key(self):
        response = self.client.post(
            "/api/settings",
            json={
                "api_key": "test-key",
                "extraction_model": "deepseek-reasoner",
                "chat_model": "deepseek-chat",
                "port": 5001,
                "browser_use_enabled": True,
                "browser_max_steps": 24,
            },
        )
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertNotIn("test-secret", text)
        self.assertTrue(response.get_json()["has_api_key"])
        self.assertEqual(response.get_json()["extraction_model"], "deepseek-reasoner")
        self.assertEqual(response.get_json()["chat_model"], "deepseek-chat")
        self.assertTrue(response.get_json()["browser_use_enabled"])
        self.assertEqual(response.get_json()["browser_max_steps"], 24)

    def test_about_returns_git_version_and_update_time(self):
        with patch.object(
            webapp,
            "_git_app_info",
            return_value={"git_version": "abc1234", "updated_at": "2026-08-05T10:36:20+08:00", "dirty": True},
        ):
            response = self.client.get("/api/about")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "name": "Job Scraper",
            "git_version": "abc1234",
            "updated_at": "2026-08-05T10:36:20+08:00",
            "dirty": True,
        })

    def test_job_lifecycle_and_excel_export(self):
        job = webapp.job_store.add(
            [{"title": "Python 工程师", "company": "示例公司", "source_url": "https://example.com/job"}]
        )[0]
        listed = self.client.get("/api/jobs").get_json()["jobs"]
        self.assertEqual(len(listed), 1)

        response = self.client.patch(
            f"/api/jobs/{job['id']}",
            json={"title": "高级 Python 工程师", "company": "新公司", "location": "深圳", "status": "面试中"},
        )
        self.assertEqual(response.status_code, 200)
        updated = response.get_json()["job"]
        self.assertEqual(updated["title"], "高级 Python 工程师")
        self.assertEqual(updated["company"], "新公司")
        self.assertEqual(updated["location"], "深圳")
        self.assertEqual(updated["status"], "面试中")
        self.assertEqual([entry["status"] for entry in updated["status_history"]], ["待投递", "面试中"])

        response = self.client.patch(
            f"/api/jobs/{job['id']}",
            json={
                "salary": "25k-35k",
                "employment_type": "全职",
                "source_url": "https://example.com/job-updated",
                "description": "更新后的职位描述",
                "requirements": ["Python", " Linux "],
            },
        )
        self.assertEqual(response.status_code, 200)
        details = response.get_json()["job"]
        self.assertEqual(details["salary"], "25k-35k")
        self.assertEqual(details["requirements"], ["Python", "Linux"])
        self.assertEqual(details["url"], "https://example.com/job-updated")
        self.assertFalse(details["description_verbatim"])
        invalid_url = self.client.patch(f"/api/jobs/{job['id']}", json={"source_url": "not-a-url"})
        self.assertEqual(invalid_url.status_code, 400)

        export = self.client.get("/api/export")
        self.assertEqual(export.status_code, 200)
        self.assertTrue(export.data.startswith(b"PK"))

        response = self.client.delete(f"/api/jobs/{job['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/jobs").get_json()["jobs"], [])

    def test_manually_creates_job_with_tracking_fields(self):
        payload = {
            "title": "嵌入式软件工程师",
            "company": "示例科技",
            "location": "深圳市、上海市",
            "recruit_type": "校招",
            "status": "已投递",
            "employment_type": "全职",
            "salary": "20k-30k",
            "source_url": "https://example.com/manual-job",
            "description": "负责嵌入式系统开发",
            "requirements": ["熟悉 C++", "熟悉 Linux"],
            "note": "朋友内推",
        }
        response = self.client.post("/api/jobs", json=payload)
        self.assertEqual(response.status_code, 201)
        job = response.get_json()["job"]
        self.assertEqual(job["location"], "深圳、上海")
        self.assertEqual(job["status"], "已投递")
        self.assertEqual(job["note"], "朋友内推")
        self.assertEqual(job["requirements"], ["熟悉 C++", "熟悉 Linux"])
        self.assertEqual([entry["status"] for entry in job["status_history"]], ["待投递", "已投递"])

        duplicate = self.client.post("/api/jobs", json=payload)
        self.assertEqual(duplicate.status_code, 409)
        invalid = self.client.post("/api/jobs", json={"title": "测试", "source_url": "not-a-url"})
        self.assertEqual(invalid.status_code, 400)

    def test_scrape_requires_api_key(self):
        response = self.client.post("/api/scrape", json={"url": "https://example.com", "dynamic": False})
        self.assertEqual(response.status_code, 400)
        self.assertIn("DeepSeek API Key", response.get_json()["error"])

    def test_job_chat_saves_loads_and_clears_history(self):
        webapp.job_store.add(
            [{"title": "后端工程师", "company": "示例公司", "source_url": "https://example.com/job"}]
        )
        webapp.settings_store.update({
            "api_key": "test-key",
            "extraction_model": "deepseek-chat",
            "chat_model": "deepseek-reasoner",
        })
        with patch.object(
            webapp,
            "stream_chat_about_jobs",
            return_value=iter([
                {"type": "reasoning", "delta": "先比较岗位的技术栈，"},
                {"type": "reasoning", "delta": "再检查地点。"},
                {"type": "answer", "delta": "## 建议\n\n"},
                {"type": "answer", "delta": "- **适合 Python 后端方向**"},
            ]),
        ) as chat:
            response = self.client.post(
                "/api/chat", json={"message": "这个岗位适合什么方向？"}, buffered=True
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/x-ndjson")
        events = [json.loads(line) for line in response.get_data(as_text=True).splitlines()]
        self.assertEqual([event["type"] for event in events[:4]], ["reasoning", "reasoning", "answer", "answer"])
        messages = events[-1]["messages"]
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual([message["role"] for message in messages], ["user", "assistant"])
        self.assertIn("<h2>建议</h2>", messages[1]["html"])
        self.assertIn("<strong>适合 Python 后端方向</strong>", messages[1]["html"])
        self.assertIn("先比较岗位的技术栈", messages[1]["reasoning_html"])
        self.assertEqual(len(self.client.get("/api/chat").get_json()["messages"]), 2)
        self.assertEqual(chat.call_args.args[1][0]["title"], "后端工程师")
        self.assertEqual(chat.call_args.args[4], "deepseek-reasoner")

        response = self.client.delete("/api/chat")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/chat").get_json()["messages"], [])

    def test_chat_automatically_starts_new_session_near_context_limit(self):
        webapp.job_store.add([{"title": "后端工程师", "source_url": "https://example.com/job"}])
        webapp.settings_store.update({"api_key": "test-key", "chat_model": "deepseek-reasoner"})
        webapp.chat_store.add_exchange("旧问题", "旧回答")
        events = iter([
            {"type": "reasoning", "delta": "新分析"},
            {"type": "answer", "delta": "新回答"},
        ])
        with (
            patch.object(webapp, "estimate_chat_context_tokens", return_value=995_000),
            patch.object(webapp, "stream_chat_about_jobs", return_value=events) as chat,
        ):
            response = self.client.post("/api/chat", json={"message": "新问题"}, buffered=True)
        streamed = [json.loads(line) for line in response.get_data(as_text=True).splitlines()]
        self.assertEqual(streamed[0]["type"], "session_reset")
        self.assertEqual(chat.call_args.args[2], [])
        self.assertEqual(webapp.chat_store.session_count(), 2)
        self.assertEqual(webapp.chat_store.context(), [
            {"role": "user", "content": "新问题"},
            {"role": "assistant", "content": "新回答"},
        ])

        context = self.client.get("/api/chat/context").get_json()
        self.assertEqual(context["context_limit"], 1_000_000)
        self.assertEqual(context["session_count"], 2)

    def test_browser_agent_result_is_added_to_chat_context(self):
        webapp.settings_store.update({
            "api_key": "test-key",
            "chat_model": "deepseek-chat",
            "browser_use_enabled": True,
            "browser_max_steps": 24,
        })
        stream_events = iter([{"type": "answer", "delta": "整理后的网页回答"}])
        with (
            patch.object(webapp, "browser_task_domains", return_value=["example.com"]),
            patch.object(webapp, "run_browser_task", return_value="网页标题与招聘内容") as browser,
            patch.object(webapp, "stream_chat_about_jobs", return_value=stream_events) as chat,
        ):
            response = self.client.post(
                "/api/chat",
                json={"message": "查看 https://example.com/jobs"},
                buffered=True,
            )
        events = [json.loads(line) for line in response.get_data(as_text=True).splitlines()]
        self.assertEqual([event["type"] for event in events[:3]], ["browser_status", "browser_result", "answer"])
        browser.assert_called_once()
        self.assertEqual(browser.call_args.args[3], 24)
        self.assertIn("网页标题与招聘内容", chat.call_args.args[0])
        self.assertEqual(webapp.chat_store.list()[0]["content"], "查看 https://example.com/jobs")

    def test_browser_agent_setting_does_not_affect_chat_without_url(self):
        webapp.job_store.add([{"title": "后端工程师", "source_url": "https://example.com/job"}])
        webapp.settings_store.update({"api_key": "test-key", "browser_use_enabled": True})
        with (
            patch.object(webapp, "run_browser_task") as browser,
            patch.object(
                webapp,
                "stream_chat_about_jobs",
                return_value=iter([{"type": "answer", "delta": "普通岗位回答"}]),
            ),
        ):
            response = self.client.post("/api/chat", json={"message": "比较已保存岗位"}, buffered=True)
        self.assertEqual(response.status_code, 200)
        browser.assert_not_called()

    def test_chat_request_cannot_override_disabled_browser_agent_setting(self):
        webapp.settings_store.update({"api_key": "test-key", "browser_use_enabled": False})
        with patch.object(webapp, "run_browser_task") as browser:
            response = self.client.post(
                "/api/chat",
                json={"message": "查看 https://example.com/jobs", "browser_use": True},
            )
        self.assertEqual(response.status_code, 400)
        browser.assert_not_called()


if __name__ == "__main__":
    unittest.main()
