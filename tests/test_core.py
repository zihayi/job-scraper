from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clean import clean_html
from config import SettingsStore
from store import JobStore


class CleanHtmlTests(unittest.TestCase):
    def test_removes_noise_and_keeps_job_text(self):
        html = "<nav>菜单</nav><main><h1>后端工程师</h1><script>bad()</script><p>负责 API</p></main>"
        self.assertEqual(clean_html(html), "后端工程师\n负责 API")


class JobStoreTests(unittest.TestCase):
    def test_add_deduplicate_update_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory) / "jobs.json")
            source = {"title": "工程师", "location": "深圳", "source_url": "https://example.com/job"}
            added = store.add([source, source])
            self.assertEqual(len(added), 1)
            job_id = added[0]["id"]
            updated = store.update(job_id, {"status": "已投递", "starred": True})
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


class SettingsStoreTests(unittest.TestCase):
    def test_saves_model_port_and_masks_key(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            public = store.update(
                {"api_key": "test-key", "model": "deepseek-chat", "port": 8001}
            )
            self.assertTrue(public["has_api_key"])
            self.assertNotIn("example-secret", public["api_key_masked"])
            self.assertEqual(public["port"], 8001)


if __name__ == "__main__":
    unittest.main()
