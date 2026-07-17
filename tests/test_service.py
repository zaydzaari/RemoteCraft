import shlex
from collections.abc import Callable
from contextlib import contextmanager

import pytest

from remotecraft.config import Settings
from remotecraft.errors import ConflictError, InvalidRequestError, RemoteCommandError
from remotecraft.models import DownloadSpec, ServerRecord
from remotecraft.service import MinecraftService
from remotecraft.ssh import CommandResult
from remotecraft.store import ServerStore


class Catalog:
    def get_vanilla_download(self, version: str) -> DownloadSpec:
        assert version == "1.21.5"
        return DownloadSpec(
            url="https://piston-data.mojang.com/v1/objects/server.jar",
            sha1="b" * 40,
            size=1234,
        )


class FakeRemote:
    def __init__(
        self,
        responder: Callable[[str, bool, int | None], CommandResult] | None = None,
    ) -> None:
        self.commands: list[tuple[str, bool, int | None]] = []
        self.responder = responder or self._default_response

    @staticmethod
    def _default_response(command: str, _check: bool, _timeout: int | None) -> CommandResult:
        if command.startswith("for tool in"):
            return CommandResult("java=ok\nscreen=ok\ncurl=ok\nsha1sum=ok\n", "", 0)
        if " -Q select " in command:
            return CommandResult("", "", 1)
        return CommandResult("", "", 0)

    def run(self, command: str, *, check: bool = True, timeout: int | None = None) -> CommandResult:
        self.commands.append((command, check, timeout))
        result = self.responder(command, check, timeout)
        if check and result.exit_status != 0:
            raise RemoteCommandError(result.stderr or "command failed")
        return result


def build_service(
    settings: Settings,
    remote: FakeRemote,
    *,
    sleeper: Callable[[float], None] = lambda _seconds: None,
) -> MinecraftService:
    @contextmanager
    def session_factory():
        yield remote

    return MinecraftService(
        settings,
        ServerStore(settings.data_dir),
        Catalog(),  # type: ignore[arg-type]
        session_factory=session_factory,
        sleeper=sleeper,
    )


def add_record(
    store: ServerStore, *, path: str = "/srv/minecraft/survival-aaaaaaaa"
) -> ServerRecord:
    return store.add(
        ServerRecord(
            id="a" * 32,
            name="survival",
            version="1.21.5",
            ram_gb=4,
            path=path,
            screen_name="rc-aaaaaaaaaaaa",
            jar_sha1="b" * 40,
        )
    )


def test_empty_inventory_does_not_open_ssh(settings: Settings) -> None:
    calls = 0

    @contextmanager
    def unexpected_session():
        nonlocal calls
        calls += 1
        yield FakeRemote()

    service = MinecraftService(
        settings,
        ServerStore(settings.data_dir),
        Catalog(),  # type: ignore[arg-type]
        session_factory=unexpected_session,
    )

    assert service.list_servers() == []
    assert calls == 0


def test_host_check_reports_required_tools(settings: Settings) -> None:
    remote = FakeRemote()
    service = build_service(settings, remote)

    assert service.check_host() == {
        "ready": True,
        "tools": {"java": True, "screen": True, "curl": True, "sha1sum": True},
    }


def test_create_server_verifies_download_and_records_metadata(settings: Settings) -> None:
    remote = FakeRemote()
    service = build_service(settings, remote)

    created = service.create_server(name="survival", version="1.21.5", ram_gb=4, accept_eula=True)

    record = service.store.get(created.id)
    assert created.status == "offline"
    assert record.path.startswith("/srv/minecraft/survival-")
    setup = next(command for command, _, _ in remote.commands if "curl --fail" in command)
    assert "sha1sum --check --status" in setup
    assert "eula=true" in setup
    assert "piston-data.mojang.com" in setup


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": "x; reboot"}, "Server name"),
        ({"version": "1.21; reboot"}, "Invalid Minecraft version"),
        ({"ram_gb": 99}, "RAM must be"),
        ({"accept_eula": False}, "EULA"),
    ],
)
def test_create_server_rejects_invalid_inputs(
    settings: Settings, kwargs: dict[str, object], message: str
) -> None:
    remote = FakeRemote()
    service = build_service(settings, remote)
    payload: dict[str, object] = {
        "name": "survival",
        "version": "1.21.5",
        "ram_gb": 4,
        "accept_eula": True,
    }
    payload.update(kwargs)

    with pytest.raises(InvalidRequestError, match=message):
        service.create_server(**payload)  # type: ignore[arg-type]

    assert remote.commands == []


def test_create_rejects_duplicate_names_case_insensitively(settings: Settings) -> None:
    remote = FakeRemote()
    service = build_service(settings, remote)
    add_record(service.store)

    with pytest.raises(ConflictError, match="already exists"):
        service.create_server(name="SURVIVAL", version="1.21.5", ram_gb=4, accept_eula=True)


def test_create_requires_remote_tools(settings: Settings) -> None:
    def respond(command: str, _check: bool, _timeout: int | None) -> CommandResult:
        if command.startswith("for tool in"):
            return CommandResult("java=ok\nscreen=missing\ncurl=ok\nsha1sum=ok\n", "", 0)
        return CommandResult("", "", 0)

    service = build_service(settings, FakeRemote(respond))

    with pytest.raises(ConflictError, match="screen"):
        service.create_server(name="survival", version="1.21.5", ram_gb=4, accept_eula=True)


