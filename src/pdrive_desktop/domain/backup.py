from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BackupVerification:
    verified_files: int
    verified_folders: int
    missing_items: int = 0
    mismatched_items: int = 0

    @property
    def complete(self) -> bool:
        return self.missing_items == 0 and self.mismatched_items == 0

    @property
    def verified_items(self) -> int:
        return self.verified_files + self.verified_folders
