"""Session Forge CLI entrypoint."""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import typer
from rich.console import Console
from rich.table import Table

from sf import __version__
from sf.core.llm import resolve_command
from sf.core.orchestrator import (
    OrchestratorError,
)
from sf.core.orchestrator import destroy_feature as orchestrator_destroy_feature
from sf.core.orchestrator import send_prompt as orchestrator_send_prompt
from sf.core.orchestrator import start_session as orchestrator_start_session
from sf.core.orchestrator import stop_session as orchestrator_stop_session
from sf.core.orchestrator import sync_feature as orchestrator_sync_feature
from sf.core.ssh import SshExecutor
from sf.core.state import StateStore, ensure_state_dirs
from sf.core.tmux import TmuxManager
from sf.models import FeatureConfig, FeatureRepoAttachment, HostConfig, RepoConfig

console = Console()
app = typer.Typer(help="Session Forge CLI (sf): manage remote LLM development sessions.")
host_app = typer.Typer(help="Manage known hosts")
repo_app = typer.Typer(help="Manage repositories")
feature_app = typer.Typer(help="Manage features")
session_app = typer.Typer(help="Manage LLM sessions")

app.add_typer(host_app, name="host")
app.add_typer(repo_app, name="repo")
app.add_typer(feature_app, name="feature")
app.add_typer(session_app, name="session")

state_store = StateStore()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def abort(message: str, code: int = 1) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code)


def parse_key_value(pairs: Iterable[str]) -> Dict[str, str]:
    output: Dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            abort(f"Expected key=value but got '{pair}'")
        key, value = pair.split("=", 1)
        output[key.strip()] = value.strip()
    return output


def ensure_feature_exists(feature: str) -> FeatureConfig:
    try:
        return state_store.load_feature(feature)
    except FileNotFoundError:
        abort(f"Feature '{feature}' has not been created. Run 'sf feature new {feature}'.")


def ensure_repo(config: RepoConfig | None, name: str) -> RepoConfig:
    if not config:
        abort(f"Repository '{name}' is not defined. Run 'sf repo add {name}'.")
    return config


def ensure_host(available: Dict[str, HostConfig], name: str) -> HostConfig:
    try:
        return available[name]
    except KeyError:
        abort(f"Host '{name}' is not defined. Run 'sf host add {name}'.")


# ---------------------------------------------------------------------------
# Root commands
# ---------------------------------------------------------------------------


@app.command()
def version() -> None:
    """Print the current Session Forge version."""

    console.print(f"Session Forge {__version__}")


@app.command()
def init(force: bool = typer.Option(False, "--force", help="Overwrite existing config")) -> None:
    """Initialize ~/.sf with default structure and empty config."""

    ensure_state_dirs()
    config_path = state_store.config_path
    if config_path.exists() and not force:
        abort("Config already exists. Pass --force to overwrite.")
    config_path.write_text("hosts: {}\nrepos: {}\n")
    features_dir = state_store.feature_path("dummy").parent
    features_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"Initialized Session Forge state at {config_path.parent}")


