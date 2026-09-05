from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pdrive_desktop.application.errors import ErrorCategory, SafeApplicationError
from pdrive_desktop.domain.update import AppVersion, PreparedUpdate

_REPOSITORY = "alpereneser/pdrive-desktop"
_SIGNER_WORKFLOW = (
    "github.com/alpereneser/pdrive-desktop/.github/workflows/release.yml"
)
_MAX_PACKAGE_BYTES = 250 * 1024 * 1024
_MAX_METADATA_BYTES = 1024 * 1024
CommandRunner = Callable[[Sequence[str], float], subprocess.CompletedProcess[bytes]]


def _run(command: Sequence[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
        env={
            key: os.environ[key]
            for key in ("HOME", "PATH", "XDG_CONFIG_HOME")
            if key in os.environ
        }
        | {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "NO_COLOR": "1"},
    )


class VerifiedUpdateService:
    """Prepares only repository-bound, digest- and provenance-verified packages."""

    def __init__(self, *, command_runner: CommandRunner = _run) -> None:
        self._run = command_runner
        self._temporary: tempfile.TemporaryDirectory[str] | None = None

    def prepare(self, current: AppVersion) -> PreparedUpdate | None:
        gh = self._trusted_tool("gh")
        release = self._release_metadata(gh)
        if bool(release.get("isDraft")) or bool(release.get("isPrerelease")):
            return None
        version = AppVersion.parse(str(release["tagName"]))
        if version <= current:
            return None
        package_name = f"pdrive-desktop_{version}_amd64.deb"
        sizes = self._asset_sizes(release.get("assets"))
        if package_name not in sizes or "SHA256SUMS" not in sizes:
            raise self._failure("Güncelleme gerekli doğrulama dosyalarını içermiyor.")
        if not 0 < sizes[package_name] <= _MAX_PACKAGE_BYTES:
            raise self._failure("Güncelleme paketi güvenli boyut sınırını aşıyor.")
        if not 0 < sizes["SHA256SUMS"] <= _MAX_METADATA_BYTES:
            raise self._failure("Güncelleme manifesti güvenli boyut sınırını aşıyor.")

        self.cleanup()
        self._temporary = tempfile.TemporaryDirectory(prefix="pdrive-update-")
        directory = Path(self._temporary.name)
        directory.chmod(0o700)
        self._checked(
            (
                gh,
                "release",
                "download",
                f"v{version}",
                "--repo",
                _REPOSITORY,
                "--pattern",
                package_name,
                "--pattern",
                "SHA256SUMS",
                "--dir",
                str(directory),
            ),
            300,
        )
        package = directory / package_name
        manifest = directory / "SHA256SUMS"
        self._validate_download(package, sizes[package_name], _MAX_PACKAGE_BYTES)
        self._validate_download(manifest, sizes["SHA256SUMS"], _MAX_METADATA_BYTES)
        expected = self._manifest_digest(manifest, package_name)
        actual = self._sha256(package)
        if actual != expected:
            raise self._failure("Güncelleme paketinin SHA-256 doğrulaması başarısız.")
        self._checked(
            (
                gh,
                "attestation",
                "verify",
                str(package),
                "--repo",
                _REPOSITORY,
                "--signer-workflow",
                _SIGNER_WORKFLOW,
                "--deny-self-hosted-runners",
            ),
            120,
        )
        return PreparedUpdate(version, package, actual)

    def install(self, update: PreparedUpdate) -> None:
        package = update.package.resolve(strict=True)
        if self._sha256(package) != update.sha256:
            raise self._failure("Kurulum öncesi paket doğrulaması başarısız.")
        pkexec = self._trusted_tool("pkexec")
        apt_get = Path("/usr/bin/apt-get")
        if not apt_get.is_file():
            raise self._failure("Sistem paket yöneticisi bulunamadı.")
        result = subprocess.run(
            (pkexec, str(apt_get), "install", "--yes", str(package)),
            stdin=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            raise self._failure("Güncelleme kurulmadı veya yönetici onayı iptal edildi.")

    def cleanup(self) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None

    def _release_metadata(self, gh: str) -> dict[str, Any]:
        result = self._checked(
            (
                gh,
                "release",
                "view",
                "--repo",
                _REPOSITORY,
                "--json",
                "tagName,isDraft,isPrerelease,assets",
            ),
            30,
        )
        if len(result.stdout) > _MAX_METADATA_BYTES:
            raise self._failure("GitHub sürüm yanıtı güvenlik sınırını aşıyor.")
        try:
            payload = json.loads(result.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise self._failure("GitHub beklenmeyen bir sürüm yanıtı döndürdü.") from error
        if not isinstance(payload, dict):
            raise self._failure("GitHub beklenmeyen bir sürüm yanıtı döndürdü.")
        return payload

    @staticmethod
    def _asset_sizes(value: object) -> dict[str, int]:
        if not isinstance(value, list):
            raise VerifiedUpdateService._failure("Sürüm dosyaları doğrulanamadı.")
        sizes: dict[str, int] = {}
        for asset in value:
            if not isinstance(asset, dict):
                raise VerifiedUpdateService._failure("Sürüm dosyaları doğrulanamadı.")
            name, size = asset.get("name"), asset.get("size")
            if not isinstance(name, str) or not isinstance(size, int) or name in sizes:
                raise VerifiedUpdateService._failure("Sürüm dosyaları doğrulanamadı.")
            sizes[name] = size
        return sizes

    @staticmethod
    def _validate_download(path: Path, expected_size: int, maximum: int) -> None:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != expected_size or info.st_size > maximum:
            raise VerifiedUpdateService._failure("İndirilen güncelleme dosyası geçersiz.")
        path.chmod(0o600)

    @staticmethod
    def _manifest_digest(manifest: Path, package_name: str) -> str:
        try:
            lines = manifest.read_text(encoding="ascii").splitlines()
        except (OSError, UnicodeError) as error:
            raise VerifiedUpdateService._failure("SHA-256 manifesti okunamadı.") from error
        matches = []
        for line in lines:
            parts = line.split()
            if len(parts) == 2 and parts[1].removeprefix("*") == package_name:
                matches.append(parts[0].lower())
        if len(matches) != 1 or len(matches[0]) != 64 or any(
            character not in "0123456789abcdef" for character in matches[0]
        ):
            raise VerifiedUpdateService._failure("SHA-256 manifesti geçersiz.")
        return matches[0]

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _trusted_tool(name: str) -> str:
        executable = shutil.which(name)
        if executable is None:
            raise VerifiedUpdateService._failure(
                f"Güvenli güncelleme için gerekli {name} aracı bulunamadı."
            )
        resolved = Path(executable).resolve(strict=True)
        info = resolved.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & stat.S_IWOTH:
            raise VerifiedUpdateService._failure("Güncelleme doğrulama aracı güvenli değil.")
        return str(resolved)

    def _checked(
        self, command: Sequence[str], timeout: float
    ) -> subprocess.CompletedProcess[bytes]:
        try:
            result = self._run(command, timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise self._failure("Güncelleme denetimi zaman aşımına uğradı.") from error
        if result.returncode != 0:
            raise self._failure("Güncellemenin kaynağı veya provenansı doğrulanamadı.")
        return result

    @staticmethod
    def _failure(message: str) -> SafeApplicationError:
        return SafeApplicationError(
            ErrorCategory.UNSUPPORTED_RESPONSE,
            message,
            False,
            "update-verification",
        )
