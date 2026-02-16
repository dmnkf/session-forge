import tempfile
from pathlib import Path

from sf.core.state import StateStore
from sf.models import FeatureConfig, FeatureRepoAttachment, HostConfig, RepoConfig


def test_state_store_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        store = StateStore(root=root)

        config = store.load_config()
        config.ensure_host(HostConfig(name="gpu-01", target="ubuntu@gpu-01"))
        config.ensure_repo(RepoConfig(name="core", url="git@example.com:core.git", base="main"))
        store.save_config(config)

        feature = FeatureConfig(
            name="demo",
            base="main",
            repos=[FeatureRepoAttachment(repo="core", hosts=["gpu-01"], subdir=None)],
        )
        store.save_feature(feature)

        reloaded = store.load_config()
        assert "gpu-01" in reloaded.hosts
        assert "core" in reloaded.repos

        loaded_feature = store.load_feature("demo")
        assert loaded_feature.name == "demo"
        assert loaded_feature.get_attachment("core").hosts == ["gpu-01"]

        snapshot = store.dump_state()
        assert "config" in snapshot
        assert "features" in snapshot
        assert "demo" in snapshot["features"]


def test_state_export_and_import_replace():
    with (
        tempfile.TemporaryDirectory() as source_tmp,
        tempfile.TemporaryDirectory() as target_tmp,
    ):
        source_store = StateStore(root=Path(source_tmp))
        config = source_store.load_config()
        config.ensure_host(HostConfig(name="gpu-01", target="ubuntu@gpu-01"))
        config.ensure_repo(RepoConfig(name="core", url="git@example.com:core.git", base="main"))
        source_store.save_config(config)
        source_store.save_feature(
            FeatureConfig(
                name="payments",
                base="main",
                repos=[FeatureRepoAttachment(repo="core", hosts=["gpu-01"], subdir=None)],
            )
        )

        export_path = Path(source_tmp) / "state.json"
        source_store.export_state(export_path)

        target_store = StateStore(root=Path(target_tmp))
        target_store.import_state(export_path, replace=True)

        imported_config = target_store.load_config()
        assert "gpu-01" in imported_config.hosts
        assert "core" in imported_config.repos
        imported_feature = target_store.load_feature("payments")
        assert imported_feature.get_attachment("core").hosts == ["gpu-01"]
