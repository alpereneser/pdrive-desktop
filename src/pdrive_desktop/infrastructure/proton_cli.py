from __future__ import annotations

import asyncio
import json
import os
import secrets
import signal
import stat
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pdrive_desktop.application.errors import ErrorCategory, SafeApplicationError
from pdrive_desktop.domain.drive import DriveNode, DrivePath, NodeKind

_MAX_OUTPUT_BYTES = 16 * 1024 * 1024
_ALLOWED_OPERATIONS = frozenset(
    {
        ("auth", "login"),
        ("filesystem", "create-folder"),
        ("filesystem", "download"),
        ("filesystem", "list"),
        ("filesystem", "trash"),
        ("filesystem", "upload"),
        ("photo", "timeline"),
        ("version",),
    }
)


class CliError(SafeApplicationError):
    """Safe error raised when the official CLI invocation fails."""


def _safe_error(
    category: ErrorCategory,
    message: str,
    *,
    retryable: bool,
) -> CliError:
    return CliError(
        category=category,
        user_message=message,
        retryable=retryable,
        correlation_id=secrets.token_hex(6),
    )


def _classify_cli_failure(stderr: bytes) -> CliError:
    normalized = stderr.decode("utf-8", errors="replace").casefold()
    if any(marker in normalized for marker in ("not authenticated", "session expired", "login")):
        return _safe_error(
            ErrorCategory.AUTHENTICATION,
            "Proton oturumunun yenilenmesi gerekiyor.",
            retryable=False,
        )
    if any(marker in normalized for marker in ("offline", "network", "connection", "dns")):
        return _safe_error(
            ErrorCategory.OFFLINE,
            "Ağ bağlantısı kurulamadı. Bağlantınızı kontrol edip yeniden deneyin.",
            retryable=True,
        )
    if any(marker in normalized for marker in ("quota", "storage limit", "insufficient storage")):
        return _safe_error(
            ErrorCategory.QUOTA,
            "Proton Drive depolama alanı yetersiz.",
            retryable=False,
        )
    if any(marker in normalized for marker in ("rate limit", "too many requests", "429")):
        return _safe_error(
            ErrorCategory.RATE_LIMIT,
            "Proton geçici bir istek sınırı uyguladı. Bir süre sonra yeniden deneyin.",
            retryable=True,
        )
    if any(marker in normalized for marker in ("permission denied", "access denied", "eacces")):
        return _safe_error(
            ErrorCategory.PERMISSION,
            "İşlem için gerekli yerel veya uzak izin bulunamadı.",
            retryable=False,
        )
    return _safe_error(
        ErrorCategory.UNKNOWN,
        "Proton Drive işlemi tamamlanamadı.",
        retryable=True,
    )


@dataclass(frozen=True, slots=True)
class CliResult:
    stdout: bytes
    stderr: bytes


