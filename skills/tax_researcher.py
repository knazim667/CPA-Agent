from __future__ import annotations

from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup


@dataclass
class TaxResearchResult:
    url: str
    title: str
    summary: str


def fetch_tax_update(url: str) -> TaxResearchResult:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.text.strip() if soup.title else url
    paragraph = soup.find("p")
    summary = paragraph.get_text(strip=True) if paragraph else "No summary available."
    return TaxResearchResult(url=url, title=title, summary=summary)
