from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_MESSAGES = 200


class ChatStore:
    def __init__(self, path: str | Path = "chat_history.json") -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"无法读取聊天记录 {self.path}: {exc}") from exc
        messages = data.get("messages", []) if isinstance(data, dict) else data
        if not isinstance(messages, list):
            raise RuntimeError(f"聊天记录 {self.path} 格式无效")
        return [
            message for message in messages
            if isinstance(message, dict)
            and message.get("role") in {"user", "assistant"}
            and isinstance(message.get("content"), str)
        ]

    def _write(self, messages: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"messages": messages[-MAX_MESSAGES:]}, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_name, self.path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._read())

    @staticmethod
    def _session_id(message: dict[str, Any]) -> str:
        return str(message.get("session_id") or "legacy")

    def current_session_id(self) -> str:
        messages = self.list()
        return self._session_id(messages[-1]) if messages else ""

    def session_count(self) -> int:
        session_ids = [self._session_id(message) for message in self.list()]
        return len(list(dict.fromkeys(session_ids)))

    def context(self) -> list[dict[str, str]]:
        messages = self.list()
        if not messages:
            return []
        current_session = self._session_id(messages[-1])
        return [
            {"role": message["role"], "content": str(message.get("content") or "")}
            for message in messages
            if message.get("role") in {"user", "assistant"}
            and self._session_id(message) == current_session
        ]

    def add_exchange(
        self,
        question: str,
        answer: str,
        reasoning: str = "",
        new_session: bool = False,
    ) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            existing = self._read()
            if new_session or not existing:
                session_id = uuid.uuid4().hex
            else:
                session_id = self._session_id(existing[-1])
            additions = [
                {
                    "id": uuid.uuid4().hex,
                    "session_id": session_id,
                    "role": "user",
                    "content": question,
                    "created_at": now,
                },
                {
                    "id": uuid.uuid4().hex,
                    "session_id": session_id,
                    "role": "assistant",
                    "content": answer,
                    "reasoning": reasoning,
                    "created_at": now,
                },
            ]
            messages = (existing + additions)[-MAX_MESSAGES:]
            self._write(messages)
            return deepcopy(messages)

    def clear(self) -> None:
        with self._lock:
            self._write([])
