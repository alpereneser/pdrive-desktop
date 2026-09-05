from __future__ import annotations

import secrets
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from pdrive_desktop.application.errors import ErrorCategory, SafeApplicationError
from pdrive_desktop.domain.transfer import TransferJob, TransferKind, TransferStatus

TransferOperation = Callable[[threading.Event], None]
TransferUpdate = Callable[[TransferJob, int], object]
TransferFailure = Callable[[SafeApplicationError], object]


@dataclass(slots=True)
class _QueuedOperation:
    job: TransferJob
    operation: TransferOperation
    cancel_event: threading.Event


class LocalTransferQueue:
    """In-memory FIFO queue that runs one local CLI transfer at a time."""

    def __init__(self, *, on_update: TransferUpdate, on_failure: TransferFailure) -> None:
        self._on_update = on_update
        self._on_failure = on_failure
        self._condition = threading.Condition()
        self._pending: deque[_QueuedOperation] = deque()
        self._records: dict[str, _QueuedOperation] = {}
        self._current: _QueuedOperation | None = None
        self._closed = False
        self._worker = threading.Thread(
            target=self._work, name="pdrive-transfer-queue", daemon=True
        )
        self._worker.start()

    def submit(
        self, kind: TransferKind, item_count: int, operation: TransferOperation
    ) -> TransferJob:
        queued = _QueuedOperation(
            job=TransferJob(secrets.token_hex(8), kind, item_count),
            operation=operation,
            cancel_event=threading.Event(),
        )
        with self._condition:
            if self._closed:
                raise RuntimeError("Transfer queue is closed")
            self._records[queued.job.job_id] = queued
            self._pending.append(queued)
            waiting = len(self._pending)
            self._on_update(queued.job, waiting)
            self._condition.notify()
        return queued.job

    def cancel(self, job_id: str) -> bool:
        with self._condition:
            queued = self._records.get(job_id)
            if queued is None:
                return False
            if queued is self._current and queued.job.status is TransferStatus.RUNNING:
                queued.job = queued.job.request_cancel()
                queued.cancel_event.set()
                job, waiting = queued.job, len(self._pending)
            elif queued.job.status is TransferStatus.QUEUED:
                self._pending.remove(queued)
                queued.job = queued.job.request_cancel()
                job, waiting = queued.job, len(self._pending)
            else:
                return False
        self._on_update(job, waiting)
        return True

    def retry(self, job_id: str) -> bool:
        with self._condition:
            queued = self._records.get(job_id)
            if queued is None:
                return False
            try:
                queued.job = queued.job.retry()
            except ValueError:
                return False
            queued.cancel_event = threading.Event()
            self._pending.append(queued)
            waiting = len(self._pending)
            self._condition.notify()
        self._on_update(queued.job, waiting)
        return True

    def shutdown(self, timeout: float = 5.0) -> None:
        updates: list[TransferJob] = []
        with self._condition:
            if self._closed:
                return
            self._closed = True
            while self._pending:
                queued = self._pending.popleft()
                queued.job = queued.job.request_cancel()
                updates.append(queued.job)
            if self._current is not None and self._current.job.status is TransferStatus.RUNNING:
                self._current.job = self._current.job.request_cancel()
                self._current.cancel_event.set()
                updates.append(self._current.job)
            self._condition.notify_all()
        for job in updates:
            self._on_update(job, 0)
        if threading.current_thread() is not self._worker:
            self._worker.join(timeout)

    def _work(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or bool(self._pending))
                if self._closed and not self._pending:
                    return
                queued = self._pending.popleft()
                self._current = queued
                queued.job = queued.job.start()
                waiting = len(self._pending)
            self._on_update(queued.job, waiting)
            try:
                queued.operation(queued.cancel_event)
            except SafeApplicationError as application_error:
                if application_error.category is ErrorCategory.CANCELLED:
                    if queued.job.status is TransferStatus.RUNNING:
                        queued.job = queued.job.request_cancel()
                    queued.job = queued.job.cancel()
                else:
                    queued.job = queued.job.fail(retryable=application_error.retryable)
                    self._on_failure(application_error)
            except Exception:
                unexpected_error = SafeApplicationError(
                    category=ErrorCategory.UNKNOWN,
                    user_message="Yerel aktarım tamamlanamadı.",
                    retryable=True,
                    correlation_id=secrets.token_hex(6),
                )
                queued.job = queued.job.fail(retryable=True)
                self._on_failure(unexpected_error)
            else:
                if queued.job.status is TransferStatus.CANCELLING:
                    queued.job = queued.job.cancel()
                else:
                    queued.job = queued.job.complete()
            finally:
                with self._condition:
                    self._current = None
                    waiting = len(self._pending)
                self._on_update(queued.job, waiting)
