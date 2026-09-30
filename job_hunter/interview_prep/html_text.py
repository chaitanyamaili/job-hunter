from __future__ import annotations

from bs4 import BeautifulSoup

_STRIP_TAGS = ("script", "style", "nav", "header", "footer")


def extract_visible_text(soup: BeautifulSoup, max_chars: int = 6000) -> str:
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = " ".join(text.split())
    return text[:max_chars]
