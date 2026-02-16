"""Data models shared across Session Forge components."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel, Field, field_validator

DEFAULT_BASE_BRANCH = "main"
STATE_ROOT = Path(os.environ.get("SF_STATE_DIR", str(Path.home() / ".sf")))
CONFIG_FILE = STATE_ROOT / "config.yml"
FEATURES_DIR = STATE_ROOT / "features"
LOG_DIR = STATE_ROOT / "logs"
CACHE_DIR = STATE_ROOT / "cache"


class HostConfig(BaseModel):
    """Represents a remote host that Session Forge can target via SSH."""

    name: str = Field(..., description="Logical name for the host")
    target: str = Field(..., description="SSH target (user@host or SSH config alias)")
    env: Dict[str, str] = Field(default_factory=dict, description="Additional env vars")
    tags: List[str] = Field(default_factory=list, description="Arbitrary tags for selection")


class RepoConfig(BaseModel):
    """Repository metadata used when creating features and worktrees."""

    name: str = Field(..., description="Logical repo name")
    url: str = Field(..., description="Git URL for anchor clone")
    base: str = Field(DEFAULT_BASE_BRANCH, description="Default base branch")
    anchor_subdir: str | None = Field(
        default=None,
        description="Optional subdirectory inside repo for sessions (e.g., monorepo subset)",
    )

    def session_root(self, worktree_path: str) -> str:
        if self.anchor_subdir:
            return f"{worktree_path}/{self.anchor_subdir}"
        return worktree_path


class FeatureRepoAttachment(BaseModel):
    """Attachment of a repo to a feature across one or more hosts."""

    repo: str
    hosts: List[str] = Field(..., description="Host names that should host the worktree")
    subdir: str | None = Field(
        default=None,
        description="Optional subdirectory override used when starting sessions",
    )
    compose_file: str | None = Field(
        default=None,
        description="Path to compose file relative to worktree root",
    )

    @field_validator("hosts")
    @classmethod
    def _hosts_not_empty(cls, value: List[str]) -> List[str]:
        if not value:
            raise ValueError("Attachment must include at least one host")
        return value


class FeatureConfig(BaseModel):
    """Metadata stored per feature file."""

    name: str
    base: str = Field(DEFAULT_BASE_BRANCH)
    repos: List[FeatureRepoAttachment] = Field(default_factory=list)

    def get_attachment(self, repo_name: str) -> Optional[FeatureRepoAttachment]:
        for attachment in self.repos:
            if attachment.repo == repo_name:
                return attachment
        return None


class SfConfig(BaseModel):
    """Top-level configuration loaded from ~/.sf/config.yml."""

    hosts: Dict[str, HostConfig] = Field(default_factory=dict)
    repos: Dict[str, RepoConfig] = Field(default_factory=dict)

    def ensure_host(self, host: HostConfig) -> None:
        self.hosts[host.name] = host

    def ensure_repo(self, repo: RepoConfig) -> None:
        self.repos[repo.name] = repo


PORT_BLOCK_SIZE = 100
PORT_BASE = 10000
PORT_BUCKETS = 500


def compute_port_offset(feature_name: str, repo_name: str | None = None) -> int:
    """Deterministic port offset from feature (and optionally repo) name."""
    key = feature_name if repo_name is None else f"{feature_name}/{repo_name}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    bucket = int(digest[:8], 16) % PORT_BUCKETS
    return PORT_BASE + bucket * PORT_BLOCK_SIZE


__all__ = [
    "CACHE_DIR",
    "CONFIG_FILE",
    "DEFAULT_BASE_BRANCH",
    "FEATURES_DIR",
    "FeatureConfig",
    "FeatureRepoAttachment",
    "HostConfig",
    "LOG_DIR",
    "RepoConfig",
    "SfConfig",
    "STATE_ROOT",
    "compute_port_offset",
]
