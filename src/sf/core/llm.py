"""LLM command adapters."""

from __future__ import annotations

from typing import Dict

DEFAULT_COMMANDS: Dict[str, str] = {
    "claude": "claude --chat",
    "codex": "codex --chat",
}


def resolve_command(llm: str) -> str:
    """Return the shell command that should run in tmux for the given LLM."""

    try:
        return DEFAULT_COMMANDS[llm]
    except KeyError as exc:  # pragma: no cover - validated in CLI layer
        raise ValueError(
            f"Unknown llm '{llm}'. Known: {', '.join(sorted(DEFAULT_COMMANDS))}"
        ) from exc


__all__ = ["resolve_command", "DEFAULT_COMMANDS"]
