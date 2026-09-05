from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pdrive_desktop.domain.backup import BackupVerification
from pdrive_desktop.domain.drive import DriveNode, DrivePath


class DriveGateway(Protocol):
    async def list_nodes(self, path: DrivePath) -> Sequence[DriveNode]: ...


class AuthenticationGateway(Protocol):
    async def login(self) -> None: ...

    async def is_authenticated(self) -> bool: ...


class FileOperationsGateway(Protocol):
    async def create_folder(self, parent: DrivePath, name: str) -> None: ...

    async def upload(self, local_paths: Sequence[Path], parent: DrivePath) -> None: ...

    async def download(self, remote_paths: Sequence[DrivePath], local_parent: Path) -> None: ...

    async def trash(self, remote_paths: Sequence[DrivePath]) -> None: ...

    async def sync_backup(
        self, local_folder: Path, parent: DrivePath
    ) -> BackupVerification: ...


class ListFolder:
    def __init__(self, gateway: DriveGateway) -> None:
        self._gateway = gateway

    async def execute(self, path: DrivePath) -> Sequence[DriveNode]:
        return await self._gateway.list_nodes(path)


class Authenticate:
    def __init__(self, gateway: AuthenticationGateway) -> None:
        self._gateway = gateway

    async def execute(self) -> None:
        await self._gateway.login()


class GetAuthenticationState:
    def __init__(self, gateway: AuthenticationGateway) -> None:
        self._gateway = gateway

    async def execute(self) -> bool:
        return await self._gateway.is_authenticated()


class CreateFolder:
    def __init__(self, gateway: FileOperationsGateway) -> None:
        self._gateway = gateway

    async def execute(self, parent: DrivePath, name: str) -> None:
        await self._gateway.create_folder(parent, name)


class UploadItems:
    def __init__(self, gateway: FileOperationsGateway) -> None:
        self._gateway = gateway

    async def execute(self, local_paths: Sequence[Path], parent: DrivePath) -> None:
        await self._gateway.upload(local_paths, parent)


class DownloadItems:
    def __init__(self, gateway: FileOperationsGateway) -> None:
        self._gateway = gateway

    async def execute(self, remote_paths: Sequence[DrivePath], local_parent: Path) -> None:
        await self._gateway.download(remote_paths, local_parent)


class TrashItems:
    def __init__(self, gateway: FileOperationsGateway) -> None:
        self._gateway = gateway

    async def execute(self, remote_paths: Sequence[DrivePath]) -> None:
        await self._gateway.trash(remote_paths)


class BackupFolder:
    """One-way, non-deleting local-to-Drive synchronization."""

    def __init__(self, gateway: FileOperationsGateway) -> None:
        self._gateway = gateway

    async def execute(
        self, local_folder: Path, parent: DrivePath
    ) -> BackupVerification:
        return await self._gateway.sync_backup(local_folder, parent)
