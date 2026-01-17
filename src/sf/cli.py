"""Session Forge CLI entrypoint."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from typing import Dict, Iterable, List

import typer
from rich.console import Console
from rich.table import Table

from sf import __version__
from sf.core.orchestrator import OrchestratorError
from sf.core.orchestrator import destroy_feature as orchestrator_destroy_feature
from sf.core.orchestrator import sync_feature as orchestrator_sync_feature
from sf.core.ssh import SshExecutor
from sf.core.state import StateStore, ensure_state_dirs
from sf.models import FeatureConfig, FeatureRepoAttachment, HostConfig, RepoConfig

console = Console()
app = typer.Typer(help="Session Forge CLI (sf): manage remote worktrees and project setup.")
host_app = typer.Typer(help="Manage known hosts")
repo_app = typer.Typer(help="Manage repositories")
feature_app = typer.Typer(help="Manage features")
worktree_app = typer.Typer(help="Inspect worktree locations")
hapi_app = typer.Typer(help="HAPI helpers")

app.add_typer(host_app, name="host")
app.add_typer(repo_app, name="repo")
app.add_typer(feature_app, name="feature")
app.add_typer(worktree_app, name="worktree")
app.add_typer(hapi_app, name="hapi")

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


def resolve_worktree_path(
    feature_cfg: FeatureConfig,
    repo_cfg: RepoConfig,
    attachment: FeatureRepoAttachment,
    *,
    extra_subdir: str | None = None,
) -> str:
    base_path = f"features/{feature_cfg.name}/{repo_cfg.name}"
    worktree_path = repo_cfg.session_root(base_path)
    if attachment.subdir:
        worktree_path = f"{worktree_path}/{attachment.subdir}"
    if extra_subdir:
        worktree_path = f"{worktree_path}/{extra_subdir}"
    return worktree_path


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
    base: str = typer.Option("main", "--base", help="Feature base branch"),
    repo_base: str | None = typer.Option(
        None, "--repo-base", help="Repository base branch", show_default=False
    ),
    accept_new_hostkeys: bool = typer.Option(
        False, "--accept-new-hostkeys", help="Set SF_ACCEPT_NEW_HOSTKEYS=1 for remote calls"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview remote operations"),
) -> None:
    """Bootstrap state, sync, and prepare the worktree in one step."""

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
    anchor_subdir: str | None = typer.Option(None, "--anchor-subdir", help="Subdir for LLM work"),
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
    subdir: str | None = typer.Option(None, "--subdir", help="Override working subdir"),
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
    repo: str | None = typer.Option(None, "--repo", help="Limit to specific repo"),
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
# Worktree + HAPI helpers
# ---------------------------------------------------------------------------


@worktree_app.command("list")
def worktree_list(feature: str = typer.Argument(..., help="Feature name")) -> None:
    config = state_store.load_config()
    feature_cfg = ensure_feature_exists(feature)
    table = Table(title=f"Worktrees for {feature}")
    table.add_column("Repo")
    table.add_column("Host")
    table.add_column("Path")
    for attachment in feature_cfg.repos:
        repo_cfg = ensure_repo(config.repos.get(attachment.repo), attachment.repo)
        worktree_path = resolve_worktree_path(feature_cfg, repo_cfg, attachment)
        for host_name in attachment.hosts:
            table.add_row(repo_cfg.name, host_name, worktree_path)
    console.print(table)


@hapi_app.command("start")
def hapi_start(
    feature: str = typer.Argument(..., help="Feature name"),
    repo: str = typer.Argument(..., help="Repo name"),
    host: str | None = typer.Option(None, "--host", help="Override host"),
    subdir: str | None = typer.Option(None, "--subdir", help="Append extra subdir"),
    execute: bool = typer.Option(False, "--execute", help="Run the SSH command directly"),
) -> None:
    config = state_store.load_config()
    feature_cfg = ensure_feature_exists(feature)
    attachment = feature_cfg.get_attachment(repo)
    if not attachment:
        abort(f"Repo '{repo}' is not attached to feature '{feature}'")
    if host:
        host_name = host
        if host_name not in attachment.hosts:
            abort(f"Host '{host_name}' is not attached to repo '{repo}'")
    else:
        host_name = attachment.hosts[0]
    host_cfg = ensure_host(config.hosts, host_name)
    repo_cfg = ensure_repo(config.repos.get(repo), repo)
    worktree_path = resolve_worktree_path(feature_cfg, repo_cfg, attachment, extra_subdir=subdir)
    remote_command = f"cd {shlex.quote(worktree_path)} && hapi"
    if host_cfg.target in {"local", "localhost"}:
        command_parts = ["sh", "-lc", remote_command]
    else:
        command_parts = ["ssh", host_cfg.target, "--", "sh", "-lc", remote_command]
    if execute:
        result = subprocess.run(command_parts, check=False)
        if result.returncode != 0:
            abort("Failed to start HAPI session")
        return
    console.print(shlex.join(command_parts))


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


@app.command()
def bootstrap(
    hosts: str = typer.Option(..., "--hosts", help="Comma-separated host names"),
    check_hapi: bool = typer.Option(True, "--hapi/--no-hapi", help="Check HAPI binary"),
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
        }
        if check_hapi:
            checks["hapi cli"] = "command -v hapi"
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
        "sf hapi start demo core",
        "sf worktree list demo",
    ]
    console.print("[bold]Five-minute quickstart[/bold]")
    for idx, step in enumerate(steps, start=1):
        console.print(f" {idx}. {step}")


if __name__ == "__main__":  # pragma: no cover
    app()
