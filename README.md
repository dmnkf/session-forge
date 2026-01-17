# Session Forge (sf)

Session Forge orchestrates LLM-assisted development sessions across fleets of machines. It combines SSH, git worktrees, and tmux automation into a single CLI (`sf`) plus an optional FastAPI server. With a five-minute onboarding flow, you can install the CLI, bootstrap your hosts, sync worktrees, and launch sessions either directly or via HAPI for mobile control.

## Highlights

- **Idempotent orchestration** – anchors repos on remote hosts, keeps feature branches in sync, and reuses git worktrees safely.
- **Multi-host fanout** – define hosts once and attach repos to features; `sf sync` fans out the same feature branch everywhere.
- **tmux session control** – start, list, and stop LLM sessions named `feat:<feature>:<repo>:<llm>` with automatic cwd resolution.
- **Prompt delivery** – build context from remote globs plus local prompt files, enforce byte caps, and paste via `tmux load-buffer`.
- **HAPI handoff** – keep SF for worktree orchestration and optionally run HAPI for mobile session control and approvals.
- **FastAPI server** – run `sf serve` for HTTP control (`/sync`, `/sessions`, `/prompt`) or embed the orchestration library in other tools.

## Installation

```bash
uv tool install session-forge
# or, from source
git clone https://github.com/you/session-forge.git
cd session-forge
uv sync --extra server
uv run sf --help
```

Need the FastAPI server or developer tooling? Sync extras during install:

```bash
uv sync --extra server --extra dev
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

# 5. launch a session
# Option A: tmux-backed session (built-in)
sf session start demo core --llm claude

# Option B: start HAPI inside the worktree for mobile control
sf hapi start demo core  # prints SSH command
sf hapi start demo core --execute

# 6. send context to the session
touch prompt.txt  # optional custom prompt
sf prompt demo core --prompt-file prompt.txt --include 'README.md'
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
| `sf session start <feature> <repo> --llm <claude|codex>` | Launch tmux-backed LLM CLI |
| `sf hapi start <feature> <repo>` | Print SSH command to start HAPI in worktree |
| `sf prompt <feature> <repo>` | Build and send prompt payload to the tmux session |
| `sf session status` | List tmux sessions per host |
| `sf feature destroy <feature> --yes` | Remove worktrees and delete the feature |
| `sf bootstrap --hosts ...` | Check git/tmux/LLM CLIs on hosts (and HAPI) |
| `sf doctor` | Display local state summary |
| `sf serve` | Run the optional FastAPI service |

## Server mode

```bash
sf serve --host 0.0.0.0 --port 8765
```

Endpoints (JSON):

- `GET /healthz` – liveness probe
- `POST /sync` – body `{ "feature": "demo", "repo": "core" }`
- `POST /sessions/start` – start tmux sessions
- `POST /sessions/stop` – stop sessions
- `POST /prompt` – send prompts (same payload as CLI options)

## Development

```bash
uv sync --extra dev --extra server
uv run pytest
uv run black --check src tests
```

Makefile recipes delegate to `uv` (`make dev`, `make lint`, `make test`).

## Deployment with uv

Publish packages directly from uv:

```bash
uv build
uv publish
```

Build and run the FastAPI container image:

```bash
docker build -t session-forge-api .
docker run -p 8765:8765 session-forge-api
```

## License

Apache License 2.0
