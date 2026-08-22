import asyncio
import json
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pdrive_desktop.domain.drive import DrivePath, NodeKind
from pdrive_desktop.infrastructure.proton_cli import (
    ProtonCliDriveGateway,
    SecureCliRunner,
)


def test_runner_rejects_group_writable_executable(tmp_path: Path) -> None:
    executable = tmp_path / "proton-drive"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IWGRP)

    with pytest.raises(ValueError, match="writable"):
        SecureCliRunner(executable)


def test_runner_rejects_non_allowlisted_operation(tmp_path: Path) -> None:
    executable = tmp_path / "proton-drive"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    runner = SecureCliRunner(executable)

    with pytest.raises(ValueError, match="not allowed"):
        asyncio.run(runner.run(("filesystem", "remove"), ("/my-files/x",)))


def test_gateway_parses_official_cli_node_contract(tmp_path: Path) -> None:
    payload = [
        {
            "uid": "node-123",
            "name": {"ok": True, "value": "Reports/2026"},
            "type": "file",
            "modificationTime": "2026-08-22T10:30:00.000Z",
            "activeRevision": {"claimedSize": 2048},
        }
    ]
    executable = tmp_path / "proton-drive"
    executable.write_text(f"#!/bin/sh\nprintf '%s' '{json.dumps(payload)}'\n")
    executable.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    gateway = ProtonCliDriveGateway(SecureCliRunner(executable))

    nodes = asyncio.run(gateway.list_nodes(DrivePath.parse("/my-files")))

    assert len(nodes) == 1
    assert nodes[0].kind is NodeKind.FILE
    assert nodes[0].size == 2048
    assert nodes[0].modified_at == datetime(2026, 8, 22, 10, 30, tzinfo=UTC)
    assert str(nodes[0].path) == "/my-files/Reports\\/2026"
