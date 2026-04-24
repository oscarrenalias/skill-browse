from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import Any

from urllib.parse import urlparse

import click

from . import authwall
from .config import Config, ConfigError, load, save_account_email
from .runner import AgentBrowserError, Runner


def _emit(data: dict[str, Any], as_json: bool = True) -> None:
    click.echo(json.dumps(data))


def _load_config(email_override: str | None = None) -> Config:
    try:
        return load(account_email=email_override)
    except ConfigError as e:
        raise click.ClickException(str(e))


@click.group()
def cli() -> None:
    """browse — authenticated-internal-site wrapper around agent-browser."""


@cli.command("login")
@click.argument("url")
@click.option("--email", "email_override", default=None, help="AAD account email to cache for the picker.")
@click.option("--timeout", default=300, type=int, help="Max seconds to wait for sign-in to complete.")
def login_cmd(url: str, email_override: str | None, timeout: int) -> None:
    """Launch Edge headed to URL for interactive AAD sign-in.

    On first run, prompts for the account email used by `browse auth` to
    click through AAD's account picker. Caches it to ~/.config/browse/config.toml.
    """
    config = _load_config(email_override)
    if not config.account_email:
        email = click.prompt(
            "AAD account email for future headless calls (used to pick the right tile on AAD's account picker)"
        ).strip()
        save_account_email(email)
        config = load(account_email=email)

    runner = Runner(config)

    # Kill every agent-browser daemon before launching. Re-using a daemon that
    # was first launched in headless mode silently ignores a later --headed
    # request; closing one session isn't enough. Run the close invocation
    # without `--session` so agent-browser scopes it daemon-wide rather than
    # narrowing to one session. `browse login` is user-initiated interactive,
    # so clobbering other sessions is an acceptable tradeoff.
    subprocess.run(
        ["agent-browser", "close", "--all", "--json"],
        capture_output=True,
        text=True,
    )
    time.sleep(1)

    try:
        runner.run("open", url, headed=True)
    except AgentBrowserError as e:
        raise click.ClickException(str(e))

    target_host = urlparse(url).hostname or ""

    # Poll until we've settled on a page in the target host's tree (or timeout).
    # Staying on login hosts means sign-in is still in progress. Landing on
    # ntp.msn.com or similar interstitials means Edge hasn't begun the target
    # navigation yet — wait rather than declare success prematurely.
    #
    # Every call during this loop must pass headed=True: agent-browser quirk is
    # that a follow-up call without --headed spawns a fresh headless browser
    # against the same profile dir, which closes the user-visible window.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            runner.run("wait", "--load", "networkidle", headed=True)
        except AgentBrowserError:
            pass
        try:
            current = runner.run("get", "url", headed=True)
            title = runner.run("get", "title", headed=True)
        except AgentBrowserError as e:
            raise click.ClickException(str(e))

        current_url = current.get("url", "")
        current_title = title.get("title", "")
        current_host = authwall._host(current_url)
        on_login_host = current_host in authwall.LOGIN_HOSTS
        host_matches_target = bool(target_host) and (
            current_host == target_host
            or current_host.endswith("." + target_host)
            or target_host.endswith("." + current_host)
        )
        if not on_login_host and host_matches_target:
            # Persist the profile, then close the headed browser so subsequent
            # headless `browse auth` calls can take the profile lock. Without
            # this, Edge stays open and the next agent-browser invocation can't
            # open a fresh Chromium against the same user-data-dir.
            subprocess.run(
                ["agent-browser", "close", "--all", "--json"],
                capture_output=True,
                text=True,
            )
            _emit({
                "success": True,
                "url": current_url,
                "title": current_title,
                "account_email": config.account_email,
            })
            return
        time.sleep(2)

    raise click.ClickException(
        f"Timed out after {timeout}s still on a login host. "
        "The Edge window is still open — finish sign-in and re-run `browse auth <url>`."
    )


@cli.command("auth")
@click.argument("url")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["both", "snapshot", "text"]),
    default="both",
    help="Content format to include in the result.",
)
@click.option("--snapshot-mode", type=click.Choice(["interactive", "full", "compact"]), default="interactive")
@click.option("--max-hops", default=2, type=int, help="Max picker click-throughs before giving up.")
def auth_cmd(url: str, output_format: str, snapshot_mode: str, max_hops: int) -> None:
    """Headless authenticated fetch. Auto-handles AAD account picker.

    Emits JSON: {success, url, title, snapshot?, text?} on authenticated load,
    or {success: false, auth_required: true, login_hint: "..."} when interactive
    sign-in is needed.
    """
    config = _load_config()
    runner = Runner(config)

    try:
        runner.run("open", url)
    except AgentBrowserError as e:
        _emit({"success": False, "error": str(e), "stage": "open"})
        sys.exit(1)

    for _ in range(max_hops + 1):
        try:
            runner.run("wait", "--load", "networkidle")
        except AgentBrowserError:
            pass

        try:
            current_url = runner.run("get", "url").get("url", "")
            current_title = runner.run("get", "title").get("title", "")
        except AgentBrowserError as e:
            _emit({"success": False, "error": str(e), "stage": "probe"})
            sys.exit(1)

        snapshot_flag = {"interactive": "-i", "full": "", "compact": "-c"}[snapshot_mode]
        snap_args = ["snapshot"]
        if snapshot_flag:
            snap_args.append(snapshot_flag)
        try:
            snapshot_data = runner.run(*snap_args)
        except AgentBrowserError:
            snapshot_data = {}
        snapshot_text = str(snapshot_data.get("snapshot") or snapshot_data or "")

        state = authwall.classify(current_url, current_title, snapshot_text, config.account_email)

        if state.is_clear:
            result: dict[str, Any] = {
                "success": True,
                "url": current_url,
                "title": current_title,
            }
            if output_format in ("both", "snapshot"):
                result["snapshot"] = snapshot_text
            if output_format in ("both", "text"):
                try:
                    text_data = runner.run("get", "text", "body")
                    result["text"] = text_data.get("text", "")
                except AgentBrowserError:
                    result["text"] = ""
            _emit(result)
            return

        if state.needs_interactive:
            _emit({
                "success": False,
                "auth_required": True,
                "login_hint": f"browse login {url}",
                "url": current_url,
                "title": current_title,
            })
            sys.exit(2)

        # state.kind == "picker" and state.picker_ref is set
        try:
            runner.run("click", f"@{state.picker_ref}")
        except AgentBrowserError as e:
            _emit({"success": False, "error": str(e), "stage": "picker-click"})
            sys.exit(1)
        # loop continues to re-probe

    _emit({
        "success": False,
        "auth_required": True,
        "login_hint": f"browse login {url}",
        "error": f"exceeded {max_hops} picker click-throughs without landing on target",
    })
    sys.exit(2)


@cli.command("close")
def close_cmd() -> None:
    """Close the browse session."""
    config = _load_config()
    runner = Runner(config)
    try:
        data = runner.run("close", with_session_context=False)
    except AgentBrowserError as e:
        _emit({"success": False, "error": str(e)})
        sys.exit(1)
    _emit({"success": True, **data})


@cli.command("status")
def status_cmd() -> None:
    """Show session + config state."""
    config = _load_config()
    result = {
        "browser_path": str(config.browser_path),
        "profile_dir": str(config.profile_dir),
        "session_name": config.session_name,
        "account_email": config.account_email,
        "profile_exists": config.profile_dir.exists(),
    }
    _emit({"success": True, **result})


if __name__ == "__main__":
    cli()
