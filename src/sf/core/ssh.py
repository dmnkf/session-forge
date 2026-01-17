"""SSH utilities built on subprocess."""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from rich.console import Console

from sf.models import HostConfig

console = Console()


@dataclass
class CommandResult:
    """Represents the outcome of a remote command."""

    exit_code: int
    stdout: str
    stderr: str

    def check(self) -> "CommandResult":
        if self.exit_code != 0:
            raise subprocess.CalledProcessError(
                returncode=self.exit_code,
                cmd="remote",
                output=self.stdout,
                stderr=self.stderr,
            )
        return self


class SshExecutor:
    """Executor utility that shells out to `ssh` and `scp` commands."""

    def __init__(self, host: HostConfig, *, dry_run: bool = False) -> None:
        self.host = host
        self.dry_run = dry_run

    # ------------------------------------------------------------------
    def _remote_preamble(self, env: Optional[Dict[str, str]]) -> str:
        exports = [f"export {key}={shlex.quote(value)}" for key, value in (env or {}).items()]
        return " && ".join(exports) if exports else ""

    def _wrap_command(
        self, command: str, *, cwd: Optional[str], env: Optional[Dict[str, str]]
    ) -> str:
        segments = []
        env_vars: Dict[str, str] = {}
        env_vars.update(self.host.env)
        if env:
            env_vars.update(env)
        exports = self._remote_preamble(env_vars or None)
        if exports:
            segments.append(exports)
        if cwd:
            segments.append(f"cd {shlex.quote(cwd)}")
        segments.append(command)
        wrapped = " && ".join(segment for segment in segments if segment)
        return wrapped

    def _build_ssh_args(self, command: str) -> Iterable[str]:
        target = self.host.target
        if target in {"local", "localhost"}:
            return ["sh", "-lc", command]
        ssh_opts = ["-o", "BatchMode=yes"]
        if os.environ.get("SF_ACCEPT_NEW_HOSTKEYS") == "1":
            ssh_opts += ["-o", "StrictHostKeyChecking=accept-new"]
        return ["ssh", *ssh_opts, target, "sh", "-lc", command]

    def run(
        self,
        command: str,
        *,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        check: bool = True,
        timeout: Optional[int] = None,
    ) -> CommandResult:
        wrapped = self._wrap_command(command, cwd=cwd, env=env)
        ssh_args = list(self._build_ssh_args(wrapped))
        if self.dry_run:
            console.print(f"[dry-run] {' '.join(shlex.quote(arg) for arg in ssh_args)}")
            return CommandResult(0, "", "")
        timeout_value = timeout if timeout is not None else 300
        proc = subprocess.run(
            ssh_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            timeout=timeout_value,
            check=False,
        )
        result = CommandResult(proc.returncode, proc.stdout, proc.stderr)
        if check:
            result.check()
        return result

    def push_file(self, local_path: Path, remote_path: str, *, create_dirs: bool = True) -> None:
        if create_dirs:
            remote_dir = str(Path(remote_path).parent)
            self.run(f"mkdir -p {shlex.quote(remote_dir)}")
        target = self.host.target
        scp_args = ["scp", "-o", "BatchMode=yes"]
        if os.environ.get("SF_ACCEPT_NEW_HOSTKEYS") == "1":
            scp_args += ["-o", "StrictHostKeyChecking=accept-new"]
        if self.dry_run:
            pretty = " ".join(
                shlex.quote(arg) for arg in scp_args + [str(local_path), f"{target}:{remote_path}"]
            )
            console.print(f"[dry-run] {pretty}")
            return
        if target in {"local", "localhost"}:
            destination = Path(remote_path)
            if not destination.is_absolute():
                destination = Path.home() / destination
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(Path(local_path).read_bytes())
            return
        subprocess.run(scp_args + [str(local_path), f"{target}:{remote_path}"], check=True)


__all__ = ["CommandResult", "SshExecutor"]
