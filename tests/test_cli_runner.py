import asyncio
import json
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pdrive_desktop.domain.drive import DrivePath, NodeKind
from pdrive_desktop.infrastructure.proton_cli import (
    CliError,
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


def test_staged_download_commits_file_without_overwrite(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    destination = tmp_path / "destination"
    staging.mkdir()
    destination.mkdir()
    staged_file = staging / "report.txt"
    local_file = destination / "report.txt"
    staged_file.write_text("remote", encoding="utf-8")
    local_file.write_text("local", encoding="utf-8")

    ProtonCliDriveGateway._commit_staged_download(staged_file, local_file)

    assert local_file.read_text(encoding="utf-8") == "local"
    assert staged_file.read_text(encoding="utf-8") == "remote"


def test_staged_download_commits_nested_tree(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    destination = tmp_path / "destination"
    nested = staging / "Documents" / "Reports"
    nested.mkdir(parents=True)
    destination.mkdir()
    (nested / "report.txt").write_text("verified", encoding="utf-8")

    ProtonCliDriveGateway._commit_staged_download(
        staging / "Documents", destination / "Documents"
    )

    assert (destination / "Documents" / "Reports" / "report.txt").read_text(
        encoding="utf-8"
    ) == "verified"


def test_staged_download_rejects_symbolic_link(tmp_path: Path) -> None:
    source = tmp_path / "link"
    source.symlink_to("/etc/passwd")

    with pytest.raises(CliError, match="symbolic link"):
        ProtonCliDriveGateway._commit_staged_download(source, tmp_path / "output")
