from __future__ import annotations

import json
import os
from io import BytesIO

from flask import Flask, Response, jsonify, render_template, request, send_file, stream_with_context
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from chat_markdown import render_chat_messages
from chat_store import ChatStore
from clean import clean_html
from config import SettingsStore
from extract import extract_jobs, stream_chat_about_jobs
from fetch import fetch_html, validate_url
from fetch_dynamic import fetch_dynamic_html
from store import JobStore, RECRUIT_TYPES, STATUSES


app = Flask(__name__, template_folder=".")
app.json.ensure_ascii = False
job_store = JobStore(os.getenv("JOB_STORE_PATH", "saved_jobs.json"))
settings_store = SettingsStore(os.getenv("JOB_SETTINGS_PATH", "settings.json"))
chat_store = ChatStore(os.getenv("CHAT_STORE_PATH", "chat_history.json"))


@app.get("/")
def index():
    return render_template("index.html", statuses=STATUSES, recruit_types=RECRUIT_TYPES)


@app.get("/api/jobs")
def list_jobs():
    return jsonify(jobs=job_store.list())


@app.patch("/api/jobs/<job_id>")
def update_job(job_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload:
        return jsonify(error="请求内容不能为空"), 400
    try:
        return jsonify(job=job_store.update(job_id, payload))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except KeyError:
        return jsonify(error="职位不存在"), 404


@app.delete("/api/jobs/<job_id>")
def delete_job(job_id: str):
    try:
        job_store.delete(job_id)
    except KeyError:
        return jsonify(error="职位不存在"), 404
    return jsonify(ok=True)


@app.post("/api/scrape")
def scrape():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="请求格式无效"), 400
    try:
        url = validate_url(str(payload.get("url") or ""))
        dynamic = payload.get("dynamic", False)
        if not isinstance(dynamic, bool):
            raise ValueError("dynamic 必须为布尔值")
        settings = settings_store.effective()
        if not settings["api_key"]:
            raise ValueError("尚未配置 DeepSeek API Key，请先打开右上角设置")
        html = fetch_dynamic_html(url) if dynamic else fetch_html(url)
        source_text = clean_html(html)
        jobs = extract_jobs(source_text, url, settings["api_key"], settings["extraction_model"])
        added = job_store.add(jobs)
        return jsonify(jobs=added, extracted_count=len(jobs), source_text=source_text)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        app.logger.exception("Scrape failed")
        return jsonify(error=f"抓取失败：{exc}"), 502


@app.get("/api/settings")
def get_settings():
    return jsonify(settings_store.public())


@app.post("/api/settings")
def save_settings():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="请求格式无效"), 400
    try:
        return jsonify(settings_store.update(payload))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@app.get("/api/chat")
def get_chat_history():
    return jsonify(messages=render_chat_messages(chat_store.list()))


@app.post("/api/chat")
def send_chat_message():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="请求格式无效"), 400
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify(error="请输入问题"), 400
    message = message.strip()
    if len(message) > 4000:
        return jsonify(error="问题不能超过 4000 个字符"), 400
    try:
        jobs = job_store.list()
        if not jobs:
            raise ValueError("暂无已保存岗位，请先抓取并保存岗位")
        settings = settings_store.effective()
        if not settings["api_key"]:
            raise ValueError("尚未配置 DeepSeek API Key，请先打开右上角设置")
        history = chat_store.context()
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        app.logger.exception("Job chat failed")
        return jsonify(error=f"问答失败：{exc}"), 502

    @stream_with_context
    def generate():
        answer_parts: list[str] = []
        reasoning_parts: list[str] = []
        try:
            for event in stream_chat_about_jobs(
                message, jobs, history, settings["api_key"], settings["chat_model"]
            ):
                if event["type"] == "reset":
                    answer_parts.clear()
                    reasoning_parts.clear()
                elif event["type"] == "answer":
                    answer_parts.append(event["delta"])
                elif event["type"] == "reasoning":
                    reasoning_parts.append(event["delta"])
                yield json.dumps(event, ensure_ascii=False) + "\n"

            answer = "".join(answer_parts).strip()
            reasoning = "".join(reasoning_parts).strip()
            messages = chat_store.add_exchange(message, answer, reasoning)
            done = {"type": "done", "messages": render_chat_messages(messages)}
            yield json.dumps(done, ensure_ascii=False) + "\n"
        except Exception as exc:
            app.logger.warning("Job chat stream failed: %s", exc)
            error = {"type": "error", "error": str(exc)}
            yield json.dumps(error, ensure_ascii=False) + "\n"

    return Response(
        generate(),
        mimetype="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/api/chat")
def clear_chat_history():
    chat_store.clear()
    return jsonify(ok=True)


@app.get("/api/export")
def export_jobs():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "职位名单"
    columns = [
        ("职位", "title"),
        ("公司", "company"),
        ("地点", "location"),
        ("薪资", "salary"),
        ("工作性质", "employment_type"),
        ("校招/社招", "recruit_type"),
        ("进度", "status"),
        ("备注", "note"),
        ("职位描述", "description"),
        ("任职要求", "requirements"),
        ("来源链接", "source_url"),
    ]
    sheet.append([title for title, _ in columns])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="0F766E")
    for job in job_store.list():
        values = []
        for _, field in columns:
            value = job.get(field, "")
            if isinstance(value, list):
                value = "\n".join(str(item) for item in value)
            values.append(value)
        sheet.append(values)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    widths = [24, 20, 18, 15, 14, 14, 12, 24, 50, 50, 40]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="job-scraper.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def main() -> None:
    settings = settings_store.effective()
    app.run(host="127.0.0.1", port=settings["port"], debug=False)


if __name__ == "__main__":
    main()
