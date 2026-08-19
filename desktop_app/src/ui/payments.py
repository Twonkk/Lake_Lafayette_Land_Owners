import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from src.db.repositories import OwnerRepository
from src.services.payment_service import (
    LotAllocation,
    PAYMENT_CATEGORY_FIELDS,
    PAYMENT_CATEGORY_LABELS,
    PAYMENT_FORM_CODES,
    PaymentRequest,
    default_paid_through,
    default_payment_date,
    post_lot_payment,
    validate_lot_allocation,
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
        self.full_paid_through_var = tk.StringVar(value=default_paid_through(db_path))
        self.selected_owner_code: str | None = None
        self.selected_lot_number: str | None = None
        self.allocations: dict[str, LotAllocation] = {}
        self.lot_balances: dict[str, float] = {}
        self.lot_category_balances: dict[str, dict[str, float]] = {}
        self.lot_paid_through: dict[str, str] = {}
        self.selected_lots: set[str] = set()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            self,
            background="#f3efe7",
            highlightthickness=0,
            borderwidth=0,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.content = ttk.Frame(self.canvas, style="App.TFrame")
        self.content.columnconfigure(0, weight=1)
        self.content_window = self.canvas.create_window(
            (0, 0),
            window=self.content,
            anchor="nw",
        )
        self.content.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._resize_content)
        self.canvas.bind("<MouseWheel>", self._scroll_with_wheel)
        self.canvas.bind("<Prior>", lambda _event: self.canvas.yview_scroll(-1, "pages"))
        self.canvas.bind("<Next>", lambda _event: self.canvas.yview_scroll(1, "pages"))

        self._build(self.content)
        self._bind_scroll_controls(self.content)
        self.run_search()

    def _build(self, parent: ttk.Frame) -> None:
        self.intro = ttk.Label(
            parent,
            text=(
                "Search for an owner, then distribute the payment among the same four balance "
                "categories used in dBase. A database backup is created before it is saved. "
                "On smaller screens, use the far-right scrollbar to reach Post Payment."
            ),
            wraplength=920,
            justify="left",
        )
        self.intro.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        search_row = ttk.Frame(parent, style="App.TFrame")
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
        ).grid(row=1, column=1, columnspan=2, sticky="w", pady=(8, 0))

        split = ttk.Panedwindow(parent, orient="horizontal")
        split.grid(row=2, column=0, sticky="nsew")

        left = ttk.Frame(split, style="App.TFrame", padding=(0, 0, 12, 0))
        right = ttk.Frame(split, style="App.TFrame")
        split.add(left, weight=2)
        split.add(right, weight=3)

        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

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
        owner_xscroll = ttk.Scrollbar(left, orient="horizontal", command=self.owner_tree.xview)
        owner_xscroll.grid(row=2, column=0, sticky="ew")
        self.owner_tree.configure(
            yscrollcommand=owner_scroll.set,
            xscrollcommand=owner_xscroll.set,
        )
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
        self.lot_tree.bind("<Double-1>", self._open_distribution_from_double_click)
        lot_scroll = ttk.Scrollbar(lot_box, orient="vertical", command=self.lot_tree.yview)
        lot_scroll.grid(row=0, column=1, sticky="ns")
        lot_xscroll = ttk.Scrollbar(lot_box, orient="horizontal", command=self.lot_tree.xview)
        lot_xscroll.grid(row=1, column=0, sticky="ew")
        self.lot_tree.configure(
            yscrollcommand=lot_scroll.set,
            xscrollcommand=lot_xscroll.set,
        )

        lot_actions = ttk.Frame(right, style="App.TFrame")
        lot_actions.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        ttk.Button(
            lot_actions,
            text="Distribute Selected Lot Payment",
            command=self.open_category_distribution,
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Button(
            lot_actions,
            text="Fill Selected Lot Balance",
            command=self.fill_selected_lot_balance,
        ).grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Button(
            lot_actions,
            text="Fill Full Owner Balance",
            command=self.fill_full_owner_balance,
        ).grid(row=1, column=0, sticky="w", pady=(8, 0), padx=(0, 8))
        ttk.Button(lot_actions, text="Check / Uncheck Lot", command=self.toggle_current_lot).grid(
            row=1, column=1, sticky="w", pady=(8, 0)
        )
        ttk.Button(lot_actions, text="Clear Selected Lots", command=self.clear_selected_lots).grid(
            row=2, column=0, sticky="w", pady=(8, 0), padx=(0, 8)
        )
        ttk.Button(lot_actions, text="Clear Distributions", command=self.clear_allocations).grid(
            row=2, column=1, sticky="w", pady=(8, 0)
        )

        form = ttk.LabelFrame(right, text="Post payment")
        form.grid(row=4, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        fields = [
            ("Selected owner", "selected_owner_value"),
            ("Selected lots", "selected_lot_value"),
            ("Payment amount", "amount"),
            ("Allocated total", "allocated_total_value"),
            ("Paid through (full payment)", "full_paid_through"),
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
            elif key == "full_paid_through":
                widget = ttk.Entry(form, textvariable=self.full_paid_through_var)
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

    def _update_scroll_region(self, _event: tk.Event | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_content(self, event: tk.Event) -> None:
        self.intro.configure(wraplength=max(event.width - 24, 320))
        self.canvas.itemconfigure(
            self.content_window,
            width=event.width,
            height=max(event.height, self.content.winfo_reqheight()),
        )

    def _bind_scroll_controls(self, widget: tk.Misc) -> None:
        if isinstance(widget, (ttk.Treeview, tk.Text)):
            return
        widget.bind("<MouseWheel>", self._scroll_with_wheel, add="+")
        widget.bind(
            "<Button-4>",
            lambda _event: self.canvas.yview_scroll(-1, "units"),
            add="+",
        )
        widget.bind(
            "<Button-5>",
            lambda _event: self.canvas.yview_scroll(1, "units"),
            add="+",
        )
        for child in widget.winfo_children():
            self._bind_scroll_controls(child)

    def _scroll_with_wheel(self, event: tk.Event) -> str:
        direction = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(direction * 3, "units")
        return "break"

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
        self.lot_category_balances = {}
        self.lot_paid_through = {}
        self.selected_lots = set()
        self.selected_owner_value.set(owner_code)
        self.selected_lot_value.set("")
        self.allocated_total_value.set("$0.00")
        self.amount_var.set("")
        self.check_var.set("")
        self.note_var.set("")

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
        for lot in detail["lots"]:
            due = float(lot["total_due"] or 0)
            lot_number = lot["lot_number"]
            self.lot_balances[lot_number] = due
            self.lot_category_balances[lot_number] = {
                field: float(lot[field] or 0)
                for field in PAYMENT_CATEGORY_FIELDS
            }
            self.lot_paid_through[lot_number] = str(lot["paid_through"] or "")
            self.lot_tree.insert(
                "",
                "end",
                iid=lot_number,
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
        if row_id and column_id == "#1":
            self.lot_tree.selection_set(row_id)
            self.toggle_lot(row_id)
            return "break"
        return None

    def _open_distribution_from_double_click(self, event: tk.Event) -> None:
        row_id = self.lot_tree.identify_row(event.y)
        if not row_id:
            return
        self.lot_tree.selection_set(row_id)
        self._update_selected_lots()
        self.open_category_distribution()

    def _update_selected_lots(self) -> None:
        current = list(self.lot_tree.selection())
        self.selected_lot_number = current[0] if current else None
        if not current:
            self.selected_lot_value.set("")
            return
        if len(self.selected_lots) == 1:
            lot_number = next(iter(self.selected_lots))
            self.selected_lot_value.set(lot_number)
            return
        if self.selected_lots:
            self.selected_lot_value.set(f"{len(self.selected_lots)} lots selected")
        else:
            self.selected_lot_value.set(current[0])

    def _refresh_lot_allocations(self) -> None:
        total = 0.0
        for lot_number in self.lot_tree.get_children():
            values = list(self.lot_tree.item(lot_number, "values"))
            allocation = self.allocations.get(lot_number)
            amount = allocation.payment_amount if allocation is not None else 0.0
            total += amount
            values[0] = "[x]" if lot_number in self.selected_lots else "[ ]"
            values[3] = f"${amount:,.2f}"
            self.lot_tree.item(lot_number, values=values)
        self.allocated_total_value.set(f"${total:,.2f}")
        self._update_selected_lots()

    def _lot_record_for_validation(self, lot_number: str) -> dict[str, float]:
        return {
            **self.lot_category_balances[lot_number],
            "total_due": self.lot_balances[lot_number],
        }

    def open_category_distribution(self) -> None:
        lot_number = self.selected_lot_number
        if not lot_number:
            messagebox.showerror("Select one lot", "Select a lot before distributing the payment.")
            return

        existing = self.allocations.get(lot_number)
        amount_vars = {
            field: tk.StringVar(
                value=(
                    f"{getattr(existing, field):.2f}"
                    if existing is not None and getattr(existing, field)
                    else ""
                )
            )
            for field in PAYMENT_CATEGORY_FIELDS
        }
        paid_through_var = tk.StringVar(
            value=(
                existing.paid_through
                if existing is not None
                else self.lot_paid_through.get(lot_number, "")
            )
        )

        dialog = tk.Toplevel(self)
        dialog.title(f"Distribute Payment — Lot {lot_number}")
        dialog.transient(self.winfo_toplevel())
        dialog.resizable(False, False)
        dialog.grab_set()

        content = ttk.Frame(dialog, padding=18)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(2, weight=1)
        ttk.Label(
            content,
            text=(
                "Enter the payment in the same four categories used by dBase. "
                "Leave an unused category blank or enter 0."
            ),
            wraplength=560,
            justify="left",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))
        ttk.Label(content, text="Category", style="Section.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Label(content, text="Amount owed", style="Section.TLabel").grid(
            row=1, column=1, sticky="e", padx=(18, 18)
        )
        ttk.Label(content, text="Payment amount", style="Section.TLabel").grid(
            row=1, column=2, sticky="w"
        )

        for row_number, field in enumerate(PAYMENT_CATEGORY_FIELDS, start=2):
            ttk.Label(content, text=PAYMENT_CATEGORY_LABELS[field]).grid(
                row=row_number, column=0, sticky="w", pady=6
            )
            ttk.Label(
                content,
                text=f"${self.lot_category_balances[lot_number][field]:,.2f}",
            ).grid(row=row_number, column=1, sticky="e", padx=(18, 18), pady=6)
            ttk.Entry(content, textvariable=amount_vars[field], width=16).grid(
                row=row_number, column=2, sticky="ew", pady=6
            )

        paid_row = 2 + len(PAYMENT_CATEGORY_FIELDS)
        ttk.Label(content, text="Paid through").grid(row=paid_row, column=0, sticky="w", pady=(10, 6))
        ttk.Entry(content, textvariable=paid_through_var, width=16).grid(
            row=paid_row, column=2, sticky="ew", pady=(10, 6)
        )
        ttk.Label(
            content,
            text=(
                "dBase rule: delinquent assessment is the only category allowed to exceed "
                "its displayed category balance. The total cannot exceed the lot balance."
            ),
            wraplength=560,
            justify="left",
        ).grid(row=paid_row + 1, column=0, columnspan=3, sticky="w", pady=(8, 14))

        def save_distribution() -> None:
            values: dict[str, float] = {}
            for field, variable in amount_vars.items():
                raw_value = variable.get().strip()
                try:
                    values[field] = float(raw_value) if raw_value else 0.0
                except ValueError:
                    messagebox.showerror(
                        "Invalid amount",
                        f"Enter a valid amount for {PAYMENT_CATEGORY_LABELS[field].lower()}.",
                        parent=dialog,
                    )
                    return
            allocation = LotAllocation(
                lot_number=lot_number,
                paid_through=paid_through_var.get().strip(),
                **values,
            )
            try:
                validate_lot_allocation(
                    allocation,
                    self._lot_record_for_validation(lot_number),
                )
            except ValueError as exc:
                messagebox.showerror("Invalid distribution", str(exc), parent=dialog)
                return
            self.allocations[lot_number] = allocation
            self.selected_lots.add(lot_number)
            self._refresh_lot_allocations()
            if not self.amount_var.get().strip():
                self.amount_var.set(f"{self._allocated_total():.2f}")
            dialog.destroy()

        buttons = ttk.Frame(content)
        buttons.grid(row=paid_row + 2, column=0, columnspan=3, sticky="ew")
        ttk.Button(buttons, text="Save Distribution", command=save_distribution).grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).grid(row=0, column=1)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.wait_visibility()
        dialog.focus_set()

    def _allocated_total(self) -> float:
        return round(sum(item.payment_amount for item in self.allocations.values()), 2)

    def _full_balance_allocation(self, lot_number: str, paid_through: str) -> LotAllocation:
        balances = self.lot_category_balances[lot_number]
        return LotAllocation(
            lot_number=lot_number,
            paid_through=paid_through,
            **balances,
        )

    def fill_selected_lot_balance(self) -> None:
        lot_number = self.selected_lot_number
        if not lot_number:
            messagebox.showerror("Select one lot", "Select a lot before filling its balance.")
            return
        if self.lot_balances.get(lot_number, 0) <= 0:
            messagebox.showerror("No balance due", f"Lot {lot_number} does not have a balance due.")
            return
        paid_through = (
            self.full_paid_through_var.get().strip()
            or self.lot_paid_through.get(lot_number, "")
        )
        self.allocations[lot_number] = self._full_balance_allocation(lot_number, paid_through)
        self.selected_lots.add(lot_number)
        self.amount_var.set(f"{self._allocated_total():.2f}")
        self._refresh_lot_allocations()

    def fill_full_owner_balance(self) -> None:
        paid_through = self.full_paid_through_var.get().strip()
        if not paid_through:
            messagebox.showerror(
                "Paid through is required",
                "Enter the paid-through period in the Post payment section before filling the full owner balance.",
            )
            return
        self.allocations = {
            lot_number: self._full_balance_allocation(lot_number, paid_through)
            for lot_number, total_due in self.lot_balances.items()
            if total_due > 0
        }
        self.selected_lots = set(self.allocations)
        self.amount_var.set(f"{self._allocated_total():.2f}")
        self._refresh_lot_allocations()

    def clear_allocations(self) -> None:
        self.allocations = {}
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
        self._refresh_lot_allocations()

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
            allocation
            for lot_number, allocation in self.allocations.items()
            if allocation.payment_amount > 0 and lot_number in self.selected_lots
        ]
        allocated_total = round(sum(item.payment_amount for item in allocations), 2)
        if not allocations:
            messagebox.showerror(
                "Missing distribution",
                "Choose Distribute Selected Lot Payment and enter the payment in the dBase categories.",
            )
            return
        if allocated_total != round(amount, 2):
            messagebox.showerror(
                "Distribution mismatch",
                "Payment amount must match the category distributions across all selected lots.",
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
                    *[
                        f"- {allocation.lot_number}: ${allocation.payment_amount:,.2f}"
                        + (
                            f" (paid through {allocation.paid_through})"
                            if allocation.paid_through
                            else ""
                        )
                        for allocation in request.allocations
                    ],
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
