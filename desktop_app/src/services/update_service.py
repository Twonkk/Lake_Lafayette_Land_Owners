from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.runtime import APP_VERSION, load_update_config, save_update_config


DEFAULT_UPDATE_CONFIG = {
    "channel": "stable",
    "provider": "github-releases",
    "repo_owner": "Twonkk",
    "repo_name": "Lake_Lafayette_Land_Owners",
    "manifest_url": "https://api.github.com/repos/Twonkk/Lake_Lafayette_Land_Owners/releases/latest",
}


@dataclass(slots=True)
class ReleaseAsset:
    name: str
    download_url: str
    size_bytes: int


@dataclass(slots=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str
    update_available: bool
    release_name: str
    release_notes: str
    release_page_url: str
    installer_asset: ReleaseAsset | None


def _normalize_version(value: str) -> str:
    return value.strip().lower().removeprefix("v")


def _version_tuple(value: str) -> tuple[int, ...]:
    pieces: list[int] = []
    for piece in _normalize_version(value).split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        pieces.append(int(digits or 0))
    return tuple(pieces)


def _merge_update_config(config_path: Path) -> dict:
    payload = DEFAULT_UPDATE_CONFIG.copy()
    saved = load_update_config(config_path)
    payload.update({key: value for key, value in saved.items() if value not in (None, "")})
    payload["current_version"] = APP_VERSION
    return payload


def _request_json(url: str) -> dict:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "LakeLotManager-Updater",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Update check failed with GitHub status {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError(f"Update check failed: {exc.reason}") from exc


def check_for_updates(config_path: Path) -> UpdateCheckResult:
    config = _merge_update_config(config_path)
    payload = _request_json(config["manifest_url"])

    latest_tag = str(payload.get("tag_name") or "").strip()
    latest_version = _normalize_version(latest_tag or APP_VERSION)
    current_version = _normalize_version(APP_VERSION)

    assets = payload.get("assets") or []
    installer_asset = None
    for asset in assets:
        name = str(asset.get("name") or "")
        if not name.lower().endswith(".exe"):
            continue
        if "setup" in name.lower() or installer_asset is None:
            installer_asset = ReleaseAsset(
                name=name,
                download_url=str(asset.get("browser_download_url") or ""),
                size_bytes=int(asset.get("size") or 0),
            )
            if "setup" in name.lower():
                break

    result = UpdateCheckResult(
        current_version=current_version,
        latest_version=latest_version,
        update_available=_version_tuple(latest_version) > _version_tuple(current_version),
        release_name=str(payload.get("name") or latest_tag or f"v{latest_version}"),
        release_notes=str(payload.get("body") or "").strip(),
        release_page_url=str(payload.get("html_url") or ""),
        installer_asset=installer_asset,
    )

    saved = load_update_config(config_path)
    saved["last_update_check_version"] = result.latest_version
    saved["last_update_check_release_name"] = result.release_name
    save_update_config(config_path, saved)
    return result


def download_update_asset(asset: ReleaseAsset, destination_dir: Path) -> Path:
    if not asset.download_url:
        raise RuntimeError("The latest release does not include a downloadable installer asset.")

    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / asset.name
    request = Request(asset.download_url, headers={"User-Agent": "LakeLotManager-Updater"})
    try:
        with urlopen(request, timeout=60) as response, destination_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 128)
                if not chunk:
                    break
                handle.write(chunk)
    except HTTPError as exc:
        raise RuntimeError(f"Download failed with GitHub status {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError(f"Download failed: {exc.reason}") from exc

    return destination_path


def launch_update_installer(installer_path: Path, updates_dir: Path, current_pid: int) -> None:
    installer = Path(installer_path).resolve()
    if not installer.exists():
        raise RuntimeError(f"Installer was not found: {installer}")

    if sys.platform != "win32":
        raise RuntimeError("Automatic installer handoff is only supported on Windows.")

    updates_dir.mkdir(parents=True, exist_ok=True)
    script_path = updates_dir / "run_update.cmd"
    script_path.write_text(
        "\n".join(
            [
                "@echo off",
                "setlocal",
                f"set TARGET_PID={int(current_pid)}",
                f'set INSTALLER={str(installer)}',
                ":waitloop",
                'tasklist /FI "PID eq %TARGET_PID%" | find "%TARGET_PID%" >nul',
                "if not errorlevel 1 (",
                "  timeout /t 1 /nobreak >nul",
                "  goto waitloop",
                ")",
                'start "" "%INSTALLER%"',
                "endlocal",
            ]
        ),
        encoding="utf-8",
    )

    creationflags = 0
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creationflags |= subprocess.DETACHED_PROCESS

    subprocess.Popen(
        ["cmd", "/c", str(script_path)],
        cwd=str(updates_dir),
        creationflags=creationflags,
        close_fds=True,
    )
