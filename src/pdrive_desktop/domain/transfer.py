from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class TransferKind(StrEnum):
    UPLOAD = "upload"
    DOWNLOAD = "download"
    BACKUP = "backup"


class TransferStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATUSES = frozenset(
    {TransferStatus.COMPLETED, TransferStatus.FAILED, TransferStatus.CANCELLED}
)


@dataclass(frozen=True, slots=True)
class TransferJob:
    """Path-free transfer state safe to expose in the local UI."""

    job_id: str
    kind: TransferKind
    item_count: int
    status: TransferStatus = TransferStatus.QUEUED
    retryable: bool = False

    def __post_init__(self) -> None:
        if not self.job_id or any(character in self.job_id for character in "\x00\r\n"):
            raise ValueError("Invalid transfer ID")
        if self.item_count < 1:
            raise ValueError("Transfer requires at least one item")
        if (
            self.status in _TERMINAL_STATUSES
            and self.status is not TransferStatus.FAILED
            and self.retryable
        ):
            raise ValueError("Only failed transfers may be retryable")

    def start(self) -> TransferJob:
        self._require(TransferStatus.QUEUED)
        return replace(self, status=TransferStatus.RUNNING)

    def request_cancel(self) -> TransferJob:
        self._require(TransferStatus.QUEUED, TransferStatus.RUNNING)
        if self.status is TransferStatus.QUEUED:
            return replace(self, status=TransferStatus.CANCELLED)
        return replace(self, status=TransferStatus.CANCELLING)

    def complete(self) -> TransferJob:
        self._require(TransferStatus.RUNNING)
        return replace(self, status=TransferStatus.COMPLETED, retryable=False)

    def fail(self, *, retryable: bool) -> TransferJob:
        self._require(TransferStatus.RUNNING, TransferStatus.CANCELLING)
        return replace(self, status=TransferStatus.FAILED, retryable=retryable)

    def cancel(self) -> TransferJob:
        self._require(TransferStatus.CANCELLING)
        return replace(self, status=TransferStatus.CANCELLED, retryable=False)

    def retry(self) -> TransferJob:
        if self.status is not TransferStatus.FAILED or not self.retryable:
            raise ValueError("Transfer cannot be retried")
        return replace(self, status=TransferStatus.QUEUED, retryable=False)

    def _require(self, *allowed: TransferStatus) -> None:
        if self.status not in allowed:
            raise ValueError(f"Illegal transfer transition from {self.status}")
