from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

import requests
from bs4 import BeautifulSoup


@dataclass
class LearnedPage:
    url: str
    title: str
    summary: str
    highlights: list[str]


class KnowledgeManager:
    def learn_from_url(self, url: str) -> LearnedPage:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.title.get_text(strip=True) if soup.title else url
        text_blocks: list[str] = []
        for tag_name in ("h1", "h2", "h3", "p", "li"):
            for tag in soup.find_all(tag_name):
                text = " ".join(tag.get_text(" ", strip=True).split())
                if text and len(text) > 20:
                    text_blocks.append(text)

        cleaned = self._deduplicate(text_blocks)
        summary = " ".join(cleaned[:4])[:1200]
        highlights = cleaned[:8]
        return LearnedPage(url=url, title=title, summary=summary, highlights=highlights)

    @staticmethod
    def make_memory_entry(page: LearnedPage, topic: str = "") -> dict[str, Any]:
        return {
            "timestamp": time.time(),
            "topic": topic,
            "url": page.url,
            "title": page.title,
            "summary": page.summary,
            "highlights": page.highlights,
        }

    @staticmethod
    def _deduplicate(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            normalized = re.sub(r"\s+", " ", item.strip().lower())
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(item)
        return result
