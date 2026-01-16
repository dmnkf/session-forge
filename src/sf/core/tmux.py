"""tmux orchestration helpers."""

from __future__ import annotations

import shlex
from typing import List

from sf.core.ssh import SshExecutor
from sf.models import SessionDescriptor


class TmuxManager:
    """Ensure tmux sessions exist (or are removed) on remote hosts."""

    def __init__(self, ssh: SshExecutor) -> None:
        self.ssh = ssh

    def start_session(self, descriptor: SessionDescriptor, *, cwd: str, command: str) -> None:
        session_name = descriptor.name
        session_q = shlex.quote(session_name)
        cwd_q = shlex.quote(cwd)
        cmd_q = shlex.quote(command)
        self.ssh.run(
            "tmux has-session -t {session} 2>/dev/null && exit 0 || "
            "tmux new-session -d -s {session} -c {cwd} {cmd}".format(
                session=session_q,
                cwd=cwd_q,
                cmd=cmd_q,
            )
        )

    def kill_session(self, descriptor: SessionDescriptor) -> None:
        session_q = shlex.quote(descriptor.name)
        self.ssh.run(
            "tmux has-session -t {session} 2>/dev/null && tmux kill-session -t {session} || true".format(
                session=session_q
            )
        )

    def list_sessions(self) -> List[str]:
        result = self.ssh.run("tmux list-sessions -F '#S'", check=False)
        if result.exit_code != 0:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]


__all__ = ["TmuxManager"]
