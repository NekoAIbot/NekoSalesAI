"""Set the WhatsApp business profile: photo, description, the visible details.

    python scripts/whatsapp_setup.py                 # what is set right now
    python scripts/whatsapp_setup.py --brand         # photo, about, description
    python scripts/whatsapp_setup.py --photo         # just the avatar

Reads every credential from the environment, never from an argument — an access
token in ``ps`` or in shell history is a token to reissue.

**Why the photo takes three calls.** Telegram accepts an avatar as a multipart
field on one method. Meta does not: a binary has to be put through the resumable
upload API first, which is attached to the *app* rather than the phone number, and
returns an opaque handle. Only then can the profile be patched, against the phone
number, with the handle standing in for the file. So:

    1. POST /{app_id}/uploads               -> an upload session id
    2. POST /{session}  file_offset: 0      -> an "h:..." file handle
    3. POST /{phone_number_id}/whatsapp_business_profile  with that handle

Step 1 is the reason ``WHATSAPP_APP_ID`` exists in settings; nothing else in the
application needs it.

None of this can run until a number is connected to the Cloud API — there is no
sandbox for a business profile. Run it once that exists; it is idempotent.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any
from urllib import error, request

BASE_URL = os.environ.get(
    "WHATSAPP_BASE_URL", "https://graph.facebook.com/v21.0"
).rstrip("/")

AVATAR = (
    Path(__file__).resolve().parent.parent
    / "app"
    / "web"
    / "static"
    / "brand"
    / "nera-avatar-512.png"
)

# The 139-character line WhatsApp shows under the business name. Same voice as
# the Telegram short description, and the same limit it was written against.
ABOUT = "An AI sales rep. Ask me what it does and what it costs."

DESCRIPTION = (
    "Nera answers questions about what we sell — what it does, what it costs, "
    "whether it fits you — from a published price list, and only from that. "
    "Anything it can't answer goes to a person."
)

# Meta's own vocabulary for a business category.
VERTICAL = "PROF_SERVICES"


def need(name: str) -> str:
    value = os.environ.get(name, "").strip()

    if not value:
        sys.exit(
            f"{name} is not set.\n"
            "Connect a number to the WhatsApp Cloud API first, then put its "
            "credentials in backend/.env and load them:\n"
            "  set -a; . .env; set +a; python scripts/whatsapp_setup.py"
        )

    return value


def call(
    path: str,
    payload: dict | None = None,
    *,
    method: str | None = None,
    headers: dict[str, str] | None = None,
    raw: bytes | None = None,
) -> Any:
    """One Graph API call, retried: this box's uplink drops requests routinely."""
    url = path if path.startswith("http") else f"{BASE_URL}/{path.lstrip('/')}"

    sent = dict(headers or {})
    sent.setdefault("Authorization", f"Bearer {need('WHATSAPP_ACCESS_TOKEN')}")

    if raw is not None:
        data: bytes | None = raw
    elif payload is not None:
        data = json.dumps(payload).encode()
        sent.setdefault("Content-Type", "application/json")
    else:
        data = None

    last = ""

    for _ in range(3):
        try:
            req = request.Request(url, data=data, headers=sent, method=method)
            with request.urlopen(req, timeout=60) as response:
                return json.loads(response.read() or b"{}")
        except error.HTTPError as exc:
            # A 4xx from Graph is a considered answer, and the body is the only
            # thing that says which of a dozen scopes is missing.
            try:
                return json.loads(exc.read())
            except Exception:  # noqa: BLE001
                return {"error": {"message": f"HTTP {exc.code}"}}
        except Exception as exc:  # noqa: BLE001 - timeouts, reset connections
            last = str(exc)

    return {"error": {"message": f"could not reach Graph: {last}"}}


def failed(result: Any) -> str:
    """The error message, or "" when the call succeeded."""
    if isinstance(result, dict) and result.get("error"):
        error_body = result["error"]

        if isinstance(error_body, dict):
            return str(error_body.get("message") or error_body)

        return str(error_body)

    return ""


def report(label: str, result: Any) -> bool:
    problem = failed(result)

    if problem:
        print(f"  !! {label}: {problem}")
        return False

    print(f"  ok {label}")

    return True


def upload_handle(path: Path) -> str | None:
    """Put the file through the resumable upload API and return its handle."""
    if not path.exists():
        print(f"  !! {path} does not exist. Run scripts/render_brand.py.")
        return None

    app_id = need("WHATSAPP_APP_ID")
    blob = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    session = call(
        f"{app_id}/uploads?file_length={len(blob)}&file_type={mime}",
        payload={},
    )

    if not report("create upload session", session):
        return None

    session_id = session.get("id", "")

    if not session_id:
        print("  !! create upload session: no id in the response")
        return None

    # file_offset: 0 — a single-shot upload. Resuming matters for video, not for
    # a four-kilobyte avatar.
    uploaded = call(
        session_id,
        raw=blob,
        headers={"file_offset": "0", "Content-Type": mime},
    )

    if not report("upload the file", uploaded):
        return None

    handle = uploaded.get("h", "")

    if not handle:
        print("  !! upload the file: no handle in the response")
        return None

    return handle


def photo() -> int:
    handle = upload_handle(AVATAR)

    if handle is None:
        return 1

    ok = report(
        "set the profile photo",
        call(
            f"{need('WHATSAPP_PHONE_NUMBER_ID')}/whatsapp_business_profile",
            {"messaging_product": "whatsapp", "profile_picture_handle": handle},
        ),
    )

    if ok:
        print(f"     {AVATAR.name} ({AVATAR.stat().st_size:,} bytes)")

    return 0 if ok else 1


def brand() -> int:
    print("Setting the WhatsApp business profile:")

    ok = all(
        [
            report(
                "set about and description",
                call(
                    f"{need('WHATSAPP_PHONE_NUMBER_ID')}/whatsapp_business_profile",
                    {
                        "messaging_product": "whatsapp",
                        "about": ABOUT,
                        "description": DESCRIPTION,
                        "vertical": VERTICAL,
                    },
                ),
            ),
            photo() == 0,
        ]
    )

    return 0 if ok else 1


def show() -> int:
    fields = "about,description,profile_picture_url,vertical,websites"
    result = call(
        f"{need('WHATSAPP_PHONE_NUMBER_ID')}/whatsapp_business_profile?fields={fields}"
    )

    problem = failed(result)

    if problem:
        print(f"could not read the profile: {problem}")
        return 1

    data = (result.get("data") or [{}])[0]

    print(f"photo       {'set' if data.get('profile_picture_url') else '(none)'}")
    print(f"about       {data.get('about') or '(none)'}")
    print(f"vertical    {data.get('vertical') or '(none)'}")
    print(f"description {data.get('description') or '(none)'}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--brand",
        action="store_true",
        help="Set the photo, the about line and the description.",
    )
    parser.add_argument("--photo", action="store_true", help="Set just the avatar.")
    args = parser.parse_args()

    if args.brand:
        return brand()

    if args.photo:
        return photo()

    return show()


if __name__ == "__main__":
    raise SystemExit(main())
