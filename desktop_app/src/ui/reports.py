import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from src.runtime import open_with_default_app
from src.services.report_service import (
    render_lot_report_pdf,
    render_mailing_labels_pdf,
    render_owner_report_pdf,
)


class ReportsFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, db_path: Path) -> None:
        super().__init__(parent, style="App.TFrame")
        self.db_path = db_path
        self.output_dir = db_path.parent / "generated_reports"

        ttk.Label(
            self,
            text="Owner and lot reports based on the legacy dBase report area.",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        actions = ttk.Frame(self, style="App.TFrame")
        actions.grid(row=1, column=0, sticky="w")
        ttk.Button(actions, text="Open Owner Report PDF", command=self.create_owner_report).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Open Lot Report PDF", command=self.create_lot_report).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text="Open Mailing Labels PDF", command=self.create_mailing_labels).grid(row=0, column=2)

    def _open_created_file(self, path: Path, title: str) -> None:
        try:
            open_with_default_app(path)
        except Exception as exc:
            messagebox.showerror(
                title,
                "\n".join(
                    [
                        "The report file was created, but it could not be opened automatically.",
                        str(path),
                        "",
                        str(exc),
                    ]
                ),
            )

    def create_owner_report(self) -> None:
        try:
            output = render_owner_report_pdf(self.db_path, self.output_dir)
        except Exception as exc:
            messagebox.showerror("Report failed", str(exc))
            return
        self._open_created_file(output, "Owner report preview failed")

    def create_lot_report(self) -> None:
        try:
            output = render_lot_report_pdf(self.db_path, self.output_dir)
        except Exception as exc:
            messagebox.showerror("Report failed", str(exc))
            return
        self._open_created_file(output, "Lot report preview failed")

    def create_mailing_labels(self) -> None:
        try:
            output = render_mailing_labels_pdf(self.db_path, self.output_dir)
        except Exception as exc:
            messagebox.showerror("Report failed", str(exc))
            return
        self._open_created_file(output, "Mailing labels preview failed")
