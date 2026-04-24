---
name: browse
description: Use when an AI agent needs to read or interact with authenticated intranet / internal sites (AAD/SSO/MFA-gated) that `WebFetch` and `curl` can't reach — e.g. "fetch this internal wiki page", "summarize the Confluence article behind our SSO", "search our intranet for X", "click through that internal dashboard". Wraps the `agent-browser` CLI with system-Edge launch flags (so device-compliance checks pass on MDM-managed machines) and automatic handling of AAD's "Pick an account" picker.
---

# browse — authenticated intranet fetcher

`browse` is a thin wrapper around [`agent-browser`](https://agent-browser.dev) that handles two things you'd otherwise repeat on every invocation:

1. Launching the **system-installed Microsoft Edge** so Intune / AAD Conditional Access compliance is satisfied on managed corporate devices (a bundled Chromium fails compliance silently).
2. Detecting AAD's "Pick an account" interstitial and clicking through it with a configured account email.

For everything else — clicking buttons, filling forms, scrolling, screenshots — use `agent-browser` directly against the same session.

## When to trigger

- "Read/fetch/summarize this internal page": any intranet URL that requires SSO.
- "Log me into site X": user needs to do interactive MFA once.
- "Click through this internal dashboard" / "search our internal tool for X".
- Anything that fails with `WebFetch` because of a login redirect.

## When NOT to trigger

- Public web — use `WebFetch` / `WebSearch`.
- Content the user has already pasted into the conversation.
- Sites protected by non-AAD SSO (Okta, Google Workspace, Ping, custom SAML). `browse login` still lets you sign in interactively and the profile will remember you, but the automatic account-picker click-through is AAD-specific; headless fetches against other IdPs may return login-page HTML as "content" if the session has rotted. Treat with caution.

## Handling `auth_required` — the agent drives login itself

When `browse auth` returns `auth_required: true`, **the agent should trigger login directly rather than instructing the user to run a terminal command**. Only the MFA taps inside the Edge window require the human; everything else can be orchestrated by the agent. Flow:

1. **Check if the account email is cached.** Run `browse status --json` and look at `account_email`. If non-null, skip step 2.
2. **Ask the user for their email** via `AskUserQuestion`. Only ever needed once per user — it gets cached at `~/.config/browse/config.toml`. Frame it: *"What's the email of the account you want to sign into? (Used to click the right tile on Microsoft's account picker — not a credential.)"*
3. **Launch login in the background.** Shell out to `browse login <original-url> --email <email>` with `run_in_background: true`. Passing `--email` bypasses the CLI's interactive prompt, so the command is fully non-interactive from the agent's side.
4. **Tell the user what's about to happen.** One short line: *"An Edge window is opening. Please complete sign-in + MFA — I'll wait for it to finish, then fetch the page."*
5. **Wait for the background task to complete.** Don't poll — the harness sends a notification when the login command exits. `browse login` exits cleanly when navigation reaches the target host (success) or the default 300s timeout fires (failure).
6. **Retry the original `browse auth`** once login reports success.

If `browse login` fails (times out, user cancels), surface the error and stop. Don't retry unprompted.

`browse login` itself:
- Launches Edge **headed** pointed at `<url>`.
- Uses system Edge so device-compliance checks pass on MDM-managed machines.
- Returns when navigation reaches the target host — agent can treat its exit as the "ready to retry" signal.

Typical AAD persistent-cookie lifetime is ~90 days, so `browse login` usually only needs to be triggered once per quarter per SSO realm. After that, `browse auth` runs silently (or with an automatic picker click-through).

## Recipes

### Fetch an authenticated page

```bash
browse auth https://intranet.example.com/some/page --json
```

Returns:
```json
{
  "success": true,
  "url": "https://intranet.example.com/some/page",
  "title": "Page Title",
  "snapshot": "- heading \"Page Title\" [level=1, ref=e1]\n  - link ...",
  "text": "main body text..."
}
```

Default format is `both` — you get the compact accessibility snapshot (with `@eN` refs for follow-up interaction) plus the plain-text version. Pass `--format snapshot` or `--format text` to narrow it.

### Auth wall detected

```json
{
  "success": false,
  "auth_required": true,
  "login_hint": "browse login https://intranet.example.com/some/page",
  "url": "https://login.microsoftonline.com/...",
  "title": "Sign in to your account"
}
```

Tell the user to run the `login_hint` command.

### Multi-step interaction (search, fill forms, click)

After `browse auth` lands on the target page, the session stays open. Continue with raw `agent-browser`:

```bash
browse auth https://search.example.com/ --json                           # lands on the SPA
agent-browser --session browse snapshot -i --json                        # refs for the search box
agent-browser --session browse fill @e19 "your query" --json             # type query
agent-browser --session browse press Enter --json
agent-browser --session browse wait --load networkidle --json
agent-browser --session browse get text body --json                      # read results
```

The session is named `browse` (configurable via `BROWSE_SESSION_NAME`).

### Dealing with SPAs / dynamic content

After any click/fill/nav that changes the DOM:
```bash
agent-browser --session browse wait --load networkidle
# or a content-based wait:
agent-browser --session browse wait --fn "document.body.innerText.length > 500"
```
Then re-snapshot or re-extract.

### Cleaning up

```bash
browse close       # close the session (Edge window disappears)
browse status      # show config + session state
```

## Failure modes

| Symptom | Meaning | What to tell the user |
|---|---|---|
| `auth_required: true, login_hint: "browse login <url>"` | Session rotted or first-ever visit to a new SSO realm. | Drive login yourself (see "Handling `auth_required`" section). Don't tell the user to run a terminal command unless the login attempt itself fails. |
| `success: false, error: "net::ERR_CONNECTION_RESET"` | Network/DNS issue — often VPN required or proxy misconfigured. | Not our problem; recommend user check VPN / retry. |
| `exceeded N picker click-throughs` | Account-picker keeps reappearing — likely wrong `BROWSE_ACCOUNT_EMAIL` or the email doesn't match any cached account. | "Check the cached email with `browse status`. Re-run `browse login <url>` if the picker shows the wrong accounts." |
| Edge window opens but stays stuck on login page during `browse login` | User got a "this device doesn't meet the requirements" screen, or MFA was cancelled. | User needs to verify device compliance in Intune Company Portal (if their org uses MDM). |

## Configuration reference

Resolution precedence: **CLI flag → env var → `~/.config/browse/config.toml` → defaults.**

| Key | Env var | Default |
|---|---|---|
| Browser executable | `BROWSE_BROWSER_PATH` | Edge if present, else Chrome on macOS |
| Profile directory | `BROWSE_PROFILE_DIR` | `~/.cache/browse/profile` |
| Session name | `BROWSE_SESSION_NAME` | `browse` |
| Account email (for AAD picker) | `BROWSE_ACCOUNT_EMAIL` | Prompted on first `browse login`, cached to TOML |

## Why system Edge matters

Corporate Conditional Access on managed devices checks for MDM compliance signals (Intune on Microsoft shops, similar on other MDM stacks). Those signals come from the OS-level SSO extension plus the installed, policy-managed Edge binary — not from a fresh Chromium downloaded by an automation tool. Running against `/Applications/Microsoft Edge.app` (or system Chrome as a fallback) is how MFA actually passes. `browse` picks this automatically; don't override `BROWSE_BROWSER_PATH` to a bundled/downloaded browser or MFA will silently fail.

## Tips for agents

- **Always pass `--json`** to both `browse` and raw `agent-browser` invocations — the human-readable format is not stable.
- **Prefer `@eN` refs from `snapshot -i`** over text-match or CSS selectors for SPAs. On AAD screens specifically, text-match locators often hit decoy elements.
- **`browse auth` already handles the AAD picker** — don't double-handle it. Only fall back to raw `agent-browser` clicks when you need to drive the target app.
- **Session persists across calls.** Don't re-launch with `browse login` unless `auth_required: true` is surfaced.
- **When `auth_required` fires, drive login yourself.** Ask for email via `AskUserQuestion` (only if not cached), launch `browse login --email <email>` in the background, wait for it to exit, retry. Do not hand the user a terminal command to run — that's the old pattern.
- **Check `agent-browser skills get core --full`** if you need the full command reference; it ships bundled with the CLI and is always version-matched.

## Known limits (v1)

- First visit to each new SSO-protected subdomain within a session re-triggers the AAD account picker (handled automatically, but adds ~1-2s per new host).
- Non-AAD SSO (Okta, Google, Ping, custom) — interactive sign-in via `browse login` works, but automatic picker click-through is AAD-only. If you hit these regularly, contribute IdP-specific heuristics to `src/browse/authwall.py`.
- No parallel fetches — one session, one browser. Run sequentially.
- `browse login` is interactive-only; cannot be driven by an agent.
