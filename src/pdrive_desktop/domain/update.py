from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, order=True, slots=True)
class AppVersion:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> AppVersion:
        normalized = value.removeprefix("v")
        parts = normalized.split(".")
        if len(parts) != 3 or any(not part.isascii() or not part.isdigit() for part in parts):
            raise ValueError("Version must be stable semantic version")
        return cls(*(int(part) for part in parts))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True, slots=True)
class PreparedUpdate:
    version: AppVersion
    package: Path
    sha256: str
