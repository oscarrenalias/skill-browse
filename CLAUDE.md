# CLAUDE.md

Guidance for Claude Code sessions working **on** this codebase. If you're about to modify `src/browse/*`, read this first. How to *use* the CLI is in `SKILL.md`.

## What this project is

`browse` is a thin Python wrapper around `agent-browser` that binds managed-Edge launch flags and handles AAD's account picker. The hard work (browser automation, CDP, snapshots) is delegated to `agent-browser`. Keep it that way — don't reimplement browser logic here.

## Non-negotiable rules

- **Never commit `~/.config/browse/config.toml` or `~/.cache/browse/profile/`.** They contain session tokens and the user's account email. Both live outside the repo by design.
- **Never hardcode an email, tenant, domain, or org-specific hostname.** Account email is a runtime config value. `LOGIN_HOSTS` in `authwall.py` is generic AAD / Microsoft-SSO. If you want to add Okta / Google / other IdPs, do it through the same mechanism (named constants + a test fixture), not through org-specific special-cases.
- **Don't bypass the system-browser path.** `config._resolve_browser_path` must point at a system-installed Edge or Chrome. A bundled Chromium will break MDM-managed SSO for users on managed devices.
- **Every `authwall.classify` change needs a test.** The picker-detection heuristic is the core risk surface — wrong answer means silent hangs (clicking the wrong tile) or false "auth required" failures. New titles, new login hosts, new snapshot formats → new fixture + test case.

## Dev workflow

```bash
uv venv --python 3.11
uv pip install -e '.[dev]'
uv run pytest -q                          # < 1s, no network
uv run browse <cmd>                       # exercise the CLI
```

## Patterns to follow

- **`runner.Runner.run` is the only place that calls `agent-browser`.** All new commands go through it. Keep parsing + error handling centralized there.
- **`authwall.AuthState` has three kinds — `clear`, `picker`, `interactive`.** Don't add more without a plan; the caller logic branches exhaustively on these.
- **Click commands in `cli.py` are thin.** They orchestrate `runner` + `authwall` + `config`, they don't embed business logic.
- **Always emit JSON.** Human-readable output is not a supported contract. Every `_emit` call produces a `{"success": bool, ...}` object.
- **Config is pure data.** `config.load` never writes. Only `save_account_email` writes, and only to the TOML file.

## Adding a new agent-browser command wrapping

1. Call it via `Runner.run("<subcommand>", ...)`. Don't shell out directly.
2. Parse the returned `data` dict defensively — `agent-browser`'s response shapes are mostly stable but not documented as a contract.
3. Add a Click command in `cli.py` that emits the standard `{success, ...}` envelope.
4. If the flow introduces a new SSO state (post-MFA consent screen, new tenant picker variant, new IdP, etc.), extend `authwall` *with a test first*.

## Adding support for a new IdP (Okta, Google, etc.)

This is the most likely extension point. The AAD-only design is a starting point, not a ceiling.

1. Capture a real account-picker snapshot from the IdP (save as a fixture under `tests/fixtures/`).
2. Add the IdP's login hosts to `LOGIN_HOSTS` in `authwall.py`.
3. Add a parallel regex alongside `_PICKER_BUTTON_RE` for the IdP's picker phrasing.
4. Generalize `_find_picker_ref` to try each regex in turn.
5. Add tests for the new fixture.

## What NOT to add

- MCP server wrapping.
- Parallel/concurrent fetches — agent-browser is one-session-one-browser.
- Credential storage. If users want vaulted creds, use `agent-browser auth save/login` directly; we are not in that business.
- Readability / HTML-to-markdown extraction. `agent-browser snapshot` + `get text body` are what we return.
- Org-specific shortcuts (pre-baked URL lists, tenant IDs, etc.).

## Tests: what they cover, what they don't

- **Covered:** `authwall` classification across snapshot fixtures, `config` precedence rules, TOML round-trip.
- **NOT covered:** actual browser launches, real network, `agent-browser` invocations, `browse login` flow (requires a human).
- If a test would need a browser or network, it doesn't belong here — put it in the manual verification section of the README.

## Quirks of agent-browser to remember

Two behaviors found the hard way during v1 — relevant if you touch session management:

1. **`--headed` is sticky per-call, not per-session.** If a session was launched headed and a follow-up command is invoked without `--headed`, agent-browser spawns a *new headless* Edge on the same profile, which takes the profile lock and closes the visible window. Every call during a headed flow must pass `--headed`. See the polling loop in `cli.login_cmd`.
2. **`--session X close --all` may scope the close to that session rather than kill all daemons.** When you genuinely want "nuke every daemon", shell out to `agent-browser close --all --json` without a `--session` prefix — that's why `login_cmd` uses `subprocess.run` directly for that specific call.

## Common failure modes

- **`browse auth` loops through the picker indefinitely** — usually a stale `~/.cache/browse/profile/` with unexpected cached accounts. `browse login <url>` resets the experience.
- **`browse login` never returns** — either user cancelled MFA, or navigated somewhere unexpected. Default timeout is 300s; shorten via `--timeout` for testing.
- **Tests pass but real `browse auth` returns `auth_required` even after `login`** — the `LOGIN_HOSTS` set may be too broad and matching your target host, or the picker snapshot format drifted on the IdP side. Re-capture the fixture.
