# Session Forge Quickstart

Welcome to the five-minute onboarding path for Session Forge (`sf`). This guide assumes you already have SSH access and keys configured for at least one remote host. Substitute hostnames, repo URLs, and LLM commands as needed.

## 1. Install the CLI

```bash
uv tool install session-forge
```

> Without a global install you can also run `uvx session-forge --help` for ad-hoc use.

## 2. Initialize local state

```bash
sf init
```

State files live under `~/.sf/` by default (config, features, logs). Override with the `SF_STATE_DIR` environment variable.

## 3. Register hosts and repos

```bash
sf host add gpu-01 ubuntu@gpu-01
sf repo add core git@github.com:org/core.git --base main
```

Use `--tag` and `--env KEY=VALUE` when you need metadata or extra environment variables for commands on the host.

## 4. Bootstrap host capabilities

```bash
sf bootstrap --hosts gpu-01
```

This checks for `git`, `tmux`, and the default LLM binaries (`claude`, `codex`). Missing tools are surfaced with suggestions.

## 5. Create the first feature

```bash
sf feature new payments --base main
sf attach payments core --hosts gpu-01
```

Attachments map repos to the hosts that should host their worktrees for the feature branch.

## 6. Sync anchors and worktrees

```bash
sf sync payments
```

This creates/updates the anchor clone (`repo-cache/<repo>.anchor`), refreshes branch `feat/payments`, and ensures a git worktree at `features/payments/<repo>` on every host.

## 7. Start an LLM session

```bash
sf session start payments core --llm claude
```

The session name is `feat:payments:core:claude`. Session Forge runs `tmux new -d -s feat:... -c features/payments/core "claude --chat"` on the host, creating an interactive shell you can attach with `tmux attach -t feat:payments:core:claude` via SSH.

## 8. Send a prompt with context

```bash
sf prompt payments core --include 'src/**/*.py' --include 'README.md'
```

The prompt builder resolves globs relative to the worktree, applies the optional byte cap, uploads the payload, and uses `tmux load-buffer` + `paste-buffer` to deliver it to the running LLM process.

## 9. Check status and teardown

```bash
sf session status
sf feature destroy payments --yes
```

`sf session status` lists active tmux sessions per host. `sf feature destroy` removes worktrees, deletes the feature branch, and cleans up the feature definition file.

## What's next?

- `sf doctor` summarizes local state.
- `sf serve` exposes the same orchestration via FastAPI (`/sync`, `/sessions`, `/prompt`).
- Customize LLM commands in `src/sf/core/llm.py` or add adapters.
- Extend prompt templates in `src/sf/core/prompt.py`.

## Local development with uv

```bash
uv sync --extra dev --extra server
uv run pytest
uv run black --check src tests
```

Happy forging! If you build something on top, open a PR or issue with your improvements.
