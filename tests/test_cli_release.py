from pdrive_desktop.infrastructure.cli_release import OFFICIAL_LINUX_X64


def test_pinned_checksum_is_sha512() -> None:
    assert len(OFFICIAL_LINUX_X64.sha512) == 128
    int(OFFICIAL_LINUX_X64.sha512, 16)
