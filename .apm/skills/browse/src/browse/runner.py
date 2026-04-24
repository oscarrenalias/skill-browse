from __future__ import annotations

import json
import subprocess
from typing import Any

from .config import Config


class AgentBrowserError(Exception):
    """agent-browser reported a failure via its JSON `error` field."""

    def __init__(self, command: list[str], error: str):
        super().__init__(f"agent-browser {' '.join(command)}: {error}")
        self.command = command
        self.error = error


class Runner:
    """Invokes agent-browser with the session's browser/profile/session bound.

    Each instance represents a specific session. Commands are run as subprocess
    calls; agent-browser's daemon handles process reuse across calls.
    """

    def __init__(self, config: Config):
        self.config = config

    def _base_args(self, with_session_context: bool) -> list[str]:
        # --executable-path and --profile only matter on the first call that
        # launches the daemon; subsequent calls against the running session
        # ignore them. Passing them on every call is harmless and keeps the
        # wrapper stateless.
        if with_session_context:
            return [
                "agent-browser",
                "--executable-path", str(self.config.browser_path),
                "--profile", str(self.config.profile_dir),
                "--session", self.config.session_name,
            ]
        return ["agent-browser", "--session", self.config.session_name]

    def run(
        self,
        *command: str,
        headed: bool = False,
        with_session_context: bool = True,
        extra_flags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run an agent-browser subcommand. Returns the `data` dict on success."""
        args = self._base_args(with_session_context)
        if headed:
            args.append("--headed")
        if extra_flags:
            args.extend(extra_flags)
        args.extend(command)
        args.append("--json")

        proc = subprocess.run(args, capture_output=True, text=True)
        if proc.returncode != 0 and not proc.stdout:
            raise AgentBrowserError(
                list(command),
                proc.stderr.strip() or f"exit code {proc.returncode}",
            )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise AgentBrowserError(list(command), f"non-JSON output: {proc.stdout[:200]}") from e
        if not payload.get("success", False):
            raise AgentBrowserError(list(command), payload.get("error") or "unknown error")
        return payload.get("data") or {}

    def run_headed_streaming(self, *command: str) -> subprocess.Popen:
        """Start a headed agent-browser command without waiting for completion.

        Used for `browse login`, where we want the Edge window to stay open
        while the user signs in. Returns a Popen handle that the caller polls
        or waits on.
        """
        args = self._base_args(with_session_context=True)
        args.append("--headed")
        args.extend(command)
        args.append("--json")
        return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
