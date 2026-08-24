"""Is Telegram reachable, and is the token still good?

Split out from every other diagnostic because a poller that answers nobody has
two very different causes — no network, or a revoked token — and they need
opposite responses. The log cannot tell them apart: a DNS failure and a 401 both
end up as "getUpdates was refused".

    .venv/bin/python scripts/telegram_ping.py

The token is read from the environment and never printed, not even partially. It
is also never passed as an argument: argv is visible to every process on the box
through ``ps``, and shell history keeps it after the terminal is closed.
"""

from __future__ import annotations

import os
import sys

import httpx

API = "https://api.telegram.org"
TIMEOUT = 15.0


def main() -> int:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()

    if not token:
        print("TELEGRAM_BOT_TOKEN is not set — nothing to ping for.")
        return 2

    try:
        response = httpx.get(f"{API}/bot{token}/getMe", timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        # Deliberately not the exception's str() alone: httpx puts the request
        # URL in some of its messages, and that URL contains the token.
        print(f"Could not reach Telegram: {type(exc).__name__}")
        print("Network, not credentials. The poller will recover on its own.")
        return 1

    if response.status_code == 401:
        print("Telegram rejected the token (401). It has been revoked or rotated.")
        print("Reissue it with @BotFather and put the new one in .env.")
        return 1

    if response.status_code != 200:
        print(f"Telegram answered {response.status_code}, which is not a yes.")
        return 1

    payload = response.json()
    bot = payload.get("result", {})

    print(f"Reachable. Bot is @{bot.get('username')} ({bot.get('first_name')}).")

    # A webhook set on this bot means getUpdates returns 409 and the poller
    # cannot start at all — the single most common reason for a silent bot.
    info = httpx.get(f"{API}/bot{token}/getWebhookInfo", timeout=TIMEOUT).json()
    url = (info.get("result") or {}).get("url") or ""

    if url:
        print(f"A webhook is set ({url}). getUpdates will be refused with 409.")
        print("Clear it with: scripts/telegram_setup.py --take-over")
        return 1

    print("No webhook set, so getUpdates is free to use.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
