import threading
import time

from pdrive_desktop.application.errors import ErrorCategory, SafeApplicationError
from pdrive_desktop.application.transfer_queue import LocalTransferQueue
from pdrive_desktop.domain.transfer import TransferKind, TransferStatus


def _wait(event: threading.Event) -> None:
    assert event.wait(2), "transfer worker did not finish"


def test_queue_runs_transfers_in_fifo_order() -> None:
    release = threading.Event()
    finished = threading.Event()
    order: list[str] = []
    statuses: list[TransferStatus] = []
    queue = LocalTransferQueue(
        on_update=lambda job, _waiting: (
            statuses.append(job.status),
            finished.set() if job.status is TransferStatus.COMPLETED and len(order) == 2 else None,
        ),
        on_failure=lambda _error: None,
    )
    try:
        queue.submit(
            TransferKind.UPLOAD,
            1,
            lambda _cancelled: (release.wait(2), order.append("first")),
        )
        queue.submit(
            TransferKind.DOWNLOAD, 1, lambda _cancelled: order.append("second")
        )
        release.set()
        _wait(finished)
        assert order == ["first", "second"]
        assert statuses.count(TransferStatus.RUNNING) == 2
    finally:
        queue.shutdown()


def test_running_transfer_can_be_cancelled() -> None:
    started = threading.Event()
    cancelled = threading.Event()
    finished = threading.Event()
    statuses: list[TransferStatus] = []

    def operation(cancel_event: threading.Event) -> None:
        started.set()
        _wait(cancel_event)
        raise SafeApplicationError(
            ErrorCategory.CANCELLED, "cancelled", False, "test-reference"
        )

    queue = LocalTransferQueue(
        on_update=lambda job, _waiting: (
            statuses.append(job.status),
            finished.set() if job.status is TransferStatus.CANCELLED else None,
        ),
        on_failure=lambda _error: cancelled.set(),
    )
    try:
        job = queue.submit(TransferKind.BACKUP, 1, operation)
        _wait(started)
        assert queue.cancel(job.job_id)
        _wait(finished)
        assert TransferStatus.CANCELLING in statuses
        assert not cancelled.is_set()
    finally:
        queue.shutdown()


def test_retry_requires_retryable_failure() -> None:
    failed = threading.Event()
    completed = threading.Event()
    attempts = 0

    def operation(_cancel_event: threading.Event) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise SafeApplicationError(
                ErrorCategory.OFFLINE, "offline", True, "test-reference"
            )

    queue = LocalTransferQueue(
        on_update=lambda job, _waiting: (
            failed.set() if job.status is TransferStatus.FAILED else None,
            completed.set() if job.status is TransferStatus.COMPLETED else None,
        ),
        on_failure=lambda _error: None,
    )
    try:
        job = queue.submit(TransferKind.UPLOAD, 1, operation)
        _wait(failed)
        assert queue.retry(job.job_id)
        _wait(completed)
        assert attempts == 2
    finally:
        queue.shutdown()


def test_shutdown_cancels_active_and_pending_work() -> None:
    started = threading.Event()
    stopped = threading.Event()

    def operation(cancel_event: threading.Event) -> None:
        started.set()
        while not cancel_event.wait(0.01):
            pass
        stopped.set()
        raise SafeApplicationError(
            ErrorCategory.CANCELLED, "cancelled", False, "test-reference"
        )

    queue = LocalTransferQueue(
        on_update=lambda *_args: None, on_failure=lambda _error: None
    )
    queue.submit(TransferKind.UPLOAD, 1, operation)
    queue.submit(TransferKind.DOWNLOAD, 1, lambda _cancelled: time.sleep(1))
    _wait(started)
    queue.shutdown()
    assert stopped.is_set()
