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


STATUSES = ["待投递", "已投递", "未进面", "笔试中", "面试中", "已offer", "已淘汰"]
RECRUIT_TYPES = ["未分类", "校招", "社招"]
TEXT_FIELDS = {"title", "company", "location"}
DETAIL_TEXT_FIELDS = {"salary", "employment_type", "description", "source_url"}
EDITABLE_FIELDS = {"status", "recruit_type", "note", "starred", "requirements", *TEXT_FIELDS, *DETAIL_TEXT_FIELDS}


class JobStore:
    def __init__(self, path: str | Path = "saved_jobs.json") -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"无法读取职位文件 {self.path}: {exc}") from exc
        jobs = data.get("jobs", []) if isinstance(data, dict) else data
        if not isinstance(jobs, list):
            raise RuntimeError(f"职位文件 {self.path} 格式无效")
        return [job for job in jobs if isinstance(job, dict)]

    def _write(self, jobs: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"jobs": jobs}, handle, ensure_ascii=False, indent=2)
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
            jobs = deepcopy(self._read())
        for job in jobs:
            job["status_history"] = self._status_history(job)
        return jobs

    @staticmethod
    def _status_history(job: dict[str, Any]) -> list[dict[str, str]]:
        history: list[dict[str, str]] = []
        raw_history = job.get("status_history")
        if isinstance(raw_history, list):
            for entry in raw_history:
                if not isinstance(entry, dict):
                    continue
                status = entry.get("status")
                changed_at = entry.get("changed_at")
                if isinstance(status, str) and status and isinstance(changed_at, str) and changed_at:
                    history.append({"status": status, "changed_at": changed_at})
        if not history:
            status = str(job.get("status") or "待投递")
            changed_at = str(job.get("updated_at") or job.get("created_at") or "")
            if changed_at:
                history.append({"status": status, "changed_at": changed_at})
        return history

    @staticmethod
    def _identity(job: dict[str, Any]) -> tuple[str, str, str, str]:
        return tuple(
            str(job.get(field) or "").strip().casefold()
            for field in ("source_url", "title", "company", "location")
        )

    def add(self, incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
        added: list[dict[str, Any]] = []
        with self._lock:
            jobs = self._read()
            identities = {self._identity(job) for job in jobs}
            now = datetime.now(timezone.utc).isoformat()
            for raw in incoming:
                if not isinstance(raw, dict) or not str(raw.get("title") or "").strip():
                    continue
                job = deepcopy(raw)
                job["source_url"] = str(job.get("source_url") or job.get("url") or "")
                job["url"] = str(job.get("url") or job["source_url"])
                identity = self._identity(job)
                if identity in identities:
                    continue
                job.update(
                    id=uuid.uuid4().hex,
                    status="待投递",
                    status_history=[{"status": "待投递", "changed_at": now}],
                    note="",
                    starred=False,
                    created_at=now,
                    updated_at=now,
                )
                if job.get("recruit_type") not in RECRUIT_TYPES:
                    job["recruit_type"] = "未分类"
                jobs.append(job)
                added.append(deepcopy(job))
                identities.add(identity)
            if added:
                self._write(jobs)
        return added

    def update(self, job_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        changes = deepcopy(changes)
        unknown = set(changes) - EDITABLE_FIELDS
        if unknown:
            raise ValueError(f"不允许更新字段：{', '.join(sorted(unknown))}")
        if "status" in changes and changes["status"] not in STATUSES:
            raise ValueError("无效的求职进度")
        if "recruit_type" in changes and changes["recruit_type"] not in RECRUIT_TYPES:
            raise ValueError("无效的招聘类型")
        if "note" in changes and not isinstance(changes["note"], str):
            raise ValueError("备注必须是字符串")
        if "starred" in changes and not isinstance(changes["starred"], bool):
            raise ValueError("标星值必须为布尔值")
        for field in TEXT_FIELDS & changes.keys():
            if not isinstance(changes[field], str):
                raise ValueError("职位、公司和地点必须是字符串")
            changes[field] = changes[field].strip()
            if len(changes[field]) > 200:
                raise ValueError("职位、公司和地点不能超过 200 个字符")
        if "title" in changes and not changes["title"]:
            raise ValueError("职位名称不能为空")
        for field in DETAIL_TEXT_FIELDS & changes.keys():
            if not isinstance(changes[field], str):
                raise ValueError("岗位详情字段必须是字符串")
            changes[field] = changes[field].strip()
        if "salary" in changes and len(changes["salary"]) > 200:
            raise ValueError("薪资不能超过 200 个字符")
        if "employment_type" in changes and len(changes["employment_type"]) > 200:
            raise ValueError("工作性质不能超过 200 个字符")
        if "source_url" in changes and len(changes["source_url"]) > 2000:
            raise ValueError("来源链接不能超过 2000 个字符")
        if "description" in changes and len(changes["description"]) > 50_000:
            raise ValueError("职位描述不能超过 50000 个字符")
        if "requirements" in changes:
            requirements = changes["requirements"]
            if not isinstance(requirements, list) or not all(isinstance(item, str) for item in requirements):
                raise ValueError("任职要求必须是字符串数组")
            requirements = [item.strip() for item in requirements if item.strip()]
            if len(requirements) > 100 or any(len(item) > 1000 for item in requirements):
                raise ValueError("任职要求最多 100 条，每条不能超过 1000 个字符")
            changes["requirements"] = requirements

        with self._lock:
            jobs = self._read()
            for job in jobs:
                if job.get("id") == job_id:
                    now = datetime.now(timezone.utc).isoformat()
                    if "status" in changes and changes["status"] != job.get("status"):
                        history = self._status_history(job)
                        history.append({"status": changes["status"], "changed_at": now})
                        job["status_history"] = history
                    job.update(changes)
                    if "source_url" in changes:
                        job["url"] = changes["source_url"]
                    if "description" in changes or "requirements" in changes:
                        job["description_verbatim"] = False
                    job["updated_at"] = now
                    self._write(jobs)
                    return deepcopy(job)
        raise KeyError(job_id)

    def delete(self, job_id: str) -> None:
        with self._lock:
            jobs = self._read()
            remaining = [job for job in jobs if job.get("id") != job_id]
            if len(remaining) == len(jobs):
                raise KeyError(job_id)
            self._write(remaining)
