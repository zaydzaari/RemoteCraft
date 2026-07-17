import json
from pathlib import Path
from urllib.error import URLError

import pytest

from remotecraft.errors import NotFoundError, UpstreamError
from remotecraft.versions import MANIFEST_URL, VersionCatalog

DETAIL_URL = "https://piston-meta.mojang.com/v1/packages/release.json"
JAR_URL = "https://piston-data.mojang.com/v1/objects/server.jar"


class Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def manifest(detail_url: str = DETAIL_URL) -> dict:
    return {
        "versions": [
            {"id": "1.21.5", "type": "release", "url": detail_url},
            {"id": "25w01a", "type": "snapshot", "url": detail_url},
        ]
    }


def test_catalog_lists_releases_and_caches_manifest(tmp_path: Path) -> None:
    calls: list[str] = []

    def opener(request, timeout: int):  # type: ignore[no-untyped-def]
        calls.append(request.full_url)
        assert timeout == 10
        return Response(manifest())

    catalog = VersionCatalog(tmp_path / "versions.json", opener=opener, clock=lambda: 100)

    assert catalog.list_releases() == ["1.21.5"]
    assert catalog.list_releases() == ["1.21.5"]
    assert calls == [MANIFEST_URL]


def test_catalog_returns_verified_download_metadata(tmp_path: Path) -> None:
    payloads = {
        MANIFEST_URL: manifest(),
        DETAIL_URL: {"downloads": {"server": {"url": JAR_URL, "sha1": "a" * 40, "size": 1234}}},
    }

    def opener(request, timeout: int):  # type: ignore[no-untyped-def]
        assert timeout == 10
        return Response(payloads[request.full_url])

    catalog = VersionCatalog(tmp_path / "versions.json", opener=opener)
    download = catalog.get_vanilla_download("1.21.5")

    assert download.url == JAR_URL
    assert download.sha1 == "a" * 40
    assert download.size == 1234


def test_catalog_rejects_untrusted_metadata_url(tmp_path: Path) -> None:
    def opener(_request, timeout: int):  # type: ignore[no-untyped-def]
        assert timeout == 10
        return Response(manifest("https://evil.example/release.json"))

    catalog = VersionCatalog(tmp_path / "versions.json", opener=opener)

    with pytest.raises(UpstreamError, match="untrusted"):
        catalog.get_vanilla_download("1.21.5")


def test_catalog_uses_expired_cache_when_mojang_is_unavailable(tmp_path: Path) -> None:
    cache = tmp_path / "versions.json"
    cache.write_text(json.dumps({"timestamp": 0, "manifest": manifest()}), encoding="utf-8")

    def opener(_request, timeout: int):  # type: ignore[no-untyped-def]
        assert timeout == 10
        raise URLError("offline")

    catalog = VersionCatalog(cache, opener=opener, clock=lambda: 9999)
    assert catalog.list_releases() == ["1.21.5"]


def test_catalog_reports_unknown_release(tmp_path: Path) -> None:
    catalog = VersionCatalog(
        tmp_path / "versions.json", opener=lambda *_args, **_kwargs: Response(manifest())
    )

    with pytest.raises(NotFoundError):
        catalog.get_vanilla_download("1.0")
