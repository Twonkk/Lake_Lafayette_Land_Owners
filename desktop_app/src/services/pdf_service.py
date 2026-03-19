from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys


def _candidate_office_commands() -> list[str]:
    commands: list[str] = []
    for name in ("soffice", "libreoffice"):
        resolved = shutil.which(name)
        if resolved:
            commands.append(resolved)
    if sys.platform == "win32":
        program_files = [
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
        ]
        for base in program_files:
            if not base:
                continue
            for candidate in (
                Path(base) / "LibreOffice" / "program" / "soffice.exe",
                Path(base) / "LibreOffice" / "program" / "soffice.com",
            ):
                if candidate.exists():
                    commands.append(str(candidate))
    return list(dict.fromkeys(commands))


def pdf_runtime_available() -> tuple[bool, str]:
    commands = _candidate_office_commands()
    if not commands:
        return False, "LibreOffice was not found. Install LibreOffice to enable PDF output."
    return True, commands[0]


def convert_html_to_pdf(html_path: Path, error_prefix: str) -> Path:
    pdf_path = html_path.with_suffix(".pdf")
    runtime_dir = html_path.parent / ".lo_runtime"
    config_home = html_path.parent / ".lo_config"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    config_home.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["HOME"] = str(config_home)
    env["XDG_CONFIG_HOME"] = str(config_home)
    env["XDG_RUNTIME_DIR"] = str(runtime_dir)

    available, runtime_value = pdf_runtime_available()
    if not available:
        raise RuntimeError(f"{error_prefix} {runtime_value}")

    result = subprocess.run(
        [
            runtime_value,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(html_path.parent),
            str(html_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0 or not pdf_path.exists():
        detail = result.stderr.strip() or result.stdout.strip() or "Unknown PDF conversion error."
        raise RuntimeError(f"{error_prefix} {detail}")
    return pdf_path
