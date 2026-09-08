#!/usr/bin/env bash
#
# Keep Nera up when the thing that keeps Nera up is itself killed.
#
#   ./guardian.sh --daemon    # watch both services, restart whatever is down
#   ./guardian.sh --once      # check once and exit — this is the cron/boot verb
#   ./guardian.sh --status    # what the guardian sees right now
#   ./guardian.sh --stop      # stop watching (does not stop Nera)
#   ./guardian.sh --log       # follow the guardian log
#
# Why this exists, and why it is a third script rather than a flag on the other
# two. Both nera.sh and dev.sh already restart their own process when it exits —
# that layer works and is not what failed. What failed is one layer up: the
# supervising *shell* was killed, so there was nothing left to notice the exit.
#
# On this box that is not hypothetical and not rare. It is a phone under PRoot
# with no systemd, and at the time of writing it had 131 MB of 5.7 GB free with
# swap at 2798/2799 MB — fully exhausted. Under that pressure the kernel OOM
# killer takes whole process groups, and it took both supervisors at once, which
# is why Nera went mute on Telegram and the website in the same minute. A restart
# loop inside a process cannot survive the loop being killed.
#
# So: a watcher that owns nothing, allocates almost nothing, and whose only job
# is to ask "is it answering?" and run the existing --daemon verb if not. It is
# deliberately a shell loop calling the scripts that already know how to start
# things safely, rather than a second way to start them. Both --daemon verbs
# already refuse to create a rival process, so calling them when something is
# already up is a no-op, and that is what makes this safe to run from cron.
#
# HONEST LIMIT, stated here because it is the kind of thing that gets forgotten:
# the guardian is a process on the same box under the same OOM killer. It is much
# smaller and much less likely to be chosen than a Python interpreter, but "less
# likely" is not "never". Nothing running inside this box can promise never. The
# two things that actually close the gap are outside it:
#
#   1. Termux:Boot — install the Termux:Boot app, then put a one-liner in
#      ~/.termux/boot/ that runs `./guardian.sh --once`. That covers a reboot and
#      covers Termux being swiped out of recents, which no in-box watcher can.
#
#   2. A VPS. ~$5/month buys systemd with Restart=always, no OOM pressure, and a
#      public HTTPS URL — which also unblocks the Paystack webhook and WhatsApp.
#      For a service taking real payments this is the honest answer; the guardian
#      is what makes the phone survivable until then, not a substitute for it.

set -uo pipefail

cd "$(dirname "$0")"

LOG_FILE="var/guardian.log"
PID_FILE="var/guardian.pid"
STOP_FILE="var/guardian.stop"

# How often to look. Long enough that the check itself is free, short enough that
# a buyer who messages during an outage waits under a minute rather than until
# somebody notices. Telegram queues undelivered updates for 24 hours and the
# poller only advances its offset after handling, so a gap here costs latency,
# not messages.
CHECK_INTERVAL=30

# The web health path. /docs answers 200 and needs no auth; /health does not
# exist on this app, and checking a 404 would report every healthy server as
# broken.
WEB_URL="http://127.0.0.1:8000/docs"

mkdir -p var

say() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG_FILE"
}

poller_up() {
    # pgrep rather than the PID file. The file says what was started; pgrep says
    # what is alive, and the whole reason this script exists is that those two
    # disagree after an OOM kill.
    pgrep -f 'app\.messaging\.poller' >/dev/null 2>&1
}

web_up() {
    # An HTTP check, not a process check. A uvicorn that is alive but wedged --
    # which is what memory pressure produces before it produces a kill -- still
    # shows up in pgrep while serving nothing.
    curl -fsS -m 8 -o /dev/null "$WEB_URL" 2>/dev/null
}

