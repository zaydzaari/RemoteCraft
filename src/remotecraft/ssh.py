"""Strict Paramiko adapter used by the domain service."""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Protocol, Self

import paramiko

from remotecraft.config import Settings
from remotecraft.errors import ConfigurationError, RemoteCommandError


@dataclass(frozen=True, slots=True)
class CommandResult:
    stdout: str
    stderr: str
    exit_status: int


class RemoteSession(Protocol):
    def run(self, command: str, *, check: bool = True, timeout: int | None = None) -> CommandResult:
        """Execute one command on the configured host."""


class ParamikoRemoteSession:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client: paramiko.SSHClient | None = None

    def __enter__(self) -> Self:
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        if self.settings.known_hosts_path:
            if not self.settings.known_hosts_path.is_file():
                raise ConfigurationError(
                    f"Known-hosts file does not exist: {self.settings.known_hosts_path}"
                )
            client.load_host_keys(str(self.settings.known_hosts_path))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(
                hostname=self.settings.ssh_host,
                port=self.settings.ssh_port,
                username=self.settings.ssh_user,
                password=self.settings.ssh_password,
                key_filename=(
                    str(self.settings.ssh_key_path) if self.settings.ssh_key_path else None
                ),
                allow_agent=self.settings.ssh_use_agent,
                look_for_keys=self.settings.ssh_use_agent,
                timeout=self.settings.connect_timeout_seconds,
                banner_timeout=self.settings.connect_timeout_seconds,
                auth_timeout=self.settings.connect_timeout_seconds,
            )
        except Exception:
            client.close()
            raise
        self.client = client
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.client:
            self.client.close()
            self.client = None

    def run(self, command: str, *, check: bool = True, timeout: int | None = None) -> CommandResult:
        if not self.client:
            raise RemoteCommandError("SSH session is not connected")
        command_timeout = timeout or self.settings.command_timeout_seconds
        _stdin, stdout, stderr = self.client.exec_command(command, timeout=command_timeout)
        exit_status = stdout.channel.recv_exit_status()
        result = CommandResult(
            stdout=stdout.read().decode("utf-8", errors="replace"),
            stderr=stderr.read().decode("utf-8", errors="replace"),
            exit_status=exit_status,
        )
        if check and exit_status != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "remote command failed"
            raise RemoteCommandError(detail[:500])
        return result
