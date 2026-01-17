# Recipes

Practical playbooks for Session Forge.

## Multi-repo feature fanout

```bash
sf feature new payments --base main
sf attach payments core --hosts gpu-01,gpu-02
sf attach payments web --hosts gpu-01
sf sync payments
```

`sf sync` will ensure both the `core` and `web` repositories have a `feat/payments` worktree on the requested hosts. Use `sf hapi start payments core --host gpu-01` to launch HAPI in the desired worktree.

## Read-only audit host

```bash
sf host add audit audit@bastion --tag audit --env SF_MODE=read-only
sf attach payments core --hosts gpu-01,audit
```

When the audit host is selected (e.g. `sf hapi start payments core --host audit`), your HAPI session inherits the `SF_MODE=read-only` environment variable.

## Teardown automation

Before deleting a feature branch or finishing a milestone, run:

```bash
sf worktree list payments
sf feature destroy payments --yes
```

Session Forge removes the worktrees, drops the `feat/payments` branch, and cleans up the YAML definition from `~/.sf/features/`.

## Release with uv

```bash
uv build
uv publish
```

Ship signed artifacts to PyPI with a single command. Add trusted publishing in your CI to avoid storing credentials locally.

