"""Observe bounded transient directory changes on systems with kqueue.

A notification is not a syscall log: coalescing loses event counts, and only the
exact watched directory is covered. This observer is not a security boundary.
"""

from __future__ import annotations

import os
import select
from pathlib import Path


class DirectoryObserver:
    """Record whether a specific directory received a vnode change notification."""

    def __init__(self, directory: Path) -> None:
        """Watch one existing directory, failing closed if kqueue is unavailable."""
        if not hasattr(select, "kqueue"):
            raise RuntimeError("kqueue directory observation is unavailable")
        self.directory = directory
        self.fd = os.open(directory, os.O_RDONLY)
        self.identity = os.fstat(self.fd).st_ino, os.fstat(self.fd).st_dev
        self.queue = select.kqueue()
        self.queue.control(
            [
                select.kevent(
                    self.fd,
                    filter=select.KQ_FILTER_VNODE,
                    flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR,
                    fflags=select.KQ_NOTE_WRITE | select.KQ_NOTE_DELETE | select.KQ_NOTE_RENAME,
                )
            ],
            0,
            0,
        )

    def observe(self) -> list[int]:
        """Drain currently queued notifications; counts can be coalesced."""
        return [event.fflags for event in self.queue.control(None, 16, 0)]

    def intact(self) -> bool:
        """Check that the watched path still names the original directory."""
        try:
            stat = self.directory.stat()
        except OSError:
            return False
        return (stat.st_ino, stat.st_dev) == self.identity

    def close(self) -> None:
        """Release the kqueue and directory descriptor."""
        self.queue.close()
        os.close(self.fd)
