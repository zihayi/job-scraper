from __future__ import annotations

import re

from bs4 import BeautifulSoup, Comment


MAX_TEXT_CHARS = 40_000
NOISE_TAGS = (
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "template",
    "nav",
    "footer",
    "aside",
)


def clean_html(html: str, max_chars: int = MAX_TEXT_CHARS) -> str:
    """Turn arbitrary page HTML into compact, model-friendly text."""
    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup(NOISE_TAGS):
        node.decompose()
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()

    root = soup.find("main") or soup.find("article") or soup.body or soup
    text = root.get_text("\n", strip=True)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n\n[页面内容过长，已截断]"
    return text
