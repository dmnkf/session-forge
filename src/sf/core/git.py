"""Git orchestration helpers for anchors and worktrees."""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from sf.core.locks import wrap_with_lock
from sf.core.ssh import SshExecutor
from sf.models import FeatureConfig, RepoConfig

ANCHOR_ROOT = "repo-cache"
FEATURE_ROOT = "features"


@dataclass
class GitManager:
    """Per-host git orchestration for Session Forge."""

    ssh: SshExecutor

    def anchor_path(self, repo: RepoConfig) -> str:
        return f"{ANCHOR_ROOT}/{repo.name}.anchor"

    def worktree_path(self, feature: FeatureConfig, repo: RepoConfig) -> str:
        return f"{FEATURE_ROOT}/{feature.name}/{repo.name}"

    def ensure_anchor(self, repo: RepoConfig) -> None:
        anchor = self.anchor_path(repo)
        anchor_q = shlex.quote(anchor)
        url_q = shlex.quote(repo.url)
        command = (
            f"mkdir -p {shlex.quote(ANCHOR_ROOT)} && "
            "if [ -d {anchor}/.git ]; then "
            "git -C {anchor} remote set-url origin {url} && "
            "git -C {anchor} fetch origin --prune; "
            "else git clone {url} {anchor}; fi"
        ).format(anchor=anchor_q, url=url_q)
        self.ssh.run(wrap_with_lock(f"anchor-{repo.name}", command))

    def refresh_branch(self, repo: RepoConfig, feature: FeatureConfig) -> str:
        anchor_path = self.anchor_path(repo)
        anchor_q = shlex.quote(anchor_path)
        base_q = shlex.quote(feature.base)
        branch_name = f"feat/{feature.name}"
        branch_q = shlex.quote(branch_name)
        command = (
            f"git -C {anchor_q} fetch origin {base_q} && "
            "(git -C {anchor} show-ref --verify --quiet refs/heads/{branch} && "
            "git -C {anchor} branch -f {branch} origin/{base} || "
            "git -C {anchor} branch {branch} origin/{base})"
        ).format(anchor=anchor_q, branch=branch_q, base=base_q)
        self.ssh.run(wrap_with_lock(f"branch-{repo.name}", command))
        return branch_name

    def ensure_worktree(self, repo: RepoConfig, feature: FeatureConfig) -> str:
        anchor_path = self.anchor_path(repo)
        anchor_q = shlex.quote(anchor_path)
        worktree_path = self.worktree_path(feature, repo)
        worktree_q = shlex.quote(worktree_path)
        branch = f"feat/{feature.name}"
        branch_q = shlex.quote(branch)
        feature_root = f"{FEATURE_ROOT}/{feature.name}"
        command = (
            f"mkdir -p {shlex.quote(feature_root)} && "
            "if [ ! -d {worktree}/.git ]; then "
            "git -C {anchor} worktree add {worktree} {branch}; "
            "else git -C {worktree} fetch origin && git -C {worktree} reset --hard {branch}; fi"
        ).format(anchor=anchor_q, worktree=worktree_q, branch=branch_q)
        self.ssh.run(wrap_with_lock(f"worktree-{repo.name}-{feature.name}", command))
        return worktree_path

    def destroy_worktree(self, repo: RepoConfig, feature: FeatureConfig) -> None:
        anchor_q = shlex.quote(self.anchor_path(repo))
        worktree = self.worktree_path(feature, repo)
        worktree_q = shlex.quote(worktree)
        command = (
            "if [ -d {wt}/.git ]; then git -C {anchor} worktree remove --force {wt}; fi && "
            f"rm -rf {worktree_q}"
        ).format(wt=worktree_q, anchor=anchor_q)
        self.ssh.run(wrap_with_lock(f"worktree-{repo.name}-{feature.name}", command))

    def delete_branch(self, repo: RepoConfig, feature: FeatureConfig) -> None:
        anchor_q = shlex.quote(self.anchor_path(repo))
        branch_q = shlex.quote(f"feat/{feature.name}")
        command = (
            "git -C {anchor} show-ref --verify --quiet refs/heads/{branch} && "
            "git -C {anchor} branch -D {branch} || true"
        ).format(anchor=anchor_q, branch=branch_q)
        self.ssh.run(wrap_with_lock(f"branch-{repo.name}", command))


__all__ = ["GitManager", "ANCHOR_ROOT", "FEATURE_ROOT"]
