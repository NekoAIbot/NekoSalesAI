"""Inspect and configure the Telegram bot Nera answers on.

    python scripts/telegram_setup.py                 # what is set right now
    python scripts/telegram_setup.py --brand         # name, bio, description, commands, photo
    python scripts/telegram_setup.py --photo         # just the avatar
    python scripts/telegram_setup.py --take-over     # remove a webhook so polling can run
    python scripts/telegram_setup.py --set-webhook https://…/api/v1/messaging/telegram/webhook

Reads ``TELEGRAM_BOT_TOKEN`` from the environment. The token is a bearer
credential for a Telegram account — anyone holding it can read every message sent
to the bot and post as it — so it is never passed as an argument, where it would
land in shell history and in ``ps``.

**On --take-over.** A bot may have a webhook or be polled, never both, so
starting the poller means removing whatever webhook is set. That is a decision
about the *other* software using this bot, not a detail of ours: it stops
receiving, immediately and silently, and the URL is not recoverable from
Telegram afterwards. So this prints the URL first and requires confirmation,
which is the difference between a decision and an accident.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib import error, request

BASE_URL = os.environ.get("TELEGRAM_BASE_URL", "https://api.telegram.org").rstrip("/")

# The avatar, rendered by scripts/render_brand.py. 512 because Telegram derives
# its own 160/320/640 crops from whatever it is given and upscaling shows.
AVATAR = (
    Path(__file__).resolve().parent.parent
    / "app"
    / "web"
    / "static"
    / "brand"
    / "nera-avatar-512.png"
)

# Nera's own words about itself.
#
# Written for a *prospect*, which is who opens this bot — not for a customer who
# has already bought. An earlier draft said "your buyers, your price list" and
# was addressed to the wrong person entirely.
#
# Plain and understated on purpose. The claim underneath it is unusual enough
# that overselling it would be the first thing to distrust, and every line here
# is one app.sales.agent structurally enforces: a bio promising something the
# rule engine will not do would be the first lie in the funnel.
NAME = "Nera"

# The one line shown under the bot's name before anyone messages it.
SHORT_DESCRIPTION = (
    "An AI sales rep for your business. Ask me what it does and what it costs."
)

DESCRIPTION = (
    "I'm Nera, an AI sales rep.\n\n"
    "I can be put on your website, Telegram or WhatsApp to answer your buyers — "
    "what you sell, what it costs, whether it fits them — at any hour.\n\n"
    "I work from a price list you publish, and only from that. I can't invent a "
    "price, approve a discount, or promise a feature that doesn't exist. Ask me "
    "for one and I'll tell you I need a human, then go and get one.\n\n"
    "Send me a message to see how I answer."
)

COMMANDS = [
    {"command": "start", "description": "Talk to Nera"},
    {"command": "reset", "description": "Start over with a fresh conversation"},
    {"command": "help", "description": "What Nera can and cannot do"},
]


def token() -> str:
    value = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

    if not value:
        sys.exit(
            "TELEGRAM_BOT_TOKEN is not set.\n"
            "It is in backend/.env — load it first:\n"
            "  set -a; . .env; set +a; python scripts/telegram_setup.py"
        )

    return value


def call(method: str, payload: dict | None = None) -> Any:
    """One Bot API call, retried: this box's uplink drops requests routinely."""
    url = f"{BASE_URL}/bot{token()}/{method}"
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}

    last = ""

    for _ in range(3):
        try:
            with request.urlopen(
                request.Request(url, data=data, headers=headers), timeout=40
            ) as response:
                return json.loads(response.read())
        except error.HTTPError as exc:
            # A 4xx is Telegram's considered answer, not a blip. Read the body:
            # the description is the only thing that says *why*.
            try:
                return json.loads(exc.read())
            except Exception:  # noqa: BLE001
                return {"ok": False, "description": f"HTTP {exc.code}"}
        except Exception as exc:  # noqa: BLE001 - timeouts and reset connections
            last = str(exc)

    return {"ok": False, "description": f"could not reach Telegram: {last}"}


def report(method: str, result: Any) -> bool:
    ok = isinstance(result, dict) and result.get("ok")
    mark = "ok " if ok else "!! "

    if ok:
        print(f"  {mark}{method}")
    else:
        detail = result.get("description") if isinstance(result, dict) else result
        print(f"  {mark}{method}: {detail}")

    return bool(ok)


