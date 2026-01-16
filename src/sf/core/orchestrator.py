"""Reusable orchestration routines shared between CLI and server."""

from __future__ import annotations

import re
import shlex
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from sf.core.git import GitManager
from sf.core.llm import resolve_command
from sf.core.prompt import PromptBuilder
from sf.core.ssh import SshExecutor
from sf.core.state import StateStore
from sf.core.tmux import TmuxManager
from sf.models import (
    FeatureConfig,
    FeatureRepoAttachment,
    HostConfig,
    PromptPlan,
    RepoConfig,
    SessionDescriptor,
)

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


def start_session(
    feature: str,
    repo: str,
    *,
    llm: str,
    host: Optional[str] = None,
    subdir: Optional[str] = None,
    command: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, str]:
    config = store.load_config()
    feature_cfg = _ensure_feature(feature)
    attachment = feature_cfg.get_attachment(repo)
    if not attachment:
        raise OrchestratorError(f"Repo '{repo}' is not attached to feature '{feature}'")
    host_name = _select_host(attachment, host)
    host_cfg = _ensure_host(host_name, config.hosts)
    repo_cfg = _ensure_repo(repo, config.repos)
    ssh = SshExecutor(host_cfg, dry_run=dry_run)
    git = GitManager(ssh)
    _guard(lambda: git.ensure_anchor(repo_cfg))
    _guard(lambda: git.refresh_branch(repo_cfg, feature_cfg))
    worktree_path = _guard(lambda: git.ensure_worktree(repo_cfg, feature_cfg))
    worktree_for_session = worktree_path
    if attachment.subdir:
        worktree_for_session = f"{worktree_for_session}/{attachment.subdir}"
    if subdir:
        worktree_for_session = f"{worktree_for_session}/{subdir}"
    try:
        llm_command = command or resolve_command(llm)
    except Exception as exc:
        raise OrchestratorError(str(exc)) from exc
    descriptor = SessionDescriptor(feature=feature, repo=repo_cfg.name, llm=llm)
    tmux = TmuxManager(ssh)
    _guard(lambda: tmux.start_session(descriptor, cwd=worktree_for_session, command=llm_command))
    return {
        "session": descriptor.name,
        "host": host_name,
        "cwd": worktree_for_session,
        "command": llm_command,
    }


def stop_session(
    feature: str, repo: str, *, llm: str, host: Optional[str] = None
) -> Dict[str, str]:
    config = store.load_config()
    feature_cfg = _ensure_feature(feature)
    attachment = feature_cfg.get_attachment(repo)
    if not attachment:
        raise OrchestratorError(f"Repo '{repo}' is not attached to feature '{feature}'")
    host_name = _select_host(attachment, host)
    host_cfg = _ensure_host(host_name, config.hosts)
    ssh = SshExecutor(host_cfg)
    tmux = TmuxManager(ssh)
    descriptor = SessionDescriptor(feature=feature, repo=repo, llm=llm)
    _guard(lambda: tmux.kill_session(descriptor))
    return {"session": descriptor.name, "host": host_name}


def send_prompt(
    feature: str,
    repo: str,
    *,
    llm: str,
    prompt_file: Optional[Path] = None,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    max_bytes: Optional[int] = None,
    host: Optional[str] = None,
) -> Dict[str, str]:
    config = store.load_config()
    feature_cfg = _ensure_feature(feature)
    attachment = feature_cfg.get_attachment(repo)
    if not attachment:
        raise OrchestratorError(f"Repo '{repo}' is not attached to feature '{feature}'")
    host_name = _select_host(attachment, host)
    host_cfg = _ensure_host(host_name, config.hosts)
    repo_cfg = _ensure_repo(repo, config.repos)
    ssh = SshExecutor(host_cfg)
    git = GitManager(ssh)
    _guard(lambda: git.ensure_anchor(repo_cfg))
    _guard(lambda: git.refresh_branch(repo_cfg, feature_cfg))
    worktree_path = _guard(lambda: git.ensure_worktree(repo_cfg, feature_cfg))
    if attachment.subdir:
        worktree_path = f"{worktree_path}/{attachment.subdir}"
    plan = PromptPlan(
        feature=feature,
        repo=repo,
        prompt_file=prompt_file,
        include=include or ["README.md"],
        exclude=exclude or [],
        max_bytes=max_bytes,
    )
    builder = PromptBuilder(ssh)
    payload = _guard(lambda: builder.build(worktree_path, plan))
    if not payload.strip():
        raise OrchestratorError("Prompt payload is empty")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)

    def _slug(value: str) -> str:
        return value.replace("/", "_").replace(":", "_")

    slug = ".".join([_slug(feature), _slug(repo), _slug(llm)])
    remote_path = f"/tmp/.sf_prompt.{slug}.{uuid.uuid4().hex}.txt"
    _guard(lambda: ssh.push_file(tmp_path, remote_path))
    tmp_path.unlink(missing_ok=True)
    descriptor = SessionDescriptor(feature=feature, repo=repo, llm=llm)
    session_q = shlex.quote(descriptor.name)
    remote_q = shlex.quote(remote_path)
    _guard(
        lambda: ssh.run(
            f"tmux load-buffer -b sf {remote_q} && tmux paste-buffer -b sf -t {session_q} && tmux send-keys -t {session_q} Enter"
        )
    )
    return {"session": descriptor.name, "host": host_name, "bytes": len(payload.encode("utf-8"))}


def destroy_feature(feature: str) -> List[Dict[str, str]]:
    config = store.load_config()
    feature_cfg = _ensure_feature(feature)
    results: List[Dict[str, str]] = []
    kill_regex = re.escape(f"feat:{feature}:")
    kill_command = (
        "tmux list-sessions -F '#S' 2>/dev/null | "
        f"grep -E {shlex.quote('^' + kill_regex)} | "
        'while read -r name; do tmux kill-session -t "$name" 2>/dev/null || true; done; true'
    )
    for attachment in feature_cfg.repos:
        repo_cfg = _ensure_repo(attachment.repo, config.repos)
        for host_name in attachment.hosts:
            host_cfg = _ensure_host(host_name, config.hosts)
            ssh = SshExecutor(host_cfg)
            ssh.run(kill_command, check=False)
            git = GitManager(ssh)
            _guard(lambda: git.destroy_worktree(repo_cfg, feature_cfg))
            _guard(lambda: git.delete_branch(repo_cfg, feature_cfg))
            results.append({"host": host_name, "repo": repo_cfg.name})
    store.feature_path(feature).unlink(missing_ok=True)
    return results


__all__ = [
    "OrchestratorError",
    "destroy_feature",
    "send_prompt",
    "start_session",
    "stop_session",
    "sync_feature",
]
