"""Remote locking utilities."""

from __future__ import annotations

import shlex

LOCK_ROOT = "/tmp"


def lock_path(identifier: str) -> str:
    return f"{LOCK_ROOT}/sf.lock.{identifier.replace('/', '_')}"


def wrap_with_lock(identifier: str, command: str) -> str:
    """Wrap a remote shell command with `flock` to ensure mutual exclusion."""

    path = shlex.quote(lock_path(identifier))
    escaped = command.replace("'", "'\"'\"'")
    return f"flock -w 30 {path} -c '{escaped}'"


__all__ = ["lock_path", "wrap_with_lock"]
