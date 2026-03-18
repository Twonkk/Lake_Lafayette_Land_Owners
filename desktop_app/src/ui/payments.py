import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from src.db.repositories import OwnerRepository
from src.services.payment_service import (
    LotAllocation,
    PAYMENT_FORM_CODES,
    PaymentRequest,
    default_payment_date,
    post_lot_payment,
)


class PaymentsFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, db_path: Path) -> None:
        super().__init__(parent, style="App.TFrame")
        self.db_path = db_path
        self.repository = OwnerRepository(db_path)
        self.search_var = tk.StringVar()
        self.only_due_var = tk.BooleanVar(value=True)
        self.amount_var = tk.StringVar()
        self.date_var = tk.StringVar(value=default_payment_date())
        self.form_var = tk.StringVar(value="Check")
        self.check_var = tk.StringVar()
        self.note_var = tk.StringVar()
        self.manual_allocation_var = tk.StringVar()
        self.selected_owner_code: str | None = None
        self.selected_lot_number: str | None = None
        self.allocation_editor: ttk.Entry | None = None
        self.editing_lot_number: str | None = None
        self.allocations: dict[str, float] = {}
        self.lot_balances: dict[str, float] = {}
        self.selected_lots: set[str] = set()
        self.amount_var.trace_add("write", self._on_amount_change)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self._build()
        self.run_search()

    def _build(self) -> None:
        intro = ttk.Label(
            self,
            text="Search for an owner, select one or more lots, allocate the payment, then post it. "
            "A database backup is created before each payment is saved.",
        )
        intro.grid(row=0, column=0, sticky="w", pady=(0, 10))

        search_row = ttk.Frame(self, style="App.TFrame")
        search_row.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="Search owner").grid(row=0, column=0, sticky="w", padx=(0, 8))
        entry = ttk.Entry(search_row, textvariable=self.search_var)
        entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        entry.bind("<Return>", self.run_search)
        ttk.Button(search_row, text="Search", command=self.run_search).grid(row=0, column=2)
        ttk.Checkbutton(
            search_row,
            text="Only owners with balance due",
            variable=self.only_due_var,
            command=self.run_search,
        ).grid(row=0, column=3, sticky="w", padx=(12, 0))

        split = ttk.Panedwindow(self, orient="horizontal")
        split.grid(row=2, column=0, sticky="nsew")

        left = ttk.Frame(split, style="App.TFrame", padding=(0, 0, 12, 0))
        right = ttk.Frame(split, style="App.TFrame")
        split.add(left, weight=2)
        split.add(right, weight=3)

        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)

        ttk.Label(left, text="Owners", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.owner_tree = ttk.Treeview(
            left,
            columns=("owner_code", "name", "owed"),
            show="headings",
        )
        for name, width in [("owner_code", 85), ("name", 250), ("owed", 90)]:
            self.owner_tree.heading(name, text=name.replace("_", " ").title())
            self.owner_tree.column(name, width=width, anchor="w")
        self.owner_tree.grid(row=1, column=0, sticky="nsew")
        owner_scroll = ttk.Scrollbar(left, orient="vertical", command=self.owner_tree.yview)
        owner_scroll.grid(row=1, column=1, sticky="ns")
        self.owner_tree.configure(yscrollcommand=owner_scroll.set)
        self.owner_tree.bind("<<TreeviewSelect>>", self._on_owner_select)

        ttk.Label(right, text="Payment entry", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        self.owner_summary = tk.Text(
            right,
            height=7,
            relief="flat",
            wrap="word",
            background="#ffffff",
            foreground="#1d2430",
            font=("TkDefaultFont", 11),
            padx=14,
            pady=14,
        )
        self.owner_summary.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.owner_summary.configure(state="disabled")

        lot_box = ttk.LabelFrame(right, text="Lots for selected owner")
        lot_box.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        lot_box.columnconfigure(0, weight=1)
        lot_box.rowconfigure(0, weight=1)
        self.lot_tree = ttk.Treeview(
            lot_box,
            columns=("selected", "lot_number", "due", "allocated", "current", "delinquent", "interest"),
            show="headings",
            height=7,
            selectmode="browse",
        )
        for name, width in [
            ("selected", 40),
            ("lot_number", 85),
            ("due", 90),
            ("allocated", 90),
            ("current", 90),
            ("delinquent", 100),
            ("interest", 90),
        ]:
            heading = "Multi-Lot" if name == "selected" else name.replace("_", " ").title()
            self.lot_tree.heading(name, text=heading)
            self.lot_tree.column(name, width=width, anchor="center")
        self.lot_tree.grid(row=0, column=0, sticky="nsew")
        self.lot_tree.bind("<<TreeviewSelect>>", self._on_lot_select)
        self.lot_tree.bind("<Button-1>", self._handle_lot_click)
        self.lot_tree.bind("<Configure>", self._cancel_allocation_edit)
        lot_scroll = ttk.Scrollbar(lot_box, orient="vertical", command=self.lot_tree.yview)
        lot_scroll.grid(row=0, column=1, sticky="ns")
        self.lot_tree.configure(yscrollcommand=lot_scroll.set)

        lot_actions = ttk.Frame(right, style="App.TFrame")
        lot_actions.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        lot_actions.columnconfigure(5, weight=1)
        ttk.Label(lot_actions, text="Allocation for selected lot").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Entry(lot_actions, textvariable=self.manual_allocation_var, width=12).grid(
            row=0, column=1, sticky="w", padx=(0, 8)
        )
        ttk.Button(lot_actions, text="Set Allocation", command=self.set_manual_allocation).grid(
            row=0, column=2, sticky="w", padx=(0, 8)
        )
        ttk.Button(lot_actions, text="Auto Fill Selected", command=self.auto_allocate_selected).grid(
            row=0, column=3, sticky="w", padx=(0, 8)
        )
        ttk.Button(lot_actions, text="Check / Uncheck Lot", command=self.toggle_current_lot).grid(
            row=0, column=4, sticky="w"
        )
        ttk.Button(lot_actions, text="Select All Lots", command=self.select_all_lots).grid(
            row=1, column=0, sticky="w", pady=(8, 0), padx=(0, 8)
        )
        ttk.Button(lot_actions, text="Select Lots With Balance", command=self.select_due_lots).grid(
            row=1, column=1, sticky="w", pady=(8, 0), padx=(0, 8)
        )
        ttk.Button(lot_actions, text="Clear Selected", command=self.clear_selected_lots).grid(
            row=1, column=2, sticky="w", pady=(8, 0), padx=(0, 8)
        )
        ttk.Button(lot_actions, text="Clear Allocations", command=self.clear_allocations).grid(
            row=1, column=3, sticky="w", pady=(8, 0)
        )

        form = ttk.LabelFrame(right, text="Post payment")
        form.grid(row=4, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        fields = [
            ("Selected owner", "selected_owner_value"),
            ("Selected lots", "selected_lot_value"),
            ("Payment amount", "amount"),
            ("Allocated total", "allocated_total_value"),
            ("Payment date", "date"),
            ("Payment form", "form"),
            ("Check / ref", "check"),
            ("Note", "note"),
        ]
        self.selected_owner_value = tk.StringVar(value="")
        self.selected_lot_value = tk.StringVar(value="")
        self.allocated_total_value = tk.StringVar(value="$0.00")

        for idx, (label, key) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=idx, column=0, sticky="w", padx=(12, 8), pady=6)
            if key == "amount":
                widget = ttk.Entry(form, textvariable=self.amount_var)
            elif key == "date":
                widget = ttk.Entry(form, textvariable=self.date_var)
            elif key == "form":
                widget = ttk.Combobox(
                    form,
                    textvariable=self.form_var,
                    values=list(PAYMENT_FORM_CODES.keys()),
                    state="readonly",
                )
            elif key == "check":
                widget = ttk.Entry(form, textvariable=self.check_var)
            elif key == "note":
                widget = ttk.Entry(form, textvariable=self.note_var)
            else:
                widget = tk.Label(
                    form,
                    textvariable=getattr(self, key),
                    background="#ffffff",
                    foreground="#1d2430",
                    anchor="w",
                )
            widget.grid(row=idx, column=1, sticky="ew", padx=(0, 12), pady=6)

        ttk.Button(form, text="Post Payment", command=self.post_payment).grid(
            row=len(fields), column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 12)
        )

    def run_search(self, _event: object | None = None) -> None:
        results = self.repository.search(self.search_var.get())
        if self.only_due_var.get():
            results = [owner for owner in results if float(owner["total_owed"] or 0) > 0]
        self.owner_tree.delete(*self.owner_tree.get_children())
        for owner in results:
            name = " ".join(part for part in [owner["last_name"], owner["first_name"]] if part).strip()
            self.owner_tree.insert(
                "",
                "end",
                iid=owner["owner_code"],
                values=(owner["owner_code"], name, f"${owner['total_owed'] or 0:,.2f}"),
            )
        children = self.owner_tree.get_children()
        if children:
            self.owner_tree.selection_set(children[0])
            self._load_owner(children[0])

    def _on_owner_select(self, _event: object | None = None) -> None:
        selected = self.owner_tree.selection()
        if selected:
            self._load_owner(selected[0])

    def _load_owner(self, owner_code: str) -> None:
        detail = self.repository.get_owner_detail(owner_code)
        if detail is None:
            return
        owner = detail["owner"]
        self.selected_owner_code = owner_code
        self.selected_lot_number = None
        self.allocations = {}
        self.lot_balances = {}
        self.selected_lots = set()
        self.selected_owner_value.set(owner_code)
        self.selected_lot_value.set("")
        self.allocated_total_value.set("$0.00")
        self.amount_var.set("")
        self.check_var.set("")
        self.note_var.set("")
        self.manual_allocation_var.set("")

        summary = "\n".join(
            [
                f"Owner: {owner['last_name'] or ''} {owner['first_name'] or ''}".strip(),
                f"Address: {owner['address'] or ''}",
                f"City/State/ZIP: {owner['city'] or ''}, {owner['state'] or ''} {owner['zip'] or ''}".strip(),
                f"Phone: {owner['phone'] or ''}",
                f"Total owed: ${float(owner['total_owed'] or 0):,.2f}",
            ]
        )
        self.owner_summary.configure(state="normal")
        self.owner_summary.delete("1.0", "end")
        self.owner_summary.insert("1.0", summary)
        self.owner_summary.configure(state="disabled")

        self.lot_tree.delete(*self.lot_tree.get_children())
        self._cancel_allocation_edit()
        for lot in detail["lots"]:
            due = float(lot["total_due"] or 0)
            self.lot_balances[lot["lot_number"]] = due
            self.lot_tree.insert(
                "",
                "end",
                iid=lot["lot_number"],
                values=(
                    "[ ]",
                    lot["lot_number"],
                    f"${due:,.2f}",
                    "$0.00",
                    f"${float(lot['current_assessment'] or 0):,.2f}",
                    f"${float(lot['delinquent_assessment'] or 0):,.2f}",
                    f"${float(lot['delinquent_interest'] or 0) + float(lot['current_interest'] or 0):,.2f}",
                ),
            )
        children = self.lot_tree.get_children()
        if children:
            self.lot_tree.selection_set(children[0])
            self._update_selected_lots()

    def _on_lot_select(self, _event: object | None = None) -> None:
        self._update_selected_lots()

    def _handle_lot_click(self, event: tk.Event) -> str | None:
        row_id = self.lot_tree.identify_row(event.y)
        column_id = self.lot_tree.identify_column(event.x)
        if self.allocation_editor is not None and not (
            row_id == self.editing_lot_number and column_id == "#4"
        ):
            self._commit_allocation_edit()
        if row_id and column_id == "#1":
            self.lot_tree.selection_set(row_id)
            self.toggle_lot(row_id)
            return "break"
        if row_id and column_id == "#4":
            self.lot_tree.selection_set(row_id)
            self._begin_allocation_edit(row_id)
            return "break"
        self._cancel_allocation_edit()
        return None

    def _begin_allocation_edit(self, lot_number: str) -> None:
        bbox = self.lot_tree.bbox(lot_number, "#4")
        if not bbox:
            return
        self._cancel_allocation_edit()
        self.editing_lot_number = lot_number
        current_value = self.allocations.get(lot_number, 0.0)
        editor = ttk.Entry(self.lot_tree)
        editor.insert(0, f"{current_value:.2f}" if current_value else "")
        editor.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        editor.focus_set()
        editor.select_range(0, "end")
        editor.bind("<Return>", self._commit_allocation_edit)
        editor.bind("<FocusOut>", self._commit_allocation_edit)
        editor.bind("<Escape>", self._cancel_allocation_edit)
        self.allocation_editor = editor

    def _cancel_allocation_edit(self, _event: object | None = None) -> None:
        if self.allocation_editor is not None:
            self.allocation_editor.destroy()
        self.allocation_editor = None
        self.editing_lot_number = None

    def _commit_allocation_edit(self, _event: object | None = None) -> None:
        if self.allocation_editor is None or self.editing_lot_number is None:
            return
        lot_number = self.editing_lot_number
        raw_value = self.allocation_editor.get().strip()
        self._cancel_allocation_edit()
        if not raw_value:
            self._set_lot_allocation(lot_number, 0.0)
            return
        try:
            amount = float(raw_value)
        except ValueError:
            messagebox.showerror("Invalid amount", "Enter a valid allocation amount.")
            return
        self._set_lot_allocation(lot_number, amount)

    def _update_selected_lots(self) -> None:
        current = list(self.lot_tree.selection())
        self.selected_lot_number = current[0] if current else None
        if not current:
            self.selected_lot_value.set("")
            self.manual_allocation_var.set("")
            return
        if len(self.selected_lots) == 1:
            lot_number = next(iter(self.selected_lots))
            self.selected_lot_value.set(lot_number)
            self.manual_allocation_var.set(
                f"{self.allocations.get(lot_number, 0.0):.2f}" if lot_number in self.allocations else ""
            )
            return
        if self.selected_lots:
            self.selected_lot_value.set(f"{len(self.selected_lots)} lots selected")
        else:
            self.selected_lot_value.set(current[0])
        self.manual_allocation_var.set("")

    def _refresh_lot_allocations(self) -> None:
        total = 0.0
        for lot_number in self.lot_tree.get_children():
            values = list(self.lot_tree.item(lot_number, "values"))
            amount = round(self.allocations.get(lot_number, 0.0), 2)
            total += amount
            values[0] = "[x]" if lot_number in self.selected_lots else "[ ]"
            values[3] = f"${amount:,.2f}"
            self.lot_tree.item(lot_number, values=values)
        self.allocated_total_value.set(f"${total:,.2f}")
        self._update_selected_lots()

    def _on_amount_change(self, *_args: object) -> None:
        if self.allocation_editor is not None:
            return
        if not self.selected_lots:
            return
        raw_amount = self.amount_var.get().strip()
        if not raw_amount:
            self.allocations = {
                lot: amount for lot, amount in self.allocations.items() if lot not in self.selected_lots
            }
            self._refresh_lot_allocations()
            return
        try:
            payment_amount = float(raw_amount)
        except ValueError:
            return
        if payment_amount < 0:
            return
        self._auto_allocate_selected_without_prompt(payment_amount)

    def clear_allocations(self) -> None:
        self.allocations = {}
        self.manual_allocation_var.set("")
        self._refresh_lot_allocations()

    def toggle_current_lot(self) -> None:
        selected = list(self.lot_tree.selection())
        if len(selected) != 1:
            messagebox.showerror("Select one lot", "Click one lot row, then use Select / Unselect Lot.")
            return
        self.toggle_lot(selected[0])

    def toggle_lot(self, lot_number: str) -> None:
        if lot_number in self.selected_lots:
            self.selected_lots.remove(lot_number)
            self.allocations.pop(lot_number, None)
        else:
            self.selected_lots.add(lot_number)
        self._refresh_lot_allocations()

    def select_all_lots(self) -> None:
        self.selected_lots = set(self.lot_tree.get_children())
        self._refresh_lot_allocations()

    def select_due_lots(self) -> None:
        self.selected_lots = {
            lot_number
            for lot_number, due in self.lot_balances.items()
            if due > 0
        }
        self._refresh_lot_allocations()

    def clear_selected_lots(self) -> None:
        self.selected_lots = set()
        self.allocations = {}
        self._cancel_allocation_edit()
        self._refresh_lot_allocations()

    def _set_lot_allocation(self, lot_number: str, amount: float) -> None:
        due = self.lot_balances.get(lot_number, 0.0)
        if amount < 0:
            messagebox.showerror("Invalid amount", "Allocation cannot be negative.")
            return
        if amount > due:
            messagebox.showerror(
                "Invalid amount",
                f"Allocation cannot exceed the lot balance of ${due:,.2f}.",
            )
            return
        if amount == 0:
            self.allocations.pop(lot_number, None)
            if lot_number in self.selected_lots:
                self.selected_lots.remove(lot_number)
        else:
            self.selected_lots.add(lot_number)
            self.allocations[lot_number] = round(amount, 2)
        if self.selected_lot_number == lot_number:
            self.manual_allocation_var.set(f"{amount:.2f}" if amount else "")
        self._refresh_lot_allocations()

    def set_manual_allocation(self) -> None:
        if self.selected_lot_number is None:
            messagebox.showerror("Select one lot", "Select one lot to set a manual allocation.")
            return
        try:
            amount = float(self.manual_allocation_var.get())
        except ValueError:
            messagebox.showerror("Invalid amount", "Enter a valid allocation amount.")
            return
        self._set_lot_allocation(self.selected_lot_number, amount)

    def auto_allocate_selected(self) -> None:
        selected = sorted(self.selected_lots)
        if not selected:
            messagebox.showerror("No lots selected", "Select one or more lots to auto-fill.")
            return
        try:
            payment_amount = float(self.amount_var.get())
        except ValueError:
            messagebox.showerror("Invalid amount", "Enter a valid payment amount first.")
            return
        if payment_amount <= 0:
            messagebox.showerror("Invalid amount", "Payment amount must be greater than zero.")
            return

        remaining = round(payment_amount, 2)
        self.allocations = {
            lot: amount for lot, amount in self.allocations.items() if lot not in selected
        }
        for lot_number in selected:
            if remaining <= 0:
                break
            due = self.lot_balances.get(lot_number, 0.0)
            allocation = round(min(due, remaining), 2)
            if allocation > 0:
                self.allocations[lot_number] = allocation
                remaining = round(remaining - allocation, 2)
        self._refresh_lot_allocations()

    def _auto_allocate_selected_without_prompt(self, payment_amount: float) -> float:
        selected = sorted(self.selected_lots)
        if not selected or payment_amount <= 0:
            return 0.0
        remaining = round(payment_amount, 2)
        self.allocations = {
            lot: amount for lot, amount in self.allocations.items() if lot not in selected
        }
        for lot_number in selected:
            if remaining <= 0:
                break
            due = self.lot_balances.get(lot_number, 0.0)
            allocation = round(min(due, remaining), 2)
            if allocation > 0:
                self.allocations[lot_number] = allocation
                remaining = round(remaining - allocation, 2)
        self._refresh_lot_allocations()
        return round(sum(self.allocations.get(lot, 0.0) for lot in selected), 2)

    def post_payment(self) -> None:
        if not self.selected_owner_code:
            messagebox.showerror("Missing owner", "Select an owner before posting a payment.")
            return

        try:
            amount = float(self.amount_var.get())
        except ValueError:
            messagebox.showerror("Invalid amount", "Enter a valid payment amount.")
            return

        allocations = [
            LotAllocation(lot_number=lot_number, payment_amount=allocated)
            for lot_number, allocated in self.allocations.items()
            if allocated > 0 and lot_number in self.selected_lots
        ]
        allocated_total = round(sum(item.payment_amount for item in allocations), 2)
        if not allocations and self.selected_lots:
            auto_total = self._auto_allocate_selected_without_prompt(amount)
            allocations = [
                LotAllocation(lot_number=lot_number, payment_amount=allocated)
                for lot_number, allocated in self.allocations.items()
                if allocated > 0 and lot_number in self.selected_lots
            ]
            allocated_total = round(sum(item.payment_amount for item in allocations), 2)
            if auto_total != round(amount, 2):
                messagebox.showerror(
                    "Allocation mismatch",
                    "The selected lots do not match the payment amount. Adjust the checked lots or use manual allocation.",
                )
                return
        if not allocations and self.selected_lot_number:
            due = self.lot_balances.get(self.selected_lot_number, 0.0)
            if amount <= due:
                allocations = [LotAllocation(self.selected_lot_number, round(amount, 2))]
                self.selected_lots.add(self.selected_lot_number)
                self.allocations[self.selected_lot_number] = round(amount, 2)
                self._refresh_lot_allocations()
                allocated_total = round(amount, 2)
        if not allocations:
            messagebox.showerror("Missing allocation", "Allocate the payment to at least one lot.")
            return
        if allocated_total != round(amount, 2):
            messagebox.showerror(
                "Allocation mismatch",
                "Payment amount must match the total allocated across selected lots.",
            )
            return

        request = PaymentRequest(
            owner_code=self.selected_owner_code,
            payment_amount=amount,
            payment_date=self.date_var.get().strip(),
            payment_form=self.form_var.get().strip(),
            allocations=allocations,
            check_number=self.check_var.get().strip(),
            note_text=self.note_var.get().strip(),
        )

        confirm = messagebox.askyesno(
            "Confirm payment",
            "\n".join(
                [
                    f"Owner: {request.owner_code}",
                    f"Amount: ${request.payment_amount:,.2f}",
                    f"Allocated to: {len(request.allocations)} lot(s)",
                    f"Date: {request.payment_date}",
                    f"Form: {request.payment_form}",
                    "",
                    "A backup will be created before this payment is saved.",
                ]
            ),
        )
        if not confirm:
            return

        try:
            result = post_lot_payment(self.db_path, request)
        except Exception as exc:
            messagebox.showerror("Payment failed", str(exc))
            return

        messagebox.showinfo(
            "Payment posted",
            "\n".join(
                [
                    f"Owner total: ${result.previous_owner_total:,.2f} -> ${result.new_owner_total:,.2f}",
                    *[
                        f"{item.lot_number}: ${item.previous_total_due:,.2f} -> ${item.new_total_due:,.2f}"
                        for item in result.lot_results
                    ],
                    f"Backup: {result.backup_path}",
                ]
            ),
        )
        owner_code = self.selected_owner_code
        self.run_search()
        if owner_code:
            children = self.owner_tree.get_children()
            if owner_code in children:
                self.owner_tree.selection_set(owner_code)
                self._load_owner(owner_code)
