from pathlib import Path

import pytest

from remotecraft.config import Settings
from remotecraft.errors import ConfigurationError

ENV_KEYS = [
    "REMOTECRAFT_API_TOKEN",
    "REMOTECRAFT_SSH_HOST",
    "REMOTECRAFT_SSH_PORT",
    "REMOTECRAFT_SSH_USER",
    "REMOTECRAFT_SSH_PASSWORD",
    "REMOTECRAFT_SSH_KEY_PATH",
    "REMOTECRAFT_SSH_USE_AGENT",
    "REMOTECRAFT_KNOWN_HOSTS_PATH",
    "REMOTECRAFT_SERVERS_ROOT",
    "REMOTECRAFT_DATA_DIR",
    "REMOTECRAFT_MAX_RAM_GB",
    "REMOTECRAFT_CONNECT_TIMEOUT",
    "REMOTECRAFT_COMMAND_TIMEOUT",
    "REMOTECRAFT_ALLOWED_ORIGINS",
]


def configure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("", encoding="utf-8")
    monkeypatch.setenv("REMOTECRAFT_API_TOKEN", "a" * 32)
    monkeypatch.setenv("REMOTECRAFT_SSH_HOST", "host.example.test")
    monkeypatch.setenv("REMOTECRAFT_SSH_USER", "minecraft")
    monkeypatch.setenv("REMOTECRAFT_SSH_USE_AGENT", "true")
    monkeypatch.setenv("REMOTECRAFT_KNOWN_HOSTS_PATH", str(known_hosts))
    monkeypatch.setenv("REMOTECRAFT_DATA_DIR", str(tmp_path / "state"))


def test_settings_load_valid_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    configure(monkeypatch, tmp_path)
    monkeypatch.setenv("REMOTECRAFT_SSH_PORT", "2222")
    monkeypatch.setenv("REMOTECRAFT_ALLOWED_ORIGINS", "https://one.test, https://two.test")

    settings = Settings.from_env()

    assert settings.ssh_port == 2222
    assert settings.servers_root == "/srv/minecraft"
    assert settings.allowed_origins == ("https://one.test", "https://two.test")
    assert settings.frontend_dir.name == "web"


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("REMOTECRAFT_API_TOKEN", "short", "at least 32"),
        ("REMOTECRAFT_SSH_PORT", "70000", "between 1 and 65535"),
        ("REMOTECRAFT_MAX_RAM_GB", "0", "between 1 and 64"),
        ("REMOTECRAFT_SERVERS_ROOT", "/", "safe absolute Linux path"),
        ("REMOTECRAFT_SSH_USE_AGENT", "sometimes", "Invalid boolean"),
    ],
)
def test_settings_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key: str, value: str, message: str
) -> None:
    configure(monkeypatch, tmp_path)
    monkeypatch.setenv(key, value)

    with pytest.raises(ConfigurationError, match=message):
        Settings.from_env()


def test_settings_report_missing_required_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configure(monkeypatch, tmp_path)
    monkeypatch.delenv("REMOTECRAFT_SSH_HOST")

    with pytest.raises(ConfigurationError, match="REMOTECRAFT_SSH_HOST"):
        Settings.from_env()


def test_settings_require_an_ssh_authentication_method(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configure(monkeypatch, tmp_path)
    monkeypatch.setenv("REMOTECRAFT_SSH_USE_AGENT", "false")

    with pytest.raises(ConfigurationError, match="SSH password, key path, or SSH agent"):
        Settings.from_env()
