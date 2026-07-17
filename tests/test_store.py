from pathlib import Path

import pytest

from remotecraft.errors import NotFoundError, StoreError
from remotecraft.models import ServerRecord
from remotecraft.store import ServerStore


def record(server_id: str = "a" * 32, name: str = "survival") -> ServerRecord:
    return ServerRecord(
        id=server_id,
        name=name,
        version="1.21.5",
        ram_gb=4,
        path=f"/srv/minecraft/{name}-{server_id[:8]}",
        screen_name=f"rc-{server_id[:12]}",
        jar_sha1="b" * 40,
    )


def test_store_round_trip_update_and_remove(tmp_path: Path) -> None:
    store = ServerStore(tmp_path)
    created = store.add(record())

    assert store.get(created.id) == created
    assert store.list() == [created]

    updated = store.update(created.id, status="online")
    assert updated.status == "online"
    assert ServerStore(tmp_path).get(created.id).status == "online"

    assert store.remove(created.id).id == created.id
    assert store.list() == []


def test_store_rejects_duplicate_ids(tmp_path: Path) -> None:
    store = ServerStore(tmp_path)
    store.add(record())

    with pytest.raises(StoreError, match="Duplicate"):
        store.add(record(name="creative"))


def test_store_reports_missing_records(tmp_path: Path) -> None:
    store = ServerStore(tmp_path)

    with pytest.raises(NotFoundError):
        store.get("f" * 32)


def test_store_rejects_corrupt_metadata(tmp_path: Path) -> None:
    store = ServerStore(tmp_path)
    store.path.write_text("not-json", encoding="utf-8")

    with pytest.raises(StoreError, match="Could not read"):
        store.list()


def test_store_validates_updates(tmp_path: Path) -> None:
    store = ServerStore(tmp_path)
    created = store.add(record())

    with pytest.raises(StoreError, match="Invalid server metadata update"):
        store.update(created.id, status="teleporting")

    assert store.get(created.id).status == "offline"
