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
from pdrive_desktop.domain.drive import DriveNode, DrivePath
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


class DesktopController:
    """Runs blocking CLI work away from GTK's main loop."""

    def __init__(
        self,
        *,
        on_nodes: NodesCallback,
        on_error: ErrorCallback,
        on_state: StateCallback,
        paths: AppPaths | None = None,
    ) -> None:
        self._on_nodes = on_nodes
        self._on_error = on_error
        self._on_state = on_state
        self._paths = paths or AppPaths.from_environment()
        self._busy_lock = threading.Lock()
        self._current_path = DrivePath.parse("/my-files")
        self._section_root = self._current_path

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
        self._start(lambda: self._upload(paths), "Yükleme devam ediyor…")

    def download(self, nodes: Sequence[DriveNode], destination: Path) -> None:
        self._start(
            lambda: self._download(nodes, destination), "İndirme devam ediyor…"
        )

    def trash(self, nodes: Sequence[DriveNode]) -> None:
        self._start(lambda: self._trash(nodes), "Öğeler çöp kutusuna taşınıyor…")

    def backup_folder(self, path: Path) -> None:
        self._start(lambda: self._backup_folder(path), "Güvenli yedekleme devam ediyor…")

    def _start(self, target: Callable[[], None], state: str) -> None:
        if not self._busy_lock.acquire(blocking=False):
            return
        self._dispatch(self._on_state, state)

        def worker() -> None:
            try:
                target()
            except (CliError, OSError, RuntimeError, ValueError) as error:
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

    def _upload(self, paths: Sequence[Path]) -> None:
        runner = self._runner()
        gateway = ProtonCliDriveGateway(runner)
        asyncio.run(UploadItems(gateway).execute(paths, self._current_path))
        self._refresh_with(runner)

    def _download(self, nodes: Sequence[DriveNode], destination: Path) -> None:
        gateway = ProtonCliDriveGateway(self._runner())
        asyncio.run(
            DownloadItems(gateway).execute(tuple(node.path for node in nodes), destination)
        )
        self._dispatch(self._on_state, "İndirme tamamlandı")

    def _trash(self, nodes: Sequence[DriveNode]) -> None:
        runner = self._runner()
        gateway = ProtonCliDriveGateway(runner)
        asyncio.run(TrashItems(gateway).execute(tuple(node.path for node in nodes)))
        self._refresh_with(runner)

    def _backup_folder(self, path: Path) -> None:
        runner = self._runner()
        gateway = ProtonCliDriveGateway(runner)
        asyncio.run(BackupFolder(gateway).execute(path, self._current_path))
        self._refresh_with(runner)

    def _runner(self) -> SecureCliRunner:
        return SecureCliRunner(self._paths.cli_executable)

    @staticmethod
    def _safe_message(error: Exception) -> str:
        if isinstance(error, CliError):
            return str(error)
        return "Yerel Proton Drive bileşeni hazırlanamadı."

    @staticmethod
    def _dispatch(callback: Callable[..., object], *arguments: object) -> None:
        GLib.idle_add(callback, *arguments)
