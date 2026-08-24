#!/usr/bin/env bash
#
# Keep Nera answering on Telegram.
#
#   ./nera.sh              # run in the foreground, Ctrl-C to stop
#   ./nera.sh --daemon     # run in the background, survives closing the shell
#   ./nera.sh --restart    # what a deploy should run: stop, wait, start
#   ./nera.sh --status     # is it running, and what has it done
#   ./nera.sh --stop       # stop it, and wait until it is really stopped
#   ./nera.sh --log        # follow the log
#
# This is the piece whose absence makes a fully-built bot look broken. The code
# to answer a message can be complete and tested, the bot can be configured, and
# a buyer's /start still does nothing — because a poller is a *process*, and
# nothing was running it. `dev.sh` starts the web server only.
#
# The other half of that lesson, learned later and more expensively: a process
# that is running is not the same as a process running the current code. This
# poller does not exit on a network failure — it catches it and retries, which is
# what keeps a phone's flaky uplink from taking the bot down. But the supervisor
# loop below only starts a fresh interpreter when the old one *exits*, so a poller
# that never crashes never reloads. One ran for a day and three quarters serving
# prices that had been deleted from the source two commits earlier. Editing files
# is not deploying. --restart is.
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

# How long to wait for a TERMed poller to finish the batch in hand. It shuts
# down gracefully: the signal sets a flag and the process returns only once the
# current getUpdates has come back, which is up to LONG_POLL_SECONDS plus the
# read timeout. Anything past that is not politeness, it is stuck.
STOP_TIMEOUT=40

running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

poller_pids() {
    # Every poller on the box, whether or not this script's PID file knows about
    # it. That distinction is the whole point: --stop used to delete the PID file
    # before the process had died, so an orphan that outlived it became invisible
    # to --status and unkillable by --stop, while still holding getUpdates.
    pgrep -f 'app\.messaging\.poller' 2>/dev/null | grep -v "^$$\$"
}

wait_for_exit() {
    # Two pollers must never overlap. Telegram hands out updates against one
    # shared offset cursor, so a second consumer does not double the throughput —
    # it steals updates from the first. Whoever acknowledges first wins and the
    # other's batch is gone. That reads to a buyer as Nera answering twice, or
    # not at all, at random. So a restart waits for the old process to be really
    # gone rather than assuming a signal is the same thing as an exit.
    local waited=0

    while [ -n "$(poller_pids)" ]; do
        if [ "$waited" -ge "$STOP_TIMEOUT" ]; then
            return 1
        fi

        sleep 1
        waited=$((waited + 1))
    done

    return 0
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

stop_poller() {
    # Returns only once nothing is polling. The PID file is deleted last and only
    # on success, because a PID file removed while the process lives is how an
    # orphan becomes invisible to every other verb in this script.
    if [ -z "$(poller_pids)" ] && ! running; then
        rm -f "$PID_FILE"
        echo "Not running."
        return 0
    fi

    # Marks the exit as intentional so the supervisor does not restart it.
    touch var/nera-poller.stop

    if [ -f "$PID_FILE" ]; then
        pid="$(cat "$PID_FILE")"
        # The whole process group: the supervisor shell and the poller under it.
        kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
    fi

    # Anything the PID file did not account for. Orphans from a previous crash
    # poll just as effectively as supervised ones, and Telegram cannot tell them
    # apart from the one we mean to keep.
    for stray in $(poller_pids); do
        kill -TERM "$stray" 2>/dev/null
    done

    if wait_for_exit; then
        rm -f "$PID_FILE" var/nera-poller.stop
        echo "Stopped."
        return 0
    fi

    echo "Still polling ${STOP_TIMEOUT}s after SIGTERM; sending SIGKILL."
    for stray in $(poller_pids); do
        kill -KILL "$stray" 2>/dev/null
    done

    if wait_for_exit; then
        rm -f "$PID_FILE" var/nera-poller.stop
        echo "Stopped (had to be killed)."
        return 0
    fi

    # Said out loud rather than swallowed. A --stop that reports success it did
    # not achieve is what lets a redeploy leave the old code answering buyers.
    echo "Could not stop it. Still alive: $(poller_pids | tr '\n' ' ')"
    return 1
}

case "${1:-}" in
    --status)
        if running; then
            echo "Nera is answering on Telegram (pid $(cat "$PID_FILE"))."
            echo

            # What the *running* process fingerprinted when it started, not what
            # the source says now. Those differ precisely when a restart was
            # skipped, which is the failure this line exists to expose.
            echo "$(grep 'Poller starting' "$LOG_FILE" 2>/dev/null | tail -1)"
            echo "on disk now: $("$PYTHON" -c \
                'from app.config import build; print(build.describe())' 2>/dev/null)"
            echo
            grep 'Telegram poll' "$LOG_FILE" 2>/dev/null | tail -5
        else
            echo "Not running. Start it with:  ./nera.sh --daemon"
        fi

        # Reported separately from "running", because it is a different and worse
        # state than either. More than one poller means updates are being split
        # between them at random.
        count="$(poller_pids | grep -c .)"
        if [ "$count" -gt 1 ]; then
            echo
            echo "WARNING: $count poller processes are alive: $(poller_pids | tr '\n' ' ')"
            echo "They are competing for the same updates. Run ./nera.sh --restart"
        fi
        ;;

    --stop)
        stop_poller
        ;;

    --log)
        tail -f "$LOG_FILE"
        ;;

    --restart)
        # The verb a deploy should use. Two separate commands leave a window in
        # which the old process is still finishing its batch and the new one has
        # already started, and this script used to open that window every time:
        # --stop deleted the PID file before the process died, so --daemon looked
        # at the PID file, concluded nothing was running, and started a rival.
        # One verb cannot interleave with itself.
        stop_poller || exit 1
        exec "$0" --daemon
        ;;

    --daemon)
        if running; then
            echo "Already running (pid $(cat "$PID_FILE"))."
            exit 0
        fi

        # An orphan polls just as effectively as a supervised process, and the PID
        # file does not know about it. Starting anyway would put two consumers on
        # one offset cursor, which loses messages rather than sharing them.
        stray="$(poller_pids | tr '\n' ' ')"
        if [ -n "${stray// /}" ]; then
            echo "A poller is already running outside this script: $stray"
            echo "Not starting a second one — they would steal each other's"
            echo "updates. Clear it first:  ./nera.sh --stop"
            exit 1
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
