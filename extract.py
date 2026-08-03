from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

import ssl_support  # noqa: F401 - installs OS certificate support on import


DEFAULT_MODEL = "deepseek-chat"
MODEL_CHOICES = [
    {"id": "deepseek-chat", "label": "DeepSeek Chat（默认）"},
    {"id": "deepseek-reasoner", "label": "DeepSeek Reasoner（深度推理）"},
]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalize_job(raw: Any, source_url: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    title = _text(raw.get("title"))
    if not title:
        return None
    requirements = raw.get("requirements")
    if not isinstance(requirements, list):
        requirements = []
    recruit_type = _text(raw.get("recruit_type"))
    if recruit_type not in {"未分类", "校招", "社招"}:
        recruit_type = "未分类"
    job_url = source_url
    return {
        "title": title,
        "company": _text(raw.get("company")),
        "location": _text(raw.get("location")),
        "salary": _text(raw.get("salary")),
        "employment_type": _text(raw.get("employment_type")),
        "description": _text(raw.get("description")),
        "requirements": [_text(item) for item in requirements if _text(item)],
        "url": job_url,
        "source_url": job_url,
        "recruit_type": recruit_type,
        "description_verbatim": bool(raw.get("description_verbatim")),
    }


def extract_jobs(text: str, source_url: str, api_key: str, model: str = DEFAULT_MODEL) -> list[dict[str, Any]]:
    if not api_key:
        raise ValueError("尚未配置 DeepSeek API Key，请先在设置中填写")
    if not text.strip():
        return []

    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )
    response = client.chat.completions.create(
        model=model,
        max_tokens=8192,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "你是招聘信息抽取器。只根据网页正文抽取，不推测、不补全。"
                    "字段缺失时使用空字符串或空数组。职位描述和任职要求应尽可能逐字照抄，"
                    "不要润色、总结或合并。页面有多个职位时全部返回。只输出合法 JSON。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请按以下固定结构输出："
                    '{"jobs":[{"title":"","company":"","location":"","salary":"",'
                    '"employment_type":"","description":"","requirements":[],"url":"",'
                    '"recruit_type":"未分类","description_verbatim":false}]}。'
                    "recruit_type 只能是未分类、校招、社招；没有职位时 jobs 为空数组。"
                    f"\n\n来源网址：{source_url}\n\n网页正文：\n{text}"
                ),
            }
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("DeepSeek 未返回职位数据")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("DeepSeek 返回了无效的 JSON") from exc
    raw_jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    if not isinstance(raw_jobs, list):
        raise RuntimeError("DeepSeek 返回的 jobs 字段不是数组")
    jobs = (_normalize_job(job, source_url) for job in raw_jobs)
    return [job for job in jobs if job is not None]
