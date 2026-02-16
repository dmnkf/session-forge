"""Docker Compose orchestration helpers."""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from sf.core.ssh import CommandResult, SshExecutor
from sf.models import (
    FeatureConfig,
    FeatureRepoAttachment,
    RepoConfig,
    compute_port_offset,
)


@dataclass
class ComposeManager:
    """Per-host Docker Compose orchestration for Session Forge."""

    ssh: SshExecutor

    def _compose_project_name(self, feature: FeatureConfig, repo: RepoConfig) -> str:
        return f"sf-{feature.name}-{repo.name}"

    def _compose_env(self, feature: FeatureConfig, repo: RepoConfig) -> dict[str, str]:
        offset = compute_port_offset(feature.name, repo.name)
        return {
            "COMPOSE_PROJECT_NAME": self._compose_project_name(feature, repo),
            "SF_PORT_OFFSET": str(offset),
            "SF_FEATURE": feature.name,
            "SF_REPO": repo.name,
        }

    def _build_compose_command(
        self,
        action: str,
        attachment: FeatureRepoAttachment,
        extra_args: str = "",
    ) -> str:
        file_flag = ""
        if attachment.compose_file:
            file_flag = f"-f {shlex.quote(attachment.compose_file)} "
        args_suffix = f" {extra_args}" if extra_args else ""
        return f"docker compose {file_flag}{action}{args_suffix}"

    def up(
        self,
        repo: RepoConfig,
        feature: FeatureConfig,
        attachment: FeatureRepoAttachment,
        worktree_path: str,
        *,
        detach: bool = True,
    ) -> CommandResult:
        extra = "-d" if detach else ""
        command = self._build_compose_command("up", attachment, extra)
        return self.ssh.run(command, cwd=worktree_path, env=self._compose_env(feature, repo))

    def down(
        self,
        repo: RepoConfig,
        feature: FeatureConfig,
        attachment: FeatureRepoAttachment,
        worktree_path: str,
        *,
        volumes: bool = False,
    ) -> CommandResult:
        extra = "-v" if volumes else ""
        command = self._build_compose_command("down", attachment, extra)
        return self.ssh.run(command, cwd=worktree_path, env=self._compose_env(feature, repo))

    def ps(
        self,
        repo: RepoConfig,
        feature: FeatureConfig,
        attachment: FeatureRepoAttachment,
        worktree_path: str,
    ) -> CommandResult:
        command = self._build_compose_command("ps", attachment)
        return self.ssh.run(
            command, cwd=worktree_path, env=self._compose_env(feature, repo), check=False
        )


__all__ = ["ComposeManager"]