class SecureCliRunner:
    def __init__(
        self,
        executable: Path,
        *,
        timeout_seconds: float = 60.0,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self._executable = executable.expanduser().resolve(strict=True)
        self._timeout = timeout_seconds
        self._cancel_event = cancel_event
        self._validate_executable()

    def _validate_executable(self) -> None:
        file_stat = self._executable.stat()
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError("CLI path is not a regular file")
        if file_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ValueError("CLI must not be writable by group or others")
        if not os.access(self._executable, os.X_OK):
            raise ValueError("CLI is not executable")

    async def run(
        self,
        operation: Sequence[str],
        arguments: Sequence[str] = (),
        *,
        json_output: bool = True,
        timeout_seconds: float | None = None,
    ) -> CliResult:
        operation_tuple = tuple(operation)
        if operation_tuple not in _ALLOWED_OPERATIONS:
            raise ValueError("CLI operation is not allowed")
        if any("\x00" in value for value in (*operation, *arguments)):
            raise ValueError("CLI argument contains a null byte")

        command = [str(self._executable), *operation, *arguments]
        if json_output:
            command.append("--json")
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._safe_environment(),
            start_new_session=True,
        )
        output_task = asyncio.ensure_future(
            asyncio.gather(
                self._read_limited(process.stdout),
                self._read_limited(process.stderr),
            )
        )
        deadline = time.monotonic() + (timeout_seconds or self._timeout)
        try:
            while not output_task.done():
                if self._cancel_event is not None and self._cancel_event.is_set():
                    raise _safe_error(
                        ErrorCategory.CANCELLED,
                        "Aktarım iptal edildi.",
                        retryable=False,
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                try:
                    await asyncio.wait_for(
                        asyncio.shield(output_task), timeout=min(0.2, remaining)
                    )
                except TimeoutError:
                    continue
            stdout, stderr = await output_task
            await process.wait()
        except (TimeoutError, CliError) as error:
            self._kill_owned_process_group(process)
            await process.wait()
            if not output_task.done():
                output_task.cancel()
            await asyncio.gather(output_task, return_exceptions=True)
            if isinstance(error, CliError):
                raise
            raise _safe_error(
                ErrorCategory.TIMEOUT,
                "Proton Drive işlemi zaman aşımına uğradı.",
                retryable=True,
            ) from error

        if process.returncode != 0:
            raise _classify_cli_failure(stderr)
        return CliResult(stdout=stdout, stderr=stderr)

    @staticmethod
    def _kill_owned_process_group(process: asyncio.subprocess.Process) -> None:
        """Stop the isolated CLI process tree without touching unrelated processes."""
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return

    @staticmethod
    async def _read_limited(stream: asyncio.StreamReader | None) -> bytes:
        if stream is None:
            return b""
        output = bytearray()
        while chunk := await stream.read(64 * 1024):
            output.extend(chunk)
            if len(output) > _MAX_OUTPUT_BYTES:
                raise _safe_error(
                    ErrorCategory.UNSUPPORTED_RESPONSE,
                    "Proton Drive yanıtı güvenlik sınırını aştı.",
                    retryable=False,
                )
        return bytes(output)

    @staticmethod
    def _safe_environment() -> Mapping[str, str]:
        allowed = (
            "HOME",
            "PATH",
            "XDG_CONFIG_HOME",
            "XDG_CACHE_HOME",
            "XDG_DATA_HOME",
            "XDG_RUNTIME_DIR",
            "DBUS_SESSION_BUS_ADDRESS",
            "DISPLAY",
            "WAYLAND_DISPLAY",
        )
        environment = {key: os.environ[key] for key in allowed if key in os.environ}
        environment.update({"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "NO_COLOR": "1"})
        return environment


class ProtonCliDriveGateway:
    def __init__(self, runner: SecureCliRunner) -> None:
        self._runner = runner

    async def list_nodes(self, path: DrivePath) -> Sequence[DriveNode]:
        if str(path) == "/photos":
            result = await self._runner.run(
                ("photo", "timeline"), ("--load-details",)
            )
        else:
            result = await self._runner.run(("filesystem", "list"), (str(path),))
        try:
            payload: Any = json.loads(result.stdout)
            items = payload if isinstance(payload, list) else payload["items"]
            return tuple(self._parse_listing_item(item, path) for item in items)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise _safe_error(
                ErrorCategory.UNSUPPORTED_RESPONSE,
                "Proton Drive beklenmeyen bir yanıt döndürdü.",
                retryable=False,
            ) from error

    @staticmethod
    def _parse_listing_item(item: Mapping[str, Any], parent: DrivePath) -> DriveNode:
        if "rootFolderUid" in item:
            name = ProtonCliDriveGateway._parse_name(item)
            return DriveNode(
                node_id=str(item["uid"]),
                name=name,
                kind=NodeKind.FOLDER,
                path=parent.child(name),
                modified_at=ProtonCliDriveGateway._parse_datetime(
                    item.get("lastSyncTime") or item.get("creationTime")
                ),
            )

        return ProtonCliDriveGateway._parse_node(item, parent)

    @staticmethod
    def _parse_node(item: Mapping[str, Any], parent: DrivePath) -> DriveNode:
        name = ProtonCliDriveGateway._parse_name(item)
        kind = NodeKind(str(item["type"]).lower())
        revision = item.get("activeRevision")
        claimed_size = revision.get("claimedSize") if isinstance(revision, Mapping) else None
        return DriveNode(
            node_id=str(item["uid"]),
            name=name,
            kind=kind,
            path=parent.child(name),
            size=int(claimed_size) if claimed_size is not None else None,
            modified_at=ProtonCliDriveGateway._parse_datetime(
                item.get("modificationTime") or item.get("creationTime")
            ),
        )

    @staticmethod
    def _parse_name(item: Mapping[str, Any]) -> str:
        name_value = item["name"]
        if isinstance(name_value, Mapping):
            return str(name_value.get("value") or item["uid"])
        return str(name_value)

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    async def create_folder(self, parent: DrivePath, name: str) -> None:
        parent.child(name)
        await self._runner.run(
            ("filesystem", "create-folder"), (str(parent), name), json_output=False
        )

    async def upload(self, local_paths: Sequence[Path], parent: DrivePath) -> None:
        validated = tuple(self._validate_upload_path(path) for path in local_paths)
        if not validated:
            raise ValueError("At least one local item is required")
        result = await self._runner.run(
            ("filesystem", "upload"),
            (
                "--file-conflict-strategy",
                "skip",
                "--folder-conflict-strategy",
                "merge",
                *validated,
                str(parent),
            ),
            timeout_seconds=24 * 60 * 60,
        )
        self._ensure_transfer_success(result)

    async def download(
        self, remote_paths: Sequence[DrivePath], local_parent: Path
    ) -> None:
        if not remote_paths:
            raise ValueError("At least one remote item is required")
        destination = local_parent.expanduser().resolve(strict=True)
        if not destination.is_dir() or destination.is_symlink():
            raise ValueError("Download destination must be a real directory")
        with tempfile.TemporaryDirectory(
            prefix=".pdrive-download-", dir=destination
        ) as staging_name:
            staging = Path(staging_name)
            staging.chmod(0o700)
            result = await self._runner.run(
                ("filesystem", "download"),
                (
                    "--file-conflict-strategy",
                    "skip",
                    "--folder-conflict-strategy",
                    "merge",
                    *(str(path) for path in remote_paths),
                    str(staging),
                ),
                timeout_seconds=24 * 60 * 60,
            )
            self._ensure_transfer_success(result)
            for staged_item in staging.iterdir():
                self._commit_staged_download(staged_item, destination / staged_item.name)

    async def trash(self, remote_paths: Sequence[DrivePath]) -> None:
        if not remote_paths:
            raise ValueError("At least one remote item is required")
        await self._runner.run(
            ("filesystem", "trash"),
            tuple(str(path) for path in remote_paths),
            json_output=False,
        )

    async def sync_backup(self, local_folder: Path, parent: DrivePath) -> None:
        validated = self._validate_upload_path(local_folder)
        if not Path(validated).is_dir():
            raise ValueError("Backup source must be a directory")
        arguments = (
            "--file-conflict-strategy",
            "create-new-revision",
            "--folder-conflict-strategy",
            "merge",
            validated,
            str(parent),
        )
        # A second idempotent pass catches items missed by an otherwise successful CLI
        # traversal. Equal file content is skipped by the official CLI.
        for _verification_pass in range(2):
            result = await self._runner.run(
                ("filesystem", "upload"),
                arguments,
                timeout_seconds=24 * 60 * 60,
            )
            self._ensure_transfer_success(result)

    @staticmethod
    def _validate_upload_path(path: Path) -> str:
        expanded = path.expanduser()
        if expanded.is_symlink():
            raise ValueError("Symbolic links are not uploaded")
        resolved = expanded.resolve(strict=True)
        if not (resolved.is_file() or resolved.is_dir()):
            raise ValueError("Upload item must be a regular file or directory")
        return str(resolved)

    @classmethod
    def _commit_staged_download(cls, source: Path, destination: Path) -> None:
        """Commit CLI output without following links or replacing local data."""

        if source.is_symlink():
            raise _safe_error(
                ErrorCategory.PERMISSION,
                "İndirilen veri güvenli olmayan bir sembolik bağlantı içeriyor.",
                retryable=False,
            )
        if source.is_file():
            try:
                source.chmod(0o600)
                os.link(source, destination, follow_symlinks=False)
            except FileExistsError:
                return
            except OSError as error:
                raise _safe_error(
                    ErrorCategory.PERMISSION,
                    "İndirilen dosya güvenli biçimde hedefe taşınamadı.",
                    retryable=False,
                ) from error
            source.unlink()
            return
        if not source.is_dir():
            raise _safe_error(
                ErrorCategory.UNSUPPORTED_RESPONSE,
                "İndirilen veri desteklenmeyen bir dosya türü içeriyor.",
                retryable=False,
            )

        try:
            destination.mkdir(mode=0o700)
        except FileExistsError:
            if destination.is_symlink() or not destination.is_dir():
                raise _safe_error(
                    ErrorCategory.PERMISSION,
                    "İndirme mevcut bir yerel öğeyle çakışıyor.",
                    retryable=False,
                ) from None
        for child in source.iterdir():
            cls._commit_staged_download(child, destination / child.name)

    @staticmethod
    def _ensure_transfer_success(result: CliResult) -> None:
        try:
            summary = json.loads(result.stdout)
            if not isinstance(summary, Mapping) or int(summary["failedItems"]) != 0:
                raise _safe_error(
                    ErrorCategory.UNKNOWN,
                    "Bir veya daha fazla aktarım öğesi tamamlanamadı.",
                    retryable=True,
                )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise _safe_error(
                ErrorCategory.UNSUPPORTED_RESPONSE,
                "Proton Drive beklenmeyen bir aktarım özeti döndürdü.",
                retryable=False,
            ) from error


class ProtonCliAuthenticationGateway:
    """Delegates identity entirely to Proton CLI and the OS secret store."""

    def __init__(self, runner: SecureCliRunner) -> None:
        self._runner = runner

    async def login(self) -> None:
        await self._runner.run(
            ("auth", "login"), json_output=False, timeout_seconds=10 * 60
        )

    async def is_authenticated(self) -> bool:
        try:
            result = await self._runner.run(("filesystem", "list"), ("/my-files",))
            json.loads(result.stdout)
            return True
        except (CliError, json.JSONDecodeError):
            return False
