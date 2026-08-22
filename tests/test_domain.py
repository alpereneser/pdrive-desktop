import pytest

from pdrive_desktop.domain.drive import DrivePath


def test_drive_path_requires_absolute_path() -> None:
    with pytest.raises(ValueError):
        DrivePath("my-files")


def test_drive_path_rejects_parent_traversal() -> None:
    with pytest.raises(ValueError):
        DrivePath.parse("/my-files/../secrets")


def test_drive_path_accepts_proton_root() -> None:
    assert str(DrivePath.parse("/my-files")) == "/my-files"


def test_child_escapes_slash_and_backslash() -> None:
    path = DrivePath.parse("/my-files").child("reports/2026\\final")
    assert str(path) == "/my-files/reports\\/2026\\\\final"
