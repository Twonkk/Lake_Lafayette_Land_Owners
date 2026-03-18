import tkinter as tk
from pathlib import Path
from tkinter import ttk

from src.services.utility_service import run_data_health_checks


class UtilitiesFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, db_path: Path, refresh_callback) -> None:
        super().__init__(parent, style="App.TFrame")
        self.db_path = db_path
        self.refresh_callback = refresh_callback
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        ttk.Label(
            self,
            text="Data-health checks inspired by the dBase file-test utilities.",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))
        actions = ttk.Frame(self, style="App.TFrame")
        actions.grid(row=1, column=0, sticky="w", pady=(0, 12))
        ttk.Button(actions, text="Run Data Health Checks", command=self.run_checks).grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Button(actions, text="Refresh From dBase", command=self.refresh_callback).grid(
            row=0, column=1, sticky="w"
        )

        self.output = tk.Text(
            self,
            wrap="word",
            relief="flat",
            background="#ffffff",
            foreground="#1d2430",
            font=("TkDefaultFont", 11),
            padx=16,
            pady=16,
        )
        self.output.grid(row=2, column=0, sticky="nsew")
        self.output.insert("1.0", "Run the checks to review duplicate codes, lot mismatches, orphan records, and total mismatches.")
        self.output.configure(state="disabled")

    def run_checks(self) -> None:
        results = run_data_health_checks(self.db_path)
        lines = []
        for result in results:
            lines.append(f"{result.title}: {result.issue_count}")
            if result.details:
                lines.extend([f"  {detail}" for detail in result.details])
            lines.append("")
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", "\n".join(lines).strip())
        self.output.configure(state="disabled")
