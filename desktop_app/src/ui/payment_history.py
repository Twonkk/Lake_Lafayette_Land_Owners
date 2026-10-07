import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from src.db.repositories import PaymentRepository
from src.runtime import open_with_default_app
from src.services.history_service import (
    render_history_pdf,
    search_id_boat_history,
    search_lot_payment_history,
    search_ownership_history,
)
from src.services.payment_service import payment_form_label


class PaymentHistoryFrame(ttk.Frame):
    """The complete four-part history menu from dBase."""

    def __init__(self, parent: tk.Misc, db_path: Path) -> None:
        super().__init__(parent, style="App.TFrame")
        self.db_path = db_path
        self.repository = PaymentRepository(db_path)
        self.search_var = tk.StringVar()
        self.current_rows: list[dict] = []
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build()
        self.run_search()

    def _build(self) -> None:
        ttk.Label(
            self,
            text="Search owner, lot, payment, property-sale, ID-card, and boat-sticker history.",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        search_row = ttk.Frame(self, style="App.TFrame")
        search_row.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="Search history").grid(row=0, column=0, sticky="w", padx=(0, 8))
        entry = ttk.Entry(search_row, textvariable=self.search_var)
        entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        entry.bind("<Return>", self.run_search)
        ttk.Button(search_row, text="Search", command=self.run_search).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(search_row, text="Open Current History PDF", command=self.open_pdf).grid(row=0, column=3)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=2, column=0, sticky="nsew")
        self.notebook.bind("<<NotebookTabChanged>>", self.run_search)

        tabs = [ttk.Frame(self.notebook, style="App.TFrame", padding=10) for _ in range(4)]
        for tab, label in zip(tabs, ["Owner Payments", "Lot Payments", "Ownership", "ID / Boat"]):
            self.notebook.add(tab, text=label)
        self.owner_tab, self.lot_tab, self.ownership_tab, self.id_tab = tabs

        self.owner_tree = self._tree(
            self.owner_tab,
            [("date", "Date", 95), ("owner", "Owner Code", 85), ("name", "Owner", 210),
             ("owed", "Owed Before", 100), ("paid", "Paid", 95), ("form", "Form", 125),
             ("check", "Check / Ref", 100)],
            self._show_owner_payment,
        )
        self.lot_tree = self._tree(
            self.lot_tab,
            [("date", "Date", 95), ("lot", "Lot", 80), ("owner", "Owner", 85),
             ("name", "Name", 190), ("paid", "Paid", 95), ("form", "Form", 120),
             ("through", "Paid Through", 100)],
            self._show_lot_payment,
        )
        self.ownership_tree = self._tree(
            self.ownership_tab,
            [("date", "Sale Date", 100), ("lot", "Lot", 85), ("seller", "Seller", 90),
             ("buyer", "Buyer", 90), ("source", "Source", 75), ("status", "Status", 90)],
            None,
        )
        self.id_tree = self._tree(
            self.id_tab,
            [("date", "Date", 100), ("owner", "Owner", 85), ("name", "Last Name", 180),
             ("lot", "Lot", 85), ("owner_cards", "Owner Cards", 90),
             ("renter_cards", "Renter Cards", 90), ("boats", "Boat", 65),
             ("source", "Source", 70)],
            None,
        )

    def _tree(self, parent: ttk.Frame, columns: list[tuple[str, str, int]], callback) -> ttk.Treeview:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        tree = ttk.Treeview(parent, columns=[item[0] for item in columns], show="headings")
        for key, heading, width in columns:
            tree.heading(key, text=heading)
            tree.column(key, width=width, anchor="w")
        tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)
        if callback:
            tree.bind("<Double-1>", callback)
            tree.bind("<Return>", callback)
        return tree

    def _active_index(self) -> int:
        return self.notebook.index(self.notebook.select()) if self.notebook.select() else 0

    def run_search(self, _event: object | None = None) -> None:
        if not hasattr(self, "notebook"):
            return
        index = self._active_index()
        query = self.search_var.get()
        if index == 0:
            self._load_owner_payments(query)
        elif index == 1:
            self._load_lot_payments(query)
        elif index == 2:
            self._load_ownership(query)
        else:
            self._load_id_boat(query)

    def _load_owner_payments(self, query: str) -> None:
        rows = self.repository.search_history(query, limit=2000)
        self.current_rows = rows
        self.owner_tree.delete(*self.owner_tree.get_children())
        for row in rows:
            name = " ".join(part for part in [row["last_name"], row["first_name"]] if part).strip()
            self.owner_tree.insert("", "end", iid=str(row["id"]), values=(
                row["payment_date"] or "", row["owner_code"], name,
                f"${float(row['total_owed'] or 0):,.2f}", f"${float(row['payment_amount'] or 0):,.2f}",
                payment_form_label(row["payment_form"]), row["check_number"] or "",
            ))

    def _load_lot_payments(self, query: str) -> None:
        rows = search_lot_payment_history(self.db_path, query)
        self.current_rows = rows
        self.lot_tree.delete(*self.lot_tree.get_children())
        for row in rows:
            name = " ".join(part for part in [row["last_name"], row["first_name"]] if part).strip()
            self.lot_tree.insert("", "end", iid=str(row["id"]), values=(
                row["payment_date"] or "", row["lot_number"], row["owner_code"] or "", name,
                f"${float(row['payment_amount'] or 0):,.2f}", payment_form_label(row["payment_form"]),
                row["paid_through"] or "",
            ))

    def _load_ownership(self, query: str) -> None:
        rows = search_ownership_history(self.db_path, query)
        self.current_rows = rows
        self.ownership_tree.delete(*self.ownership_tree.get_children())
        for index, row in enumerate(rows):
            self.ownership_tree.insert("", "end", iid=f"sale-{index}", values=(
                row["sale_date"] or "", row["lot_number"] or "", row["seller_owner_code"] or "",
                row["buyer_owner_code"] or "", row["source"], row["status"] or "",
            ))

    def _load_id_boat(self, query: str) -> None:
        rows = search_id_boat_history(self.db_path, query)
        self.current_rows = rows
        self.id_tree.delete(*self.id_tree.get_children())
        for index, row in enumerate(rows):
            self.id_tree.insert("", "end", iid=f"id-{index}", values=(
                row["record_date"] or "", row["owner_code"] or "", row["last_name"] or "",
                row["lot_number"] or "", row["owner_cards"] or 0, row["renter_cards"] or 0,
                row["boat_stickers"] or 0, row["source"],
            ))

    def _show_owner_payment(self, _event: object | None = None) -> None:
        selected = self.owner_tree.selection()
        if not selected:
            return
        row = self.repository.get_history_detail(int(selected[0]))
        if row is None:
            return
        messagebox.showinfo(
            "Owner payment detail",
            f"Owner: {row['owner_code']} {row['first_name'] or ''} {row['last_name'] or ''}\n"
            f"Date: {row['payment_date'] or ''}\nPaid: ${float(row['payment_amount'] or 0):,.2f}\n"
            f"Form: {payment_form_label(row['payment_form'])}\nCheck / ref: {row['check_number'] or ''}",
        )

    def _show_lot_payment(self, _event: object | None = None) -> None:
        selected = self.lot_tree.selection()
        if not selected:
            return
        row = next((item for item in self.current_rows if str(item["id"]) == selected[0]), None)
        if row is None:
            return
        messagebox.showinfo(
            "Lot payment detail",
            f"Lot: {row['lot_number']}\nOwner at payment: {row['owner_code'] or ''}\n"
            f"Date: {row['payment_date'] or ''}\nPaid: ${float(row['payment_amount'] or 0):,.2f}\n"
            f"Delinquent assessment: ${float(row['delinquent_assessment_1'] or 0):,.2f}\n"
            f"Delinquent interest: ${float(row['delinquent_interest_1'] or 0):,.2f}\n"
            f"Current assessment: ${float(row['current_assessment_1'] or 0):,.2f}\n"
            f"Current interest: ${float(row['current_interest_1'] or 0):,.2f}",
        )

    def open_pdf(self) -> None:
        index = self._active_index()
        titles = ["Owner Payment History", "Lot Payment History", "Ownership History", "ID and Boat History"]
        headings = [
            ["Date", "Owner", "Name", "Owed", "Paid", "Form", "Check"],
            ["Date", "Lot", "Owner", "Name", "Paid", "Form", "Through"],
            ["Date", "Lot", "Seller", "Buyer", "Source", "Status"],
            ["Date", "Owner", "Name", "Lot", "Owner Cards", "Renter Cards", "Boat", "Source"],
        ][index]
        tree = [self.owner_tree, self.lot_tree, self.ownership_tree, self.id_tree][index]
        rows = [list(tree.item(item, "values")) for item in tree.get_children()]
        try:
            output = render_history_pdf(self.db_path.parent / "generated_reports", titles[index], headings, rows)
            open_with_default_app(output)
        except Exception as exc:
            messagebox.showerror("History PDF failed", str(exc))
