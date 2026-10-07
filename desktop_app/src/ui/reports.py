import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import messagebox, ttk

from src.runtime import open_with_default_app
from src.services.cards_stickers_service import mark_open_id_orders_completed
from src.services.report_service import (
    render_card_sticker_summary_pdf,
    render_custom_lot_report_pdf,
    render_custom_owner_report_pdf,
    render_lot_report_pdf,
    render_mailing_labels_pdf,
    render_owner_report_pdf,
    render_voter_list_pdf,
)


class ReportsFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, db_path: Path) -> None:
        super().__init__(parent, style="App.TFrame")
        self.db_path = db_path
        self.output_dir = db_path.parent / "generated_reports"

        self.label_resident_var = tk.StringVar(value="All")
        self.label_lien_var = tk.BooleanVar(value=False)
        self.owner_zip_var = tk.StringVar()
        self.owner_resident_var = tk.StringVar(value="All")
        self.owner_lien_var = tk.StringVar(value="All")
        self.owner_collection_var = tk.StringVar(value="All")
        self.owner_unknown_var = tk.BooleanVar(value=False)
        self.owner_min_var = tk.StringVar()
        self.owner_max_var = tk.StringVar()
        self.lot_plat_var = tk.StringVar()
        self.lot_lien_var = tk.StringVar(value="All")
        self.lot_current_var = tk.BooleanVar(value=False)
        self.lot_min_var = tk.StringVar()
        self.lot_max_var = tk.StringVar()
        self.lot_lakefront_var = tk.BooleanVar(value=False)
        self.lot_development_var = tk.StringVar()
        self.lot_trust_var = tk.StringVar(value="All")
        self.card_mode_var = tk.StringVar(value="Open ID orders")
        self.card_year_var = tk.StringVar(value=str(date.today().year))
        self.card_sort_var = tk.StringVar(value="Name")
        self.card_complete_var = tk.BooleanVar(value=True)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text="Standard and custom owner, lot, voter, mailing, ID-card, and boat reports.").grid(
            row=0, column=0, sticky="w", pady=(0, 12)
        )
        notebook = ttk.Notebook(self)
        notebook.grid(row=1, column=0, sticky="nsew")
        standard = ttk.Frame(notebook, style="App.TFrame", padding=12)
        owner = ttk.Frame(notebook, style="App.TFrame", padding=12)
        lot = ttk.Frame(notebook, style="App.TFrame", padding=12)
        cards = ttk.Frame(notebook, style="App.TFrame", padding=12)
        notebook.add(standard, text="Standard / Labels")
        notebook.add(owner, text="Custom Owner")
        notebook.add(lot, text="Custom Lot")
        notebook.add(cards, text="ID / Boat Lists")
        self._build_standard(standard)
        self._build_owner(owner)
        self._build_lot(lot)
        self._build_cards(cards)

    def _open(self, creator, title: str) -> None:
        try:
            output = creator()
            open_with_default_app(output)
        except Exception as exc:
            messagebox.showerror(f"{title} failed", str(exc))

    def _build_standard(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        ttk.Button(parent, text="Open Current Owner Report PDF", command=lambda: self._open(
            lambda: render_owner_report_pdf(self.db_path, self.output_dir), "Owner report"
        )).grid(row=0, column=0, columnspan=2, sticky="ew", pady=5)
        ttk.Button(parent, text="Open Complete Lot Report PDF", command=lambda: self._open(
            lambda: render_lot_report_pdf(self.db_path, self.output_dir), "Lot report"
        )).grid(row=1, column=0, columnspan=2, sticky="ew", pady=5)
        ttk.Button(parent, text="Open Eligible Voter List PDF", command=lambda: self._open(
            lambda: render_voter_list_pdf(self.db_path, self.output_dir), "Voter list"
        )).grid(row=2, column=0, columnspan=2, sticky="ew", pady=5)

        labels = ttk.LabelFrame(parent, text="Mailing labels")
        labels.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        labels.columnconfigure(1, weight=1)
        ttk.Label(labels, text="Owners").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=5)
        ttk.Combobox(labels, textvariable=self.label_resident_var,
                     values=["All", "Residents", "Nonresidents"], state="readonly").grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Checkbutton(labels, text="Only owners with liens", variable=self.label_lien_var).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=5
        )
        ttk.Button(labels, text="Open Mailing Labels PDF", command=lambda: self._open(
            lambda: render_mailing_labels_pdf(
                self.db_path, self.output_dir,
                resident_filter=self.label_resident_var.get(), lien_only=self.label_lien_var.get(),
            ), "Mailing labels"
        )).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _row(self, parent: ttk.Frame, row: int, label: str, variable: tk.Variable, values=None) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=5)
        widget = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly") if values else ttk.Entry(parent, textvariable=variable)
        widget.grid(row=row, column=1, sticky="ew", pady=5)

    def _build_owner(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        self._row(parent, 0, "ZIP code", self.owner_zip_var)
        self._row(parent, 1, "Resident status", self.owner_resident_var, ["All", "Residents", "Nonresidents"])
        self._row(parent, 2, "Lien status", self.owner_lien_var, ["All", "With lien", "Without lien"])
        self._row(parent, 3, "Collection agency", self.owner_collection_var, ["All", "In collection", "Not in collection"])
        self._row(parent, 4, "Minimum owed", self.owner_min_var)
        self._row(parent, 5, "Maximum owed", self.owner_max_var)
        ttk.Checkbutton(parent, text="Only unknown addresses", variable=self.owner_unknown_var).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=5
        )
        ttk.Button(parent, text="Open Custom Owner Report PDF", command=self.create_custom_owner).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )

    def _build_lot(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        self._row(parent, 0, "Plat", self.lot_plat_var)
        self._row(parent, 1, "Lien status", self.lot_lien_var, ["All", "With lien", "Without lien"])
        self._row(parent, 2, "Minimum owed", self.lot_min_var)
        self._row(parent, 3, "Maximum owed", self.lot_max_var)
        self._row(parent, 4, "Development status", self.lot_development_var)
        self._row(parent, 5, "County land trust", self.lot_trust_var, ["All", "County trust", "Not county trust"])
        ttk.Checkbutton(parent, text="Only lots current on assessments", variable=self.lot_current_var).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=5
        )
        ttk.Checkbutton(parent, text="Only lakefront lots", variable=self.lot_lakefront_var).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=5
        )
        ttk.Button(parent, text="Open Custom Lot Report PDF", command=self.create_custom_lot).grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )

    def _build_cards(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        self._row(parent, 0, "Report", self.card_mode_var, ["Open ID orders", "Cards by year", "Boat stickers by year"])
        self._row(parent, 1, "Year", self.card_year_var)
        self._row(parent, 2, "Sort by", self.card_sort_var, ["Name", "Lot"])
        ttk.Checkbutton(
            parent,
            text="Mark the listed open ID orders filled after creating the PDF (dBase behavior)",
            variable=self.card_complete_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Button(parent, text="Open ID / Boat Report PDF", command=self.create_card_report).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )

    @staticmethod
    def _optional_float(value: str) -> float | None:
        return float(value) if value.strip() else None

    def create_custom_owner(self) -> None:
        try:
            minimum = self._optional_float(self.owner_min_var.get())
            maximum = self._optional_float(self.owner_max_var.get())
        except ValueError:
            messagebox.showerror("Invalid amount", "Minimum and maximum owed must be numbers.")
            return
        self._open(lambda: render_custom_owner_report_pdf(
            self.db_path, self.output_dir, zip_code=self.owner_zip_var.get(),
            resident_filter=self.owner_resident_var.get(), lien_filter=self.owner_lien_var.get(),
            collection_filter=self.owner_collection_var.get(), unknown_only=self.owner_unknown_var.get(),
            minimum_owed=minimum, maximum_owed=maximum,
        ), "Custom owner report")

    def create_custom_lot(self) -> None:
        try:
            minimum = self._optional_float(self.lot_min_var.get())
            maximum = self._optional_float(self.lot_max_var.get())
        except ValueError:
            messagebox.showerror("Invalid amount", "Minimum and maximum owed must be numbers.")
            return
        self._open(lambda: render_custom_lot_report_pdf(
            self.db_path, self.output_dir, plat=self.lot_plat_var.get(), lien_filter=self.lot_lien_var.get(),
            current_only=self.lot_current_var.get(), minimum_owed=minimum, maximum_owed=maximum,
            lakefront_only=self.lot_lakefront_var.get(), development_status=self.lot_development_var.get(),
            trust_filter=self.lot_trust_var.get(),
        ), "Custom lot report")

    def create_card_report(self) -> None:
        try:
            year = int(self.card_year_var.get())
        except ValueError:
            messagebox.showerror("Invalid year", "Enter a four-digit year.")
            return
        mode = self.card_mode_var.get()
        try:
            output = render_card_sticker_summary_pdf(
                self.db_path, self.output_dir, mode=mode, year=year,
                sort_by=self.card_sort_var.get(),
            )
        except Exception as exc:
            messagebox.showerror("ID / boat report failed", str(exc))
            return
        try:
            open_with_default_app(output)
        except Exception as exc:
            messagebox.showwarning(
                "Report created; preview could not open",
                f"The PDF was created at:\n{output}\n\nPreview issue: {exc}",
            )
        if mode == "Open ID orders" and self.card_complete_var.get():
            try:
                count, backup = mark_open_id_orders_completed(self.db_path)
            except Exception as exc:
                messagebox.showerror("Report created; orders not marked filled", str(exc))
                return
            if count:
                messagebox.showinfo(
                    "ID orders marked filled",
                    f"{count} open ID card order(s) were marked filled.\nBackup: {backup}",
                )
