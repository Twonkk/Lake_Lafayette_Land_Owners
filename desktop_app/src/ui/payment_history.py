import tkinter as tk
from pathlib import Path
from tkinter import ttk

from src.db.repositories import PaymentRepository


class PaymentHistoryFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, db_path: Path) -> None:
        super().__init__(parent, style="App.TFrame")
        self.repository = PaymentRepository(db_path)
        self.search_var = tk.StringVar()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self._build()
        self.run_search()

    def _build(self) -> None:
        intro = ttk.Label(
            self,
            text="Search posted payments by owner, lot, date, or check/reference number.",
        )
        intro.grid(row=0, column=0, sticky="w", pady=(0, 10))

        search_row = ttk.Frame(self, style="App.TFrame")
        search_row.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="Search history").grid(row=0, column=0, sticky="w", padx=(0, 8))
        entry = ttk.Entry(search_row, textvariable=self.search_var)
        entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        entry.bind("<Return>", self.run_search)
        ttk.Button(search_row, text="Search", command=self.run_search).grid(row=0, column=2)

        split = ttk.Panedwindow(self, orient="horizontal")
        split.grid(row=2, column=0, sticky="nsew")

        left = ttk.Frame(split, style="App.TFrame", padding=(0, 0, 12, 0))
        right = ttk.Frame(split, style="App.TFrame")
        split.add(left, weight=3)
        split.add(right, weight=2)

        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        ttk.Label(left, text="Posted payments", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        self.history_tree = ttk.Treeview(
            left,
            columns=("payment_date", "owner_code", "name", "lot_number", "amount", "form"),
            show="headings",
        )
        for name, width in [
            ("payment_date", 95),
            ("owner_code", 85),
            ("name", 220),
            ("lot_number", 85),
            ("amount", 85),
            ("form", 70),
        ]:
            self.history_tree.heading(name, text=name.replace("_", " ").title())
            self.history_tree.column(name, width=width, anchor="w")
        self.history_tree.grid(row=1, column=0, sticky="nsew")
        self.history_tree.bind("<<TreeviewSelect>>", self._on_select)
        history_scroll = ttk.Scrollbar(left, orient="vertical", command=self.history_tree.yview)
        history_scroll.grid(row=1, column=1, sticky="ns")
        self.history_tree.configure(yscrollcommand=history_scroll.set)

        ttk.Label(right, text="Payment detail", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        self.detail_text = tk.Text(
            right,
            wrap="word",
            relief="flat",
            background="#ffffff",
            foreground="#1d2430",
            font=("TkDefaultFont", 11),
            padx=16,
            pady=16,
        )
        self.detail_text.grid(row=1, column=0, sticky="nsew")
        self.detail_text.configure(state="disabled")

    def run_search(self, _event: object | None = None) -> None:
        results = self.repository.search_history(self.search_var.get())
        self.history_tree.delete(*self.history_tree.get_children())
        for row in results:
            name = " ".join(part for part in [row["last_name"], row["first_name"]] if part).strip()
            self.history_tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["payment_date"] or "",
                    row["owner_code"],
                    name,
                    row["lot_number"],
                    f"${float(row['payment_amount'] or 0):,.2f}",
                    row["payment_form"] or "",
                ),
            )
        children = self.history_tree.get_children()
        if children:
            self.history_tree.selection_set(children[0])
            self._show_detail(int(children[0]))
        else:
            self._set_detail("No matching payment history found.")

    def _on_select(self, _event: object | None = None) -> None:
        selected = self.history_tree.selection()
        if selected:
            self._show_detail(int(selected[0]))

    def _show_detail(self, audit_id: int) -> None:
        row = self.repository.get_history_detail(audit_id)
        if row is None:
            self._set_detail("Payment detail not found.")
            return

        name = " ".join(part for part in [row["last_name"], row["first_name"]] if part).strip()
        lines = [
            f"Posted at: {row['created_at'] or ''}",
            f"Payment date: {row['payment_date'] or ''}",
            f"Owner: {row['owner_code']} {name}".strip(),
            f"Address: {row['address'] or ''}",
            f"City/State/ZIP: {row['city'] or ''}, {row['state'] or ''} {row['zip'] or ''}".strip(),
            f"Lot: {row['lot_number'] or ''}",
            f"Amount: ${float(row['payment_amount'] or 0):,.2f}",
            f"Form: {row['payment_form'] or ''}",
            f"Check / ref: {row['check_number'] or ''}",
            "",
            f"Lot balance: ${float(row['previous_total_due'] or 0):,.2f} -> ${float(row['new_total_due'] or 0):,.2f}",
            f"Owner total: ${float(row['previous_owner_total'] or 0):,.2f} -> ${float(row['new_owner_total'] or 0):,.2f}",
            "",
            f"Note: {row['note_text'] or ''}",
            "",
            f"Backup: {row['backup_path'] or ''}",
        ]
        self._set_detail("\n".join(lines))

    def _set_detail(self, text: str) -> None:
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", text)
        self.detail_text.configure(state="disabled")
