from __future__ import annotations

from pathlib import Path
import os
import subprocess


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

    result = subprocess.run(
        [
            "libreoffice",
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
