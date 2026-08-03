from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import app as webapp
from config import SettingsStore
from store import JobStore


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        directory = Path(self.temp_dir.name)
        webapp.app.config.update(TESTING=True)
        webapp.job_store = JobStore(directory / "jobs.json")
        webapp.settings_store = SettingsStore(directory / "settings.json")
        self.client = webapp.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_index_and_public_settings(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Job Scraper", response.get_data(as_text=True))

        settings = self.client.get("/api/settings").get_json()
        self.assertFalse(settings["has_api_key"])
        self.assertEqual(settings["model"], "deepseek-chat")

    def test_settings_never_returns_plain_api_key(self):
        response = self.client.post(
            "/api/settings",
            json={"api_key": "test-key", "model": "deepseek-chat", "port": 5001},
        )
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertNotIn("test-secret", text)
        self.assertTrue(response.get_json()["has_api_key"])

    def test_job_lifecycle_and_excel_export(self):
        job = webapp.job_store.add(
            [{"title": "Python 工程师", "company": "示例公司", "source_url": "https://example.com/job"}]
        )[0]
        listed = self.client.get("/api/jobs").get_json()["jobs"]
        self.assertEqual(len(listed), 1)

        response = self.client.patch(f"/api/jobs/{job['id']}", json={"status": "面试中"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["job"]["status"], "面试中")

        export = self.client.get("/api/export")
        self.assertEqual(export.status_code, 200)
        self.assertTrue(export.data.startswith(b"PK"))

        response = self.client.delete(f"/api/jobs/{job['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/jobs").get_json()["jobs"], [])

    def test_scrape_requires_api_key(self):
        response = self.client.post("/api/scrape", json={"url": "https://example.com", "dynamic": False})
        self.assertEqual(response.status_code, 400)
        self.assertIn("DeepSeek API Key", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
