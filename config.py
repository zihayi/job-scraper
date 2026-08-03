from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from extract import DEFAULT_MODEL, MODEL_CHOICES


DEFAULT_PORT = 5000


class SettingsStore:
    def __init__(self, path: str | Path = "settings.json") -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"无法读取设置文件 {self.path}: {exc}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"设置文件 {self.path} 格式无效")
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_name, self.path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    def effective(self) -> dict[str, Any]:
        with self._lock:
            saved = self._read()
        api_key = str(saved.get("api_key") or os.getenv("DEEPSEEK_API_KEY") or "")
        model = str(saved.get("model") or os.getenv("JOB_SCRAPER_MODEL") or DEFAULT_MODEL)
        if model not in {choice["id"] for choice in MODEL_CHOICES}:
            model = DEFAULT_MODEL
        try:
            port = int(saved.get("port") or os.getenv("JOB_SCRAPER_PORT") or DEFAULT_PORT)
        except (TypeError, ValueError):
            port = DEFAULT_PORT
        if not 1 <= port <= 65535:
            port = DEFAULT_PORT
        return {"api_key": api_key, "model": model, "port": port}

    def public(self) -> dict[str, Any]:
        values = self.effective()
        key = values["api_key"]
        if len(key) > 10:
            masked = f"{key[:7]}…{key[-4:]}"
        elif key:
            masked = "••••••••"
        else:
            masked = ""
        return {
            "has_api_key": bool(key),
            "api_key_masked": masked,
            "model": values["model"],
            "model_choices": MODEL_CHOICES,
            "port": values["port"],
        }

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        allowed_models = {choice["id"] for choice in MODEL_CHOICES}
        with self._lock:
            saved = self._read()
            if "api_key" in changes:
                api_key = changes["api_key"]
                if not isinstance(api_key, str):
                    raise ValueError("API Key 必须是字符串")
                if api_key.strip():
                    saved["api_key"] = api_key.strip()
                else:
                    saved.pop("api_key", None)
            if "model" in changes:
                model = changes["model"]
                if model not in allowed_models:
                    raise ValueError("不支持的抽取模型")
                saved["model"] = model
            if "port" in changes:
                port = changes["port"]
                if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
                    raise ValueError("端口需为 1–65535 的整数")
                saved["port"] = port
            self._write(saved)
        return self.public()
