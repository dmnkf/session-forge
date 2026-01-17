# Session Forge (sf)

Session Forge orchestrates LLM-assisted development sessions across fleets of machines. It combines SSH automation, git worktrees, and project metadata into a single CLI (`sf`) that prepares workspaces for tools like [HAPI](https://github.com/tiann/hapi). With a five-minute onboarding flow, you can install the CLI, bootstrap your hosts, sync worktrees, and then hand off sessions to HAPI for mobile control.

## Highlights

- **Idempotent orchestration** – anchors repos on remote hosts, keeps feature branches in sync, and reuses git worktrees safely.
- **Multi-host fanout** – define hosts once and attach repos to features; `sf sync` fans out the same feature branch everywhere.
- **Project overview** – inspect host, repo, and feature mapping to keep fleets aligned.
- **HAPI handoff** – use SF to prepare worktrees, then run HAPI for mobile session control and approvals.

## Project view (feature = workspace)

A feature in Session Forge is a project workspace that can span multiple repositories. `sf attach` binds repos to a feature, and `sf sync` lays them out under a shared directory on each host.

```mermaid
flowchart LR
    SF[Session Forge] -->|sf attach/sync| Host
    subgraph Host[gpu-01]
        direction TB
        Cache[repo-cache/*.anchor]
        Feature[features/payments]
        Feature --> Core[core (worktree)]
        Feature --> Web[web (worktree)]
        Feature --> Infra[infra (worktree)]
    end
    HAPI[HAPI mobile UI] -->|run in worktree| Core
    HAPI -->|run at feature root| Feature
```

```text
host: gpu-01
├─ repo-cache/
│  ├─ core.anchor/
│  └─ web.anchor/
└─ features/
   └─ payments/
      ├─ core/   (worktree, feat/payments)
      ├─ web/    (worktree, feat/payments)
      └─ infra/  (worktree, feat/payments)
```

That `features/<feature>` directory is the shared workspace. Start HAPI at a repo worktree or at the feature root if you want a cross‑repo session (or hop between repos in the same directory).

```bash
sf hapi start payments core
ssh ubuntu@gpu-01 'cd ~/features/payments && hapi'
```

## Installation

```bash
uv tool install session-forge
# or, from source
git clone https://github.com/you/session-forge.git
cd session-forge
uv sync
uv run sf --help
```

Publishing to PyPI is automated on git tags (see "Release" below).

Need developer tooling? Sync extras during install:

```bash
uv sync --extra dev
```

## Five-minute quickstart

```bash
# 1. install
uv tool install session-forge

# 2. initialize local state and register a host + repo
sf init
sf host add a100-01 ubuntu@a100-01
sf repo add core git@github.com:org/core.git --base main

# 3. verify host capabilities
sf bootstrap --hosts a100-01

# 4. create a feature, attach repos, sync
sf feature new demo --base main
sf attach demo core --hosts a100-01
sf sync demo

# 5. launch HAPI for mobile control
sf hapi start demo core  # prints SSH command
sf hapi start demo core --execute

# 6. verify worktree paths when needed
sf worktree list demo
```

## CLI reference (MVP)

| Command | Description |
| --- | --- |
| `sf init` | Initialize `~/.sf` state directory and config |
| `sf host add <name> <user@host>` | Register an SSH target |
| `sf repo add <name> <git-url>` | Register a git repo and base branch |
| `sf feature new <feature>` | Create a feature definition |
| `sf attach <feature> <repo> --hosts ...` | Attach a repo to a feature on specific hosts |
| `sf sync <feature>` | Ensure anchor clone, feature branch, and worktrees exist on each host |
| `sf worktree list <feature>` | Show worktree paths per host |
| `sf hapi start <feature> <repo>` | Print SSH command to start HAPI in repo worktree |
| `sf feature destroy <feature> --yes` | Remove worktrees and delete the feature |
| `sf bootstrap --hosts ...` | Check git (and optional HAPI) on hosts |
| `sf doctor` | Display local state summary |

## Development

```bash
uv sync --extra dev
uv run pytest
uv run black --check src tests
```

Makefile recipes delegate to `uv` (`make dev`, `make lint`, `make test`).

## Release

Publish happens automatically when you push a version tag (PyPI trusted publishing):

```bash
git tag v0.1.0
 git push origin v0.1.0
```

To publish manually:

```bash
uv build
uv publish
```

## HAPI integration

Session Forge focuses on project setup and worktree orchestration; HAPI provides the mobile session UI. After `sf sync`, start HAPI inside a repo worktree or the shared feature directory (use `sf worktree list` to locate paths).

## License

Apache License 2.0
