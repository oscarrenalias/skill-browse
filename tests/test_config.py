from pathlib import Path

import pytest

from browse import config


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Redirect HOME + config paths into a tmp dir so tests don't touch real config."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / ".config" / "browse" / "config.toml")
    monkeypatch.setattr(config, "DEFAULT_PROFILE_DIR", tmp_path / ".cache" / "browse" / "profile")
    # Clear any BROWSE_* env so the test starts from a known state.
    for var in ("BROWSE_BROWSER_PATH", "BROWSE_PROFILE_DIR", "BROWSE_SESSION_NAME", "BROWSE_ACCOUNT_EMAIL"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def _fake_browser(tmp_path: Path, name: str = "fake-browser") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / name
    p.write_text("")
    p.chmod(0o755)
    return p


def test_explicit_arg_beats_env_and_toml(isolated_home, monkeypatch):
    explicit = _fake_browser(isolated_home)
    env_browser = _fake_browser(isolated_home / "env")
    monkeypatch.setenv("BROWSE_BROWSER_PATH", str(env_browser))
    isolated_home.joinpath(".config/browse").mkdir(parents=True)
    isolated_home.joinpath(".config/browse/config.toml").write_text('session_name = "from-toml"\n')

    c = config.load(browser_path=str(explicit), session_name="from-arg")
    assert c.browser_path == explicit
    assert c.session_name == "from-arg"


def test_env_beats_toml(isolated_home, monkeypatch):
    browser = _fake_browser(isolated_home)
    monkeypatch.setenv("BROWSE_BROWSER_PATH", str(browser))
    monkeypatch.setenv("BROWSE_SESSION_NAME", "from-env")
    isolated_home.joinpath(".config/browse").mkdir(parents=True)
    isolated_home.joinpath(".config/browse/config.toml").write_text('session_name = "from-toml"\n')

    c = config.load()
    assert c.session_name == "from-env"


def test_toml_beats_default(isolated_home, monkeypatch):
    browser = _fake_browser(isolated_home)
    monkeypatch.setenv("BROWSE_BROWSER_PATH", str(browser))
    isolated_home.joinpath(".config/browse").mkdir(parents=True)
    isolated_home.joinpath(".config/browse/config.toml").write_text(
        'session_name = "from-toml"\naccount_email = "user@example.com"\n'
    )

    c = config.load()
    assert c.session_name == "from-toml"
    assert c.account_email == "user@example.com"


def test_defaults_when_nothing_set(isolated_home, monkeypatch):
    browser = _fake_browser(isolated_home)
    monkeypatch.setenv("BROWSE_BROWSER_PATH", str(browser))

    c = config.load()
    assert c.session_name == config.DEFAULT_SESSION_NAME
    assert c.profile_dir == config.DEFAULT_PROFILE_DIR
    assert c.account_email is None


def test_missing_browser_raises(isolated_home, monkeypatch):
    monkeypatch.setattr(config, "EDGE_MACOS", isolated_home / "nope-edge")
    monkeypatch.setattr(config, "CHROME_MACOS", isolated_home / "nope-chrome")
    with pytest.raises(config.ConfigError):
        config.load()


def test_explicit_browser_must_exist(isolated_home):
    with pytest.raises(config.ConfigError):
        config.load(browser_path=str(isolated_home / "does-not-exist"))


def test_save_account_email_roundtrip(isolated_home):
    browser = _fake_browser(isolated_home)
    import os
    os.environ["BROWSE_BROWSER_PATH"] = str(browser)

    config.save_account_email("me@example.com")
    c = config.load()
    assert c.account_email == "me@example.com"

    config.save_account_email("other@example.com")
    c2 = config.load()
    assert c2.account_email == "other@example.com"

    del os.environ["BROWSE_BROWSER_PATH"]
