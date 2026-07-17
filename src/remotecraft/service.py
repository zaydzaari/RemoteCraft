"""Minecraft server lifecycle operations executed through a strict SSH boundary."""

from __future__ import annotations

import re
import shlex
import time
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import PurePosixPath

from remotecraft.config import Settings
from remotecraft.errors import ConflictError, InvalidRequestError, RemoteCommandError
from remotecraft.models import ServerRecord, ServerStatus, ServerView
from remotecraft.ssh import ParamikoRemoteSession, RemoteSession
from remotecraft.store import ServerStore
from remotecraft.versions import VersionCatalog

NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,31}$")
VERSION_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,31}$")
CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")

SessionFactory = Callable[[], AbstractContextManager[RemoteSession]]


class MinecraftService:
    def __init__(
        self,
        settings: Settings,
        store: ServerStore,
        catalog: VersionCatalog,
        *,
        session_factory: SessionFactory | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self.store = store
        self.catalog = catalog
        self.session_factory = session_factory or (lambda: ParamikoRemoteSession(settings))
        self.sleeper = sleeper

    @staticmethod
    def _quote(value: str) -> str:
        return shlex.quote(value)

    @staticmethod
    def _validate_name(name: str) -> str:
        if not NAME_PATTERN.fullmatch(name):
            raise InvalidRequestError(
                "Server name must be 2-32 characters using letters, numbers, dashes, or underscores"
            )
        return name

    @staticmethod
    def _validate_version(version: str) -> str:
        if not VERSION_PATTERN.fullmatch(version):
            raise InvalidRequestError("Invalid Minecraft version")
        return version

    def _validate_ram(self, ram_gb: int) -> int:
        if not 1 <= ram_gb <= self.settings.max_ram_gb:
            raise InvalidRequestError(f"RAM must be between 1 and {self.settings.max_ram_gb} GB")
        return ram_gb

    @staticmethod
    def _tool_status(remote: RemoteSession) -> dict[str, bool]:
        command = (
            "for tool in java screen curl sha1sum; do "
            'if command -v "$tool" >/dev/null 2>&1; then '
            "printf '%s=ok\\n' \"$tool\"; else printf '%s=missing\\n' \"$tool\"; fi; done"
        )
        output = remote.run(command).stdout
        return {
            line.split("=", 1)[0]: line.endswith("=ok")
            for line in output.splitlines()
            if "=" in line
        }

    def check_host(self) -> dict[str, object]:
        with self.session_factory() as remote:
            tools = self._tool_status(remote)
        required = {name: tools.get(name, False) for name in ("java", "screen", "curl", "sha1sum")}
        return {"ready": all(required.values()), "tools": required}

    @staticmethod
    def _session_running(remote: RemoteSession, screen_name: str) -> bool:
        command = f"screen -S {shlex.quote(screen_name)} -Q select . >/dev/null 2>&1"
        return remote.run(command, check=False).exit_status == 0

    def list_servers(self) -> list[ServerView]:
        records = self.store.list()
        if not records:
            return []
        with self.session_factory() as remote:
            screen_output = remote.run("screen -ls", check=False).stdout
        views: list[ServerView] = []
        for record in records:
            pattern = rf"\d+\.{re.escape(record.screen_name)}\s"
            status: ServerStatus = "online" if re.search(pattern, screen_output) else "offline"
            views.append(ServerView.from_record(record, status=status))
        return views

    def create_server(
        self, *, name: str, version: str, ram_gb: int, accept_eula: bool
    ) -> ServerView:
        if not accept_eula:
            raise InvalidRequestError("You must explicitly accept the Minecraft EULA")
        name = self._validate_name(name)
        version = self._validate_version(version)
        ram_gb = self._validate_ram(ram_gb)
        if any(record.name.casefold() == name.casefold() for record in self.store.list()):
            raise ConflictError("A server with this name already exists")

        download = self.catalog.get_vanilla_download(version)
        server_id = uuid.uuid4().hex
        directory_name = f"{name}-{server_id[:8]}"
        server_path = str(PurePosixPath(self.settings.servers_root) / directory_name)
        screen_name = f"rc-{server_id[:12]}"
        quoted_path = self._quote(server_path)

        with self.session_factory() as remote:
            tools = self._tool_status(remote)
            required_tools = ("java", "screen", "curl", "sha1sum")
            missing = [tool for tool in required_tools if not tools.get(tool)]
            if missing:
                raise ConflictError(f"Remote host is missing required tools: {', '.join(missing)}")

            create_directory = (
                f"install -d -m 0750 {self._quote(self.settings.servers_root)} && "
                f"test ! -e {quoted_path} && install -d -m 0750 {quoted_path}"
            )
            remote.run(create_directory)
            try:
                setup = (
                    f"cd {quoted_path} && "
                    "curl --fail --location --proto '=https' --tlsv1.2 --silent --show-error "
                    f"--output server.jar {self._quote(download.url)} && "
                    f"printf '%s  %s\\n' {self._quote(download.sha1)} server.jar "
                    "| sha1sum --check --status && "
                    "printf 'eula=true\\n' > eula.txt"
                )
                remote.run(setup, timeout=max(self.settings.command_timeout_seconds, 300))
            except Exception:
                remote.run(f"rm -rf -- {quoted_path}", check=False)
                raise

        record = ServerRecord(
            id=server_id,
            name=name,
            version=version,
            ram_gb=ram_gb,
            path=server_path,
            screen_name=screen_name,
            jar_sha1=download.sha1,
        )
        self.store.add(record)
        return ServerView.from_record(record)

    def start_server(self, server_id: str) -> ServerView:
        record = self.store.get(server_id)
        with self.session_factory() as remote:
            if self._session_running(remote, record.screen_name):
                return ServerView.from_record(record, status="online")
            inner = (
                f"cd {self._quote(record.path)} && "
                f"exec java -Xms1G -Xmx{record.ram_gb}G -jar server.jar nogui"
            )
            command = f"screen -DmS {self._quote(record.screen_name)} bash -lc {self._quote(inner)}"
            remote.run(command)
        updated = self.store.update(server_id, status="starting")
        return ServerView.from_record(updated)

    def stop_server(self, server_id: str) -> ServerView:
        record = self.store.get(server_id)
        with self.session_factory() as remote:
            if not self._session_running(remote, record.screen_name):
                updated = self.store.update(server_id, status="offline")
                return ServerView.from_record(updated)
            payload = self._quote("stop\n")
            remote.run(f"screen -S {self._quote(record.screen_name)} -X stuff {payload}")
        updated = self.store.update(server_id, status="stopping")
        return ServerView.from_record(updated)

    def restart_server(self, server_id: str) -> ServerView:
        record = self.store.get(server_id)
        with self.session_factory() as remote:
            if self._session_running(remote, record.screen_name):
                stop_payload = self._quote("stop\n")
                remote.run(f"screen -S {self._quote(record.screen_name)} -X stuff {stop_payload}")
                for _ in range(30):
                    if not self._session_running(remote, record.screen_name):
                        break
                    self.sleeper(1)
                else:
                    raise ConflictError("Server did not stop within 30 seconds")
            inner = (
                f"cd {self._quote(record.path)} && "
                f"exec java -Xms1G -Xmx{record.ram_gb}G -jar server.jar nogui"
            )
            remote.run(
                f"screen -DmS {self._quote(record.screen_name)} bash -lc {self._quote(inner)}"
            )
        updated = self.store.update(server_id, status="starting")
        return ServerView.from_record(updated)

    def kill_server(self, server_id: str) -> ServerView:
        record = self.store.get(server_id)
        with self.session_factory() as remote:
            remote.run(f"screen -S {self._quote(record.screen_name)} -X quit", check=False)
        updated = self.store.update(server_id, status="offline")
        return ServerView.from_record(updated)

    def delete_server(self, server_id: str, *, confirm: str) -> ServerView:
        record = self.store.get(server_id)
        if confirm != record.name:
            raise InvalidRequestError("Confirmation must exactly match the server name")
        with self.session_factory() as remote:
            if self._session_running(remote, record.screen_name):
                raise ConflictError("Stop the server before deleting it")
            expected_parent = PurePosixPath(self.settings.servers_root)
            target = PurePosixPath(record.path)
            if target.parent != expected_parent:
                raise RemoteCommandError("Refusing to delete a path outside the servers root")
            remote.run(f"rm -rf -- {self._quote(record.path)}")
        removed = self.store.remove(server_id)
        return ServerView.from_record(removed, status="offline")

    def send_command(self, server_id: str, command: str) -> dict[str, str]:
        record = self.store.get(server_id)
        command = command.strip()
        if not command or len(command) > 512 or CONTROL_PATTERN.search(command):
            raise InvalidRequestError("Command must be 1-512 printable characters")
        with self.session_factory() as remote:
            if not self._session_running(remote, record.screen_name):
                raise ConflictError("Server is offline")
            payload = self._quote(command + "\n")
            remote.run(f"screen -S {self._quote(record.screen_name)} -X stuff {payload}")
        return {"status": "sent"}

    def get_logs(self, server_id: str, lines: int = 100) -> dict[str, object]:
        record = self.store.get(server_id)
        if not 1 <= lines <= 500:
            raise InvalidRequestError("Log line count must be between 1 and 500")
        log_path = str(PurePosixPath(record.path) / "logs" / "latest.log")
        with self.session_factory() as remote:
            result = remote.run(
                f"test -f {self._quote(log_path)} && tail -n {lines} -- {self._quote(log_path)}",
                check=False,
            )
        if result.exit_status != 0:
            return {"lines": [], "available": False}
        return {"lines": result.stdout.splitlines(), "available": True}
