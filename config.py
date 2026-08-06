from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from extract import CHAT_MODEL, DEFAULT_MODEL, MODEL_CHOICES


DEFAULT_PORT = 5000
DEFAULT_BROWSER_MAX_STEPS = 20


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
        allowed_models = {choice["id"] for choice in MODEL_CHOICES}
        extraction_model = str(
            saved.get("extraction_model")
            or saved.get("model")
            or os.getenv("JOB_SCRAPER_MODEL")
            or DEFAULT_MODEL
        )
        chat_model = str(saved.get("chat_model") or os.getenv("JOB_CHAT_MODEL") or CHAT_MODEL)
        if extraction_model not in allowed_models:
            extraction_model = DEFAULT_MODEL
        if chat_model not in allowed_models:
            chat_model = CHAT_MODEL
        try:
            port = int(saved.get("port") or os.getenv("JOB_SCRAPER_PORT") or DEFAULT_PORT)
        except (TypeError, ValueError):
            port = DEFAULT_PORT
        if not 1 <= port <= 65535:
            port = DEFAULT_PORT
        browser_use_enabled = saved.get("browser_use_enabled", False)
        if not isinstance(browser_use_enabled, bool):
            browser_use_enabled = False
        browser_max_steps = saved.get("browser_max_steps", DEFAULT_BROWSER_MAX_STEPS)
        if (
            isinstance(browser_max_steps, bool)
            or not isinstance(browser_max_steps, int)
            or not 1 <= browser_max_steps <= 50
        ):
            browser_max_steps = DEFAULT_BROWSER_MAX_STEPS
        return {
            "api_key": api_key,
            "extraction_model": extraction_model,
            "chat_model": chat_model,
            "port": port,
            "browser_use_enabled": browser_use_enabled,
            "browser_max_steps": browser_max_steps,
        }

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
            "extraction_model": values["extraction_model"],
            "chat_model": values["chat_model"],
            "model_choices": MODEL_CHOICES,
            "port": values["port"],
            "browser_use_enabled": values["browser_use_enabled"],
            "browser_max_steps": values["browser_max_steps"],
        }

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        allowed_models = {choice["id"] for choice in MODEL_CHOICES}
        changes = dict(changes)
        if "model" in changes and "extraction_model" not in changes:
            changes["extraction_model"] = changes["model"]
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
            for field, label in (
                ("extraction_model", "抽取模型"),
                ("chat_model", "聊天模型"),
            ):
                if field not in changes:
                    continue
                model = changes[field]
                if model not in allowed_models:
                    raise ValueError(f"不支持的{label}")
                saved[field] = model
            if "extraction_model" in changes:
                saved.pop("model", None)
            if "port" in changes:
                port = changes["port"]
                if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
                    raise ValueError("端口需为 1–65535 的整数")
                saved["port"] = port
            if "browser_use_enabled" in changes:
                enabled = changes["browser_use_enabled"]
                if not isinstance(enabled, bool):
                    raise ValueError("网页代理开关必须为布尔值")
                saved["browser_use_enabled"] = enabled
            if "browser_max_steps" in changes:
                max_steps = changes["browser_max_steps"]
                if isinstance(max_steps, bool) or not isinstance(max_steps, int) or not 1 <= max_steps <= 50:
                    raise ValueError("网页代理最大步数需为 1–50 的整数")
                saved["browser_max_steps"] = max_steps
            self._write(saved)
        return self.public()
