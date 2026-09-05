import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from pdrive_desktop.application.errors import SafeApplicationError
from pdrive_desktop.domain.update import AppVersion
from pdrive_desktop.infrastructure.app_update import VerifiedUpdateService


def _service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    version: str = "v0.1.4",
    package: bytes = b"package",
    manifest_digest: str | None = None,
    fail_verification: bool = False,
) -> tuple[VerifiedUpdateService, list[tuple[str, ...]]]:
    tool = tmp_path / "gh"
    tool.write_text("tool", encoding="utf-8")
    tool.chmod(0o700)
    monkeypatch.setattr("shutil.which", lambda _name: str(tool))
    commands: list[tuple[str, ...]] = []
    package_name = f"pdrive-desktop_{version.removeprefix('v')}_amd64.deb"
    digest = manifest_digest or hashlib.sha256(package).hexdigest()
    manifest = f"{digest}  {package_name}\n".encode()

    def run(command: tuple[str, ...], _timeout: float) -> subprocess.CompletedProcess[bytes]:
        commands.append(tuple(command))
        if command[1:3] == ("release", "view"):
            payload = json.dumps(
                {
                    "tagName": version,
                    "isDraft": False,
                    "isPrerelease": False,
                    "assets": [
                        {"name": package_name, "size": len(package)},
                        {"name": "SHA256SUMS", "size": len(manifest)},
                    ],
                }
            ).encode()
            return subprocess.CompletedProcess(command, 0, payload, b"")
        if command[1:3] == ("release", "download"):
            directory = Path(command[command.index("--dir") + 1])
            (directory / package_name).write_bytes(package)
            (directory / "SHA256SUMS").write_bytes(manifest)
            return subprocess.CompletedProcess(command, 0, b"", b"")
        return subprocess.CompletedProcess(command, int(fail_verification), b"", b"")

    return VerifiedUpdateService(command_runner=run), commands


def test_prepares_only_new_digest_and_provenance_verified_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, commands = _service(tmp_path, monkeypatch)
    try:
        update = service.prepare(AppVersion.parse("0.1.3"))
        assert update is not None
        assert update.version == AppVersion.parse("0.1.4")
        verification = commands[-1]
        assert "alpereneser/pdrive-desktop" in verification
        assert "github.com/alpereneser/pdrive-desktop/.github/workflows/release.yml" in verification
        assert "--deny-self-hosted-runners" in verification
    finally:
        service.cleanup()


def test_rejects_manifest_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _commands = _service(tmp_path, monkeypatch, manifest_digest="0" * 64)
    with pytest.raises(SafeApplicationError, match="SHA-256"):
        service.prepare(AppVersion.parse("0.1.3"))
    service.cleanup()


def test_rejects_failed_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _commands = _service(tmp_path, monkeypatch, fail_verification=True)
    with pytest.raises(SafeApplicationError, match="provenansı"):
        service.prepare(AppVersion.parse("0.1.3"))
    service.cleanup()


def test_rejects_downgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, commands = _service(tmp_path, monkeypatch, version="v0.1.2")
    assert service.prepare(AppVersion.parse("0.1.3")) is None
    assert len(commands) == 1


def test_timeout_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = tmp_path / "gh"
    tool.write_text("tool", encoding="utf-8")
    tool.chmod(0o700)
    monkeypatch.setattr("shutil.which", lambda _name: str(tool))

    def timeout(_command: tuple[str, ...], seconds: float) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired("gh", seconds)

    with pytest.raises(SafeApplicationError, match="zaman aşımına"):
        VerifiedUpdateService(command_runner=timeout).prepare(AppVersion.parse("0.1.3"))
