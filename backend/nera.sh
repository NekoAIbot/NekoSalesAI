#!/usr/bin/env bash
#
# Keep Nera answering on Telegram.
#
#   ./nera.sh              # run in the foreground, Ctrl-C to stop
#   ./nera.sh --daemon     # run in the background, survives closing the shell
#   ./nera.sh --status     # is it running, and what has it done
#   ./nera.sh --stop       # stop it
#   ./nera.sh --log        # follow the log
#
# This is the piece whose absence makes a fully-built bot look broken. The code
# to answer a message can be complete and tested, the bot can be configured, and
# a buyer's /start still does nothing — because a poller is a *process*, and
# nothing was running it. `dev.sh` starts the web server only.
#
# Why a restart loop rather than plain `python -m app.messaging.poller`: this box
# is a phone. The uplink drops, the process gets killed when memory is tight, and
# a poller that exits on the first dropped connection is a bot that stops
# answering at an hour nobody chose. The loop makes stopping deliberate — through
# --stop — and everything else recoverable.
#
# No systemd here, so this is deliberately just a PID file and a loop. On a real
# server, run `python -m app.messaging.poller` under systemd or a container
# restart policy and delete this file.

set -uo pipefail

cd "$(dirname "$0")"

PYTHON=".venv/bin/python"
PID_FILE="var/nera-poller.pid"
LOG_FILE="var/nera-poller.log"

# Long enough not to hammer Telegram after a persistent failure, short enough
# that a passing network blip costs one missed message, not a lunch break.
RESTART_DELAY=5

mkdir -p var

running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

load_env() {
    if [ -f .env ]; then
        set -a
        # shellcheck disable=SC1091
        . ./.env
        set +a
    fi

    if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
        echo "TELEGRAM_BOT_TOKEN is not set in .env — there is no bot to poll for."
        exit 1
    fi
}

supervise() {
    # The loop the poller runs inside. Every restart is logged: a log that goes
    # quiet is then unambiguous — it means stopped, not crash-looping silently.
    while true; do
        "$PYTHON" -m app.messaging.poller >> "$LOG_FILE" 2>&1
        code=$?

        if [ -f var/nera-poller.stop ]; then
            echo "$(date '+%H:%M:%S') stopped deliberately" >> "$LOG_FILE"
            rm -f var/nera-poller.stop
            exit 0
        fi

        echo "$(date '+%H:%M:%S') poller exited ($code); restarting in ${RESTART_DELAY}s" \
            >> "$LOG_FILE"
        sleep "$RESTART_DELAY"
    done
}

case "${1:-}" in
    --status)
        if running; then
            echo "Nera is answering on Telegram (pid $(cat "$PID_FILE"))."
            echo
            grep 'Telegram poll' "$LOG_FILE" 2>/dev/null | tail -5
        else
            echo "Not running. Start it with:  ./nera.sh --daemon"
        fi
        ;;

    --stop)
        if ! running; then
            echo "Not running."
            exit 0
        fi

        pid="$(cat "$PID_FILE")"
        # Marks the exit as intentional so the supervisor does not restart it.
        touch var/nera-poller.stop
        # The whole process group: the supervisor shell and the poller under it.
        kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
        rm -f "$PID_FILE"
        echo "Stopped."
        ;;

    --log)
        tail -f "$LOG_FILE"
        ;;

    --daemon)
        if running; then
            echo "Already running (pid $(cat "$PID_FILE"))."
            exit 0
        fi

        load_env
        rm -f var/nera-poller.stop

        # setsid so it survives the terminal closing — on a phone the shell goes
        # away whenever the app does.
        setsid "$0" --supervise >> "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"

        sleep 2

        if running; then
            echo "Nera is answering on Telegram (pid $(cat "$PID_FILE"))."
            echo "  log:     ./nera.sh --log"
            echo "  stop:    ./nera.sh --stop"
        else
            echo "It did not stay up. Last lines of $LOG_FILE:"
            tail -20 "$LOG_FILE"
            exit 1
        fi
        ;;

    --supervise)
        # Internal: the daemon re-invokes itself here, already detached.
        load_env
        supervise
        ;;

    "")
        load_env
        echo "==> Nera is answering on Telegram. Ctrl-C to stop."
        exec "$PYTHON" -m app.messaging.poller
        ;;

    *)
        sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'
        exit 1
        ;;
esac
