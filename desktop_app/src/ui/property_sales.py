import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from src.db.repositories import OwnerRepository
from src.runtime import open_with_default_app
from src.services.property_sale_service import (
    NewBuyerRequest,
    PropertySaleGroup,
    PropertySaleRequest,
    build_property_sale_receipt_lines,
    convert_property_sale_html_to_pdf,
    default_sale_date,
    record_property_sale,
    render_property_sale_receipt_html,
    reverse_property_sale,
)


class PropertySalesFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, db_path: Path) -> None:
        super().__init__(parent, style="App.TFrame")
        self.db_path = db_path
        self.repository = OwnerRepository(db_path)
        self.seller_search_var = tk.StringVar()
        self.buyer_search_var = tk.StringVar()
        self.sale_date_var = tk.StringVar(value=default_sale_date())
        self.new_buyer_var = tk.BooleanVar(value=False)
        self.new_last_name_var = tk.StringVar()
        self.new_first_name_var = tk.StringVar()
        self.new_address_var = tk.StringVar()
        self.new_city_var = tk.StringVar()
        self.new_state_var = tk.StringVar()
        self.new_zip_var = tk.StringVar()
        self.new_phone_var = tk.StringVar()
        self.selected_seller_code: str | None = None
        self.selected_buyer_code: str | None = None
        self.selected_lots: set[str] = set()
        self.selected_sale_group: PropertySaleGroup | None = None
        self.seller_results: list[dict] = []
        self.buyer_results: list[dict] = []

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build()
        self.search_sellers()
        self.search_buyers()

    def _build(self) -> None:
        ttk.Label(
            self,
            text="Record sale / purchase of property. Select the seller, check the lots being sold, then choose an existing buyer or enter a new one.",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        split = ttk.Panedwindow(self, orient="horizontal")
        split.grid(row=1, column=0, sticky="nsew")

        left = ttk.Frame(split, style="App.TFrame", padding=(0, 0, 12, 0))
        right = ttk.Frame(split, style="App.TFrame")
        split.add(left, weight=3)
        split.add(right, weight=2)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)
        left.rowconfigure(5, weight=1)
        right.columnconfigure(1, weight=1)

        seller_bar = ttk.Frame(left, style="App.TFrame")
        seller_bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        seller_bar.columnconfigure(1, weight=1)
        ttk.Label(seller_bar, text="Search seller").grid(row=0, column=0, sticky="w", padx=(0, 8))
        seller_entry = ttk.Entry(seller_bar, textvariable=self.seller_search_var)
        seller_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        seller_entry.bind("<Return>", self.search_sellers)
        ttk.Button(seller_bar, text="Search", command=self.search_sellers).grid(row=0, column=2, sticky="w")

        ttk.Label(left, text="Seller", style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.seller_tree = ttk.Treeview(
            left,
            columns=("owner_code", "name", "lots", "owed"),
            show="headings",
            height=8,
        )
        for name, width in [("owner_code", 85), ("name", 220), ("lots", 60), ("owed", 90)]:
            self.seller_tree.heading(name, text=name.replace("_", " ").title())
            self.seller_tree.column(name, width=width, anchor="center" if name in {"lots", "owed"} else "w")
        self.seller_tree.grid(row=2, column=0, sticky="nsew")
        self.seller_tree.bind("<<TreeviewSelect>>", self._on_select_seller)

        ttk.Label(left, text="Lots being sold", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=(12, 8))
        self.lot_tree = ttk.Treeview(
            left,
            columns=("selected", "lot_number", "due"),
            show="headings",
            height=8,
        )
        self.lot_tree.heading("selected", text="Sell")
        self.lot_tree.heading("lot_number", text="Lot Number")
        self.lot_tree.heading("due", text="Balance")
        self.lot_tree.column("selected", width=55, anchor="center")
        self.lot_tree.column("lot_number", width=120, anchor="center")
        self.lot_tree.column("due", width=100, anchor="center")
        self.lot_tree.grid(row=4, column=0, sticky="nsew")
        self.lot_tree.bind("<Button-1>", self._handle_lot_click)

        recent_box = ttk.LabelFrame(left, text="Recent recorded sales")
        recent_box.grid(row=5, column=0, sticky="nsew", pady=(12, 0))
        recent_box.columnconfigure(0, weight=1)
        recent_box.rowconfigure(1, weight=1)
        recent_actions = ttk.Frame(recent_box, style="App.TFrame")
        recent_actions.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        ttk.Button(
            recent_actions,
            text="Reverse Selected Sale",
            command=self.reverse_selected_sale,
        ).grid(row=0, column=0, sticky="w")
        self.recent_tree = ttk.Treeview(
            recent_box,
            columns=("sale_date", "seller", "buyer", "lots"),
            show="headings",
            height=8,
        )
        for name, width in [("sale_date", 95), ("seller", 160), ("buyer", 160), ("lots", 180)]:
            self.recent_tree.heading(name, text=name.replace("_", " ").title())
            self.recent_tree.column(name, width=width, anchor="w")
        self.recent_tree.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.recent_tree.bind("<<TreeviewSelect>>", self._on_select_sale_group)

        ttk.Label(right, text="Buyer and sale details", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(right, text="Sale date").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(right, textvariable=self.sale_date_var).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Checkbutton(
            right,
            text="Buyer is a new owner",
            variable=self.new_buyer_var,
            command=self._toggle_buyer_mode,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 10))

        self.existing_buyer_frame = ttk.Frame(right, style="App.TFrame")
        self.existing_buyer_frame.grid(row=3, column=0, columnspan=2, sticky="nsew")
        self.existing_buyer_frame.columnconfigure(1, weight=1)
        ttk.Label(self.existing_buyer_frame, text="Search buyer").grid(row=0, column=0, sticky="w", padx=(0, 8))
        buyer_entry = ttk.Entry(self.existing_buyer_frame, textvariable=self.buyer_search_var)
        buyer_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        buyer_entry.bind("<Return>", self.search_buyers)
        ttk.Button(self.existing_buyer_frame, text="Search", command=self.search_buyers).grid(row=0, column=2, sticky="w")
        self.buyer_tree = ttk.Treeview(
            self.existing_buyer_frame,
            columns=("owner_code", "name", "lots"),
            show="headings",
            height=8,
        )
        for name, width in [("owner_code", 85), ("name", 220), ("lots", 60)]:
            self.buyer_tree.heading(name, text=name.replace("_", " ").title())
            self.buyer_tree.column(name, width=width, anchor="center" if name == "lots" else "w")
        self.buyer_tree.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        self.buyer_tree.bind("<<TreeviewSelect>>", self._on_select_buyer)

        self.new_buyer_frame = ttk.Frame(right, style="App.TFrame")
        self.new_buyer_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.new_buyer_frame.columnconfigure(1, weight=1)
        fields = [
            ("Last name", self.new_last_name_var),
            ("First name", self.new_first_name_var),
            ("Address", self.new_address_var),
            ("City", self.new_city_var),
            ("State", self.new_state_var),
            ("ZIP", self.new_zip_var),
            ("Phone", self.new_phone_var),
        ]
        for idx, (label, variable) in enumerate(fields):
            ttk.Label(self.new_buyer_frame, text=label).grid(row=idx, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Entry(self.new_buyer_frame, textvariable=variable).grid(row=idx, column=1, sticky="ew", pady=4)

        ttk.Button(right, text="Record Sale / Purchase", command=self.record_sale).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(16, 0)
        )
        self._toggle_buyer_mode()
        self.refresh_recent_sales()

    def _open_created_file(self, path: Path, title: str) -> None:
        try:
            open_with_default_app(path)
        except Exception as exc:
            messagebox.showerror(
                title,
                "\n".join(
                    [
                        "The sale receipt was created, but it could not be opened automatically.",
                        str(path),
                        "",
                        str(exc),
                    ]
                ),
            )

    def _toggle_buyer_mode(self) -> None:
        if self.new_buyer_var.get():
            self.existing_buyer_frame.grid_remove()
            self.new_buyer_frame.grid()
        else:
            self.new_buyer_frame.grid_remove()
            self.existing_buyer_frame.grid()

    def search_sellers(self, _event: object | None = None) -> None:
        self.seller_results = self.repository.search(self.seller_search_var.get())
        self.seller_tree.delete(*self.seller_tree.get_children())
        for owner in self.seller_results:
            name = " ".join(part for part in [owner["last_name"], owner["first_name"]] if part).strip()
            self.seller_tree.insert(
                "",
                "end",
                iid=owner["owner_code"],
                values=(
                    owner["owner_code"],
                    name,
                    owner["lot_count"],
                    f"${float(owner['total_owed'] or 0):,.2f}",
                ),
            )
        children = self.seller_tree.get_children()
        if children:
            self.seller_tree.selection_set(children[0])
            self._load_seller(children[0])

    def search_buyers(self, _event: object | None = None) -> None:
        self.buyer_results = self.repository.search(self.buyer_search_var.get())
        self.buyer_tree.delete(*self.buyer_tree.get_children())
        for owner in self.buyer_results:
            name = " ".join(part for part in [owner["last_name"], owner["first_name"]] if part).strip()
            self.buyer_tree.insert(
                "",
                "end",
                iid=owner["owner_code"],
                values=(owner["owner_code"], name, owner["lot_count"]),
            )

    def _on_select_seller(self, _event: object | None = None) -> None:
        selected = self.seller_tree.selection()
        if selected:
            self._load_seller(selected[0])

    def _load_seller(self, owner_code: str) -> None:
        detail = self.repository.get_owner_detail(owner_code)
        if detail is None:
            return
        self.selected_seller_code = owner_code
        self.selected_lots = set()
        self.lot_tree.delete(*self.lot_tree.get_children())
        for lot in detail["lots"]:
            self.lot_tree.insert(
                "",
                "end",
                iid=lot["lot_number"],
                values=("[ ]", lot["lot_number"], f"${float(lot['total_due'] or 0):,.2f}"),
            )

    def _on_select_buyer(self, _event: object | None = None) -> None:
        selected = self.buyer_tree.selection()
        self.selected_buyer_code = selected[0] if selected else None

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

    def refresh_recent_sales(self) -> None:
        sales = self.repository.list_recent_property_sale_groups()
        self.selected_sale_group = None
        self.recent_tree.delete(*self.recent_tree.get_children())
        for sale in sales:
            seller = " ".join(
                part for part in [sale["seller_last_name"], sale["seller_first_name"]] if part
            ).strip()
            buyer = " ".join(
                part for part in [sale["buyer_last_name"], sale["buyer_first_name"]] if part
            ).strip()
            item_id = "|".join(
                [
                    str(sale["created_at"] or ""),
                    str(sale["sale_date"] or ""),
                    str(sale["seller_owner_code"] or ""),
                    str(sale["buyer_owner_code"] or ""),
                ]
            )
            self.recent_tree.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    sale["sale_date"] or "",
                    seller or sale["seller_owner_code"],
                    buyer or sale["buyer_owner_code"],
                    sale["lot_numbers"] or "",
                ),
            )
        children = self.recent_tree.get_children()
        if children:
            self.recent_tree.selection_set(children[0])
            self._load_sale_group(children[0])

    def _on_select_sale_group(self, _event: object | None = None) -> None:
        selected = self.recent_tree.selection()
        if selected:
            self._load_sale_group(selected[0])

    def _load_sale_group(self, item_id: str) -> None:
        created_at, sale_date, seller_owner_code, buyer_owner_code = item_id.split("|", 3)
        self.selected_sale_group = PropertySaleGroup(
            created_at=created_at,
            sale_date=sale_date,
            seller_owner_code=seller_owner_code,
            buyer_owner_code=buyer_owner_code,
        )

    def record_sale(self) -> None:
        if not self.selected_seller_code:
            messagebox.showerror("Missing seller", "Select the seller first.")
            return
        if not self.selected_lots:
            messagebox.showerror("Missing lots", "Check at least one lot being sold.")
            return

        if self.new_buyer_var.get():
            new_buyer = NewBuyerRequest(
                last_name=self.new_last_name_var.get(),
                first_name=self.new_first_name_var.get(),
                address=self.new_address_var.get(),
                city=self.new_city_var.get(),
                state=self.new_state_var.get(),
                zip_code=self.new_zip_var.get(),
                phone=self.new_phone_var.get(),
            )
            request = PropertySaleRequest(
                seller_owner_code=self.selected_seller_code,
                lot_numbers=sorted(self.selected_lots),
                sale_date=self.sale_date_var.get().strip(),
                new_buyer=new_buyer,
            )
        else:
            if not self.selected_buyer_code:
                messagebox.showerror("Missing buyer", "Select the buyer first.")
                return
            request = PropertySaleRequest(
                seller_owner_code=self.selected_seller_code,
                lot_numbers=sorted(self.selected_lots),
                sale_date=self.sale_date_var.get().strip(),
                buyer_owner_code=self.selected_buyer_code,
            )

        confirm = messagebox.askyesno(
            "Confirm property sale",
            "\n".join(
                [
                    f"Seller: {request.seller_owner_code}",
                    f"Buyer: {request.buyer_owner_code or 'New buyer'}",
                    f"Lots: {', '.join(request.lot_numbers)}",
                    f"Sale date: {request.sale_date}",
                    "",
                    "A backup will be created before this sale is saved.",
                ]
            ),
        )
        if not confirm:
            return

        try:
            result = record_property_sale(self.db_path, request)
        except Exception as exc:
            messagebox.showerror("Sale failed", str(exc))
            return

        receipt_dir = self.db_path.parent / "generated_reports"
        try:
            receipt_lines = build_property_sale_receipt_lines(self.db_path, result)
            html_output = render_property_sale_receipt_html(
                receipt_lines,
                receipt_dir,
                "property_sale_receipt",
            )
            pdf_output = convert_property_sale_html_to_pdf(html_output)
            html_output.unlink(missing_ok=True)
        except Exception as exc:
            messagebox.showerror("Receipt failed", str(exc))
            return

        messagebox.showinfo(
            "Sale recorded",
            "\n".join(
                [
                    f"Seller: {result.seller_owner_code}",
                    f"Buyer: {result.buyer_owner_code}",
                    f"Lots transferred: {', '.join(result.transferred_lots)}",
                    f"Backup: {result.backup_path}",
                ]
            ),
        )
        self._open_created_file(pdf_output, "Sale receipt preview failed")
        self.search_sellers()
        self.search_buyers()
        self.refresh_recent_sales()

    def reverse_selected_sale(self) -> None:
        if self.selected_sale_group is None:
            messagebox.showerror("Missing sale", "Select a recent sale to reverse.")
            return

        confirm = messagebox.askyesno(
            "Confirm sale reversal",
            "\n".join(
                [
                    f"Seller: {self.selected_sale_group.seller_owner_code}",
                    f"Buyer: {self.selected_sale_group.buyer_owner_code}",
                    f"Sale date: {self.selected_sale_group.sale_date}",
                    "",
                    "The selected property sale will be reversed and a backup will be created first.",
                ]
            ),
        )
        if not confirm:
            return

        try:
            result = reverse_property_sale(self.db_path, self.selected_sale_group)
        except Exception as exc:
            messagebox.showerror("Reverse sale failed", str(exc))
            return

        messagebox.showinfo(
            "Sale reversed",
            "\n".join(
                [
                    f"Seller restored: {result.seller_owner_code}",
                    f"Buyer updated: {result.buyer_owner_code}",
                    f"Lots returned: {', '.join(result.returned_lots)}",
                    f"Backup: {result.backup_path}",
                ]
            ),
        )
        self.search_sellers()
        self.search_buyers()
        self.refresh_recent_sales()
