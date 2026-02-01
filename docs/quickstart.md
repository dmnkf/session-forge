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

## 3. Register repos (and optional remote hosts)

```bash
sf repo add core git@github.com:org/core.git --base main
# sf host add gpu-01 ubuntu@gpu-01
```

`sf init` creates a default `local` host targeting `localhost`. Use `sf host add` when you need remote hosts.

## 4. Bootstrap host capabilities

```bash
sf bootstrap --hosts local
```

This checks for `git` (and optionally `hapi`). Missing tools are surfaced with suggestions.

## 5. Create the first feature

```bash
sf feature new payments --base main
sf attach payments core
```

Attachments map repos to the hosts that should host their worktrees for the feature branch. Use `--hosts gpu-01` to target a remote host.

## 6. Sync anchors and worktrees

```bash
sf sync payments
```

This creates/updates the anchor clone (`repo-cache/<repo>.anchor`), refreshes branch `feat/payments`, and ensures a git worktree at `features/payments/<repo>` on every host.

## 7. Start HAPI in the worktree

```bash
sf hapi start payments core
sf hapi start payments core --execute
```

HAPI runs in `features/payments/core` and exposes mobile control for the session.

## 8. Check status and teardown

```bash
sf worktree list payments
sf feature destroy payments --yes
```

`sf worktree list` helps you confirm paths across hosts. `sf feature destroy` removes worktrees, deletes the feature branch, and cleans up the feature definition file.

## What's next?

- `sf doctor` summarizes local state.
- `sf worktree list payments` shows worktree paths when you want to open HAPI directly.
- Adjust worktree handling in `src/sf/core/git.py` if you need custom layouts.

## Local development with uv

```bash
uv sync --extra dev
uv run pytest
uv run black --check src tests
```

Happy forging! If you build something on top, open a PR or issue with your improvements.
