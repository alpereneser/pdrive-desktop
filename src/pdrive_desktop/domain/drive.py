from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class NodeKind(StrEnum):
    FILE = "file"
    FOLDER = "folder"
    PHOTO = "photo"
    ALBUM = "album"


@dataclass(frozen=True, slots=True)
class DrivePath:
    value: str

    def __post_init__(self) -> None:
        raw = self.value
        if not raw.startswith("/"):
            raise ValueError("Drive path must be absolute")
        if "\x00" in raw or "\n" in raw or "\r" in raw:
            raise ValueError("Drive path contains control characters")
        if any(segment in {".", ".."} for segment in _split_remote_path(raw)):
            raise ValueError("Drive path cannot contain traversal segments")

    @classmethod
    def parse(cls, raw: str) -> DrivePath:
        return cls(raw)

    def child(self, name: str) -> DrivePath:
        if not name or name in {".", ".."} or any(char in name for char in "\x00\r\n"):
            raise ValueError("Invalid node name")
        escaped = name.replace("\\", "\\\\").replace("/", "\\/")
        return DrivePath(f"{self.value.rstrip('/')}/{escaped}")

    def __str__(self) -> str:
        return self.value


def _split_remote_path(raw: str) -> tuple[str, ...]:
    segments: list[str] = []
    current: list[str] = []
    escaped = False
    for character in raw[1:]:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "/":
            segments.append("".join(current))
            current = []
        else:
            current.append(character)
    if escaped:
        raise ValueError("Drive path ends with an incomplete escape")
    segments.append("".join(current))
    return tuple(segments)


@dataclass(frozen=True, slots=True)
class DriveNode:
    node_id: str
    name: str
    kind: NodeKind
    path: DrivePath
    size: int | None = None
    modified_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.node_id or any(char in self.node_id for char in "\x00\r\n"):
            raise ValueError("Invalid node ID")
        if not self.name or self.name in {".", ".."} or any(
            char in self.name for char in "\x00\r\n"
        ):
            raise ValueError("Invalid node name")
        if self.size is not None and self.size < 0:
            raise ValueError("Size cannot be negative")
        if self.modified_at is not None and self.modified_at.tzinfo is None:
            object.__setattr__(self, "modified_at", self.modified_at.replace(tzinfo=UTC))
