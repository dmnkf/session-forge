"""Tests for SSH executor functionality."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from sf.core.ssh import CommandResult, SshExecutor
from sf.models import HostConfig


def test_command_result_check_success():
    """Test CommandResult.check() with successful command."""
    result = CommandResult(exit_code=0, stdout="output", stderr="")
    assert result.check() == result


def test_command_result_check_failure():
    """Test CommandResult.check() with failed command."""
    result = CommandResult(exit_code=1, stdout="", stderr="error")
    with pytest.raises(Exception):
        result.check()


def test_ssh_executor_init(sample_host):
    """Test SshExecutor initialization."""
    executor = SshExecutor(sample_host)
    assert executor.host == sample_host
    assert executor.dry_run is False


def test_ssh_executor_dry_run_mode(sample_host):
    """Test SshExecutor in dry-run mode."""
    executor = SshExecutor(sample_host, dry_run=True)
    result = executor.run("ls -la")
    assert result.exit_code == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_ssh_executor_local_target():
    """Test SshExecutor with localhost target uses local shell."""
    local = HostConfig(name="local", target="localhost", tags=[], env={})
    executor = SshExecutor(local)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout=b"output", stderr=b"")
        executor.run("echo test")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "sh"
        assert args[1] == "-lc"


def test_ssh_executor_remote_target(sample_host):
    """Test SshExecutor with remote target uses SSH."""
    executor = SshExecutor(sample_host)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout=b"output", stderr=b"")
        executor.run("echo test")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "ssh" in args
        assert "-o" in args
        assert "BatchMode=yes" in args
        assert sample_host.target in args


def test_ssh_executor_with_cwd(sample_host):
    """Test SshExecutor command with working directory."""
    executor = SshExecutor(sample_host)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout=b"", stderr=b"")
        executor.run("ls", cwd="/tmp")

        command_str = mock_run.call_args[0][0][-1]
        assert "cd /tmp" in command_str


def test_ssh_executor_with_env(sample_host):
    """Test SshExecutor command with environment variables."""
    executor = SshExecutor(sample_host)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout=b"", stderr=b"")
        executor.run("echo $VAR", env={"VAR": "value"})

        command_str = mock_run.call_args[0][0][-1]
        assert "export VAR=value" in command_str


def test_ssh_executor_push_file(sample_host, tmp_path):
    """Test SshExecutor file push via SCP."""
    executor = SshExecutor(sample_host)
    local_file = tmp_path / "file.txt"
    local_file.write_text("payload")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout=b"", stderr=b"")
        executor.push_file(local_file, "/remote/file.txt")

        assert mock_run.call_count == 2
        args = mock_run.call_args_list[1][0][0]
        assert "scp" in args
        assert str(local_file) in args
        assert f"{sample_host.target}:/remote/file.txt" in args


def test_ssh_executor_push_file_localhost(tmp_path):
    """Test SshExecutor file push to localhost uses local copy."""
    local = HostConfig(name="local", target="localhost", tags=[], env={})
    executor = SshExecutor(local)
    local_file = tmp_path / "file.txt"
    local_file.write_text("payload")

    destination = tmp_path / "out" / "file.txt"
    executor.push_file(local_file, str(destination))
    assert destination.read_text() == "payload"


def test_ssh_executor_check_false(sample_host):
    """Test SshExecutor with check=False doesn't raise on failure."""
    executor = SshExecutor(sample_host)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="error")
        result = executor.run("false", check=False)

        assert result.exit_code == 1
        assert result.stderr == "error"


def test_ssh_executor_host_env_merged(sample_host):
    """Test that host environment variables are included in commands."""
    executor = SshExecutor(sample_host)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        executor.run("echo test")

        command_str = mock_run.call_args[0][0][-1]
        assert "export ENV_VAR=value" in command_str
