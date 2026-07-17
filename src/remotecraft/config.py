"""Environment-backed configuration with conservative defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from dotenv import load_dotenv

from remotecraft.errors import ConfigurationError


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"Invalid boolean value: {value!r}")


def _optional_path(value: str | None) -> Path | None:
    if not value or not value.strip():
        return None
    return Path(value).expanduser().resolve()


@dataclass(frozen=True, slots=True)
class Settings:
    api_token: str
    ssh_host: str
    ssh_port: int
    ssh_user: str
    servers_root: str
    data_dir: Path
    frontend_dir: Path
    ssh_password: str | None = None
    ssh_key_path: Path | None = None
    ssh_use_agent: bool = True
    known_hosts_path: Path | None = None
    max_ram_gb: int = 16
    connect_timeout_seconds: int = 10
    command_timeout_seconds: int = 90
    allowed_origins: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()

        api_token = os.getenv("REMOTECRAFT_API_TOKEN", "").strip()
        ssh_host = os.getenv("REMOTECRAFT_SSH_HOST", "").strip()
        ssh_user = os.getenv("REMOTECRAFT_SSH_USER", "").strip()
        servers_root = os.getenv("REMOTECRAFT_SERVERS_ROOT", "/srv/minecraft").strip()

        missing = [
            name
            for name, value in {
                "REMOTECRAFT_API_TOKEN": api_token,
                "REMOTECRAFT_SSH_HOST": ssh_host,
                "REMOTECRAFT_SSH_USER": ssh_user,
            }.items()
            if not value
        ]
        if missing:
            raise ConfigurationError(f"Missing required settings: {', '.join(missing)}")
        if len(api_token) < 32:
            raise ConfigurationError("REMOTECRAFT_API_TOKEN must contain at least 32 characters")

        root = PurePosixPath(servers_root)
        if not root.is_absolute() or ".." in root.parts or len(root.parts) < 3:
            raise ConfigurationError(
                "REMOTECRAFT_SERVERS_ROOT must be a safe absolute Linux path such as /srv/minecraft"
            )

        try:
            ssh_port = int(os.getenv("REMOTECRAFT_SSH_PORT", "22"))
            max_ram_gb = int(os.getenv("REMOTECRAFT_MAX_RAM_GB", "16"))
            connect_timeout = int(os.getenv("REMOTECRAFT_CONNECT_TIMEOUT", "10"))
            command_timeout = int(os.getenv("REMOTECRAFT_COMMAND_TIMEOUT", "90"))
        except ValueError as exc:
            raise ConfigurationError("Port, RAM, and timeout settings must be integers") from exc

        if not 1 <= ssh_port <= 65535:
            raise ConfigurationError("REMOTECRAFT_SSH_PORT must be between 1 and 65535")
        if not 1 <= max_ram_gb <= 64:
            raise ConfigurationError("REMOTECRAFT_MAX_RAM_GB must be between 1 and 64")
        if connect_timeout < 1 or command_timeout < 1:
            raise ConfigurationError("SSH timeouts must be positive")

        password = os.getenv("REMOTECRAFT_SSH_PASSWORD", "").strip() or None
        key_path = _optional_path(os.getenv("REMOTECRAFT_SSH_KEY_PATH"))
        use_agent = _as_bool(os.getenv("REMOTECRAFT_SSH_USE_AGENT"), True)
        if not password and not key_path and not use_agent:
            raise ConfigurationError("Configure an SSH password, key path, or SSH agent")

        data_dir = Path(os.getenv("REMOTECRAFT_DATA_DIR", "./data")).expanduser().resolve()
        frontend_dir = Path(__file__).resolve().parent / "web"
        known_hosts = _optional_path(
            os.getenv("REMOTECRAFT_KNOWN_HOSTS_PATH", "~/.ssh/known_hosts")
        )
        origins = tuple(
            origin.strip()
            for origin in os.getenv("REMOTECRAFT_ALLOWED_ORIGINS", "").split(",")
            if origin.strip()
        )

        return cls(
            api_token=api_token,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_user=ssh_user,
            servers_root=str(root),
            data_dir=data_dir,
            frontend_dir=frontend_dir,
            ssh_password=password,
            ssh_key_path=key_path,
            ssh_use_agent=use_agent,
            known_hosts_path=known_hosts,
            max_ram_gb=max_ram_gb,
            connect_timeout_seconds=connect_timeout,
            command_timeout_seconds=command_timeout,
            allowed_origins=origins,
        )
