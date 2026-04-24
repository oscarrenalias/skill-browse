from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

# Hosts that mean "we're in some SSO/IdP interstitial, not the target site."
# Add here sparingly — too broad and we'll mis-flag legitimate pages.
LOGIN_HOSTS = {
    "login.microsoftonline.com",
    "login.microsoft.com",
    "login.live.com",
    "login.windows.net",
    "aadcdn.msauth.net",
}

@dataclass
class AuthState:
    kind: str  # "clear" | "picker" | "interactive"
    picker_ref: str | None = None  # set when kind == "picker" and email matched

    @property
    def is_clear(self) -> bool:
        return self.kind == "clear"

    @property
    def needs_interactive(self) -> bool:
        return self.kind == "interactive"


def _host(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except ValueError:
        return ""


def classify(url: str, title: str, snapshot: str, account_email: str | None) -> AuthState:
    """Classify the current browser state.

    Title alone is unreliable — AAD reuses "Sign in to your account" across the
    email-entry page, the password page, and the account picker. The snapshot
    is the ground truth: if it has a "Pick an account" heading, it's the picker.

    Returns:
        AuthState with kind "clear" (we're on the target site),
        "picker" (AAD account picker — picker_ref is the button @ref to click
        if an account_email match was found, else None meaning interactive),
        or "interactive" (user action required, cannot auto-proceed).
    """
    if _host(url) not in LOGIN_HOSTS:
        return AuthState(kind="clear")

    if _looks_like_picker(snapshot):
        ref = _find_picker_ref(snapshot, account_email) if account_email else None
        if ref:
            return AuthState(kind="picker", picker_ref=ref)
        return AuthState(kind="interactive")

    # On a login host with no picker visible → interactive sign-in needed.
    # Title-based refinement is noise; the only actionable signal is "picker
    # showing = we can click through" vs "anything else = user needed".
    return AuthState(kind="interactive")


_PICKER_HEADING_RE = re.compile(r'heading "Pick an account"')


def _looks_like_picker(snapshot: str) -> bool:
    return bool(_PICKER_HEADING_RE.search(snapshot))


# agent-browser snapshot format for the picker button looks like:
#   - button "Sign in with jane.doe@example.com work or school account." [ref=e9]
_PICKER_BUTTON_RE = re.compile(
    r'button "Sign in with (?P<email>\S+?) work or school account\." '
    r'\[ref=(?P<ref>e\d+)\]'
)


def _find_picker_ref(snapshot: str, email: str) -> str | None:
    for m in _PICKER_BUTTON_RE.finditer(snapshot):
        if m.group("email").lower() == email.lower():
            return m.group("ref")
    return None
