"""The poller loop.

Untested until now, which is worth stating plainly: this is the process that
faces buyers on Telegram, it is the one that ran for a day and three quarters
serving prices deleted two commits earlier, and it had no tests at all. The suite
covered what to *say* — ``compose_reply`` — and nothing about the loop that gets
a message to it and an answer back.

``fetch`` is injectable, so none of this needs a bot, a token or a network.
"""

from __future__ import annotations

import pytest

from app.messaging.poller import (
    FAILURE_BACKOFF_BASE,
    FAILURE_BACKOFF_MAX,
    PollerError,
    TelegramPoller,
)


class Recorder:
    """Stands in for ``time.sleep`` and remembers what it was asked to wait."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def _update(update_id: int, text: str = "hello", chat_id: int = 4242) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 1_700_000_000,
            "text": text,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "first_name": "Buyer", "is_bot": False},
        },
    }


def _ok(*updates: dict) -> dict:
    return {"ok": True, "result": list(updates)}


UNREACHABLE = {"ok": False, "description": "[Errno -3] Temporary failure in name resolution"}


# ---------- the busy loop ----------


def test_an_unreachable_telegram_is_waited_out_rather_than_hammered(monkeypatch):
    """The bug: a failed poll returns instantly, so the loop had no sleep in it.

    A long poll is its own timer — 25 seconds of silence costs one request. That
    was the stated reason this loop needed no delay, and it was true right up
    until the request stopped being made. A DNS failure on a dropped uplink comes
    back in microseconds, and the loop spun as fast as resolution could fail.

    What made it hard to see: nothing broke. Messages were still answered the
    moment the network returned. The only symptoms were a hot CPU on a phone and
    a log growing by a line per retry, which is how it reached 213,775 of them.
    """
    sleeps = Recorder()
    monkeypatch.setattr("app.messaging.poller.time.sleep", sleeps)

    calls = {"n": 0}

    def fetch(_payload):
        calls["n"] += 1

        # Fail five times, then stop the loop so the test terminates.
        if calls["n"] >= 5:
            poller.stop()

        return UNREACHABLE

    poller = TelegramPoller(bot_token="test-token", fetch=fetch)
    poller.run()

    assert sleeps.delays, (
        "the loop retried an unreachable Telegram without waiting at all"
    )

    # Growing, and never past the cap.
    assert sleeps.delays[0] <= FAILURE_BACKOFF_BASE
    assert max(sleeps.delays) <= FAILURE_BACKOFF_MAX


def test_the_backoff_grows_with_consecutive_failures(monkeypatch):
    monkeypatch.setattr("app.messaging.poller.time.sleep", Recorder())

    poller = TelegramPoller(bot_token="test-token", fetch=lambda _p: UNREACHABLE)

    seen = []

    for expected in range(1, 6):
        poller.drain()
        assert poller._failures == expected
        seen.append(poller._failures)

    assert seen == [1, 2, 3, 4, 5]


def test_a_successful_poll_clears_the_backoff(monkeypatch):
    """An uplink that comes back must be answered at full speed immediately.

    Otherwise the buyer who messaged during the outage waits out a backoff that
    is no longer measuring anything.
    """
    monkeypatch.setattr("app.messaging.poller.time.sleep", Recorder())

    replies = iter([UNREACHABLE, UNREACHABLE, UNREACHABLE, _ok()])

    poller = TelegramPoller(bot_token="test-token", fetch=lambda _p: next(replies))

    poller.drain()
    poller.drain()
    poller.drain()
    assert poller._failures == 3

    poller.drain()
    assert poller._failures == 0


def test_a_quiet_telegram_is_not_treated_as_a_failure(monkeypatch):
    """``ok`` with an empty result is the normal case, not an outage.

    The distinction the backoff depends on: nothing waiting means the long poll
    already slept for us, and adding a delay on top would make an idle bot slower
    to answer than a busy one.
    """
    sleeps = Recorder()
    monkeypatch.setattr("app.messaging.poller.time.sleep", sleeps)

    poller = TelegramPoller(bot_token="test-token", fetch=lambda _p: _ok())

    poller.drain()

    assert poller._failures == 0

    poller._wait_after_failure()
    assert sleeps.delays == []


def test_a_backoff_in_progress_is_cut_short_by_a_stop(monkeypatch):
    """SIGTERM during an outage must not wait out the whole delay.

    A deploy that has to sit through a 30-second backoff before the old process
    will exit is a deploy people stop waiting for — and skipping the wait is what
    leaves two pollers running.
    """
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        poller.stop()

    monkeypatch.setattr("app.messaging.poller.time.sleep", sleep)

    poller = TelegramPoller(bot_token="test-token", fetch=lambda _p: UNREACHABLE)
    poller._failures = 8  # a long backoff by now

    poller._wait_after_failure()

    assert len(slept) == 1, "the wait ignored a stop and slept the full delay"


# ---------- the things the loop must not get wrong ----------


def test_no_token_is_refused_before_any_request(monkeypatch):
    def fetch(_payload):  # pragma: no cover - must never be reached
        raise AssertionError("polled without a token")

    poller = TelegramPoller(bot_token="", fetch=fetch)

    with pytest.raises(PollerError, match="TELEGRAM_BOT_TOKEN"):
        poller.run()


def test_a_webhook_conflict_says_how_to_fix_it(monkeypatch):
    """The single most common reason for a silent bot, and it must not be a blip.

    A webhook set on the bot makes getUpdates return an error forever. Backing
    off and retrying would hide a misconfiguration behind what looks like a
    network problem, so this raises instead — and names the command that fixes it.
    """
    poller = TelegramPoller(
        bot_token="test-token",
        fetch=lambda _p: {
            "ok": False,
            "description": "Conflict: can't use getUpdates method while webhook is active",
        },
    )

    with pytest.raises(PollerError, match="take-over"):
        poller.drain()


def test_once_drains_what_is_waiting_and_returns(monkeypatch):
    """--once must make exactly one pass, whatever is or is not waiting."""
    calls = {"n": 0}

    def fetch(_payload):
        calls["n"] += 1
        return _ok()

    poller = TelegramPoller(bot_token="test-token", fetch=fetch)
    report = poller.run(once=True)

    assert calls["n"] == 1
    assert report.updates == 0
