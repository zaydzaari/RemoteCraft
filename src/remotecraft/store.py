"""Thread-safe JSON persistence for managed server metadata."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from pydantic import ValidationError

from remotecraft.errors import NotFoundError, StoreError
from remotecraft.models import ServerRecord


class ServerStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.path = data_dir / "servers.json"
        self._lock = threading.RLock()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    def _read(self) -> list[ServerRecord]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise StoreError("Server metadata must contain a JSON array")
            return [ServerRecord.model_validate(item) for item in raw]
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise StoreError("Could not read server metadata") from exc

    def _write(self, records: list[ServerRecord]) -> None:
        payload = json.dumps(
            [record.model_dump(mode="json") for record in records], indent=2, sort_keys=True
        )
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.data_dir, delete=False
            ) as handle:
                handle.write(payload + "\n")
                temp_path = Path(handle.name)
            os.replace(temp_path, self.path)
        except OSError as exc:
            raise StoreError("Could not write server metadata") from exc

    def list(self) -> list[ServerRecord]:
        with self._lock:
            return self._read()

    def get(self, server_id: str) -> ServerRecord:
        with self._lock:
            for record in self._read():
                if record.id == server_id:
                    return record
        raise NotFoundError("Server not found")

    def add(self, record: ServerRecord) -> ServerRecord:
        with self._lock:
            records = self._read()
            if any(existing.id == record.id for existing in records):
                raise StoreError("Duplicate server identifier")
            records.append(record)
            self._write(records)
        return record

    def update(self, server_id: str, **changes: object) -> ServerRecord:
        with self._lock:
            records = self._read()
            for index, record in enumerate(records):
                if record.id == server_id:
                    try:
                        records[index] = ServerRecord.model_validate(
                            {**record.model_dump(), **changes}
                        )
                    except ValidationError as exc:
                        raise StoreError("Invalid server metadata update") from exc
                    self._write(records)
                    return records[index]
        raise NotFoundError("Server not found")

    def remove(self, server_id: str) -> ServerRecord:
        with self._lock:
            records = self._read()
            for index, record in enumerate(records):
                if record.id == server_id:
                    removed = records.pop(index)
                    self._write(records)
                    return removed
        raise NotFoundError("Server not found")
