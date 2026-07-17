from datetime import UTC, datetime

from fastapi.testclient import TestClient

from remotecraft.api import create_app
from remotecraft.config import Settings
from remotecraft.errors import ConflictError
from remotecraft.models import ServerView


class Catalog:
    def list_releases(self, limit: int) -> list[str]:
        assert limit <= 100
        return ["1.21.5", "1.21.4"][:limit]


class FakeService:
    def __init__(self) -> None:
        self.catalog = Catalog()
        self.calls: list[tuple[str, object]] = []
        self.server = ServerView(
            id="a" * 32,
            name="survival",
            version="1.21.5",
            ram_gb=4,
            status="offline",
            created_at=datetime(2026, 7, 17, tzinfo=UTC),
        )

    def check_host(self) -> dict[str, object]:
        return {"ready": True, "tools": {"java": True}}

    def list_servers(self) -> list[ServerView]:
        return [self.server]

    def create_server(self, **payload: object) -> ServerView:
        self.calls.append(("create", payload))
        return self.server

    def start_server(self, server_id: str) -> ServerView:
        self.calls.append(("start", server_id))
        return self.server

    def stop_server(self, server_id: str) -> ServerView:
        self.calls.append(("stop", server_id))
        return self.server

    def restart_server(self, server_id: str) -> ServerView:
        self.calls.append(("restart", server_id))
        return self.server

    def kill_server(self, server_id: str) -> ServerView:
        self.calls.append(("kill", server_id))
        return self.server

    def delete_server(self, server_id: str, *, confirm: str) -> ServerView:
        self.calls.append(("delete", (server_id, confirm)))
        return self.server

    def send_command(self, server_id: str, command: str) -> dict[str, str]:
        self.calls.append(("command", (server_id, command)))
        return {"status": "sent"}

    def get_logs(self, server_id: str, lines: int) -> dict[str, object]:
        self.calls.append(("logs", (server_id, lines)))
        return {"available": True, "lines": ["ready"]}


def build_client(settings: Settings) -> tuple[TestClient, FakeService, dict[str, str]]:
    service = FakeService()
    app = create_app(settings, service)  # type: ignore[arg-type]
    return TestClient(app), service, {"Authorization": f"Bearer {settings.api_token}"}


def test_dashboard_health_and_security_headers(settings: Settings) -> None:
    client, _service, _headers = build_client(settings)

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "RemoteCraft" in dashboard.text
    assert client.get("/assets/app.js").status_code == 200

    health = client.get("/api/health")
    assert health.json()["status"] == "ok"
    assert health.headers["cache-control"] == "no-store"
    assert health.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in health.headers["content-security-policy"]
    assert health.headers["cross-origin-opener-policy"] == "same-origin"


def test_protected_routes_require_valid_bearer_token(settings: Settings) -> None:
    client, _service, headers = build_client(settings)

    assert client.get("/api/servers").status_code == 401
    assert (
        client.get("/api/servers", headers={"Authorization": "Bearer incorrect"}).status_code == 401
    )
    assert client.get("/api/servers", headers=headers).status_code == 200


def test_inventory_host_and_versions_routes(settings: Settings) -> None:
    client, _service, headers = build_client(settings)

    assert client.get("/api/host", headers=headers).json()["ready"] is True
    assert client.get("/api/versions?limit=1", headers=headers).json() == {"versions": ["1.21.5"]}
    assert client.get("/api/versions?limit=101", headers=headers).status_code == 422


def test_create_validates_eula_and_calls_service(settings: Settings) -> None:
    client, service, headers = build_client(settings)
    payload = {
        "name": "survival",
        "version": "1.21.5",
        "ram_gb": 4,
        "accept_eula": False,
    }

    assert client.post("/api/servers", headers=headers, json=payload).status_code == 422
    payload["accept_eula"] = True
    response = client.post("/api/servers", headers=headers, json=payload)

    assert response.status_code == 201
    assert service.calls == [("create", payload)]


def test_lifecycle_console_logs_and_delete_routes(settings: Settings) -> None:
    client, service, headers = build_client(settings)
    server_id = "a" * 32

    for action in ("start", "stop", "restart", "kill"):
        assert client.post(f"/api/servers/{server_id}/{action}", headers=headers).status_code == 200
    assert client.post(
        f"/api/servers/{server_id}/command",
        headers=headers,
        json={"command": "list"},
    ).json() == {"status": "sent"}
    assert client.get(f"/api/servers/{server_id}/logs?lines=25", headers=headers).json() == {
        "available": True,
        "lines": ["ready"],
    }
    assert (
        client.delete(f"/api/servers/{server_id}?confirm=survival", headers=headers).status_code
        == 200
    )

    assert [name for name, _ in service.calls] == [
        "start",
        "stop",
        "restart",
        "kill",
        "command",
        "logs",
        "delete",
    ]


def test_domain_errors_have_stable_json_shape(settings: Settings) -> None:
    client, service, headers = build_client(settings)

    def conflict(_server_id: str) -> ServerView:
        raise ConflictError("server is busy")

    service.start_server = conflict  # type: ignore[method-assign]
    response = client.post(f"/api/servers/{'a' * 32}/start", headers=headers)

    assert response.status_code == 409
    assert response.json() == {"error": "conflict", "detail": "server is busy"}
