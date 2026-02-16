"""Tests for Docker Compose support."""

from __future__ import annotations

import pytest

from sf.core.compose import ComposeManager
from sf.core.ssh import SshExecutor
from sf.models import (
    FeatureConfig,
    FeatureRepoAttachment,
    HostConfig,
    RepoConfig,
    compute_port_offset,
)


# --- Port offset tests ---


def test_port_offset_is_deterministic():
    a = compute_port_offset("my-feature", "my-repo")
    b = compute_port_offset("my-feature", "my-repo")
    assert a == b


def test_port_offset_varies_by_feature():
    a = compute_port_offset("feature-a", "repo")
    b = compute_port_offset("feature-b", "repo")
    assert a != b


def test_port_offset_varies_by_repo():
    a = compute_port_offset("feat", "repo-a")
    b = compute_port_offset("feat", "repo-b")
    assert a != b


def test_port_offset_range():
    offset = compute_port_offset("anything")
    assert 10000 <= offset < 60000


def test_port_offset_without_repo():
    offset = compute_port_offset("solo-feature")
    assert isinstance(offset, int)
    assert offset >= 10000


# --- ComposeManager tests ---


@pytest.fixture
def compose_setup(sample_host, sample_repo, sample_feature):
    ssh = SshExecutor(sample_host, dry_run=True)
    compose = ComposeManager(ssh)
    attachment = sample_feature.repos[0]
    return compose, sample_repo, sample_feature, attachment


def test_compose_project_name(compose_setup):
    compose, repo, feature, _ = compose_setup
    name = compose._compose_project_name(feature, repo)
    assert name == f"sf-{feature.name}-{repo.name}"


def test_compose_env_contains_expected_vars(compose_setup):
    compose, repo, feature, _ = compose_setup
    env = compose._compose_env(feature, repo)
    assert "SF_PORT_OFFSET" in env
    assert "COMPOSE_PROJECT_NAME" in env
    assert env["SF_FEATURE"] == feature.name
    assert env["SF_REPO"] == repo.name


def test_compose_up_dry_run(compose_setup):
    compose, repo, feature, attachment = compose_setup
    result = compose.up(repo, feature, attachment, "features/test/repo")
    assert result.exit_code == 0


def test_compose_down_dry_run(compose_setup):
    compose, repo, feature, attachment = compose_setup
    result = compose.down(repo, feature, attachment, "features/test/repo")
    assert result.exit_code == 0


def test_compose_ps_dry_run(compose_setup):
    compose, repo, feature, attachment = compose_setup
    result = compose.ps(repo, feature, attachment, "features/test/repo")
    assert result.exit_code == 0


def test_compose_build_command_with_file(compose_setup):
    compose, _, _, _ = compose_setup
    attachment = FeatureRepoAttachment(repo="r", hosts=["h"], compose_file="custom.yml")
    cmd = compose._build_compose_command("up", attachment)
    assert "-f" in cmd
    assert "custom.yml" in cmd


def test_compose_build_command_default_file(compose_setup):
    compose, _, _, attachment = compose_setup
    cmd = compose._build_compose_command("up", attachment)
    assert "-f" not in cmd