def upload(method: str, fields: dict[str, str], file_field: str, path: Path) -> Any:
    """One Bot API call carrying a file, as multipart/form-data.

    Hand-encoded because ``urllib`` has no multipart writer and this script has
    no dependencies on purpose — it has to run before, and independently of, the
    application's virtualenv.
    """
    if not path.exists():
        return {"ok": False, "description": f"{path} does not exist. Run scripts/render_brand.py."}

    boundary = f"----------{uuid.uuid4().hex}"
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = bytearray()

    for name, value in fields.items():
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()

    body += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{file_field}"; filename="{path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode()
    body += path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()

    url = f"{BASE_URL}/bot{token()}/{method}"
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    last = ""

    for _ in range(3):
        try:
            with request.urlopen(
                request.Request(url, data=bytes(body), headers=headers), timeout=60
            ) as response:
                return json.loads(response.read())
        except error.HTTPError as exc:
            try:
                return json.loads(exc.read())
            except Exception:  # noqa: BLE001
                return {"ok": False, "description": f"HTTP {exc.code}"}
        except Exception as exc:  # noqa: BLE001
            last = str(exc)

    return {"ok": False, "description": f"could not reach Telegram: {last}"}


def photo() -> int:
    """Set the bot's avatar.

    ``setMyProfilePhoto`` is recent — for years the profile photo could only be
    set by hand through @BotFather, and much of what is written about the Bot API
    still says so. It takes an ``InputProfilePhoto``, which references the
    attached file rather than containing it.

    Telegram derives its own 160/320/640 square crops from what is uploaded, and
    clients display them in a circle. The mark's geometry stays inside ~165 units
    of centre for that reason: nothing to lose at the corners.
    """
    result = upload(
        "setMyProfilePhoto",
        {"photo": json.dumps({"type": "static", "photo": "attach://pic"})},
        "pic",
        AVATAR,
    )

    if not report("setMyProfilePhoto", result):
        return 1

    print(f"     {AVATAR.name} ({AVATAR.stat().st_size:,} bytes)")

    return 0


def show() -> int:
    me = call("getMe")

    if not isinstance(me, dict) or not me.get("ok"):
        print(f"getMe failed: {me}")
        return 1

    bot = me["result"]
    print(f"bot        @{bot.get('username')}  ({bot.get('first_name')})")
    print(f"id         {bot.get('id')}")

    # Read back rather than assumed. An avatar that silently failed to upload
    # looks identical to one that worked until someone opens the chat.
    photos = call("getUserProfilePhotos", {"user_id": bot.get("id"), "limit": 1})
    total = 0

    if isinstance(photos, dict) and photos.get("ok"):
        total = photos["result"].get("total_count", 0)

    print(f"photo      {'set' if total else '(none)'}")

    hook = call("getWebhookInfo")
    info = hook.get("result", {}) if isinstance(hook, dict) else {}
    url = info.get("url") or ""

    if url:
        print(f"webhook    {url}")
        print(f"pending    {info.get('pending_update_count', 0)}")

        if info.get("last_error_message"):
            print(f"last error {info['last_error_message']}")

        print()
        print("A webhook is set, so getUpdates polling is refused (409).")
        print("Run --take-over to remove it and let the poller run.")
    else:
        print("webhook    (none) — getUpdates polling can run")

    commands = call("getMyCommands")

    if isinstance(commands, dict) and commands.get("ok"):
        listed = commands["result"]
        print(f"commands   {', '.join('/' + c['command'] for c in listed) or '(none)'}")

    return 0


def brand() -> int:
    print("Setting how the bot presents itself:")

    ok = all(
        [
            report("setMyName", call("setMyName", {"name": NAME})),
            report(
                "setMyShortDescription",
                call("setMyShortDescription", {"short_description": SHORT_DESCRIPTION}),
            ),
            report(
                "setMyDescription",
                call("setMyDescription", {"description": DESCRIPTION}),
            ),
            report("setMyCommands", call("setMyCommands", {"commands": COMMANDS})),
            photo() == 0,
        ]
    )

    return 0 if ok else 1


def take_over(assume_yes: bool) -> int:
    hook = call("getWebhookInfo")
    info = hook.get("result", {}) if isinstance(hook, dict) else {}
    url = info.get("url") or ""

    if not url:
        print("No webhook is set. Polling can already run.")
        return 0

    print("This bot currently delivers to:")
    print(f"  {url}")
    print()
    print("Removing it stops that endpoint receiving messages, immediately.")
    print("Telegram does not keep the URL, so save the line above if you might")
    print("want it back.")
    print()

    if not assume_yes:
        if input("Remove it? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Left alone.")
            return 1

    # Pending updates are kept: they are real buyer messages that arrived while
    # the old endpoint was failing, and Nera can still answer them.
    if not report("deleteWebhook", call("deleteWebhook", {"drop_pending_updates": False})):
        return 1

    print()
    print("Polling can now run:  python -m app.messaging.poller")

    return 0


def set_webhook(url: str) -> int:
    if not url.startswith("https://"):
        sys.exit("Telegram requires https for a webhook URL.")

    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()

    if not secret:
        sys.exit(
            "TELEGRAM_WEBHOOK_SECRET is not set, and the webhook route rejects "
            "every delivery without it — a public endpoint that trusts anything "
            "posted to it would let a stranger put words in a buyer's mouth.\n"
            "Generate one:  python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )

    ok = report(
        "setWebhook",
        call(
            "setWebhook",
            {
                "url": url,
                "secret_token": secret,
                "allowed_updates": ["message"],
                # Anything queued was addressed to whatever was there before.
                "drop_pending_updates": True,
            },
        ),
    )

    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--brand", action="store_true", help="Set name, bio, commands and photo.")
    parser.add_argument(
        "--photo",
        action="store_true",
        help="Set just the avatar from the rendered brand asset.",
    )
    parser.add_argument(
        "--take-over",
        action="store_true",
        help="Remove the current webhook so the poller can run.",
    )
    parser.add_argument(
        "--set-webhook",
        metavar="URL",
        help="Deliver to an https URL instead of polling.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation on --take-over.",
    )
    args = parser.parse_args()

    if args.set_webhook:
        return set_webhook(args.set_webhook)

    if args.take_over:
        return take_over(args.yes)

    if args.brand:
        return brand()

    if args.photo:
        return photo()

    return show()


if __name__ == "__main__":
    raise SystemExit(main())
