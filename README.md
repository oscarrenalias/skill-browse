# skill-browse

A Claude Code skill that wraps [`agent-browser`](https://agent-browser.dev) so AI agents can reach authenticated intranet pages on MDM-managed devices — without `WebFetch` hitting a login redirect.

The skill launches the system-installed Microsoft Edge (so Conditional Access / device-compliance checks pass), handles AAD's "Pick an account" interstitial automatically, and exposes a small CLI (`browse login`, `browse auth`, `browse close`) that the agent orchestrates end-to-end.

See [`.apm/skills/browse/SKILL.md`](.apm/skills/browse/SKILL.md) for the full agent-facing documentation and [`CLAUDE.md`](CLAUDE.md) for developer notes.

Works on macOS only for now.

## Requirements

- `agent-browser >= 0.26` (`brew install agent-browser`)
- `uv` (`brew install uv`) — used to manage the skill's local Python venv on first run. **No Python packages are installed globally.**
- Microsoft Edge installed (Chrome works as a fallback; Edge is required for Intune-managed corporate SSO).

## Installation

**With apm:**
```
apm install oscarrenalias/skill-browse#vX.Y.Z
```
Replace `vX.Y.Z` with the current release tag (see the Releases tab).

**Without apm:** download the zip from the [latest release](https://github.com/oscarrenalias/skill-browse/releases) and extract it into your `.claude/skills/` folder:
```
unzip skill-browse-<version>.zip -d ~/.claude/skills/
```

That's it. No install step after unzipping — the `~/.claude/skills/browse/bin/browse` wrapper uses `uv` to create a skill-local `.venv/` the first time it's invoked. Claude Code discovers the skill automatically.

## How it's used

In normal use, you don't invoke the CLI yourself. Ask Claude something like *"summarize this intranet page"* or *"search our internal tool for X"* and the agent will drive the skill.

If you want to pre-authenticate manually or exercise the CLI directly:
```
~/.claude/skills/browse/bin/browse login https://your-intranet.example.com/
~/.claude/skills/browse/bin/browse auth https://your-intranet.example.com/some/page --json
~/.claude/skills/browse/bin/browse status
~/.claude/skills/browse/bin/browse close
```

First invocation per fresh checkout takes ~1-2s extra while `uv` syncs the skill-local venv. Subsequent calls are near-instant.

## Dev

```
cd .apm/skills/browse
uv run --extra dev pytest -q         # 21 tests, < 1s, no network
uv run browse --help                 # exercise the CLI locally
```

See [`CLAUDE.md`](CLAUDE.md) for editing rules, non-negotiables, and how to extend it (new IdPs, new agent-browser subcommand wrappings).
