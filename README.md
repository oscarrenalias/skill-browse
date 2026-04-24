# browse

A thin Python wrapper around [`agent-browser`](https://agent-browser.dev) for fetching authenticated intranet pages from AI agents. Targets AAD/SSO/MFA-protected sites on MDM-managed macOS devices by launching the system-installed Microsoft Edge (so Conditional Access / device-compliance checks pass) as that is usually a safe choice.

Built to plug into [Claude Code](https://claude.com/claude-code) as a skill, but works standalone as a CLI.

Works on macOS only for now.

## What it solves

AI agents can't reach content behind corporate SSO. `WebFetch`/`curl` see only the login redirect. `browse` gives the agent a way to:

1. Ask the user to sign in once, interactively, in a real managed Edge (so Intune / device compliance is satisfied).
2. From then on, headlessly fetch authenticated pages and return them as text or as a compact accessibility snapshot with element refs for follow-up interaction.

AAD's "Pick an account" interstitial — which reappears on every new SSO-protected subdomain — is clicked through automatically using a configured account email.

## Install

```bash
brew install agent-browser            # Rust CLI that does the heavy lifting
uv venv --python 3.11
uv pip install -e '.[dev]'
```

Requires:
- macOS with Microsoft Edge installed (Chrome works as a fallback; Edge is required for Intune-managed corporate SSO).
- `agent-browser >= 0.26`.
- Python 3.11+.

## First-time sign-in

```bash
uv run browse login https://intranet.example.com/
```

Edge opens headed. Complete MFA. The command returns when navigation reaches the requested host. On first run you're prompted once for the AAD account email used for subsequent automated picker click-throughs; it's cached at `~/.config/browse/config.toml`.

## Fetch an authenticated page

```bash
uv run browse auth https://intranet.example.com/some/page --json
```

Returns JSON with `url`, `title`, `snapshot` (accessibility tree with `@eN` refs), and `text` (plain).

## Multi-step interaction

After `browse auth`, the session stays open. Drive it with raw `agent-browser`:

```bash
uv run browse auth https://search.example.com/
agent-browser --session browse snapshot -i
agent-browser --session browse fill @e19 "your query"
agent-browser --session browse press Enter
agent-browser --session browse wait --load networkidle
agent-browser --session browse get text body
```

## Close

```bash
uv run browse close
uv run browse status           # inspect config + session state
```

## Configuration

Env-var or TOML driven. Precedence: CLI flag > env var > `~/.config/browse/config.toml` > defaults.

| Variable | Default |
|---|---|
| `BROWSE_BROWSER_PATH` | `/Applications/Microsoft Edge.app/...` → Chrome fallback |
| `BROWSE_PROFILE_DIR` | `~/.cache/browse/profile` |
| `BROWSE_SESSION_NAME` | `browse` |
| `BROWSE_ACCOUNT_EMAIL` | Prompted on first `browse login` |

## Why system Edge specifically

Corporate Conditional Access on MDM-managed devices checks for device-compliance signals (Intune MDM extension on managed Edge, OS-level SSO extension, device-enrollment certificates). A bundled/downloaded Chromium from an automation tool won't satisfy these — MFA will silently fail with a "this device doesn't meet the requirements" screen. `browse` defaults to the system-installed Edge binary; don't override `BROWSE_BROWSER_PATH` to a bundled browser unless you know your environment accepts it.

## Scope

**Supported**: AAD/Microsoft-tenant SSO (any tenant, not just one), public sites, cookie-based auth, any site where the user can sign in once interactively and the session persists in the browser profile.

**Partial**: Non-AAD SSO (Okta, Google Workspace, Ping, custom SAML). Interactive `browse login` works and the profile remembers the session, but automatic account-picker click-through is AAD-specific. Contributions welcome — see `src/browse/authwall.py`.

## Test

```bash
uv run pytest -q
```

No network — tests use captured snapshot fixtures.

## Dev

See `CLAUDE.md` for the rules of the road when editing this repo.

## License

Apache-2.0. See `LICENSE`.