@app.command()
def up(
    host: str = typer.Option(..., "--host", help="Format: name=user@host"),
    repo: str = typer.Option(..., "--repo", help="Format: name=git-url"),
    feature: str = typer.Option(..., "--feature", help="Feature name to create or reuse"),
    llm: str = typer.Option("claude", "--llm", help="LLM command alias"),
    base: str = typer.Option("main", "--base", help="Feature base branch"),
    repo_base: Optional[str] = typer.Option(
        None, "--repo-base", help="Repository base branch", show_default=False
    ),
    prompt: bool = typer.Option(False, "--prompt", help="Send prompt after starting session"),
    prompt_file: Optional[Path] = typer.Option(
        None, "--prompt-file", help="Optional prompt file", show_default=False
    ),
    include: Optional[List[str]] = typer.Option(
        None, "--include", help="Glob pattern to include (repeatable)", show_default=False
    ),
    exclude: Optional[List[str]] = typer.Option(
        None, "--exclude", help="Glob pattern to exclude", show_default=False
    ),
    max_bytes: Optional[int] = typer.Option(
        None, "--max-bytes", help="Maximum prompt payload size", show_default=False
    ),
    accept_new_hostkeys: bool = typer.Option(
        False, "--accept-new-hostkeys", help="Set SF_ACCEPT_NEW_HOSTKEYS=1 for remote calls"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview remote operations"),
) -> None:
    """Bootstrap state, sync, and start an LLM session in one step."""

    def _parse_pair(flag: str, payload: str) -> tuple[str, str]:
        if "=" not in payload:
            abort(f"Expected {flag} in name=value format")
        name, value = payload.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name or not value:
            abort(f"Expected {flag} in name=value format")
        return name, value

    host_name, host_target = _parse_pair("--host", host)
    repo_name, repo_url = _parse_pair("--repo", repo)
    repo_branch = repo_base or base

    if accept_new_hostkeys:
        os.environ["SF_ACCEPT_NEW_HOSTKEYS"] = "1"

    ensure_state_dirs()
    config = state_store.load_config()

    if host_name in config.hosts:
        updated_host = config.hosts[host_name].model_copy(update={"target": host_target})
    else:
        updated_host = HostConfig(name=host_name, target=host_target)
    config.ensure_host(updated_host)

    if repo_name in config.repos:
        existing_repo = config.repos[repo_name]
        updated_repo = existing_repo.model_copy(update={"url": repo_url, "base": repo_branch})
    else:
        updated_repo = RepoConfig(name=repo_name, url=repo_url, base=repo_branch)
    config.ensure_repo(updated_repo)
    state_store.save_config(config)

    feature_cfg = state_store.load_feature(feature, required=False)
    if feature_cfg is None:
        feature_cfg = FeatureConfig(name=feature, base=base, repos=[])
    else:
        if feature_cfg.base != base:
            feature_cfg.base = base
    attachment = feature_cfg.get_attachment(repo_name)
    if attachment:
        if host_name not in attachment.hosts:
            attachment.hosts.append(host_name)
    else:
        feature_cfg.repos.append(FeatureRepoAttachment(repo=repo_name, hosts=[host_name]))
    state_store.save_feature(feature_cfg)

    try:
        sync_summary = orchestrator_sync_feature(feature, repo=repo_name, dry_run=dry_run)
        for item in sync_summary:
            console.print(
                f"Synced [bold]{item['repo']}[/bold] on [bold]{item['host']}[/bold] -> {item['worktree']}"
            )
        session_info = orchestrator_start_session(
            feature,
            repo_name,
            llm=llm,
            host=host_name,
            dry_run=dry_run,
        )
        console.print(
            f"Session [bold]{session_info['session']}[/bold] ready on {session_info['host']} (cwd={session_info['cwd']})"
        )
        should_prompt = (
            prompt
            or prompt_file is not None
            or include is not None
            or exclude is not None
            or max_bytes is not None
        )
        if should_prompt and not dry_run:
            orchestrator_send_prompt(
                feature,
                repo_name,
                llm=llm,
                prompt_file=prompt_file,
                include=include,
                exclude=exclude,
                max_bytes=max_bytes,
                host=host_name,
            )
            console.print("Prompt delivered to LLM session")
        elif should_prompt and dry_run:
            console.print("[yellow]Skipping prompt delivery due to --dry-run[/yellow]")
    except OrchestratorError as exc:
        abort(str(exc))


# ---------------------------------------------------------------------------
# Host commands
# ---------------------------------------------------------------------------


@host_app.command("add")
def host_add(
    name: str = typer.Argument(..., help="Logical host name"),
    target: str = typer.Argument(..., help="ssh target: user@host"),
    tag: List[str] = typer.Option(None, "--tag", help="Tag for grouping", show_default=False),
    env: List[str] = typer.Option(
        None, "--env", help="Environment variable KEY=VALUE", show_default=False
    ),
) -> None:
    config = state_store.load_config()
    host = HostConfig(name=name, target=target, tags=tag or [], env=parse_key_value(env or []))
    config.ensure_host(host)
    state_store.save_config(config)
    console.print(f"Saved host [bold]{name}[/bold] -> {target}")


@host_app.command("list")
def host_list() -> None:
    config = state_store.load_config()
    table = Table(title="Hosts")
    table.add_column("Name")
    table.add_column("Target")
    table.add_column("Tags")
    table.add_column("Env")
    for host in config.hosts.values():
        table.add_row(host.name, host.target, ",".join(host.tags), json.dumps(host.env))
    console.print(table)


# ---------------------------------------------------------------------------
# Repo commands
# ---------------------------------------------------------------------------


@repo_app.command("add")
def repo_add(
    name: str = typer.Argument(..., help="Repo name"),
    url: str = typer.Argument(..., help="Git URL"),
    base: str = typer.Option("main", "--base", help="Default base branch"),
    anchor_subdir: Optional[str] = typer.Option(
        None, "--anchor-subdir", help="Subdir for LLM work"
    ),
) -> None:
    config = state_store.load_config()
    repo = RepoConfig(name=name, url=url, base=base, anchor_subdir=anchor_subdir)
    config.ensure_repo(repo)
    state_store.save_config(config)
    console.print(f"Saved repo [bold]{name}[/bold] -> {url}")


@repo_app.command("list")
def repo_list() -> None:
    config = state_store.load_config()
    table = Table(title="Repos")
    table.add_column("Name")
    table.add_column("URL")
    table.add_column("Base")
    table.add_column("Subdir")
    for repo in config.repos.values():
        table.add_row(repo.name, repo.url, repo.base, repo.anchor_subdir or "-")
    console.print(table)


# ---------------------------------------------------------------------------
# Feature commands
# ---------------------------------------------------------------------------


@feature_app.command("new")
def feature_new(
    name: str = typer.Argument(..., help="Feature name"),
    base: str = typer.Option("main", "--base", help="Base branch"),
) -> None:
    if state_store.feature_path(name).exists():
        abort(f"Feature '{name}' already exists")
    feature = FeatureConfig(name=name, base=base, repos=[])
    state_store.save_feature(feature)
    console.print(f"Created feature [bold]{name}[/bold] with base {base}")


@feature_app.command("list")
def feature_list() -> None:
    names = state_store.list_features()
    if not names:
        console.print("No features defined. Use 'sf feature new'.")
        return
    table = Table(title="Features")
    table.add_column("Name")
    table.add_column("Base")
    table.add_column("Repos")
    for name in names:
        feature = state_store.load_feature(name)
        repos = ", ".join(f"{att.repo}@{','.join(att.hosts)}" for att in feature.repos) or "-"
        table.add_row(feature.name, feature.base, repos)
    console.print(table)


@feature_app.command("attach")
def feature_attach(
    feature: str = typer.Argument(..., help="Feature name"),
    repo: str = typer.Argument(..., help="Repo name"),
    hosts: str = typer.Option(..., "--hosts", help="Comma-separated host names"),
    subdir: Optional[str] = typer.Option(None, "--subdir", help="Override working subdir"),
) -> None:
    config = state_store.load_config()
    feature_cfg = ensure_feature_exists(feature)
    repo_cfg = ensure_repo(config.repos.get(repo), repo)
    host_names = [name.strip() for name in hosts.split(",") if name.strip()]
    if not host_names:
        abort("--hosts must include at least one host name")
    for host_name in host_names:
        ensure_host(config.hosts, host_name)
    existing = feature_cfg.get_attachment(repo)
    attachment = FeatureRepoAttachment(repo=repo_cfg.name, hosts=host_names, subdir=subdir)
    if existing:
        feature_cfg.repos = [att if att.repo != repo else attachment for att in feature_cfg.repos]
    else:
        feature_cfg.repos.append(attachment)
    state_store.save_feature(feature_cfg)
    console.print(
        f"Attached repo [bold]{repo}[/bold] to feature [bold]{feature}[/bold] on hosts {', '.join(host_names)}"
    )


@feature_app.command("sync")
def feature_sync(
    feature: str = typer.Argument(..., help="Feature name"),
    repo: Optional[str] = typer.Option(None, "--repo", help="Limit to specific repo"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print commands without executing"),
) -> None:
    try:
        summary = orchestrator_sync_feature(feature, repo=repo, dry_run=dry_run)
    except OrchestratorError as exc:
        abort(str(exc))
    for item in summary:
        console.print(
            f"[cyan]Synced feature {feature} repo {item['repo']} on host {item['host']}[/cyan]\n"
            f" - worktree ready at {item['worktree']}"
        )


@feature_app.command("destroy")
def feature_destroy(
    feature: str = typer.Argument(..., help="Feature name"),
    yes: bool = typer.Option(False, "--yes", help="Confirm deletion"),
) -> None:
    if not yes:
        abort("Pass --yes to confirm destroying the feature")
    try:
        summary = orchestrator_destroy_feature(feature)
    except OrchestratorError as exc:
        abort(str(exc))
    for item in summary:
        console.print(f"Removed worktree for repo {item['repo']} on host {item['host']}")
    console.print(f"Destroyed feature [bold]{feature}[/bold]")


# ---------------------------------------------------------------------------
# Session commands
# ---------------------------------------------------------------------------


@session_app.command("start")
def session_start(
    feature: str = typer.Argument(..., help="Feature name"),
    repo: str = typer.Argument(..., help="Repo name"),
    llm: str = typer.Option("claude", "--llm", help="LLM adapter"),
    host: Optional[str] = typer.Option(None, "--host", help="Override host"),
    subdir: Optional[str] = typer.Option(None, "--subdir", help="Override subdir"),
    command: Optional[str] = typer.Option(None, "--command", help="Override command"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print commands without executing"),
) -> None:
    try:
        result = orchestrator_start_session(
            feature,
            repo,
            llm=llm,
            host=host,
            subdir=subdir,
            command=command,
            dry_run=dry_run,
        )
    except OrchestratorError as exc:
        abort(str(exc))
    console.print(
        f"Started session [bold]{result['session']}[/bold] on host {result['host']} (cwd={result['cwd']})"
    )


@session_app.command("stop")
def session_stop(
    feature: str = typer.Argument(..., help="Feature name"),
    repo: str = typer.Argument(..., help="Repo"),
    llm: str = typer.Option("claude", "--llm", help="LLM adapter"),
    host: Optional[str] = typer.Option(None, "--host", help="Host override"),
) -> None:
    try:
        result = orchestrator_stop_session(
            feature,
            repo,
            llm=llm,
            host=host,
        )
    except OrchestratorError as exc:
        abort(str(exc))
    console.print(f"Stopped session {result['session']} on {result['host']}")


@session_app.command("status")
def session_status() -> None:
    config = state_store.load_config()
    table = Table(title="Sessions")
    table.add_column("Host")
    table.add_column("Sessions")
    if not config.hosts:
        console.print("No hosts configured")
        return
    for host_cfg in config.hosts.values():
        ssh = SshExecutor(host_cfg, dry_run=False)
        tmux = TmuxManager(ssh)
        sessions = tmux.list_sessions()
        table.add_row(host_cfg.name, ", ".join(sessions) or "-")
    console.print(table)


@session_app.command("prompt")
def session_prompt(
    feature: str = typer.Argument(..., help="Feature name"),
    repo: str = typer.Argument(..., help="Repo name"),
    llm: str = typer.Option("claude", "--llm", help="LLM adapter"),
    host: Optional[str] = typer.Option(None, "--host", help="Target host"),
    prompt_file: Optional[Path] = typer.Option(None, "--prompt-file", help="Local prompt file"),
    include: List[str] = typer.Option(
        [], "--include", help="Remote glob to include", show_default=False
    ),
    exclude: List[str] = typer.Option(
        [], "--exclude", help="Remote glob exclude", show_default=False
    ),
    max_bytes: Optional[int] = typer.Option(None, "--max-bytes", help="Byte cap for context"),
) -> None:
    try:
        result = orchestrator_send_prompt(
            feature,
            repo,
            llm=llm,
            prompt_file=prompt_file,
            include=include,
            exclude=exclude,
            max_bytes=max_bytes,
            host=host,
        )
    except OrchestratorError as exc:
        abort(str(exc))
    console.print(
        f"Sent prompt ({result['bytes']} bytes) to session {result['session']} on {result['host']}"
    )


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


@app.command()
def bootstrap(
    hosts: str = typer.Option(..., "--hosts", help="Comma-separated host names"),
    llms: List[str] = typer.Option(["claude", "codex"], "--llm", help="LLM binaries to check"),
) -> None:
    config = state_store.load_config()
    host_names = [name.strip() for name in hosts.split(",") if name.strip()]
    if not host_names:
        abort("--hosts must include at least one host")
    for name in host_names:
        host_cfg = ensure_host(config.hosts, name)
        console.print(f"[cyan]Bootstrapping host {name} ({host_cfg.target})[/cyan]")
        ssh = SshExecutor(host_cfg)
        checks = {
            "git": "git --version",
            "tmux": "tmux -V",
        }
        for llm in llms:
            command = resolve_command(llm).split()[0]
            checks[f"{llm} cli"] = f"command -v {shlex.quote(command)}"
        for label, command in checks.items():
            result = ssh.run(command, check=False)
            if result.exit_code == 0:
                console.print(f" - [green]{label}[/green]: {result.stdout.strip() or 'ok'}")
            else:
                console.print(
                    f" - [red]{label} missing[/red]: {result.stderr.strip() or result.stdout.strip()}"
                )


@app.command()
def doctor() -> None:
    config = state_store.load_config()
    table = Table(title="Session Forge Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_row("Config path", str(state_store.config_path))
    table.add_row("Features", ", ".join(state_store.list_features()) or "-")
    table.add_row("Hosts", str(len(config.hosts)))
    table.add_row("Repos", str(len(config.repos)))
    console.print(table)


@app.command()
def quickstart() -> None:
    """Print the five-minute quickstart sequence."""

    steps = [
        "uv tool install session-forge",
        "sf init",
        "sf host add a100-01 ubuntu@a100-01",
        "sf repo add core git@github.com:org/core.git --base main",
        "sf bootstrap --hosts a100-01",
        "sf feature new demo --base main",
        "sf attach demo core --hosts a100-01",
        "sf sync demo",
        "sf session start demo core --llm claude",
        'sf prompt demo core --include "README.md"',
    ]
    console.print("[bold]Five-minute quickstart[/bold]")
    for idx, step in enumerate(steps, start=1):
        console.print(f" {idx}. {step}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(8765, "--port", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Enable autoreload"),
    log_level: str = typer.Option("info", "--log-level", help="uvicorn log level"),
) -> None:
    """Run the Session Forge FastAPI server."""

    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - runtime import
        abort(
            "uvicorn is not installed. Install the server extra with 'uv tool install \"session-"
            "forge[server]\"' or run 'uv sync --extra server'."
        )
    from sf.server.app import app as fastapi_app

    uvicorn.run(fastapi_app, host=host, port=port, reload=reload, log_level=log_level)


if __name__ == "__main__":  # pragma: no cover
    app()
