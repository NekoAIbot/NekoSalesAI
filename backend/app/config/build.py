"""What code is this process actually running?

A question that sounds trivial and was not. A poller ran here for a day and three
quarters quoting a price that had been deleted from the source two commits
earlier — because it caught its own network errors and retried instead of exiting,
so the supervisor never started a fresh interpreter, so the edit never loaded.
From the outside that is indistinguishable from a bug in the current code, and it
sent someone hunting through files that were already correct.

The cost of answering it that day was process archaeology: elapsed-seconds
arithmetic against file mtimes, because this box boots with a clock three years
out and ``ps -o lstart`` is fiction. So it is answered here instead, once, at
startup, in the log — and the log is the first place anyone looks.

Nothing in here can raise. A fingerprint that breaks the process it is describing
would be a poor trade for a line of log output, so every lookup degrades to
"unknown" rather than failing.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# app/config/build.py -> app/config -> app -> backend
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_ROOT = BACKEND_ROOT / "app"

GIT_TIMEOUT = 5.0
DIGEST_CHARS = 12


@dataclass(frozen=True)
class Build:
    """The identity of the code in memory, as far as it can be established."""

    commit: str
    dirty: bool
    digest: str
    newest_file: str
    newest_at: str

    def describe(self) -> str:
        """One line, written to be greppable and read by a person in a hurry."""
        state = "dirty" if self.dirty else "clean"

        return (
            f"code {self.commit} ({state}), source digest {self.digest}, "
            f"newest edit {self.newest_at} ({self.newest_file})"
        )


def _git(*args: str) -> str | None:
    """Run a git command, or decide quietly that git is not available.

    No shell, a fixed argument list and a timeout: this runs at startup on a
    phone, where the repository may be absent entirely if the code arrived as an
    archive, and where a hung subprocess would mean a bot that never starts.
    """
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "-C", str(BACKEND_ROOT), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    return result.stdout.strip()


def _source_files() -> list[Path]:
    return sorted(p for p in SOURCE_ROOT.rglob("*.py") if p.is_file())


def _digest(files: list[Path]) -> str:
    """A hash of the source as it sits on disk.

    Independent of git on purpose. Git tells you which commit was checked out;
    this tells you what the bytes are, which is the thing Python actually
    imported. They disagree exactly when someone has edited without committing —
    the state most likely to be running during a debugging session.
    """
    hasher = hashlib.sha256()

    for path in files:
        try:
            hasher.update(path.relative_to(BACKEND_ROOT).as_posix().encode())
            hasher.update(path.read_bytes())
        except OSError:
            continue

    return hasher.hexdigest()[:DIGEST_CHARS]


def _newest(files: list[Path]) -> tuple[str, str]:
    newest: Path | None = None
    newest_mtime = 0.0

    for path in files:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue

        if mtime > newest_mtime:
            newest_mtime = mtime
            newest = path

    if newest is None:
        return "unknown", "unknown"

    stamp = datetime.fromtimestamp(newest_mtime, timezone.utc)

    return (
        newest.relative_to(BACKEND_ROOT).as_posix(),
        stamp.strftime("%Y-%m-%d %H:%M:%S"),
    )


def current() -> Build:
    """Fingerprint the code this interpreter loaded."""
    files = _source_files()
    newest_file, newest_at = _newest(files)

    commit = _git("rev-parse", "--short", "HEAD") or "no-git"

    # An empty porcelain listing means clean. None means git could not tell us,
    # which is not the same as clean and must not be reported as it.
    porcelain = _git("status", "--porcelain")
    dirty = bool(porcelain) if porcelain is not None else False

    return Build(
        commit=commit,
        dirty=dirty,
        digest=_digest(files),
        newest_file=newest_file,
        newest_at=newest_at,
    )


def describe() -> str:
    """``current().describe()``, but guaranteed not to raise on the way."""
    try:
        return current().describe()
    except Exception:  # noqa: BLE001 - a log line is never worth a crash
        return "code unknown (could not fingerprint the source)"
