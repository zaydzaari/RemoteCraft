"""Shared data models."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ServerStatus = Literal["offline", "online", "starting", "stopping", "unknown"]


class ServerRecord(BaseModel):
    """Persistent server metadata kept on the RemoteCraft host."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[0-9a-f]{32}$")
    name: str
    version: str
    ram_gb: int = Field(ge=1, le=64)
    path: str
    screen_name: str
    jar_sha1: str = Field(pattern=r"^[0-9a-f]{40}$")
    status: ServerStatus = "offline"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ServerView(BaseModel):
    """Public server representation returned by the API."""

    id: str
    name: str
    version: str
    ram_gb: int
    status: ServerStatus
    created_at: datetime

    @classmethod
    def from_record(cls, record: ServerRecord, status: ServerStatus | None = None) -> "ServerView":
        return cls(
            id=record.id,
            name=record.name,
            version=record.version,
            ram_gb=record.ram_gb,
            status=status or record.status,
            created_at=record.created_at,
        )


class DownloadSpec(BaseModel):
    """Trusted Mojang download metadata."""

    url: str
    sha1: str = Field(pattern=r"^[0-9a-f]{40}$")
    size: int = Field(gt=0)
