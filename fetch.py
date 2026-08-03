from __future__ import annotations

from urllib.parse import urlparse

import requests

import ssl_support  # noqa: F401 - installs OS certificate support on import


DEFAULT_TIMEOUT = 30
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36 "
    "JobScraper/1.0"
)


def validate_url(url: str) -> str:
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("请输入有效的 http:// 或 https:// 网址")
    if parsed.username or parsed.password:
        raise ValueError("网址不能包含用户名或密码")
    return url


def fetch_html(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Fetch a static page and return decoded HTML."""
    url = validate_url(url)
    with requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=timeout,
        allow_redirects=True,
        stream=True,
    ) as response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if content_type and not any(kind in content_type for kind in ("html", "text/plain", "xml")):
            raise ValueError(f"网址返回的不是网页内容：{content_type.split(';', 1)[0]}")

        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise ValueError("网页内容超过 10 MB，已停止抓取")
            chunks.append(chunk)

        raw = b"".join(chunks)
        encoding = response.encoding or response.apparent_encoding or "utf-8"
        return raw.decode(encoding, errors="replace")
