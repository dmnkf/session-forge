from pathlib import Path

from sf.models import FeatureConfig, FeatureRepoAttachment, RepoConfig


def test_feature_attachment_lookup():
    feature = FeatureConfig(
        name="demo",
        base="main",
        repos=[FeatureRepoAttachment(repo="core", hosts=["host-a"], subdir=None)],
    )
    assert feature.get_attachment("core") is not None
    assert feature.get_attachment("missing") is None


def test_repo_session_root_uses_anchor_subdir():
    repo = RepoConfig(
        name="demo",
        url="https://example.com/demo.git",
        base="main",
        anchor_subdir="packages/core",
    )
    assert repo.session_root("features/demo/core") == "features/demo/core/packages/core"


def test_repo_session_root_without_anchor_subdir():
    repo = RepoConfig(
        name="demo",
        url="https://example.com/demo.git",
        base="main",
        anchor_subdir=None,
    )
    assert repo.session_root("features/demo/core") == "features/demo/core"
