import asyncio
from collections.abc import Sequence
from pathlib import Path

import pytest

from pdrive_desktop.application.errors import ErrorCategory
from pdrive_desktop.domain.drive import DriveNode, DrivePath, NodeKind
from pdrive_desktop.infrastructure.proton_cli import CliError, ProtonCliDriveGateway


class _ListingGateway(ProtonCliDriveGateway):
    def __init__(self, listings: dict[str, Sequence[DriveNode]]) -> None:
        self._listings = listings

    async def list_nodes(self, path: DrivePath) -> Sequence[DriveNode]:
        return self._listings.get(str(path), ())


def _node(parent: str, name: str, kind: NodeKind, size: int | None = None) -> DriveNode:
    path = DrivePath.parse(parent).child(name)
    return DriveNode(f"id-{name}", name, kind, path, size=size)


def test_backup_verification_counts_complete_remote_tree(tmp_path: Path) -> None:
    source = tmp_path / "Archive"
    nested = source / "Reports"
    nested.mkdir(parents=True)
    (source / "notes.txt").write_bytes(b"notes")
    (nested / "annual.pdf").write_bytes(b"report")
    root = "/my-files/Archive"
    reports = f"{root}/Reports"
    gateway = _ListingGateway(
        {
            root: (
                _node(root, "notes.txt", NodeKind.FILE, 5),
                _node(root, "Reports", NodeKind.FOLDER),
            ),
            reports: (_node(reports, "annual.pdf", NodeKind.FILE, 6),),
        }
    )

    report = asyncio.run(
        gateway._verify_backup_tree(source, DrivePath.parse(root))
    )

    assert report.complete
    assert report.verified_files == 2
    assert report.verified_folders == 2


def test_backup_verification_reports_missing_and_size_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "Archive"
    source.mkdir()
    (source / "missing.txt").write_bytes(b"missing")
    (source / "changed.txt").write_bytes(b"local")
    root = "/my-files/Archive"
    gateway = _ListingGateway(
        {root: (_node(root, "changed.txt", NodeKind.FILE, 999),)}
    )

    report = asyncio.run(
        gateway._verify_backup_tree(source, DrivePath.parse(root))
    )

    assert not report.complete
    assert report.missing_items == 1
    assert report.mismatched_items == 1


def test_backup_preflight_rejects_nested_symlink(tmp_path: Path) -> None:
    source = tmp_path / "Archive"
    source.mkdir()
    (source / "private-link").symlink_to("/etc/passwd")

    with pytest.raises(CliError) as captured:
        ProtonCliDriveGateway._validate_backup_tree(source)

    assert captured.value.category is ErrorCategory.PERMISSION