ensure_web() {
    if web_up; then
        return 0
    fi

    say "web is not answering $WEB_URL — starting it"

    # --restart, not --daemon: a wedged-but-alive uvicorn is exactly the case
    # --daemon refuses to touch ("already running"), and it is the case that
    # needs replacing. --restart stops it properly first and waits.
    if ./dev.sh --restart >> "$LOG_FILE" 2>&1; then
        say "web restarted"
    else
        say "web restart FAILED — see the lines above"
    fi
}

ensure_poller() {
    if poller_up; then
        return 0
    fi

    say "poller is not running — starting it"

    # --daemon here rather than --restart. Two pollers on one Telegram offset
    # cursor steal each other's updates, and --daemon is the verb that refuses to
    # create a second one; since we only get here when none is alive, it is both
    # sufficient and the safer of the two.
    if ./nera.sh --daemon >> "$LOG_FILE" 2>&1; then
        say "poller started"
    else
        say "poller start FAILED — see the lines above"
    fi
}

check_once() {
    ensure_poller
    ensure_web
}

running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

watch_loop() {
    say "guardian starting (interval ${CHECK_INTERVAL}s)"

    while true; do
        if [ -f "$STOP_FILE" ]; then
            say "guardian stopped deliberately"
            rm -f "$STOP_FILE" "$PID_FILE"
            exit 0
        fi

        check_once
        sleep "$CHECK_INTERVAL"
    done
}

case "${1:-}" in
    --once)
        # The verb for cron and for ~/.termux/boot. Idempotent by construction:
        # everything it calls is a no-op when the service is already healthy, so
        # running it every minute forever is fine.
        check_once
        ;;

    --status)
        if poller_up; then
            echo "poller:   answering (pid $(pgrep -f 'app\.messaging\.poller' | tr '\n' ' '))"
        else
            echo "poller:   DOWN"
        fi

        if web_up; then
            echo "web:      answering $WEB_URL"
        else
            echo "web:      DOWN"
        fi

        if running; then
            echo "guardian: watching (pid $(cat "$PID_FILE"), every ${CHECK_INTERVAL}s)"
        else
            echo "guardian: not watching — start it with ./guardian.sh --daemon"
        fi

        # The number that predicts the next outage. Printed here because the
        # guardian cannot fix it and the operator is the only one who can.
        echo
        free -m 2>/dev/null | awk '/^Mem:/ {printf "memory:   %s MB free of %s MB\n", $4, $2}
                                   /^Swap:/ {printf "swap:     %s MB free of %s MB\n", $4, $2}'
        ;;

    --stop)
        if running; then
            touch "$STOP_FILE"
            kill -TERM "$(cat "$PID_FILE")" 2>/dev/null
            echo "Guardian stopping. Nera itself is left running."
        else
            rm -f "$PID_FILE"
            echo "Not watching."
        fi
        ;;

    --log)
        tail -f "$LOG_FILE"
        ;;

    --daemon)
        if running; then
            echo "Already watching (pid $(cat "$PID_FILE"))."
            exit 0
        fi

        rm -f "$STOP_FILE"

        setsid "$0" --watch >> "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"

        sleep 2

        if running; then
            echo "Guardian is watching (pid $(cat "$PID_FILE"))."
            echo "  It restarts the poller or the web server within ${CHECK_INTERVAL}s of either going down."
            echo
            echo "  status:  ./guardian.sh --status"
            echo "  log:     ./guardian.sh --log"
            echo
            echo "  For a reboot or Termux being closed, this is not enough on its own."
            echo "  Install Termux:Boot and add:  ~/.termux/boot/nera  ->  ./guardian.sh --once"
        else
            echo "The guardian did not stay up. Last lines of $LOG_FILE:"
            tail -20 "$LOG_FILE"
            exit 1
        fi
        ;;

    --watch)
        # Internal: --daemon re-invokes itself here, already detached.
        watch_loop
        ;;

    "")
        echo "==> Guardian watching in the foreground. Ctrl-C to stop."
        watch_loop
        ;;

    *)
        sed -n '3,10p' "$0" | sed 's/^# \{0,1\}//'
        exit 1
        ;;
esac
