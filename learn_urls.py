from __future__ import annotations

import sys
from pathlib import Path

from main import CPAAgent


def main(argv: list[str]) -> int:
    urls = [arg for arg in argv[1:] if arg.startswith("http://") or arg.startswith("https://")]
    if not urls:
        print("Usage: python learn_urls.py <url1> <url2> ...")
        return 1

    agent = CPAAgent()
    result = agent.learn_from_urls(urls, topic="manual_learning")
    for entry in result["entries"]:
        print(f"Learned: {entry['title']} -> {entry['url']}")
    print(f"Stored {result['count']} source(s) in memory/knowledge/learned_sources.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
