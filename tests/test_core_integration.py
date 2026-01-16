"""Integration tests for core components with correct API usage."""

from unittest.mock import Mock, patch

import pytest

from sf.core.git import GitManager
from sf.core.prompt import PromptBuilder
from sf.core.ssh import CommandResult, SshExecutor
from sf.core.tmux import TmuxManager
from sf.models import (
    FeatureConfig,
    HostConfig,
    PromptPlan,
    RepoConfig,
    SessionDescriptor,
)


@pytest.fixture
def sample_host():
    return HostConfig(name="test", target="test.example.com", tags=[], env={})


@pytest.fixture
def sample_repo():
    return RepoConfig(name="test-repo", url="https://github.com/test/repo.git", base="main")


@pytest.fixture
def sample_feature():
    return FeatureConfig(name="test-feature", base="main", repos=[])


@pytest.fixture
def mock_ssh():
    mock = Mock(spec=SshExecutor)
    mock.run.return_value = CommandResult(exit_code=0, stdout="", stderr="")
    return mock


def test_git_manager_uses_ssh(mock_ssh, sample_repo, sample_feature):
    """Test GitManager correctly calls SSH executor."""
    git = GitManager(mock_ssh)

    git.ensure_anchor(sample_repo)

    assert mock_ssh.run.called
    call_args = str(mock_ssh.run.call_args_list)
    assert "flock" in call_args


def test_tmux_manager_keyword_args(mock_ssh):
    """Test TmuxManager uses keyword arguments correctly."""
    tmux = TmuxManager(mock_ssh)
    session = SessionDescriptor(feature="test", repo="repo", llm="claude")

    tmux.start_session(session, cwd="/work/dir", command="claude --chat")

    mock_ssh.run.assert_called_once()
    call = str(mock_ssh.run.call_args)
    assert "tmux" in call


def test_prompt_builder_uses_plan(mock_ssh, tmp_path):
    """Test PromptBuilder uses PromptPlan correctly."""
    builder = PromptBuilder(mock_ssh)

    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("Test content")

    plan = PromptPlan(
        feature="test-feature",
        repo="test-repo",
        prompt_file=str(prompt_file),
        include=["*.md"],
        exclude=[],
        max_bytes=None,
    )

    mock_ssh.run.return_value = CommandResult(exit_code=0, stdout="", stderr="")

    result = builder.build("/work/dir", plan)

    assert "Test content" in result


def test_ssh_executor_dry_run(sample_host):
    """Test SshExecutor dry-run doesn't execute."""
    ssh = SshExecutor(sample_host, dry_run=True)

    result = ssh.run("echo test")

    assert result.exit_code == 0
    assert result.stdout == ""


def test_ssh_executor_localhost_bypass():
    """Test localhost uses local shell."""
    local_host = HostConfig(name="local", target="localhost", tags=[], env={})
    ssh = SshExecutor(local_host)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout=b"test", stderr=b"")
        ssh.run("echo test")

        args = mock_run.call_args[0][0]
        assert args[0] == "sh"
        assert "localhost" not in str(args)


def test_session_descriptor_name_format():
    """Test session name formatting."""
    session = SessionDescriptor(feature="payments", repo="core", llm="claude")
    assert session.name == "feat:payments:core:claude"


def test_command_result_check_raises_on_error():
    """Test CommandResult.check() raises on non-zero exit."""
    result = CommandResult(exit_code=1, stdout="", stderr="error message")

    with pytest.raises(Exception):
        result.check()


def test_command_result_check_passes_on_success():
    """Test CommandResult.check() returns self on success."""
    result = CommandResult(exit_code=0, stdout="output", stderr="")

    assert result.check() == result
    assert result.stdout == "output"
