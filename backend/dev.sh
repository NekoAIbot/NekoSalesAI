#!/usr/bin/env bash
#
# Start the NekoSalesAI development server.
#
#   ./dev.sh              # run in the foreground, Ctrl-C to stop
#   ./dev.sh --daemon     # run in the background, restarting if it dies
#   ./dev.sh --restart    # what a deploy should run
#   ./dev.sh --stop
#   ./dev.sh --status
#
# Applies migrations, seeds demo data, then serves on http://127.0.0.1:8000.
# Safe to run repeatedly — migrations and seeding are both idempotent.
#
# Two things here are not defaults, and both were bought with an outage.
#
# `--loop asyncio`: uvicorn picks up uvloop automatically when it is installed,
# and uvloop dies on this box. PRoot's syscall interception returns errnos libuv
# does not expect, and libuv's response is to abort the process outright —
# `Assertion 'errno == EINTR' failed` — taking the site down mid-request while a
# real visitor was on it. asyncio's own loop is slower and does not do that.
#
# `--daemon` supervises: the crash above left nothing listening and nothing to
# notice. A site that stays down until someone looks at it is indistinguishable,
# to a buyer, from a business that does not exist.

set -uo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
PYTHON=".venv/bin/python"
PID_FILE="var/web.pid"
LOG_FILE="var/web.log"
RESTART_DELAY=3
STOP_TIMEOUT=20

mkdir -p var

if [ ! -x "$PYTHON" ]; then
    echo "No virtualenv found at .venv"
    echo "Create it first:"
    echo "    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

serve() {
    exec "$PYTHON" -m uvicorn app.main:app \
        --host "$HOST" --port "$PORT" --loop asyncio "$@"
}

prepare() {
    echo "==> Applying database migrations"
    .venv/bin/alembic upgrade head

    echo "==> Seeding demo data"
    "$PYTHON" -m app.seed
}

web_pids() {
    pgrep -f "uvicorn app.main:app" 2>/dev/null
}

running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

supervise() {
    while true; do
        "$PYTHON" -m uvicorn app.main:app \
            --host "$HOST" --port "$PORT" --loop asyncio >> "$LOG_FILE" 2>&1
        code=$?

        if [ -f var/web.stop ]; then
            echo "$(date '+%H:%M:%S') web stopped deliberately" >> "$LOG_FILE"
            rm -f var/web.stop
            exit 0
        fi

        echo "$(date '+%H:%M:%S') web exited ($code); restarting in ${RESTART_DELAY}s" \
            >> "$LOG_FILE"
        sleep "$RESTART_DELAY"
    done
}

stop_web() {
    if [ -z "$(web_pids)" ] && ! running; then
        rm -f "$PID_FILE"
        echo "Not running."
        return 0
    fi

    touch var/web.stop

    if [ -f "$PID_FILE" ]; then
        pid="$(cat "$PID_FILE")"
        kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
    fi

    for stray in $(web_pids); do
        kill -TERM "$stray" 2>/dev/null
    done

    waited=0
    while [ -n "$(web_pids)" ]; do
        if [ "$waited" -ge "$STOP_TIMEOUT" ]; then
            for stray in $(web_pids); do
                kill -KILL "$stray" 2>/dev/null
            done
            break
        fi

        sleep 1
        waited=$((waited + 1))
    done

    rm -f "$PID_FILE" var/web.stop
    echo "Stopped."
}

case "${1:-}" in
    --status)
        if running; then
            echo "Serving on http://${HOST}:${PORT} (pid $(cat "$PID_FILE"))."
            grep 'Running code' "$LOG_FILE" 2>/dev/null | tail -1
            echo "on disk now: $("$PYTHON" -c \
                'from app.config import build; print(build.describe())' 2>/dev/null)"
        else
            echo "Not running. Start it with:  ./dev.sh --daemon"
        fi
        ;;

    --stop)
        stop_web
        ;;

    --restart)
        stop_web || exit 1
        exec "$0" --daemon
        ;;

    --daemon)
        if running; then
            echo "Already running (pid $(cat "$PID_FILE"))."
            exit 0
        fi

        stray="$(web_pids | tr '\n' ' ')"
        if [ -n "${stray// /}" ]; then
            echo "Something is already serving on this app: $stray"
            echo "Clear it first:  ./dev.sh --stop"
            exit 1
        fi

        prepare
        rm -f var/web.stop

        setsid "$0" --supervise >> "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"

        # Long enough for migrations, seeding and startup on a phone.
        for _ in $(seq 1 25); do
            if curl -sf -o /dev/null "http://${HOST}:${PORT}/"; then
                break
            fi
            sleep 1
        done

        if running && curl -sf -o /dev/null "http://${HOST}:${PORT}/"; then
            echo "Serving on http://${HOST}:${PORT} (pid $(cat "$PID_FILE"))."
        else
            echo "It did not come up. Last lines of $LOG_FILE:"
            tail -20 "$LOG_FILE"
            exit 1
        fi
        ;;

    --supervise)
        supervise
        ;;

    "")
        prepare
        echo "==> Starting server on http://${HOST}:${PORT}"
        serve --reload
        ;;

    *)
        sed -n '3,12p' "$0" | sed 's/^# \{0,1\}//'
        exit 1
        ;;
esac
