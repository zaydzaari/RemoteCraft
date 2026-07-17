from dataclasses import replace
from pathlib import Path

import paramiko
import pytest

from remotecraft.config import Settings
from remotecraft.errors import ConfigurationError, RemoteCommandError
from remotecraft.ssh import CommandResult, ParamikoRemoteSession


class Channel:
    def __init__(self, status: int) -> None:
        self.status = status

    def recv_exit_status(self) -> int:
        return self.status


class Stream:
    def __init__(self, payload: bytes, status: int = 0) -> None:
        self.payload = payload
        self.channel = Channel(status)

    def read(self) -> bytes:
        return self.payload


class Client:
    def __init__(self, *, status: int = 0) -> None:
        self.status = status
        self.closed = False
        self.policy = None
        self.connect_kwargs: dict[str, object] = {}
        self.loaded_host_files: list[str] = []

    def load_system_host_keys(self) -> None:
        return None

    def load_host_keys(self, path: str) -> None:
        self.loaded_host_files.append(path)

    def set_missing_host_key_policy(self, policy: object) -> None:
        self.policy = policy

    def connect(self, **kwargs: object) -> None:
        self.connect_kwargs = kwargs

    def close(self) -> None:
        self.closed = True

    def exec_command(self, command: str, *, timeout: int):
        assert command == "whoami"
        assert timeout == 12
        return None, Stream(b"minecraft\n", self.status), Stream(b"failed\n")


def test_session_uses_known_hosts_reject_policy_and_closes(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = Client()
    monkeypatch.setattr(paramiko, "SSHClient", lambda: client)

    with ParamikoRemoteSession(settings) as remote:
        result = remote.run("whoami", timeout=12)

    assert result == CommandResult("minecraft\n", "failed\n", 0)
    assert isinstance(client.policy, paramiko.RejectPolicy)
    assert client.loaded_host_files == [str(settings.known_hosts_path)]
    assert client.connect_kwargs["hostname"] == settings.ssh_host
    assert client.closed is True


def test_session_rejects_missing_known_hosts_file(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = Client()
    monkeypatch.setattr(paramiko, "SSHClient", lambda: client)
    missing = tmp_path / "missing_known_hosts"
    bad_settings = replace(settings, known_hosts_path=missing)

    with pytest.raises(ConfigurationError, match="does not exist"):
        ParamikoRemoteSession(bad_settings).__enter__()


def test_run_requires_connection_and_reports_remote_failure(settings: Settings) -> None:
    remote = ParamikoRemoteSession(settings)
    with pytest.raises(RemoteCommandError, match="not connected"):
        remote.run("whoami")

    remote.client = Client(status=1)  # type: ignore[assignment]
    with pytest.raises(RemoteCommandError, match="failed"):
        remote.run("whoami", timeout=12)
