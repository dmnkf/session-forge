"""Shared test fixtures for Session Forge tests."""

import pytest
from sf.models import HostConfig, RepoConfig, FeatureConfig, FeatureRepoAttachment


@pytest.fixture
def sample_host():
    """Return a sample host configuration."""
    return HostConfig(
        name="test-host",
        target="user@test.example.com",
        tags=["test", "dev"],
        env={"ENV_VAR": "value"},
    )


@pytest.fixture
def local_host():
    """Return a localhost configuration for testing without SSH."""
    return HostConfig(name="local", target="localhost", tags=["local"], env={})


@pytest.fixture
def sample_repo():
    """Return a sample repository configuration."""
    return RepoConfig(
        name="test-repo",
        url="https://github.com/example/test-repo.git",
        base="main",
        anchor_subdir=None,
    )


@pytest.fixture
def sample_repo_with_subdir():
    """Return a sample repository with anchor_subdir."""
    return RepoConfig(
        name="monorepo",
        url="https://github.com/example/monorepo.git",
        base="develop",
        anchor_subdir="packages/core",
    )


@pytest.fixture
def sample_feature():
    """Return a sample feature configuration."""
    return FeatureConfig(
        name="test-feature",
        base="main",
        repos=[
            FeatureRepoAttachment(
                repo="test-repo", hosts=["test-host"], subdir=None
            )
        ],
    )


@pytest.fixture
def sample_feature_multi_host():
    """Return a feature with multiple hosts."""
    return FeatureConfig(
        name="multi-host-feature",
        base="develop",
        repos=[
            FeatureRepoAttachment(
                repo="test-repo", hosts=["host1", "host2", "host3"], subdir=None
            ),
            FeatureRepoAttachment(
                repo="another-repo", hosts=["host1"], subdir="src"
            ),
        ],
    )
