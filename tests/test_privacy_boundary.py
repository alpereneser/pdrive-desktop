from pathlib import Path


def test_runtime_has_no_direct_http_client() -> None:
    runtime_files = (
        Path("src/pdrive_desktop/domain"),
        Path("src/pdrive_desktop/application"),
        Path("src/pdrive_desktop/presentation"),
        Path("src/pdrive_desktop/infrastructure/proton_cli.py"),
    )
    forbidden = (
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
        "import aiohttp",
        "from aiohttp",
        "import urllib.request",
        "from urllib import request",
        "import socket",
        "from socket",
    )
    for target in runtime_files:
        files = target.rglob("*.py") if target.is_dir() else (target,)
        for source_file in files:
            source = source_file.read_text(encoding="utf-8")
            assert not any(token in source for token in forbidden), source_file
