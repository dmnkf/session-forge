# Recipes

Practical playbooks for Session Forge.

## Multi-repo feature fanout

```bash
sf feature new payments --base main
sf attach payments core --hosts gpu-01,gpu-02
sf attach payments web --hosts gpu-01
sf sync payments
```

`sf sync` will ensure both the `core` and `web` repositories have a `feat/payments` worktree on the requested hosts. Run `sf session start payments core --llm claude` on GPU nodes and `sf session start payments web --llm codex --host gpu-01` for the frontend.

## Read-only audit host

```bash
sf host add audit audit@bastion --tag audit --env SF_MODE=read-only
sf attach payments core --hosts gpu-01,audit
```

When the audit host is selected (e.g. `sf session start payments core --host audit`), your tmux session inherits the `SF_MODE=read-only` environment variable. You can add logic in your prompt templates to detect and switch behavior.

## Teardown automation

Before deleting a feature branch or finishing a milestone, run:

```bash
sf session status
sf feature destroy payments --yes
```

Session Forge removes tmux sessions, deletes the worktrees, drops the `feat/payments` branch, and cleans up the YAML definition from `~/.sf/features/`.

## Release with uv

```bash
uv build
uv publish
```

Ship signed artifacts to PyPI with a single command. Add trusted publishing in your CI to avoid storing credentials locally.

## Build the API container

```bash
docker build -t session-forge-api .
docker run -p 8765:8765 session-forge-api
```

The Dockerfile uses the uv base image to reuse dependency caching and runs `uv run sf serve` as the entrypoint.
