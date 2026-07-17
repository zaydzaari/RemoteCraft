from pathlib import Path

import pytest

from remotecraft.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("", encoding="utf-8")
    frontend = Path(__file__).resolve().parents[1] / "src" / "remotecraft" / "web"
    return Settings(
        api_token="test-token-that-is-at-least-32-characters",
        ssh_host="minecraft.example.test",
        ssh_port=22,
        ssh_user="minecraft",
        ssh_password=None,
        ssh_key_path=None,
        ssh_use_agent=True,
        known_hosts_path=known_hosts,
        servers_root="/srv/minecraft",
        data_dir=tmp_path / "data",
        frontend_dir=frontend,
        max_ram_gb=16,
        connect_timeout_seconds=5,
        command_timeout_seconds=30,
    )
