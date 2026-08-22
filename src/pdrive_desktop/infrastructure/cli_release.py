from __future__ import annotations

import hashlib
import os
import platform
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CliRelease:
    version: str
    architecture: str
    url: str
    sha512: str


OFFICIAL_LINUX_X64 = CliRelease(
    version="0.8.0",
    architecture="x86_64",
    url="https://proton.me/download/drive/cli/0.8.0/linux-x64/proton-drive",
    sha512=(
        "cf61c2688c45e1055d8add6221d9471a5a5b64bf3bcdb86460f5cb18414596c"
        "c4df3cdb6627c9097c94bec32a3c9915ada3211ef2ae5be33c46ebbc996ccaa28"
    ),
)


class CliInstaller:
    """Installs a pinned official CLI release without executing the download."""

    def __init__(self, release: CliRelease = OFFICIAL_LINUX_X64) -> None:
        self._release = release

    def install(self, destination: Path) -> Path:
        if platform.system() != "Linux" or platform.machine() != self._release.architecture:
            raise RuntimeError("This pinned CLI release does not support the current platform")

        destination = destination.expanduser().resolve(strict=False)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".proton-drive-", dir=destination.parent
        )
        temporary = Path(temporary_name)
        try:
            digest = hashlib.sha512()
            request = urllib.request.Request(  # noqa: S310
                self._release.url,
                headers={"User-Agent": "PDrive-Desktop/0.1 (CLI installer)"},
            )
            with os.fdopen(descriptor, "wb") as output, urllib.request.urlopen(  # noqa: S310
                request, timeout=30
            ) as response:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())

            if digest.hexdigest() != self._release.sha512:
                raise RuntimeError("Official CLI checksum verification failed")
            temporary.chmod(0o500)
            temporary.replace(destination)
            return destination
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
