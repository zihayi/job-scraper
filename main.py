from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from clean import clean_html
from extract import DEFAULT_MODEL, extract_jobs
from fetch import fetch_html, validate_url
from fetch_dynamic import fetch_dynamic_html


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="抓取网页并抽取结构化招聘信息")
    parser.add_argument("url", help="招聘网页 URL")
    parser.add_argument("--dynamic", action="store_true", help="使用系统 Edge 渲染动态页面")
    parser.add_argument("-o", "--output", default="result.json", help="JSON 输出路径（默认 result.json）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        url = validate_url(args.url)
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise ValueError("请先设置环境变量 DEEPSEEK_API_KEY")
        html = fetch_dynamic_html(url) if args.dynamic else fetch_html(url)
        text = clean_html(html)
        jobs = extract_jobs(text, url, api_key, os.getenv("JOB_SCRAPER_MODEL", DEFAULT_MODEL))
        result = {"source_url": url, "jobs": jobs}
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(jobs, ensure_ascii=False, indent=2))
        print(f"\n已保存 {len(jobs)} 条职位到 {output}")
        return 0
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
