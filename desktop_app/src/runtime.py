from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


APP_NAME = "Lake Lafayette Landowners Association"
APP_SLUG = "LakeLotManager"
APP_VERSION = "0.1.6"
DB_FILENAME = "lake_lot.sqlite3"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_data_home() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base)
        return Path.home() / "AppData" / "Local"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".local" / "share"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


@dataclass(slots=True)
class AppPaths:
    install_dir: Path
    project_dir: Path
    data_dir: Path
    logs_dir: Path
    backup_dir: Path
    notices_dir: Path
    reports_dir: Path
    db_path: Path
    legacy_dir: Path
    update_config_path: Path


def resolve_app_paths() -> AppPaths:
    project_dir = _project_root()
    install_dir = Path(sys.executable).resolve().parent if is_frozen() else project_dir
    data_dir = _default_data_home() / APP_SLUG
    logs_dir = data_dir / "logs"
    backup_dir = data_dir / "backups"
    notices_dir = data_dir / "generated_notices"
    reports_dir = data_dir / "generated_reports"
    db_path = data_dir / DB_FILENAME
    update_config_path = data_dir / "update_config.json"

    saved_legacy = load_saved_legacy_dir(update_config_path)
    bundled_legacy = install_dir / "dbase"
    project_legacy = project_dir.parent / "dbase"
    default_legacy = bundled_legacy if bundled_legacy.exists() else project_legacy
    legacy_dir = saved_legacy or default_legacy

    return AppPaths(
        install_dir=install_dir,
        project_dir=project_dir,
        data_dir=data_dir,
        logs_dir=logs_dir,
        backup_dir=backup_dir,
        notices_dir=notices_dir,
        reports_dir=reports_dir,
        db_path=db_path,
        legacy_dir=legacy_dir,
        update_config_path=update_config_path,
    )


def ensure_runtime_dirs(paths: AppPaths) -> None:
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    paths.backup_dir.mkdir(parents=True, exist_ok=True)
    paths.notices_dir.mkdir(parents=True, exist_ok=True)
    paths.reports_dir.mkdir(parents=True, exist_ok=True)


def bootstrap_existing_local_database(paths: AppPaths) -> None:
    if paths.db_path.exists():
        return

    candidates = [
        paths.project_dir / "data" / DB_FILENAME,
        paths.project_dir / "data" / "lake_lot (1).sqlite3",
    ]
    for candidate in candidates:
        if candidate.exists():
            shutil.copy2(candidate, paths.db_path)
            return


def load_update_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_update_config(config_path: Path, payload: dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_saved_legacy_dir(config_path: Path) -> Path | None:
    payload = load_update_config(config_path)
    legacy_dir = payload.get("legacy_dir")
    if not legacy_dir:
        return None
    return Path(str(legacy_dir)).expanduser()


def save_legacy_dir(config_path: Path, legacy_dir: Path) -> None:
    payload = load_update_config(config_path)
    payload["legacy_dir"] = str(Path(legacy_dir).resolve())
    save_update_config(config_path, payload)


def has_seen_screen_help(config_path: Path, screen_key: str) -> bool:
    payload = load_update_config(config_path)
    seen = payload.get("seen_screen_help", {})
    return bool(seen.get(screen_key))


def save_seen_screen_help(config_path: Path, screen_key: str, seen: bool = True) -> None:
    payload = load_update_config(config_path)
    seen_map = payload.get("seen_screen_help", {})
    if not isinstance(seen_map, dict):
        seen_map = {}
    seen_map[screen_key] = bool(seen)
    payload["seen_screen_help"] = seen_map
    save_update_config(config_path, payload)


def reset_seen_screen_help(config_path: Path) -> None:
    payload = load_update_config(config_path)
    payload["seen_screen_help"] = {}
    save_update_config(config_path, payload)


def open_with_default_app(path: Path) -> None:
    target = Path(path)
    if sys.platform == "win32":
        os.startfile(str(target))
        return
    if sys.platform == "darwin":
        result = subprocess.run(["open", str(target)], check=False, capture_output=True, text=True)
    else:
        result = subprocess.run(
            ["xdg-open", str(target)],
            check=False,
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "Unknown viewer launch error."
        raise RuntimeError(detail)
