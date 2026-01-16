# Troubleshooting

## SSH timeouts

- Verify `ssh <target>` works without interaction (keys, host keys, agent).
- If you rely on proxies or jump hosts, configure them in `~/.ssh/config` and reuse the alias in `sf host add`.
- Commands run with `ssh -o BatchMode=yes` to avoid interactive hangs. For first-contact hosts, export `SF_ACCEPT_NEW_HOSTKEYS=1` when running `sf` to accept the fingerprint automatically, or trust the host key via plain `ssh` beforehand.

```bash
SF_ACCEPT_NEW_HOSTKEYS=1 sf bootstrap --hosts gpu-01
```

## git worktree conflicts

`sf sync` uses locks (`flock /tmp/sf.lock.<repo>`) to guard anchor and worktree operations, but you might still see git refusing to reset if there are local changes. Manually clean the directory:

```bash
ssh ubuntu@gpu-01 'cd ~/features/payments/core && git status'
```

Commit or stash changes, then rerun `sf sync payments`.

## tmux not installed

`sf bootstrap` surfaces missing binaries. Install tmux on Ubuntu:

```bash
sudo apt-get update && sudo apt-get install -y tmux
```

On macOS hosts, use `brew install tmux`.

## Prompt payload empty

Make sure the glob actually matches files on the remote worktree. Use `sf prompt ... --include 'src/**/*.py'` after running `sf sync`, or specify `--prompt-file` to seed content. The prompt builder truncates output according to `--max-bytes`.

## Server 500 errors

FastAPI wraps orchestration errors with HTTP 400 responses. Check the JSON body for the detailed message. For deeper debugging, run `sf serve --reload --log-level debug` and watch the console.
