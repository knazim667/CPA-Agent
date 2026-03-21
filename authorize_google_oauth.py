from __future__ import annotations

from core.google_auth import GoogleWorkspaceAuth


def main() -> int:
    auth = GoogleWorkspaceAuth()
    token_path = auth.authorize_oauth()
    print(f"OAuth authorization complete. Token saved to {token_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
