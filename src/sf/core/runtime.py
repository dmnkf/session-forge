"""Service runtime orchestration helpers."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Callable

from sf.core.ssh import CommandResult, SshExecutor
from sf.models import (
    FeatureConfig,
    FeatureRepoAttachment,
    RepoConfig,
    ServiceConfig,
    compute_port_offset,
)

CommandBuilder = Callable[[str, ServiceConfig, str], str]


def _docker_compose_cmd(action: str, config: ServiceConfig, extra: str) -> str:
    file_flag = ""
    if config.file:
        file_flag = f"-f {shlex.quote(config.file)} "
    args_suffix = f" {extra}" if extra else ""
    return f"docker compose {file_flag}{action}{args_suffix}"


def _podman_compose_cmd(action: str, config: ServiceConfig, extra: str) -> str:
    file_flag = ""
    if config.file:
        file_flag = f"-f {shlex.quote(config.file)} "
    args_suffix = f" {extra}" if extra else ""
    return f"podman compose {file_flag}{action}{args_suffix}"


def _script_cmd(action: str, config: ServiceConfig, extra: str) -> str:
    commands = config.commands or {}
    try:
        return commands[action]
    except KeyError as exc:
        raise ValueError(f"Missing script command for action '{action}'") from exc


RUNTIME_BUILDERS: dict[str, CommandBuilder] = {
    "docker_compose": _docker_compose_cmd,
    "podman_compose": _podman_compose_cmd,
    "script": _script_cmd,
}


@dataclass
class ServiceRuntime:
    """Per-host service runtime orchestration for Session Forge."""

    ssh: SshExecutor

    def _service_env(self, feature: FeatureConfig, repo: RepoConfig) -> dict[str, str]:
        offset = compute_port_offset(feature.name, repo.name)
        return {
            "COMPOSE_PROJECT_NAME": f"sf-{feature.name}-{repo.name}",
            "SF_PORT_OFFSET": str(offset),
            "SF_FEATURE": feature.name,
            "SF_REPO": repo.name,
        }

    def _build_command(
        self,
        action: str,
        attachment: FeatureRepoAttachment,
        extra: str = "",
    ) -> str:
        config = attachment.service or ServiceConfig()
        try:
            builder = RUNTIME_BUILDERS[config.runtime]
        except KeyError as exc:
            raise ValueError(f"Unknown service runtime '{config.runtime}'") from exc
        return builder(action, config, extra)

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
        command = self._build_command("up", attachment, extra)
        return self.ssh.run(command, cwd=worktree_path, env=self._service_env(feature, repo))

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
        command = self._build_command("down", attachment, extra)
        return self.ssh.run(command, cwd=worktree_path, env=self._service_env(feature, repo))

    def ps(
        self,
        repo: RepoConfig,
        feature: FeatureConfig,
        attachment: FeatureRepoAttachment,
        worktree_path: str,
    ) -> CommandResult:
        command = self._build_command("ps", attachment)
        return self.ssh.run(
            command, cwd=worktree_path, env=self._service_env(feature, repo), check=False
        )


__all__ = ["CommandBuilder", "RUNTIME_BUILDERS", "ServiceRuntime"]
