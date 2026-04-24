from pathlib import Path

import pytest

from browse import authwall


FIXTURES = Path(__file__).parent / "fixtures"
PICKER_SNAPSHOT = (FIXTURES / "picker_snapshot.txt").read_text()

TARGET_URL = "https://intranet.example.com/home/"
PICKER_URL = "https://login.microsoftonline.com/00000000-0000-0000-0000-000000000000/saml2?SAMLRequest=..."
LOGIN_URL = "https://login.microsoftonline.com/common/oauth2/authorize?..."


def test_clear_when_on_target_site():
    state = authwall.classify(TARGET_URL, "Home", "", "jane.doe@example.com")
    assert state.is_clear
    assert state.picker_ref is None


def test_picker_matches_primary_account():
    state = authwall.classify(PICKER_URL, "Pick an account", PICKER_SNAPSHOT, "jane.doe@example.com")
    assert state.kind == "picker"
    assert state.picker_ref == "e9"


def test_picker_matches_secondary_account():
    state = authwall.classify(PICKER_URL, "Pick an account", PICKER_SNAPSHOT, "jane.doe-ext@partner.example.org")
    assert state.kind == "picker"
    assert state.picker_ref == "e10"


def test_picker_email_case_insensitive():
    state = authwall.classify(PICKER_URL, "Pick an account", PICKER_SNAPSHOT, "Jane.Doe@Example.com")
    assert state.kind == "picker"
    assert state.picker_ref == "e9"


def test_picker_unknown_email_falls_back_to_interactive():
    state = authwall.classify(PICKER_URL, "Pick an account", PICKER_SNAPSHOT, "someone.else@other.example.net")
    assert state.needs_interactive
    assert state.picker_ref is None


def test_picker_without_email_falls_back_to_interactive():
    state = authwall.classify(PICKER_URL, "Pick an account", PICKER_SNAPSHOT, None)
    assert state.needs_interactive


def test_sign_in_page_is_interactive():
    # AAD labels many different screens with "Sign in to your account". Title
    # alone isn't enough; the absence of a picker heading in the snapshot is
    # what drives classification.
    state = authwall.classify(LOGIN_URL, "Sign in to your account", "", "jane.doe@example.com")
    assert state.needs_interactive


def test_enter_password_is_interactive():
    state = authwall.classify(LOGIN_URL, "Enter password", "", "jane.doe@example.com")
    assert state.needs_interactive


def test_mfa_approval_is_interactive():
    state = authwall.classify(LOGIN_URL, "Approve sign in request", "", "jane.doe@example.com")
    assert state.needs_interactive


def test_unfamiliar_title_on_login_host_is_interactive():
    state = authwall.classify(LOGIN_URL, "Some new AAD screen", "", "jane.doe@example.com")
    assert state.needs_interactive


@pytest.mark.parametrize("url", [
    "https://intranet.example.com/",
    "https://search.example.com/search?k=x",
    "https://httpbin.org/html",
    "",
])
def test_non_login_host_is_clear(url):
    state = authwall.classify(url, "some title", "", "jane.doe@example.com")
    assert state.is_clear
