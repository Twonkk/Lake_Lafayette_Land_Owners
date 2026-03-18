import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from src.db.repositories import OwnerRepository
from src.runtime import open_with_default_app
from src.services.cards_stickers_service import (
    BoatStickerRequest,
    IdCardRequest,
    convert_cards_stickers_html_to_pdf,
    default_issue_date,
    default_sticker_year,
    record_boat_sticker_purchase,
    record_id_card_issue,
    render_boat_sticker_receipt_html,
    render_id_card_receipt_html,
)


class CardsStickersFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, db_path: Path) -> None:
        super().__init__(parent, style="App.TFrame")
        self.db_path = db_path
        self.repository = OwnerRepository(db_path)
        self.search_var = tk.StringVar()
        self.selected_owner_code: str | None = None
        self.selected_lot_var = tk.StringVar()
        self.sticker_year_var = tk.StringVar(value=default_sticker_year())
        self.sticker_quantity_var = tk.StringVar(value="1")
        self.sticker_amount_var = tk.StringVar(value="0.00")
        self.id_issue_date_var = tk.StringVar(value=default_issue_date())
        self.id_quantity_var = tk.StringVar(value="1")
        self.results: list[dict] = []

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build()
        self.run_search()

    def _build(self) -> None:
        ttk.Label(
            self,
            text="Record boat sticker purchases and issue ID cards for the selected owner.",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        split = ttk.Panedwindow(self, orient="horizontal")
        split.grid(row=1, column=0, sticky="nsew")

        left = ttk.Frame(split, style="App.TFrame", padding=(0, 0, 12, 0))
        right = ttk.Frame(split, style="App.TFrame")
        split.add(left, weight=2)
        split.add(right, weight=3)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)
        right.columnconfigure(1, weight=1)

        search_row = ttk.Frame(left, style="App.TFrame")
        search_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="Search owner").grid(row=0, column=0, sticky="w", padx=(0, 8))
        entry = ttk.Entry(search_row, textvariable=self.search_var)
        entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        entry.bind("<Return>", self.run_search)
        ttk.Button(search_row, text="Search", command=self.run_search).grid(row=0, column=2, sticky="w")

        ttk.Label(left, text="Owners", style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.owner_tree = ttk.Treeview(
            left,
            columns=("owner_code", "name", "lots"),
            show="headings",
            height=18,
        )
        for name, width in [("owner_code", 85), ("name", 220), ("lots", 60)]:
            self.owner_tree.heading(name, text=name.replace("_", " ").title())
            self.owner_tree.column(name, width=width, anchor="center" if name == "lots" else "w")
        self.owner_tree.grid(row=2, column=0, sticky="nsew")
        self.owner_tree.bind("<<TreeviewSelect>>", self._on_select_owner)

        ttk.Label(right, text="Owner lot", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Label(right, text="Lot").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=6)
        self.lot_combo = ttk.Combobox(right, textvariable=self.selected_lot_var, state="readonly")
        self.lot_combo.grid(row=1, column=1, sticky="ew", pady=6)

        sticker_box = ttk.LabelFrame(right, text="Boat Stickers")
        sticker_box.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        sticker_box.columnconfigure(1, weight=1)
        ttk.Label(sticker_box, text="Sticker year").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(sticker_box, textvariable=self.sticker_year_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(sticker_box, text="Quantity").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(sticker_box, textvariable=self.sticker_quantity_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(sticker_box, text="Amount").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(sticker_box, textvariable=self.sticker_amount_var).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(sticker_box, text="Notes").grid(row=3, column=0, sticky="nw", padx=(0, 8), pady=4)
        self.sticker_notes = tk.Text(sticker_box, height=5, wrap="word")
        self.sticker_notes.grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Button(sticker_box, text="Record Boat Sticker Purchase", command=self.record_sticker_purchase).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

        id_box = ttk.LabelFrame(right, text="ID Cards")
        id_box.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        id_box.columnconfigure(1, weight=1)
        ttk.Label(id_box, text="Issue date").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(id_box, textvariable=self.id_issue_date_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(id_box, text="Quantity").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(id_box, textvariable=self.id_quantity_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(id_box, text="Notes").grid(row=2, column=0, sticky="nw", padx=(0, 8), pady=4)
        self.id_notes = tk.Text(id_box, height=5, wrap="word")
        self.id_notes.grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Button(id_box, text="Issue ID Card", command=self.issue_id_card).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

    def run_search(self, _event: object | None = None) -> None:
        self.results = self.repository.search(self.search_var.get())
        self.owner_tree.delete(*self.owner_tree.get_children())
        for owner in self.results:
            name = " ".join(part for part in [owner["last_name"], owner["first_name"]] if part).strip()
            self.owner_tree.insert("", "end", iid=owner["owner_code"], values=(owner["owner_code"], name, owner["lot_count"]))
        children = self.owner_tree.get_children()
        if children:
            self.owner_tree.selection_set(children[0])
            self._load_owner(children[0])

    def _on_select_owner(self, _event: object | None = None) -> None:
        selected = self.owner_tree.selection()
        if selected:
            self._load_owner(selected[0])

    def _load_owner(self, owner_code: str) -> None:
        detail = self.repository.get_owner_detail(owner_code)
        if detail is None:
            return
        self.selected_owner_code = owner_code
        lots = [row["lot_number"] for row in detail["lots"]]
        self.lot_combo["values"] = lots
        self.selected_lot_var.set(lots[0] if lots else "")

    def _open_created_file(self, path: Path, title: str) -> None:
        try:
            open_with_default_app(path)
        except Exception as exc:
            messagebox.showerror(title, f"The PDF was created but could not be opened automatically.\n\n{path}\n\n{exc}")

    def record_sticker_purchase(self) -> None:
        if not self.selected_owner_code:
            messagebox.showerror("Missing owner", "Select an owner first.")
            return
        try:
            request = BoatStickerRequest(
                owner_code=self.selected_owner_code,
                lot_number=self.selected_lot_var.get().strip(),
                sticker_year=self.sticker_year_var.get().strip(),
                quantity=int(self.sticker_quantity_var.get().strip() or "0"),
                amount=float(self.sticker_amount_var.get().strip() or "0"),
                notes=self.sticker_notes.get("1.0", "end").strip(),
            )
            record_boat_sticker_purchase(self.db_path, request)
            html = render_boat_sticker_receipt_html(self.db_path, request, self.db_path.parent / "generated_reports")
            pdf = convert_cards_stickers_html_to_pdf(html)
            html.unlink(missing_ok=True)
        except Exception as exc:
            messagebox.showerror("Boat sticker failed", str(exc))
            return
        self._open_created_file(pdf, "Boat sticker preview failed")
        self.sticker_notes.delete("1.0", "end")

    def issue_id_card(self) -> None:
        if not self.selected_owner_code:
            messagebox.showerror("Missing owner", "Select an owner first.")
            return
        try:
            request = IdCardRequest(
                owner_code=self.selected_owner_code,
                lot_number=self.selected_lot_var.get().strip(),
                issue_date=self.id_issue_date_var.get().strip(),
                quantity=int(self.id_quantity_var.get().strip() or "0"),
                notes=self.id_notes.get("1.0", "end").strip(),
            )
            record_id_card_issue(self.db_path, request)
            html = render_id_card_receipt_html(self.db_path, request, self.db_path.parent / "generated_reports")
            pdf = convert_cards_stickers_html_to_pdf(html)
            html.unlink(missing_ok=True)
        except Exception as exc:
            messagebox.showerror("ID card issue failed", str(exc))
            return
        self._open_created_file(pdf, "ID card preview failed")
        self.id_notes.delete("1.0", "end")
