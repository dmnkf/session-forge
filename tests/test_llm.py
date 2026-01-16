import pytest

from sf.core.llm import DEFAULT_COMMANDS, resolve_command


def test_default_commands_expose_claude():
    assert "claude" in DEFAULT_COMMANDS


def test_resolve_command_known():
    assert resolve_command("claude").startswith("claude")


def test_resolve_command_unknown():
    with pytest.raises(ValueError):
        resolve_command("unknown")
