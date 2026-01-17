"""Reusable orchestration routines shared between CLI and server."""

from __future__ import annotations

import subprocess
from typing import Dict, List, Optional

from sf.core.git import GitManager
from sf.core.ssh import SshExecutor
from sf.core.state import StateStore
from sf.models import FeatureConfig, FeatureRepoAttachment, HostConfig, RepoConfig

store = StateStore()


class OrchestratorError(RuntimeError):
    """Raised when orchestration fails."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _guard(fn):
    try:
        return fn()
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.output or str(exc)).strip()
        raise OrchestratorError(message or "Remote command failed") from exc


def _ensure_feature(feature: str) -> FeatureConfig:
    try:
        return store.load_feature(feature)
    except FileNotFoundError as exc:
        raise OrchestratorError(f"Feature '{feature}' does not exist") from exc


def _ensure_repo(name: str, config: Dict[str, RepoConfig]) -> RepoConfig:
    try:
        return config[name]
    except KeyError as exc:
        raise OrchestratorError(f"Repository '{name}' is not defined") from exc


def _ensure_host(name: str, config: Dict[str, HostConfig]) -> HostConfig:
    try:
        return config[name]
    except KeyError as exc:
        raise OrchestratorError(f"Host '{name}' is not defined") from exc


def _select_host(attachment: FeatureRepoAttachment, preferred: Optional[str]) -> str:
    if preferred and preferred in attachment.hosts:
        return preferred
    if attachment.hosts:
        return attachment.hosts[0]
    raise OrchestratorError("Attachment has no hosts configured")


# ---------------------------------------------------------------------------
# Public routines
# ---------------------------------------------------------------------------


def sync_feature(
    feature: str, *, repo: Optional[str] = None, dry_run: bool = False
) -> List[Dict[str, str]]:
    """Sync anchors and worktrees for the feature. Returns summary per host."""

    config = store.load_config()
    feature_cfg = _ensure_feature(feature)
    attachments = feature_cfg.repos
    if repo:
        attachments = [att for att in attachments if att.repo == repo]
    if not attachments:
        raise OrchestratorError("No repo attachments found to sync")
    summary: List[Dict[str, str]] = []
    for attachment in attachments:
        repo_cfg = _ensure_repo(attachment.repo, config.repos)
        for host_name in attachment.hosts:
            host_cfg = _ensure_host(host_name, config.hosts)
            ssh = SshExecutor(host_cfg, dry_run=dry_run)
            git = GitManager(ssh)
            _guard(lambda: git.ensure_anchor(repo_cfg))
            _guard(lambda: git.refresh_branch(repo_cfg, feature_cfg))
            worktree_path = _guard(lambda: git.ensure_worktree(repo_cfg, feature_cfg))
            summary.append(
                {
                    "host": host_name,
                    "repo": repo_cfg.name,
                    "worktree": worktree_path,
                }
            )
    return summary


def destroy_feature(feature: str) -> List[Dict[str, str]]:
    config = store.load_config()
    feature_cfg = _ensure_feature(feature)
    results: List[Dict[str, str]] = []
    for attachment in feature_cfg.repos:
        repo_cfg = _ensure_repo(attachment.repo, config.repos)
        for host_name in attachment.hosts:
            host_cfg = _ensure_host(host_name, config.hosts)
            ssh = SshExecutor(host_cfg)
            git = GitManager(ssh)
            _guard(lambda: git.destroy_worktree(repo_cfg, feature_cfg))
            _guard(lambda: git.delete_branch(repo_cfg, feature_cfg))
            results.append({"host": host_name, "repo": repo_cfg.name})
    store.feature_path(feature).unlink(missing_ok=True)
    return results


__all__ = [
    "OrchestratorError",
    "destroy_feature",
    "sync_feature",
]
