from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorCategory(StrEnum):
    OFFLINE = "offline"
    AUTHENTICATION = "authentication"
    QUOTA = "quota"
    RATE_LIMIT = "rate-limit"
    PERMISSION = "permission"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    UNSUPPORTED_RESPONSE = "unsupported-response"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SafeApplicationError(RuntimeError):
    category: ErrorCategory
    user_message: str
    retryable: bool
    correlation_id: str

    def __str__(self) -> str:
        return f"{self.user_message} (Referans: {self.correlation_id})"
