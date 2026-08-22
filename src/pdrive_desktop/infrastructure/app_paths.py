from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    data_dir: Path

    @classmethod
    def from_environment(cls) -> AppPaths:
        data_home = Path(
            os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        )
        return cls(data_dir=data_home / "pdrive-desktop")

    @property
    def cli_executable(self) -> Path:
        return self.data_dir / "bin" / "proton-drive"

