"""Tests for service runtime support."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sf.core.orchestrator import OrchestratorError, _guard
from sf.core.runtime import (
    RUNTIME_BUILDERS,
    ServiceRuntime,
    _docker_compose_cmd,
    _podman_compose_cmd,
    _script_cmd,
)
from sf.core.ssh import SshExecutor
from sf.models import FeatureRepoAttachment, ServiceConfig, compute_port_offset


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


def test_service_config_defaults():
    config = ServiceConfig()
    assert config.runtime == "docker_compose"
    assert config.file is None
    assert config.commands is None


def test_service_config_accepts_script_commands():
    config = ServiceConfig(runtime="script", commands={"up": "./scripts/up.sh"})
    assert config.runtime == "script"
    assert config.commands == {"up": "./scripts/up.sh"}


def test_service_config_rejects_non_dict_commands():
    with pytest.raises(ValidationError):
        ServiceConfig(commands=["up"])


def test_service_config_rejects_non_string_runtime():
    with pytest.raises(ValidationError):
        ServiceConfig(runtime=123)


def test_service_config_script_requires_commands():
    with pytest.raises(ValidationError, match="'script' runtime requires a 'commands' mapping"):
        ServiceConfig(runtime="script")


def test_feature_repo_attachment_migrates_compose_file_to_service():
    attachment = FeatureRepoAttachment(repo="r", hosts=["h"], compose_file="custom.yml")
    assert attachment.service is not None
    assert attachment.service.runtime == "docker_compose"
    assert attachment.service.file == "custom.yml"


def test_feature_repo_attachment_rejects_compose_file_and_service_conflict():
    with pytest.raises(ValidationError, match="Cannot specify both"):
        FeatureRepoAttachment(
            repo="r",
            hosts=["h"],
            compose_file="old.yml",
            service={"runtime": "docker_compose", "file": "new.yml"},
        )


@pytest.fixture
def runtime_setup(sample_host, sample_repo, sample_feature):
    ssh = SshExecutor(sample_host, dry_run=True)
    runtime = ServiceRuntime(ssh)
    attachment = sample_feature.repos[0]
    return runtime, sample_repo, sample_feature, attachment


def test_service_project_name(runtime_setup):
    runtime, repo, feature, _ = runtime_setup
    env = runtime._service_env(feature, repo)
    assert env["COMPOSE_PROJECT_NAME"] == f"sf-{feature.name}-{repo.name}"


def test_service_env_contains_expected_vars(runtime_setup):
    runtime, repo, feature, _ = runtime_setup
    env = runtime._service_env(feature, repo)
    assert "SF_PORT_OFFSET" in env
    assert "COMPOSE_PROJECT_NAME" in env
    assert env["SF_FEATURE"] == feature.name
    assert env["SF_REPO"] == repo.name


def test_runtime_up_dry_run(runtime_setup):
    runtime, repo, feature, attachment = runtime_setup
    result = runtime.up(repo, feature, attachment, "features/test/repo")
    assert result.exit_code == 0


def test_runtime_down_dry_run(runtime_setup):
    runtime, repo, feature, attachment = runtime_setup
    result = runtime.down(repo, feature, attachment, "features/test/repo")
    assert result.exit_code == 0


def test_runtime_ps_dry_run(runtime_setup):
    runtime, repo, feature, attachment = runtime_setup
    result = runtime.ps(repo, feature, attachment, "features/test/repo")
    assert result.exit_code == 0


def test_runtime_build_command_with_file(runtime_setup):
    runtime, _, _, _ = runtime_setup
    attachment = FeatureRepoAttachment(repo="r", hosts=["h"], service=ServiceConfig(file="custom.yml"))
    cmd = runtime._build_command("up", attachment)
    assert "-f" in cmd
    assert "custom.yml" in cmd


def test_runtime_build_command_default_file(runtime_setup):
    runtime, _, _, attachment = runtime_setup
    cmd = runtime._build_command("up", attachment)
    assert "-f" not in cmd


def test_runtime_builders_registry():
    assert RUNTIME_BUILDERS["docker_compose"] is _docker_compose_cmd
    assert RUNTIME_BUILDERS["podman_compose"] is _podman_compose_cmd
    assert RUNTIME_BUILDERS["script"] is _script_cmd


def test_podman_command_builder():
    config = ServiceConfig(runtime="podman_compose", file="podman.yml")
    cmd = _podman_compose_cmd("up", config, "-d")
    assert cmd == "podman compose -f podman.yml up -d"


def test_script_command_builder():
    config = ServiceConfig(runtime="script", commands={"up": "./scripts/up.sh"})
    cmd = _script_cmd("up", config, "-d")
    assert cmd == "./scripts/up.sh"


def test_script_command_builder_missing_action_raises():
    config = ServiceConfig(runtime="script", commands={"up": "./scripts/up.sh"})
    with pytest.raises(ValueError, match="Missing script command for action 'down'"):
        _script_cmd("down", config, "")


def test_unknown_runtime_raises(runtime_setup):
    runtime, _, _, _ = runtime_setup
    attachment = FeatureRepoAttachment(
        repo="r", hosts=["h"], service=ServiceConfig(runtime="nope")
    )
    with pytest.raises(ValueError, match="Unknown service runtime 'nope'"):
        runtime._build_command("up", attachment)


def test_docker_compose_cmd_without_extra():
    config = ServiceConfig()
    cmd = _docker_compose_cmd("ps", config, "")
    assert cmd == "docker compose ps"


def test_podman_compose_cmd_without_file():
    config = ServiceConfig(runtime="podman_compose")
    cmd = _podman_compose_cmd("down", config, "-v")
    assert cmd == "podman compose down -v"


def test_migration_drops_null_compose_file():
    attachment = FeatureRepoAttachment(repo="r", hosts=["h"], compose_file=None)
    assert attachment.service is None


def test_guard_wraps_value_error_as_orchestrator_error():
    with pytest.raises(OrchestratorError, match="Unknown service runtime 'bogus'"):
        _guard(lambda: (_ for _ in ()).throw(ValueError("Unknown service runtime 'bogus'")))
