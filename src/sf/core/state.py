"""State management for Session Forge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from rich.console import Console

from sf.models import STATE_ROOT, FeatureConfig, HostConfig, RepoConfig, SfConfig

console = Console()


def ensure_state_dirs(root: Path = STATE_ROOT) -> None:
    """Create the ~/.sf folder structure if it does not exist."""

    (root).mkdir(parents=True, exist_ok=True)
    (root / "features").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)


class StateStore:
    """Persistent configuration helper for both CLI and server modes."""

    def __init__(self, config_path: Optional[Path] = None, *, root: Optional[Path] = None) -> None:
        self.root = root or STATE_ROOT
        self.config_path = config_path or (self.root / "config.yml")
        self.features_dir = self.root / "features"
        self.log_dir = self.root / "logs"
        ensure_state_dirs(self.root)

    # ------------------------------------------------------------------
    # Config operations
    # ------------------------------------------------------------------
    def load_config(self) -> SfConfig:
        if not self.config_path.exists():
            return SfConfig()
        data = yaml.safe_load(self.config_path.read_text()) or {}
        hosts = {name: HostConfig(**payload) for name, payload in data.get("hosts", {}).items()}
        repos = {name: RepoConfig(**payload) for name, payload in data.get("repos", {}).items()}
        return SfConfig(hosts=hosts, repos=repos)

    def save_config(self, config: SfConfig) -> None:
        payload = {
            "hosts": {name: host.model_dump() for name, host in config.hosts.items()},
            "repos": {name: repo.model_dump() for name, repo in config.repos.items()},
        }
        self.config_path.write_text(yaml.safe_dump(payload, sort_keys=True))

    # ------------------------------------------------------------------
    # Feature operations
    # ------------------------------------------------------------------
    def feature_path(self, feature: str) -> Path:
        return self.features_dir / f"{feature}.yml"

    def list_features(self) -> List[str]:
        return sorted(path.stem for path in self.features_dir.glob("*.yml"))

    def load_feature(self, feature: str, *, required: bool = True) -> Optional[FeatureConfig]:
        path = self.feature_path(feature)
        if not path.exists():
            if required:
                raise FileNotFoundError(f"Feature '{feature}' has not been created yet")
            return None
        data = yaml.safe_load(path.read_text()) or {}
        return FeatureConfig(**data)

    def save_feature(self, feature: FeatureConfig) -> Path:
        path = self.feature_path(feature.name)
        path.write_text(yaml.safe_dump(feature.model_dump(), sort_keys=True))
        return path

    # ------------------------------------------------------------------
    # Debug helpers
    # ------------------------------------------------------------------
    def dump_state(self) -> Dict[str, object]:
        """Return a JSON-friendly snapshot of current state."""

        config = self.load_config()
        features: Dict[str, Dict[str, object]] = {}
        for name in self.list_features():
            feature = self.load_feature(name, required=False)
            if feature is not None:
                features[name] = feature.model_dump()
        snapshot = {
            "config": config.model_dump(),
            "features": features,
        }
        return snapshot

    def export_state(self, destination: Path) -> None:
        snapshot = self.dump_state()
        destination.write_text(json.dumps(snapshot, indent=2))
        console.print(f"Exported state to {destination}")


__all__ = ["StateStore", "ensure_state_dirs"]
