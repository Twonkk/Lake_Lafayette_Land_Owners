import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from src.db.repositories import OwnerRepository
from src.services.encumbrance_service import (
    assign_collection,
    default_action_date,
    record_lien,
    remove_collection,
    remove_lien,
)


class LienCollectionFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, db_path: Path) -> None:
        super().__init__(parent, style="App.TFrame")
        self.db_path = db_path
        self.repository = OwnerRepository(db_path)
        self.search_var = tk.StringVar()
        self.date_var = tk.StringVar(value=default_action_date())
        self.lien_amount_var = tk.StringVar(value="0.00")
        self.lien_book_var = tk.StringVar()
        self.lien_page_var = tk.StringVar()
        self.selected_owner_code: str | None = None
        self.selected_lots: set[str] = set()
        self.results: list[dict] = []

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build()
        self.run_search()

    def _build(self) -> None:
        ttk.Label(
            self,
            text="Record lien filing/removal and assign or remove lots from collection.",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        split = ttk.Panedwindow(self, orient="horizontal")
        split.grid(row=1, column=0, sticky="nsew")

        left = ttk.Frame(split, style="App.TFrame", padding=(0, 0, 12, 0))
        right = ttk.Frame(split, style="App.TFrame")
        split.add(left, weight=3)
        split.add(right, weight=2)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)
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
            columns=("owner_code", "name", "lots", "owed"),
            show="headings",
            height=10,
        )
        for name, width in [("owner_code", 85), ("name", 220), ("lots", 60), ("owed", 90)]:
            self.owner_tree.heading(name, text=name.replace("_", " ").title())
            self.owner_tree.column(name, width=width, anchor="center" if name in {"lots", "owed"} else "w")
        self.owner_tree.grid(row=2, column=0, sticky="nsew")
        self.owner_tree.bind("<<TreeviewSelect>>", self._on_select_owner)

        ttk.Label(left, text="Owner lots", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=(12, 8))
        self.lot_tree = ttk.Treeview(
            left,
            columns=("selected", "lot_number", "due", "lien", "collection"),
            show="headings",
            height=10,
        )
        for name, text, width in [
            ("selected", "Pick", 55),
            ("lot_number", "Lot", 90),
            ("due", "Balance", 90),
            ("lien", "Lien", 60),
            ("collection", "Collection", 80),
        ]:
            self.lot_tree.heading(name, text=text)
            self.lot_tree.column(name, width=width, anchor="center")
        self.lot_tree.grid(row=4, column=0, sticky="nsew")
        self.lot_tree.bind("<Button-1>", self._handle_lot_click)

        ttk.Label(right, text="Action details", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(right, text="Action date").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(right, textvariable=self.date_var).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(right, text="Lien amount").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(right, textvariable=self.lien_amount_var).grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(right, text="Book").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(right, textvariable=self.lien_book_var).grid(row=3, column=1, sticky="ew", pady=6)
        ttk.Label(right, text="Page").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(right, textvariable=self.lien_page_var).grid(row=4, column=1, sticky="ew", pady=6)

        actions = ttk.Frame(right, style="App.TFrame")
        actions.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        ttk.Button(actions, text="File Lien On Selected Lots", command=self.file_lien).grid(row=0, column=0, sticky="ew", pady=4)
        ttk.Button(actions, text="Remove Lien From Selected Lots", command=self.clear_lien).grid(row=1, column=0, sticky="ew", pady=4)
        ttk.Button(actions, text="Assign Selected Lots To Collection", command=self.mark_collection).grid(row=2, column=0, sticky="ew", pady=4)
        ttk.Button(actions, text="Remove Selected Lots From Collection", command=self.clear_collection).grid(row=3, column=0, sticky="ew", pady=4)

    def run_search(self, _event: object | None = None) -> None:
        self.results = self.repository.search(self.search_var.get())
        self.owner_tree.delete(*self.owner_tree.get_children())
        for owner in self.results:
            name = " ".join(part for part in [owner["last_name"], owner["first_name"]] if part).strip()
            self.owner_tree.insert(
                "",
                "end",
                iid=owner["owner_code"],
                values=(owner["owner_code"], name, owner["lot_count"], f"${float(owner['total_owed'] or 0):,.2f}"),
            )
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
        self.selected_lots = set()
        self.lot_tree.delete(*self.lot_tree.get_children())
        for lot in detail["lots"]:
            self.lot_tree.insert(
                "",
                "end",
                iid=lot["lot_number"],
                values=(
                    "[ ]",
                    lot["lot_number"],
                    f"${float(lot['total_due'] or 0):,.2f}",
                    lot["lien_flag"] or "",
                    lot["collection_flag"] or "",
                ),
            )

    def _handle_lot_click(self, event: tk.Event) -> str | None:
        row_id = self.lot_tree.identify_row(event.y)
        column_id = self.lot_tree.identify_column(event.x)
        if row_id and column_id == "#1":
            if row_id in self.selected_lots:
                self.selected_lots.remove(row_id)
            else:
                self.selected_lots.add(row_id)
            values = list(self.lot_tree.item(row_id, "values"))
            values[0] = "[x]" if row_id in self.selected_lots else "[ ]"
            self.lot_tree.item(row_id, values=values)
            return "break"
        return None

    def _refresh_current_owner(self) -> None:
        current = self.selected_owner_code
        self.run_search()
        if current and current in self.owner_tree.get_children():
            self.owner_tree.selection_set(current)
            self._load_owner(current)

    def _selected_lot_list(self) -> list[str]:
        return sorted(self.selected_lots)

    def file_lien(self) -> None:
        try:
            amount = float(self.lien_amount_var.get().strip() or 0)
            result = record_lien(
                self.db_path,
                self.selected_owner_code or "",
                self._selected_lot_list(),
                self.date_var.get().strip(),
                amount,
                self.lien_book_var.get().strip(),
                self.lien_page_var.get().strip(),
            )
        except Exception as exc:
            messagebox.showerror("Lien failed", str(exc))
            return
        messagebox.showinfo("Lien recorded", f"Filed lien on {len(result.lot_numbers)} lot(s).")
        self._refresh_current_owner()

    def clear_lien(self) -> None:
        try:
            result = remove_lien(
                self.db_path,
                self.selected_owner_code or "",
                self._selected_lot_list(),
                self.date_var.get().strip(),
            )
        except Exception as exc:
            messagebox.showerror("Lien removal failed", str(exc))
            return
        messagebox.showinfo("Lien removed", f"Removed lien from {len(result.lot_numbers)} lot(s).")
        self._refresh_current_owner()

    def mark_collection(self) -> None:
        try:
            result = assign_collection(
                self.db_path,
                self.selected_owner_code or "",
                self._selected_lot_list(),
                self.date_var.get().strip(),
            )
        except Exception as exc:
            messagebox.showerror("Collection assignment failed", str(exc))
            return
        messagebox.showinfo("Collection updated", f"Assigned {len(result.lot_numbers)} lot(s) to collection.")
        self._refresh_current_owner()

    def clear_collection(self) -> None:
        try:
            result = remove_collection(
                self.db_path,
                self.selected_owner_code or "",
                self._selected_lot_list(),
            )
        except Exception as exc:
            messagebox.showerror("Collection removal failed", str(exc))
            return
        messagebox.showinfo("Collection updated", f"Removed {len(result.lot_numbers)} lot(s) from collection.")
        self._refresh_current_owner()
