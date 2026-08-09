#!/usr/bin/env bash
#
# Publish the local dev server on a public HTTPS URL.
#
#   ./share.sh
#
# Opens an SSH reverse tunnel to localhost.run, which needs no account and no
# installed binary — just the ssh client. It prints a https://<random>.lhr.life
# URL that anyone can open. Ctrl-C closes the tunnel and the URL stops working.
#
# Why a tunnel rather than binding a port: this machine sits behind carrier NAT
# on a cellular interface with a /32 address. There is no inbound route to it,
# so no amount of --host 0.0.0.0 would make it reachable. A reverse tunnel
# works because the connection is established outbound, from here.
#
# READ THIS BEFORE RUNNING IT. The URL is public and unlisted, not private.
# Anyone who has it can reach the landing page, talk to the sales agent and
# attempt a login. Two things must be true first, and dev.sh will not enforce
# them for you:
#
#   1. SECRET_KEY is set in .env to something other than the published
#      default. Otherwise anyone reading this repo can forge a valid session
#      token for any account.
#   2. DEMO_USER_PASSWORD is set in .env. The fallback is printed in
#      app/config/settings.py, and the account it opens is an admin on the
#      demo workspace — buyer conversations, contact details, approval queue.
#
# Checkout is unaffected either way: with no Paystack keys configured payments
# are disabled and say so, so there is no path to a real charge.

set -euo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-8000}"

if ! curl -sS -o /dev/null --max-time 5 "http://127.0.0.1:${PORT}/"; then
    echo "Nothing is serving on 127.0.0.1:${PORT}."
    echo "Start it first, in another shell:"
    echo "    ./dev.sh"
    exit 1
fi

# Refuse to publish a server still using either published credential. This is
# the one check worth being strict about: the failure mode is silent, and the
# cost of getting it wrong is an admin login on the open internet.
.venv/bin/python - <<'PY'
import sys

from app.config.settings import Settings, settings

problems = []

for name in ("SECRET_KEY", "DEMO_USER_PASSWORD"):
    if getattr(settings, name) == Settings.model_fields[name].default:
        problems.append(name)

if problems:
    print()
    print("Refusing to publish: still using the published default for:")
    for name in problems:
        print(f"    {name}")
    print()
    print("Set them in backend/.env, then re-run ./dev.sh so they take effect:")
    print("    python3 -c 'import secrets; print(secrets.token_urlsafe(48))'")
    sys.exit(1)
PY

cat <<'EOF'

==> Opening a public tunnel to localhost.run
    The https://....lhr.life URL below is the shareable link.
    Ctrl-C closes it.

    Note: Paystack redirects back to PUBLIC_BASE_URL, which is still
    127.0.0.1. If you want to demo the full checkout return trip, put the
    tunnel URL in .env as PUBLIC_BASE_URL and CORS_ORIGINS, then restart.

EOF

exec ssh \
    -o StrictHostKeyChecking=accept-new \
    -o ServerAliveInterval=30 \
    -o ExitOnForwardFailure=yes \
    -R "80:localhost:${PORT}" \
    nokey@localhost.run
