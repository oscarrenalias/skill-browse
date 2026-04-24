from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

try:
    import tomli_w  # type: ignore
except ImportError:
    tomli_w = None


CONFIG_PATH = Path.home() / ".config" / "browse" / "config.toml"
DEFAULT_PROFILE_DIR = Path.home() / ".cache" / "browse" / "profile"
DEFAULT_SESSION_NAME = "browse"

EDGE_MACOS = Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")
CHROME_MACOS = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


@dataclass
class Config:
    browser_path: Path
    profile_dir: Path
    session_name: str
    account_email: str | None


class ConfigError(Exception):
    pass


def _resolve_browser_path(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.exists():
            raise ConfigError(f"BROWSE_BROWSER_PATH does not exist: {p}")
        return p
    env = os.environ.get("BROWSE_BROWSER_PATH")
    if env:
        p = Path(env).expanduser()
        if not p.exists():
            raise ConfigError(f"BROWSE_BROWSER_PATH does not exist: {p}")
        return p
    for candidate in (EDGE_MACOS, CHROME_MACOS):
        if candidate.exists():
            return candidate
    raise ConfigError(
        "No browser found. Install Microsoft Edge or Google Chrome, "
        "or set BROWSE_BROWSER_PATH."
    )


def _load_toml() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("rb") as f:
        return tomllib.load(f)


def load(
    browser_path: str | None = None,
    profile_dir: str | None = None,
    session_name: str | None = None,
    account_email: str | None = None,
) -> Config:
    """Resolve config. Precedence: explicit args > env > TOML > defaults."""
    toml = _load_toml()

    resolved_browser = _resolve_browser_path(browser_path)

    resolved_profile = (
        profile_dir
        or os.environ.get("BROWSE_PROFILE_DIR")
        or toml.get("profile_dir")
        or str(DEFAULT_PROFILE_DIR)
    )
    resolved_session = (
        session_name
        or os.environ.get("BROWSE_SESSION_NAME")
        or toml.get("session_name")
        or DEFAULT_SESSION_NAME
    )
    resolved_email = (
        account_email
        or os.environ.get("BROWSE_ACCOUNT_EMAIL")
        or toml.get("account_email")
    )

    return Config(
        browser_path=resolved_browser,
        profile_dir=Path(resolved_profile).expanduser(),
        session_name=resolved_session,
        account_email=resolved_email,
    )


def save_account_email(email: str) -> None:
    """Persist account_email to the TOML config. Creates parent dirs."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_toml()
    existing["account_email"] = email
    CONFIG_PATH.write_text(_render_toml(existing))


def _render_toml(data: dict) -> str:
    """Minimal TOML writer so we don't take a dep on tomli-w for one key."""
    lines = []
    for k, v in data.items():
        if isinstance(v, str):
            escaped = v.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{escaped}"')
        elif isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k} = {v}")
        else:
            raise ConfigError(f"Unsupported config value type for {k}: {type(v)}")
    return "\n".join(lines) + "\n"
