from __future__ import annotations

import asyncio
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pdrive_desktop.domain.drive import DrivePath, NodeKind
from pdrive_desktop.infrastructure.app_paths import AppPaths
from pdrive_desktop.infrastructure.cli_release import OFFICIAL_LINUX_X64
from pdrive_desktop.infrastructure.proton_cli import (
    ProtonCliDriveGateway,
    SecureCliRunner,
)


class DomainSecurityTests(unittest.TestCase):
    def test_rejects_relative_and_traversing_paths(self) -> None:
        for raw in ("relative", "/my-files/../secret"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                DrivePath.parse(raw)

    def test_escapes_remote_node_separators(self) -> None:
        child = DrivePath.parse("/my-files").child("Reports/2026\\final")
        self.assertEqual(str(child), "/my-files/Reports\\/2026\\\\final")

    def test_official_checksum_has_sha512_shape(self) -> None:
        self.assertEqual(len(OFFICIAL_LINUX_X64.sha512), 128)
        int(OFFICIAL_LINUX_X64.sha512, 16)


class CliBoundaryTests(unittest.TestCase):
    def _executable(self, directory: str, body: str) -> Path:
        executable = Path(directory) / "proton-drive"
        executable.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        executable.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        return executable

    def test_rejects_destructive_command_outside_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = SecureCliRunner(self._executable(directory, "exit 0"))
            with self.assertRaises(ValueError):
                asyncio.run(
                    runner.run(("filesystem", "delete"), ("/my-files/private",))
                )

    def test_parses_official_node_contract(self) -> None:
        payload = [
            {
                "uid": "node-123",
                "name": {"ok": True, "value": "Reports/2026"},
                "type": "file",
                "modificationTime": "2026-08-22T10:30:00.000Z",
                "activeRevision": {"claimedSize": 2048},
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            encoded = json.dumps(payload)
            executable = self._executable(directory, f"printf '%s' '{encoded}'")
            gateway = ProtonCliDriveGateway(SecureCliRunner(executable))
            nodes = asyncio.run(gateway.list_nodes(DrivePath.parse("/my-files")))
        self.assertEqual(len(nodes), 1)
        self.assertIs(nodes[0].kind, NodeKind.FILE)
        self.assertEqual(nodes[0].size, 2048)
        self.assertEqual(str(nodes[0].path), "/my-files/Reports\\/2026")

    def test_rejects_group_writable_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = self._executable(directory, "exit 0")
            executable.chmod(executable.stat().st_mode | stat.S_IWGRP)
            with self.assertRaises(ValueError):
                SecureCliRunner(executable)

    def test_parses_device_as_navigable_folder(self) -> None:
        item = {
            "uid": "device-1",
            "name": {"ok": True, "value": "Alperen PC"},
            "type": "Linux",
            "rootFolderUid": "root-1",
            "creationTime": "2026-08-20T10:00:00Z",
        }
        node = ProtonCliDriveGateway._parse_listing_item(
            item, DrivePath.parse("/devices")
        )
        self.assertIs(node.kind, NodeKind.FOLDER)
        self.assertEqual(str(node.path), "/devices/Alperen PC")

    def test_parses_photo_contract(self) -> None:
        item = {
            "uid": "photo-1",
            "name": {"ok": True, "value": "holiday.jpg"},
            "type": "photo",
            "creationTime": "2026-08-20T10:00:00Z",
            "activeRevision": {"claimedSize": 4096},
        }
        node = ProtonCliDriveGateway._parse_listing_item(
            item, DrivePath.parse("/photos")
        )
        self.assertIs(node.kind, NodeKind.PHOTO)
        self.assertEqual(node.size, 4096)


class PrivacyBoundaryTests(unittest.TestCase):
    def test_flatpak_uses_bundled_official_cli(self) -> None:
        with patch.dict(
            "os.environ",
            {"FLATPAK_ID": "io.github.alpereneser.pdrive-desktop"},
            clear=True,
        ):
            paths = AppPaths.from_environment()
            self.assertEqual(paths.cli_executable, Path("/app/libexec/proton-drive"))

    def test_runtime_has_no_direct_http_client(self) -> None:
        runtime_targets = (
            Path("src/pdrive_desktop/domain"),
            Path("src/pdrive_desktop/application"),
            Path("src/pdrive_desktop/presentation"),
            Path("src/pdrive_desktop/infrastructure/proton_cli.py"),
        )
        forbidden = (
            "import requests",
            "from requests",
            "import httpx",
            "from httpx",
            "import aiohttp",
            "from aiohttp",
            "import urllib.request",
            "from urllib import request",
            "import socket",
            "from socket",
        )
        for target in runtime_targets:
            files = target.rglob("*.py") if target.is_dir() else (target,)
            for source_file in files:
                source = source_file.read_text(encoding="utf-8")
                self.assertFalse(
                    any(token in source for token in forbidden),
                    f"Direct network client found in {source_file}",
                )


if __name__ == "__main__":
    unittest.main()
