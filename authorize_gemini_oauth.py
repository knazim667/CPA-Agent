from __future__ import annotations

from core.gemini_client import GeminiClient


def main() -> int:
    client = GeminiClient()
    token_path = client.authorize_oauth()
    print(f"Gemini OAuth authorization complete. Token saved to {token_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
