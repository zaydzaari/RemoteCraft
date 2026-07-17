"""Mojang version discovery and trusted download metadata."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from remotecraft.errors import NotFoundError, UpstreamError
from remotecraft.models import DownloadSpec

MANIFEST_URL = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
ALLOWED_MOJANG_HOSTS = {
    "launcher.mojang.com",
    "launchermeta.mojang.com",
    "piston-data.mojang.com",
    "piston-meta.mojang.com",
}


class VersionCatalog:
    def __init__(
        self,
        cache_path: Path,
        *,
        ttl_seconds: int = 3600,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.cache_path = cache_path
        self.ttl_seconds = ttl_seconds
        self.opener = opener
        self.clock = clock

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_MOJANG_HOSTS:
            raise UpstreamError("Mojang returned an untrusted download URL")
        if parsed.username or parsed.password or parsed.fragment:
            raise UpstreamError("Mojang returned an invalid URL")

    def _fetch_json(self, url: str) -> dict[str, Any]:
        self._validate_url(url)
        request = Request(  # noqa: S310 - _validate_url permits trusted HTTPS hosts only.
            url, headers={"User-Agent": "RemoteCraft/0.2"}
        )
        try:
            with self.opener(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise UpstreamError("Could not reach Mojang's version service") from exc
        if not isinstance(payload, dict):
            raise UpstreamError("Mojang returned an unexpected response")
        return payload

    def _read_cache(self) -> tuple[dict[str, Any] | None, bool]:
        try:
            cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            manifest = cache.get("manifest")
            timestamp = float(cache.get("timestamp", 0))
            if isinstance(manifest, dict):
                return manifest, self.clock() - timestamp < self.ttl_seconds
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return None, False

    def _write_cache(self, manifest: dict[str, Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"timestamp": self.clock(), "manifest": manifest}
        self.cache_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _manifest(self) -> dict[str, Any]:
        cached, fresh = self._read_cache()
        if fresh and cached:
            return cached
        try:
            manifest = self._fetch_json(MANIFEST_URL)
            self._write_cache(manifest)
            return manifest
        except UpstreamError:
            if cached:
                return cached
            raise

    def list_releases(self, limit: int = 30) -> list[str]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        versions = self._manifest().get("versions", [])
        return [
            item["id"]
            for item in versions
            if isinstance(item, dict)
            and item.get("type") == "release"
            and isinstance(item.get("id"), str)
        ][:limit]

    def get_vanilla_download(self, version: str) -> DownloadSpec:
        versions = self._manifest().get("versions", [])
        entry = next(
            (
                item
                for item in versions
                if isinstance(item, dict)
                and item.get("id") == version
                and item.get("type") == "release"
            ),
            None,
        )
        if not entry:
            raise NotFoundError("Minecraft release not found")
        detail_url = entry.get("url")
        if not isinstance(detail_url, str):
            raise UpstreamError("Mojang did not provide release metadata")
        details = self._fetch_json(detail_url)
        server = details.get("downloads", {}).get("server")
        if not isinstance(server, dict):
            raise UpstreamError("This release does not include a server download")
        url = server.get("url")
        sha1 = server.get("sha1")
        size = server.get("size")
        if not isinstance(url, str) or not isinstance(sha1, str) or not isinstance(size, int):
            raise UpstreamError("Mojang returned incomplete server metadata")
        self._validate_url(url)
        if not re.fullmatch(r"[0-9a-f]{40}", sha1):
            raise UpstreamError("Mojang returned an invalid server checksum")
        return DownloadSpec(url=url, sha1=sha1, size=size)
