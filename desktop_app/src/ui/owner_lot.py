import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from src.db.repositories import OwnerRepository
from src.services.owner_lot_service import (
    LotUpdateRequest,
    OwnerUpdateRequest,
    add_owner_note,
    update_lot_record,
    update_owner_record,
)


class OwnerLotFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, db_path: Path) -> None:
        super().__init__(parent, style="App.TFrame")
        self.db_path = db_path
        self.repository = OwnerRepository(db_path)
        self.search_var = tk.StringVar()
        self.results: list[dict] = []
        self.selected_owner_code: str | None = None
        self.selected_lot_number: str | None = None

        self.owner_vars = {
            "owner_code": tk.StringVar(),
            "last_name": tk.StringVar(),
            "first_name": tk.StringVar(),
            "address": tk.StringVar(),
            "city": tk.StringVar(),
            "state": tk.StringVar(),
            "zip_code": tk.StringVar(),
            "phone": tk.StringVar(),
            "status": tk.StringVar(),
            "resident_flag": tk.StringVar(),
            "hold_mail_flag": tk.StringVar(),
            "ineligible_flag": tk.StringVar(),
            "total_owed": tk.StringVar(),
        }
        self.lot_vars = {
            "lot_number": tk.StringVar(),
            "total_due": tk.StringVar(),
            "current_assessment": tk.StringVar(),
            "delinquent_assessment": tk.StringVar(),
            "delinquent_interest": tk.StringVar(),
            "current_interest": tk.StringVar(),
            "paid_through": tk.StringVar(),
            "development_status": tk.StringVar(),
            "freeze_flag": tk.StringVar(),
            "lakefront_flag": tk.StringVar(),
            "dock_flag": tk.StringVar(),
            "lien_flag": tk.StringVar(),
            "collection_flag": tk.StringVar(),
            "appraised_value": tk.StringVar(),
            "assessed_value": tk.StringVar(),
            "previous_review_date": tk.StringVar(),
            "last_review_date": tk.StringVar(),
        }

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self._build()
        self.run_search()

    def _build(self) -> None:
        ttk.Label(self, text="Owners and Lots", style="Title.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 12)
        )

        search_row = ttk.Frame(self, style="App.TFrame")
        search_row.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="Search by name, owner code, or lot number").grid(
            row=0, column=0, sticky="w", padx=(0, 12)
        )
        entry = ttk.Entry(search_row, textvariable=self.search_var)
        entry.grid(row=0, column=1, sticky="ew", padx=(0, 12))
        entry.bind("<Return>", self.run_search)
        ttk.Button(search_row, text="Search", command=self.run_search).grid(row=0, column=2, sticky="ew")

        split = ttk.Panedwindow(self, orient="horizontal")
        split.grid(row=2, column=0, sticky="nsew")

        left = ttk.Frame(split, style="App.TFrame", padding=(0, 0, 12, 0))
        right = ttk.Frame(split, style="App.TFrame")
        split.add(left, weight=2)
        split.add(right, weight=3)

        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        ttk.Label(left, text="Matching owners", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.result_tree = ttk.Treeview(
            left,
            columns=("owner_code", "name", "primary_lot", "lots", "owed"),
            show="headings",
            height=22,
        )
        for name, width, anchor in [
            ("owner_code", 90, "center"),
            ("name", 240, "w"),
            ("primary_lot", 90, "center"),
            ("lots", 60, "center"),
            ("owed", 90, "center"),
        ]:
            self.result_tree.heading(name, text=name.replace("_", " ").title())
            self.result_tree.column(name, width=width, anchor=anchor)
        self.result_tree.grid(row=1, column=0, sticky="nsew")
        self.result_tree.bind("<<TreeviewSelect>>", self._on_select_owner)
        result_scroll = ttk.Scrollbar(left, orient="vertical", command=self.result_tree.yview)
        result_scroll.grid(row=1, column=1, sticky="ns")
        self.result_tree.configure(yscrollcommand=result_scroll.set)

        notebook = ttk.Notebook(right)
        notebook.grid(row=0, column=0, sticky="nsew")

        owner_tab = ttk.Frame(notebook, style="App.TFrame", padding=12)
        lot_tab = ttk.Frame(notebook, style="App.TFrame", padding=12)
        note_tab = ttk.Frame(notebook, style="App.TFrame", padding=12)
        notebook.add(owner_tab, text="Owner")
        notebook.add(lot_tab, text="Lot")
        notebook.add(note_tab, text="Notes")

        self._build_owner_tab(owner_tab)
        self._build_lot_tab(lot_tab)
        self._build_note_tab(note_tab)

    def _build_owner_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        fields = [
            ("Owner code", "owner_code", True),
            ("Last name", "last_name", False),
            ("First name", "first_name", False),
            ("Address", "address", False),
            ("City", "city", False),
            ("State", "state", False),
            ("ZIP", "zip_code", False),
            ("Phone", "phone", False),
            ("Status", "status", False),
            ("Resident", "resident_flag", False),
            ("Hold mail", "hold_mail_flag", False),
            ("Ineligible", "ineligible_flag", False),
            ("Total owed", "total_owed", True),
        ]
        for idx, (label, key, readonly) in enumerate(fields):
            ttk.Label(parent, text=label).grid(row=idx, column=0, sticky="w", padx=(0, 8), pady=5)
            state = "readonly" if readonly else "normal"
            ttk.Entry(parent, textvariable=self.owner_vars[key], state=state).grid(
                row=idx, column=1, sticky="ew", pady=5
            )
        ttk.Button(parent, text="Save Owner Changes", command=self.save_owner).grid(
            row=len(fields), column=0, columnspan=2, sticky="ew", pady=(16, 0)
        )

    def _build_lot_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        ttk.Label(parent, text="Lots for selected owner", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.lot_tree = ttk.Treeview(
            parent,
            columns=("lot_number", "due", "freeze", "lien", "collection"),
            show="headings",
            height=8,
        )
        for name, text, width in [
            ("lot_number", "Lot", 90),
            ("due", "Balance", 90),
            ("freeze", "Freeze", 60),
            ("lien", "Lien", 60),
            ("collection", "Collection", 80),
        ]:
            self.lot_tree.heading(name, text=text)
            self.lot_tree.column(name, width=width, anchor="center")
        self.lot_tree.grid(row=1, column=0, sticky="nsew")
        self.lot_tree.bind("<<TreeviewSelect>>", self._on_select_lot)

        form = ttk.LabelFrame(parent, text="Selected lot detail")
        form.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        form.columnconfigure(1, weight=1)

        fields = [
            ("Lot number", "lot_number", True),
            ("Total due", "total_due", True),
            ("Current assess.", "current_assessment", True),
            ("Delinq. assess.", "delinquent_assessment", True),
            ("Delinq. interest", "delinquent_interest", True),
            ("Current interest", "current_interest", True),
            ("Paid through", "paid_through", False),
            ("Development", "development_status", False),
            ("Freeze", "freeze_flag", False),
            ("Lakefront", "lakefront_flag", False),
            ("Dock", "dock_flag", False),
            ("Lien", "lien_flag", True),
            ("Collection", "collection_flag", True),
            ("Appraised", "appraised_value", False),
            ("Assessed", "assessed_value", False),
            ("Prev review", "previous_review_date", False),
            ("Last review", "last_review_date", False),
        ]
        for idx, (label, key, readonly) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=idx, column=0, sticky="w", padx=(0, 8), pady=4)
            state = "readonly" if readonly else "normal"
            ttk.Entry(form, textvariable=self.lot_vars[key], state=state).grid(
                row=idx, column=1, sticky="ew", pady=4
            )
        ttk.Button(form, text="Save Lot Changes", command=self.save_lot).grid(
            row=len(fields), column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )

    def _build_note_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(3, weight=1)

        ttk.Label(parent, text="Recent notes", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.notes_text = tk.Text(
            parent,
            wrap="word",
            relief="flat",
            background="#ffffff",
            foreground="#1d2430",
            font=("TkDefaultFont", 10),
            padx=12,
            pady=12,
            height=10,
        )
        self.notes_text.grid(row=1, column=0, sticky="nsew")
        self.notes_text.configure(state="disabled")

        ttk.Label(parent, text="Add note", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=(12, 8))
        self.new_note_text = tk.Text(
            parent,
            wrap="word",
            relief="flat",
            background="#ffffff",
            foreground="#1d2430",
            font=("TkDefaultFont", 10),
            padx=12,
            pady=12,
            height=8,
        )
        self.new_note_text.grid(row=3, column=0, sticky="nsew")
        ttk.Button(parent, text="Save Note", command=self.save_note).grid(row=4, column=0, sticky="ew", pady=(12, 0))

    def run_search(self, _event: object | None = None) -> None:
        self.results = self.repository.search(self.search_var.get())
        self.result_tree.delete(*self.result_tree.get_children())
        for owner in self.results:
            name = " ".join(part for part in [owner["last_name"], owner["first_name"]] if part).strip()
            self.result_tree.insert(
                "",
                "end",
                iid=owner["owner_code"],
                values=(
                    owner["owner_code"],
                    name,
                    owner["primary_lot_number"] or "",
                    owner["lot_count"],
                    f"${float(owner['total_owed'] or 0):,.2f}",
                ),
            )
        children = self.result_tree.get_children()
        if children:
            self.result_tree.selection_set(children[0])
            self._show_owner_detail(children[0])
        else:
            self._clear_owner_forms()

    def _on_select_owner(self, _event: object | None = None) -> None:
        selected = self.result_tree.selection()
        if selected:
            self._show_owner_detail(selected[0])

    def _show_owner_detail(self, owner_code: str) -> None:
        detail = self.repository.get_owner_detail(owner_code)
        if detail is None:
            self._clear_owner_forms()
            return

        self.selected_owner_code = owner_code
        owner = detail["owner"]
        lots = detail["lots"]
        notes = detail["notes"]

        self.owner_vars["owner_code"].set(owner["owner_code"] or "")
        self.owner_vars["last_name"].set(owner["last_name"] or "")
        self.owner_vars["first_name"].set(owner["first_name"] or "")
        self.owner_vars["address"].set(owner["address"] or "")
        self.owner_vars["city"].set(owner["city"] or "")
        self.owner_vars["state"].set(owner["state"] or "")
        self.owner_vars["zip_code"].set(owner["zip"] or "")
        self.owner_vars["phone"].set(owner["phone"] or "")
        self.owner_vars["status"].set(owner["status"] or "")
        self.owner_vars["resident_flag"].set(owner["resident_flag"] or "")
        self.owner_vars["hold_mail_flag"].set(owner["hold_mail_flag"] or "")
        self.owner_vars["ineligible_flag"].set(owner["ineligible_flag"] or "")
        self.owner_vars["total_owed"].set(f"${float(owner['total_owed'] or 0):,.2f}")

        self.lot_tree.delete(*self.lot_tree.get_children())
        self.selected_lot_number = None
        for lot in lots:
            self.lot_tree.insert(
                "",
                "end",
                iid=lot["lot_number"],
                values=(
                    lot["lot_number"],
                    f"${float(lot['total_due'] or 0):,.2f}",
                    lot["freeze_flag"] or "",
                    lot["lien_flag"] or "",
                    lot["collection_flag"] or "",
                ),
            )
        lot_children = self.lot_tree.get_children()
        if lot_children:
            self.lot_tree.selection_set(lot_children[0])
            self._load_lot_detail(lot_children[0], lots)
        else:
            self._clear_lot_form()

        lines = []
        if notes:
            for note in notes:
                note_text = (note["note_text"] or "").strip()
                preview = note_text[:220] + ("..." if len(note_text) > 220 else "")
                lines.append(f"{note['review_date'] or ''}  {preview}".rstrip())
        else:
            lines.append("No notes found.")
        self.notes_text.configure(state="normal")
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", "\n\n".join(lines))
        self.notes_text.configure(state="disabled")

    def _on_select_lot(self, _event: object | None = None) -> None:
        selected = self.lot_tree.selection()
        if not selected or not self.selected_owner_code:
            return
        detail = self.repository.get_owner_detail(self.selected_owner_code)
        if detail is None:
            return
        self._load_lot_detail(selected[0], detail["lots"])

    def _load_lot_detail(self, lot_number: str, lots: list[dict]) -> None:
        lot = next((row for row in lots if row["lot_number"] == lot_number), None)
        if lot is None:
            self._clear_lot_form()
            return
        self.selected_lot_number = lot_number
        self.lot_vars["lot_number"].set(lot["lot_number"] or "")
        self.lot_vars["total_due"].set(f"${float(lot['total_due'] or 0):,.2f}")
        self.lot_vars["current_assessment"].set(f"${float(lot['current_assessment'] or 0):,.2f}")
        self.lot_vars["delinquent_assessment"].set(f"${float(lot['delinquent_assessment'] or 0):,.2f}")
        self.lot_vars["delinquent_interest"].set(f"${float(lot['delinquent_interest'] or 0):,.2f}")
        self.lot_vars["current_interest"].set(f"${float(lot['current_interest'] or 0):,.2f}")
        self.lot_vars["paid_through"].set(lot["paid_through"] or "")
        self.lot_vars["development_status"].set(lot["development_status"] or "")
        self.lot_vars["freeze_flag"].set(lot["freeze_flag"] or "")
        self.lot_vars["lakefront_flag"].set(lot["lakefront_flag"] or "")
        self.lot_vars["dock_flag"].set(lot["dock_flag"] or "")
        self.lot_vars["lien_flag"].set(lot["lien_flag"] or "")
        self.lot_vars["collection_flag"].set(lot["collection_flag"] or "")
        self.lot_vars["appraised_value"].set(f"{float(lot['appraised_value'] or 0):,.2f}")
        self.lot_vars["assessed_value"].set(f"{float(lot['assessed_value'] or 0):,.2f}")
        self.lot_vars["previous_review_date"].set(lot["previous_review_date"] or "")
        self.lot_vars["last_review_date"].set(lot["last_review_date"] or "")

    def _clear_owner_forms(self) -> None:
        self.selected_owner_code = None
        self.selected_lot_number = None
        for variable in self.owner_vars.values():
            variable.set("")
        self.lot_tree.delete(*self.lot_tree.get_children())
        self._clear_lot_form()
        self.notes_text.configure(state="normal")
        self.notes_text.delete("1.0", "end")
        self.notes_text.configure(state="disabled")

    def _clear_lot_form(self) -> None:
        self.selected_lot_number = None
        for variable in self.lot_vars.values():
            variable.set("")

    def save_owner(self) -> None:
        if not self.selected_owner_code:
            messagebox.showerror("Missing owner", "Select an owner first.")
            return
        request = OwnerUpdateRequest(
            owner_code=self.selected_owner_code,
            last_name=self.owner_vars["last_name"].get(),
            first_name=self.owner_vars["first_name"].get(),
            address=self.owner_vars["address"].get(),
            city=self.owner_vars["city"].get(),
            state=self.owner_vars["state"].get(),
            zip_code=self.owner_vars["zip_code"].get(),
            phone=self.owner_vars["phone"].get(),
            status=self.owner_vars["status"].get(),
            resident_flag=self.owner_vars["resident_flag"].get(),
            hold_mail_flag=self.owner_vars["hold_mail_flag"].get(),
            ineligible_flag=self.owner_vars["ineligible_flag"].get(),
        )
        try:
            update_owner_record(self.db_path, request)
        except Exception as exc:
            messagebox.showerror("Owner update failed", str(exc))
            return
        self._refresh_selected_owner()

    def save_lot(self) -> None:
        if not self.selected_owner_code or not self.selected_lot_number:
            messagebox.showerror("Missing lot", "Select a lot first.")
            return
        try:
            appraised_value = float(self.lot_vars["appraised_value"].get().replace(",", "") or 0)
            assessed_value = float(self.lot_vars["assessed_value"].get().replace(",", "") or 0)
        except ValueError:
            messagebox.showerror("Invalid amount", "Appraised and assessed values must be valid numbers.")
            return
        request = LotUpdateRequest(
            lot_number=self.selected_lot_number,
            paid_through=self.lot_vars["paid_through"].get(),
            development_status=self.lot_vars["development_status"].get(),
            freeze_flag=self.lot_vars["freeze_flag"].get(),
            lakefront_flag=self.lot_vars["lakefront_flag"].get(),
            dock_flag=self.lot_vars["dock_flag"].get(),
            appraised_value=appraised_value,
            assessed_value=assessed_value,
            previous_review_date=self.lot_vars["previous_review_date"].get(),
            last_review_date=self.lot_vars["last_review_date"].get(),
        )
        try:
            update_lot_record(self.db_path, self.selected_owner_code, request)
        except Exception as exc:
            messagebox.showerror("Lot update failed", str(exc))
            return
        self._refresh_selected_owner()

    def save_note(self) -> None:
        if not self.selected_owner_code:
            messagebox.showerror("Missing owner", "Select an owner first.")
            return
        note_text = self.new_note_text.get("1.0", "end").strip()
        try:
            add_owner_note(self.db_path, self.selected_owner_code, note_text)
        except Exception as exc:
            messagebox.showerror("Note save failed", str(exc))
            return
        self.new_note_text.delete("1.0", "end")
        self._refresh_selected_owner()

    def _refresh_selected_owner(self) -> None:
        current_owner = self.selected_owner_code
        current_lot = self.selected_lot_number
        self.run_search()
        if current_owner and current_owner in self.result_tree.get_children():
            self.result_tree.selection_set(current_owner)
            self._show_owner_detail(current_owner)
            if current_lot and current_lot in self.lot_tree.get_children():
                self.lot_tree.selection_set(current_lot)
                self._on_select_lot()
