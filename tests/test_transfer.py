import pytest

from pdrive_desktop.domain.transfer import TransferJob, TransferKind, TransferStatus


def test_transfer_completes_through_legal_states() -> None:
    job = TransferJob("job-1", TransferKind.DOWNLOAD, 2)

    completed = job.start().complete()

    assert completed.status is TransferStatus.COMPLETED
    assert completed.retryable is False


def test_running_transfer_cancels_in_two_steps() -> None:
    job = TransferJob("job-1", TransferKind.UPLOAD, 1).start()

    cancelling = job.request_cancel()
    cancelled = cancelling.cancel()

    assert cancelling.status is TransferStatus.CANCELLING
    assert cancelled.status is TransferStatus.CANCELLED


def test_queued_transfer_cancels_without_starting() -> None:
    cancelled = TransferJob("job-1", TransferKind.BACKUP, 1).request_cancel()

    assert cancelled.status is TransferStatus.CANCELLED


def test_only_retryable_failure_can_return_to_queue() -> None:
    failed = TransferJob("job-1", TransferKind.DOWNLOAD, 1).start().fail(retryable=True)

    assert failed.retry().status is TransferStatus.QUEUED

    nonretryable = TransferJob("job-2", TransferKind.DOWNLOAD, 1).start().fail(
        retryable=False
    )
    with pytest.raises(ValueError, match="cannot be retried"):
        nonretryable.retry()


def test_illegal_transition_is_rejected() -> None:
    with pytest.raises(ValueError, match="Illegal transfer transition"):
        TransferJob("job-1", TransferKind.UPLOAD, 1).complete()


def test_transfer_state_contains_no_paths() -> None:
    fields = set(TransferJob.__dataclass_fields__)

    assert fields == {"job_id", "kind", "item_count", "status", "retryable"}
