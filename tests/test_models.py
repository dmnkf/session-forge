from pathlib import Path

from sf.models import FeatureConfig, FeatureRepoAttachment, SessionDescriptor


def test_session_descriptor_name():
    desc = SessionDescriptor(feature="demo", repo="core", llm="claude")
    assert desc.name == "feat:demo:core:claude"


def test_feature_attachment_lookup():
    feature = FeatureConfig(
        name="demo",
        base="main",
        repos=[FeatureRepoAttachment(repo="core", hosts=["host-a"], subdir=None)],
    )
    assert feature.get_attachment("core") is not None
    assert feature.get_attachment("missing") is None
