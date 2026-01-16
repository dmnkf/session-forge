"""Prompt assembly for Session Forge."""

from __future__ import annotations

import shlex
import textwrap
from pathlib import Path, PurePosixPath
from typing import Optional

from sf.core.ssh import SshExecutor
from sf.models import PromptPlan


class PromptBuilder:
    """Combine local prompt fragments with remote file globs."""

    def __init__(self, ssh: SshExecutor) -> None:
        self.ssh = ssh

    def build(self, worktree_path: str, plan: PromptPlan) -> str:
        parts = []
        if plan.prompt_file:
            parts.append(Path(plan.prompt_file).read_text())
        remote_content = self._collect_remote_content(
            worktree_path,
            includes=plan.include,
            excludes=plan.exclude,
            max_bytes=plan.max_bytes,
        )
        if remote_content:
            parts.append(remote_content)
        return "\n\n".join(part.strip() for part in parts if part.strip())

    def _collect_remote_content(
        self,
        worktree_path: str,
        *,
        includes: list[str],
        excludes: list[str],
        max_bytes: Optional[int],
    ) -> str:
        includes = includes or []
        excludes = excludes or []
        if not includes:
            return ""

        find_command = f"cd {shlex.quote(worktree_path)} && find . -type f"
        listing = self.ssh.run(find_command)

        candidates: list[str] = []
        for raw in listing.stdout.splitlines():
            rel = raw[2:] if raw.startswith("./") else raw
            if not rel:
                continue
            posix_path = PurePosixPath(rel)
            if not any(posix_path.match(pattern) for pattern in includes):
                continue
            if any(posix_path.match(pattern) for pattern in excludes):
                continue
            candidates.append(rel)

        if not candidates:
            return ""

        candidates.sort()
        files_payload = "\n".join(candidates)
        script = textwrap.dedent(
            f"""
            set -e
            cd {shlex.quote(worktree_path)}
            while IFS= read -r path; do
                [ -f "$path" ] || continue
                printf '\n# File: %s\n\n' "$path"
                cat -- "$path"
                printf '\n'
            done <<'EOF'
            {files_payload}
            EOF
            """
        )
        result = self.ssh.run(script)
        content = result.stdout

        if max_bytes is None:
            return content

        encoded = content.encode("utf-8")
        if len(encoded) <= max_bytes:
            return content

        truncated = encoded[:max_bytes].decode("utf-8", "ignore")
        return truncated + "\n# [truncated due to max-bytes]\n"


__all__ = ["PromptBuilder"]
