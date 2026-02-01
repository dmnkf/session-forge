---
name: session-forge
description: Worktree orchestration and project setup with the Session Forge (sf) CLI. Use when registering hosts and repos, creating multi-repo features, syncing worktrees across hosts, listing worktree paths, or handing off to HAPI for mobile sessions.
---

# Session Forge (sf)

## Quick workflow
1. Install: `uv tool install session-forge`
2. Initialize: `sf init`
3. Register repo: `sf repo add <name> <git-url> --base <branch> [--anchor-subdir <path>]`
4. Add remote host when needed: `sf host add <name> <user@host>`
5. Create feature: `sf feature new <feature> --base <branch>`
6. Attach repos: `sf attach <feature> <repo> [--hosts host1,host2] [--subdir <path>]`
7. Sync worktrees: `sf sync <feature>`
8. Start HAPI: `sf hapi start <feature> <repo> [--host <host>] [--execute]`
9. Inspect paths: `sf worktree list <feature>`
10. Tear down: `sf feature destroy <feature> --yes`

`sf init` creates a default `local` host pointing to `localhost`, so `sf attach` works without `--hosts` for local-only use.

## Layout
- Anchor clones: `repo-cache/<repo>.anchor`
- Worktrees: `features/<feature>/<repo>`
- Feature root: `features/<feature>`

## Multi-repo features
- Attach each repo: `sf attach <feature> <repo> [--hosts ...]`
- Run `sf sync <feature>` once to fan out all repos.
- Use `sf worktree list <feature>` to confirm repo paths per host.

## HAPI handoff
- Print the SSH command: `sf hapi start <feature> <repo>`
- Execute it immediately: `sf hapi start <feature> <repo> --execute`
- Cross-repo session at feature root: `ssh <host> "cd ~/features/<feature> && hapi"`

## One-shot setup
- `sf up --host name=user@host --repo name=url --feature name` to create config and sync in one step.

## State
- Config: `~/.sf/config.yml`
- Features: `~/.sf/features/<feature>.yml`
- Override root with `SF_STATE_DIR`

## Diagnostics
- `sf bootstrap --hosts ... [--no-hapi]`
- `sf doctor`
- `sf quickstart`
