import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from src.services.assessment_service import (
    EXEMPT_OWNER_CODES,
    apply_assessment_run,
    default_assessment_date,
    preview_assessment_run,
)


class AssessmentsFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, db_path: Path) -> None:
        super().__init__(parent, style="App.TFrame")
        self.db_path = db_path
        self.amount_var = tk.StringVar()
        self.date_var = tk.StringVar(value=default_assessment_date())
        self.preview_text = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build()

    def _build(self) -> None:
        intro = ttk.Label(
            self,
            text=(
                "Run the next assessment update across all lots. "
                "This follows the legacy UPDATE.PRG rules, including exempt owner codes and freeze handling."
            ),
        )
        intro.grid(row=0, column=0, sticky="w", pady=(0, 12))

        form = ttk.LabelFrame(self, text="Assessment run")
        form.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="New assessment amount").grid(row=0, column=0, sticky="w", padx=12, pady=8)
        ttk.Entry(form, textvariable=self.amount_var).grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=8)
        ttk.Label(form, text="Assessment date").grid(row=1, column=0, sticky="w", padx=12, pady=8)
        ttk.Entry(form, textvariable=self.date_var).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=8)
        ttk.Label(
            form,
            text=f"Exempt owner codes: {', '.join(sorted(EXEMPT_OWNER_CODES))}",
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 10))

        actions = ttk.Frame(self, style="App.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        ttk.Button(actions, text="Preview Update", command=self.preview_run).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Apply Assessment Update", command=self.apply_run).grid(row=0, column=1)

        self.preview_text = tk.Text(
            self,
            wrap="word",
            relief="flat",
            background="#ffffff",
            foreground="#1d2430",
            font=("TkDefaultFont", 11),
            padx=16,
            pady=16,
            height=18,
        )
        self.preview_text.grid(row=3, column=0, sticky="nsew")
        self.preview_text.insert(
            "1.0",
            "Preview the assessment run before applying it. A full database backup will be created before any update is saved.",
        )
        self.preview_text.configure(state="disabled")

    def _set_preview(self, text: str) -> None:
        if self.preview_text is None:
            return
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.preview_text.configure(state="disabled")

    def _parse_amount(self) -> float | None:
        try:
            amount = float(self.amount_var.get())
        except ValueError:
            messagebox.showerror("Invalid amount", "Enter a valid assessment amount.")
            return None
        if amount <= 0:
            messagebox.showerror("Invalid amount", "Assessment amount must be greater than zero.")
            return None
        return amount

    def preview_run(self) -> None:
        amount = self._parse_amount()
        if amount is None:
            return
        try:
            preview = preview_assessment_run(self.db_path, amount)
        except Exception as exc:
            messagebox.showerror("Preview failed", str(exc))
            return
        self._set_preview(
            "\n".join(
                [
                    f"Assessment amount: ${preview.assessment_amount:,.2f}",
                    f"Assessment date: {self.date_var.get().strip()}",
                    "",
                    f"Eligible lots: {preview.eligible_lots}",
                    f"Exempt lots: {preview.exempt_lots}",
                    f"Freeze lots: {preview.freeze_lots}",
                    f"Owners affected: {preview.owner_count}",
                    f"Projected total current assessment posted: ${preview.projected_current_assessment:,.2f}",
                    "",
                    "Legacy notes:",
                    "- Exempt owner codes are zeroed out if they carry a due balance.",
                    "- Frozen lots carry forward current assessment instead of rolling it into delinquent balance.",
                    "- Owner totals are recalculated after all lot updates.",
                    "- A backup is created before the run is applied.",
                ]
            )
        )

    def apply_run(self) -> None:
        amount = self._parse_amount()
        if amount is None:
            return
        confirm = messagebox.askyesno(
            "Confirm assessment update",
            "\n".join(
                [
                    f"Assessment amount: ${amount:,.2f}",
                    f"Assessment date: {self.date_var.get().strip()}",
                    "",
                    "This updates every eligible lot and recalculates owner totals.",
                    "A backup will be created first.",
                ]
            ),
        )
        if not confirm:
            return
        try:
            result = apply_assessment_run(self.db_path, amount, self.date_var.get().strip())
        except Exception as exc:
            messagebox.showerror("Assessment update failed", str(exc))
            return

        self._set_preview(
            "\n".join(
                [
                    "Assessment update completed.",
                    f"Lots updated: {result.lots_updated}",
                    f"Owners updated: {result.owners_updated}",
                    f"Exempt lots: {result.exempt_lots}",
                    f"Freeze lots: {result.freeze_lots}",
                    f"Backup: {result.backup_path}",
                ]
            )
        )
        messagebox.showinfo(
            "Assessment update complete",
            "\n".join(
                [
                    f"Lots updated: {result.lots_updated}",
                    f"Owners updated: {result.owners_updated}",
                    f"Backup: {result.backup_path}",
                ]
            ),
        )