def test_create_rolls_back_remote_directory_on_setup_failure(settings: Settings) -> None:
    def respond(command: str, _check: bool, _timeout: int | None) -> CommandResult:
        if command.startswith("for tool in"):
            return FakeRemote._default_response(command, True, None)
        if "curl --fail" in command:
            raise RemoteCommandError("download failed")
        return CommandResult("", "", 0)

    remote = FakeRemote(respond)
    service = build_service(settings, remote)

    with pytest.raises(RemoteCommandError, match="download failed"):
        service.create_server(name="survival", version="1.21.5", ram_gb=4, accept_eula=True)

    assert service.store.list() == []
    assert any(command.startswith("rm -rf --") for command, _, _ in remote.commands)


def test_list_servers_uses_screen_inventory(settings: Settings) -> None:
    def respond(command: str, _check: bool, _timeout: int | None) -> CommandResult:
        if command == "screen -ls":
            return CommandResult("123.rc-aaaaaaaaaaaa (Detached)\n", "", 0)
        return CommandResult("", "", 0)

    service = build_service(settings, FakeRemote(respond))
    add_record(service.store)

    assert service.list_servers()[0].status == "online"


def test_start_stop_kill_and_restart_server(settings: Settings) -> None:
    running = False

    def respond(command: str, _check: bool, _timeout: int | None) -> CommandResult:
        nonlocal running
        if " -Q select " in command:
            return CommandResult("", "", 0 if running else 1)
        if command.startswith("screen -DmS"):
            running = True
        if " -X stuff " in command or " -X quit" in command:
            running = False
        return CommandResult("", "", 0)

    remote = FakeRemote(respond)
    service = build_service(settings, remote)
    record = add_record(service.store)

    assert service.start_server(record.id).status == "starting"
    assert service.start_server(record.id).status == "online"
    assert service.stop_server(record.id).status == "stopping"
    assert service.stop_server(record.id).status == "offline"
    assert service.restart_server(record.id).status == "starting"
    assert service.kill_server(record.id).status == "offline"
    assert any("exec java -Xms1G -Xmx4G" in command for command, _, _ in remote.commands)


def test_restart_times_out_when_server_will_not_stop(settings: Settings) -> None:
    remote = FakeRemote(lambda _command, _check, _timeout: CommandResult("", "", 0))
    service = build_service(settings, remote)
    record = add_record(service.store)

    with pytest.raises(ConflictError, match="30 seconds"):
        service.restart_server(record.id)


def test_send_command_quotes_payload_as_one_shell_argument(settings: Settings) -> None:
    remote = FakeRemote(lambda _command, _check, _timeout: CommandResult("", "", 0))
    service = build_service(settings, remote)
    record = add_record(service.store)
    raw = "say hello; touch /tmp/not-created"

    assert service.send_command(record.id, raw) == {"status": "sent"}
    command = remote.commands[-1][0]
    assert shlex.split(command)[-1] == raw + "\n"

    with pytest.raises(InvalidRequestError):
        service.send_command(record.id, "say hello\nstop")


def test_send_command_requires_online_server(settings: Settings) -> None:
    service = build_service(settings, FakeRemote())
    record = add_record(service.store)

    with pytest.raises(ConflictError, match="offline"):
        service.send_command(record.id, "list")


def test_delete_requires_confirmation_offline_state_and_safe_parent(settings: Settings) -> None:
    remote = FakeRemote()
    service = build_service(settings, remote)
    record = add_record(service.store)

    with pytest.raises(InvalidRequestError, match="exactly match"):
        service.delete_server(record.id, confirm="wrong")

    assert service.delete_server(record.id, confirm="survival").name == "survival"
    assert service.store.list() == []
    assert remote.commands[-1][0].startswith("rm -rf --")

    unsafe = add_record(service.store, path="/home/minecraft/survival-aaaaaaaa")
    with pytest.raises(RemoteCommandError, match="outside"):
        service.delete_server(unsafe.id, confirm="survival")


def test_delete_rejects_running_server(settings: Settings) -> None:
    remote = FakeRemote(lambda _command, _check, _timeout: CommandResult("", "", 0))
    service = build_service(settings, remote)
    record = add_record(service.store)

    with pytest.raises(ConflictError, match="Stop the server"):
        service.delete_server(record.id, confirm="survival")


def test_get_logs_handles_present_and_missing_files(settings: Settings) -> None:
    def respond(command: str, _check: bool, _timeout: int | None) -> CommandResult:
        if "tail -n 25" in command:
            return CommandResult("line one\nline two\n", "", 0)
        return CommandResult("", "", 1)

    service = build_service(settings, FakeRemote(respond))
    record = add_record(service.store)

    assert service.get_logs(record.id, 25) == {
        "lines": ["line one", "line two"],
        "available": True,
    }
    assert service.get_logs(record.id, 30) == {"lines": [], "available": False}
    with pytest.raises(InvalidRequestError):
        service.get_logs(record.id, 501)
