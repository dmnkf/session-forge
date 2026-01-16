# LLM adapters

Session Forge ships with lightweight command templates for two CLIs:

| Adapter | Command |
| --- | --- |
| `claude` | `claude --chat` |
| `codex` | `codex --chat` |

Adapters live in `src/sf/core/llm.py`. Update `DEFAULT_COMMANDS` to point at the binaries installed on your hosts:

```python
DEFAULT_COMMANDS = {
    "claude": "~/bin/claude --chat",
    "codex": "pipx run codex --chat",
    "gpt4": "openai chat"  # custom adapter
}
```

When you need advanced logic (flags, env vars, wrappers), override the command at runtime:

```bash
sf session start payments core --llm claude --command 'poetry run claude --chat'
```

The `sf bootstrap` command extracts the first token (binary name) from the adapter command and checks for its presence using `command -v`. Make sure the first token matches an executable present in the host PATH.
