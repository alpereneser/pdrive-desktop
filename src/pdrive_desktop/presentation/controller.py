from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from gi.repository import GLib

from pdrive_desktop.application.ports import (
    Authenticate,
    BackupFolder,
    CreateFolder,
    DownloadItems,
    ListFolder,
    TrashItems,
    UploadItems,
)
from pdrive_desktop.application.transfer_queue import LocalTransferQueue
from pdrive_desktop.domain.drive import DriveNode, DrivePath
from pdrive_desktop.domain.transfer import TransferJob, TransferKind, TransferStatus
from pdrive_desktop.infrastructure.app_paths import AppPaths
from pdrive_desktop.infrastructure.cli_release import CliInstaller
from pdrive_desktop.infrastructure.proton_cli import (
    CliError,
    ProtonCliAuthenticationGateway,
    ProtonCliDriveGateway,
    SecureCliRunner,
)

NodesCallback = Callable[[DrivePath, Sequence[DriveNode]], object]
ErrorCallback = Callable[[str], object]
StateCallback = Callable[[str], object]
TransferCallback = Callable[[TransferJob, int], object]


class DesktopController:
    """Runs blocking CLI work away from GTK's main loop."""

    def __init__(
        self,
        *,
        on_nodes: NodesCallback,
        on_error: ErrorCallback,
        on_state: StateCallback,
        on_transfer: TransferCallback,
        paths: AppPaths | None = None,
    ) -> None:
        self._on_nodes = on_nodes
        self._on_error = on_error
        self._on_state = on_state
        self._on_transfer = on_transfer
        self._paths = paths or AppPaths.from_environment()
        self._busy_lock = threading.Lock()
        self._current_path = DrivePath.parse("/my-files")
        self._section_root = self._current_path
        self._active_transfer_id: str | None = None
        self._active_transfer_job: TransferJob | None = None
        self._last_retryable_id: str | None = None
        self._transfers = LocalTransferQueue(
            on_update=self._transfer_updated,
            on_failure=lambda error: self._dispatch(self._on_error, str(error)),
        )

    def connect(self) -> None:
        self._start(self._connect, "Resmî Proton Drive CLI hazırlanıyor…")

    def refresh(self) -> None:
        if not self._paths.cli_executable.exists():
            self._dispatch(self._on_state, "Bağlantı bekleniyor")
            return
        self._start(self._refresh, "Dosyalar güvenli şekilde yükleniyor…")

    def open_folder(self, path: DrivePath) -> None:
        if self._busy_lock.locked():
            return
        self._current_path = path
        self.refresh()

    def open_location(self, path: DrivePath) -> None:
        if self._busy_lock.locked():
            return
        self._section_root = path
        self._current_path = path
        self.refresh()

    def go_up(self) -> None:
        if self._current_path == self._section_root:
            return
        raw = str(self._current_path)
        escaped = False
        separator = 0
        for index, character in enumerate(raw):
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == "/":
                separator = index
        parent = DrivePath.parse(raw[:separator]) if separator else self._section_root
        if len(str(parent)) < len(str(self._section_root)):
            parent = self._section_root
        self.open_folder(parent)

    def create_folder(self, name: str) -> None:
        self._start(lambda: self._create_folder(name), "Klasör oluşturuluyor…")

    def upload(self, paths: Sequence[Path]) -> None:
        immutable_paths = tuple(paths)
        self._transfers.submit(
            TransferKind.UPLOAD,
            len(immutable_paths),
            lambda cancelled: self._upload(immutable_paths, cancelled),
        )

    def download(self, nodes: Sequence[DriveNode], destination: Path) -> None:
        immutable_nodes = tuple(nodes)
        self._transfers.submit(
            TransferKind.DOWNLOAD,
            len(immutable_nodes),
            lambda cancelled: self._download(immutable_nodes, destination, cancelled),
        )

    def trash(self, nodes: Sequence[DriveNode]) -> None:
        self._start(lambda: self._trash(nodes), "Öğeler çöp kutusuna taşınıyor…")

    def backup_folder(self, path: Path) -> None:
        self._transfers.submit(
            TransferKind.BACKUP,
            1,
            lambda cancelled: self._backup_folder(path, cancelled),
        )

    def cancel_transfer(self) -> None:
        if self._active_transfer_id is not None:
            self._transfers.cancel(self._active_transfer_id)

    def retry_last_failed(self) -> None:
        if self._last_retryable_id is not None:
            self._transfers.retry(self._last_retryable_id)

    def shutdown(self) -> None:
        self._transfers.shutdown()

    def _start(self, target: Callable[[], None], state: str) -> None:
        if not self._busy_lock.acquire(blocking=False):
            return
        self._dispatch(self._on_state, state)

        def worker() -> None:
            try:
                target()
            except (CliError, OSError, RuntimeError, ValueError) as error:
                self._dispatch(self._on_state, "İşlem durdu")
                self._dispatch(self._on_error, self._safe_message(error))
            finally:
                self._busy_lock.release()

        threading.Thread(target=worker, name="pdrive-cli-worker", daemon=True).start()

    def _connect(self) -> None:
        executable = self._paths.cli_executable
        if not executable.exists():
            CliInstaller().install(executable)
        runner = SecureCliRunner(executable)
        gateway = ProtonCliAuthenticationGateway(runner)
        asyncio.run(Authenticate(gateway).execute())
        self._refresh_with(runner)

    def _refresh(self) -> None:
        self._refresh_with(SecureCliRunner(self._paths.cli_executable))

    def _refresh_with(self, runner: SecureCliRunner) -> None:
        nodes = asyncio.run(
            ListFolder(ProtonCliDriveGateway(runner)).execute(self._current_path)
        )
        self._dispatch(self._on_nodes, self._current_path, nodes)
        self._dispatch(self._on_state, "Güncel")

    def _create_folder(self, name: str) -> None:
        runner = self._runner()
        gateway = ProtonCliDriveGateway(runner)
        asyncio.run(CreateFolder(gateway).execute(self._current_path, name))
        self._refresh_with(runner)

    def _upload(self, paths: Sequence[Path], cancelled: threading.Event) -> None:
        runner = self._runner(cancelled)
        gateway = ProtonCliDriveGateway(runner)
        asyncio.run(UploadItems(gateway).execute(paths, self._current_path))
        self._refresh_with(runner)

    def _download(
        self,
        nodes: Sequence[DriveNode],
        destination: Path,
        cancelled: threading.Event,
    ) -> None:
        gateway = ProtonCliDriveGateway(self._runner(cancelled))
        asyncio.run(
            DownloadItems(gateway).execute(tuple(node.path for node in nodes), destination)
        )
        self._dispatch(self._on_state, "İndirme tamamlandı")

    def _trash(self, nodes: Sequence[DriveNode]) -> None:
        runner = self._runner()
        gateway = ProtonCliDriveGateway(runner)
        asyncio.run(TrashItems(gateway).execute(tuple(node.path for node in nodes)))
        self._refresh_with(runner)

    def _backup_folder(self, path: Path, cancelled: threading.Event) -> None:
        runner = self._runner(cancelled)
        gateway = ProtonCliDriveGateway(runner)
        asyncio.run(BackupFolder(gateway).execute(path, self._current_path))
        self._refresh_with(runner)

    def _runner(self, cancelled: threading.Event | None = None) -> SecureCliRunner:
        return SecureCliRunner(self._paths.cli_executable, cancel_event=cancelled)

    def _transfer_updated(self, job: TransferJob, waiting: int) -> None:
        if job.status in {TransferStatus.RUNNING, TransferStatus.CANCELLING}:
            self._active_transfer_id = job.job_id
            self._active_transfer_job = job
        elif self._active_transfer_id == job.job_id:
            self._active_transfer_id = None
            self._active_transfer_job = None
        if job.status is TransferStatus.FAILED and job.retryable:
            self._last_retryable_id = job.job_id
        elif self._last_retryable_id == job.job_id and job.status is not TransferStatus.FAILED:
            self._last_retryable_id = None
        visible_job = (
            self._active_transfer_job
            if job.status is TransferStatus.QUEUED and self._active_transfer_job is not None
            else job
        )
        self._dispatch(self._on_transfer, visible_job, waiting)

    @staticmethod
    def _safe_message(error: Exception) -> str:
        if isinstance(error, CliError):
            return str(error)
        return "Yerel Proton Drive bileşeni hazırlanamadı."

    @staticmethod
    def _dispatch(callback: Callable[..., object], *arguments: object) -> None:
        GLib.idle_add(callback, *arguments)
