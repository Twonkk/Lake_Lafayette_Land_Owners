import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from src.services.migration_review_service import (
    MigrationReviewItem,
    OwnerReviewUpdate,
    accept_x_lot_exclusion,
    complete_owner_manually,
    completed_decision_count,
    delete_unused_placeholder,
    keep_dbase_owner_total,
    keep_historical_owner,
    list_migration_review_items,
    owner_review_defaults,
    restore_suggested_owner,
    use_lot_balance_total,
)


class MigrationReviewFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, db_path: Path) -> None:
        super().__init__(parent, style="App.TFrame")
        self.db_path = db_path
        self.items: dict[str, MigrationReviewItem] = {}
        self.selected_item: MigrationReviewItem | None = None
        self.summary_var = tk.StringVar()
        self.recommendation_var = tk.StringVar()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build()
        self.refresh()

    def _build(self) -> None:
        ttk.Label(
            self,
            text=(
                "Review records that dBase left incomplete or inconsistent. Select an item to see "
                "the evidence and safe choices. Complete this review after the final dBase refresh. "
                "Every decision creates a database backup first."
            ),
            style="Section.TLabel",
            wraplength=940,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(self, textvariable=self.summary_var).grid(row=1, column=0, sticky="w", pady=(0, 10))

        split = ttk.Panedwindow(self, orient="vertical")
        split.grid(row=2, column=0, sticky="nsew")

        list_frame = ttk.Frame(split, style="App.TFrame")
        detail_frame = ttk.Frame(split, style="App.TFrame")
        split.add(list_frame, weight=3)
        split.add(detail_frame, weight=2)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(1, weight=1)

        self.tree = ttk.Treeview(
            list_frame,
            columns=("type", "record", "summary", "status"),
            show="headings",
            height=8,
        )
        for name, heading, width, anchor in [
            ("type", "Review Type", 160, "w"),
            ("record", "Owner Code", 100, "center"),
            ("summary", "What Was Found", 650, "w"),
            ("status", "Decision", 190, "w"),
        ]:
            self.tree.heading(name, text=heading)
            self.tree.column(name, width=width, anchor=anchor)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        list_scroll.grid(row=0, column=1, sticky="ns")
        list_scroll_x = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        list_scroll_x.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=list_scroll.set, xscrollcommand=list_scroll_x.set)

        ttk.Label(detail_frame, text="Selected item", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(10, 6)
        )
        self.detail_text = tk.Text(
            detail_frame,
            wrap="word",
            height=6,
            relief="flat",
            background="#ffffff",
            foreground="#1d2430",
            font=("TkDefaultFont", 11),
            padx=12,
            pady=12,
        )
        self.detail_text.grid(row=1, column=0, sticky="nsew")
        self.detail_text.configure(state="disabled")
        ttk.Label(
            detail_frame,
            textvariable=self.recommendation_var,
            wraplength=940,
            justify="left",
        ).grid(row=2, column=0, sticky="ew", pady=(8, 6))

        actions = ttk.Frame(detail_frame, style="App.TFrame")
        actions.grid(row=3, column=0, sticky="ew")
        for column in range(4):
            actions.columnconfigure(column, weight=1)

        self.restore_button = ttk.Button(
            actions, text="Restore Suggested Owner", command=self._restore_owner
        )
        self.manual_button = ttk.Button(
            actions, text="Enter Owner Details", command=self._complete_owner
        )
        self.historical_button = ttk.Button(
            actions, text="Keep as Historical", command=self._keep_historical
        )
        self.delete_button = ttk.Button(
            actions, text="Delete Unused Placeholder", command=self._delete_placeholder
        )
        self.x_lot_button = ttk.Button(
            actions, text="Accept X-Lot Exclusion", command=self._accept_x_lot
        )
        self.lot_total_button = ttk.Button(
            actions, text="Use Lot Balance Total", command=self._use_lot_total
        )
        self.dbase_total_button = ttk.Button(
            actions, text="Keep dBase Owner Total", command=self._keep_dbase_total
        )
        self.refresh_button = ttk.Button(actions, text="Refresh Review List", command=self.refresh)
        self.action_buttons = [
            self.restore_button,
            self.manual_button,
            self.historical_button,
            self.delete_button,
            self.x_lot_button,
            self.lot_total_button,
            self.dbase_total_button,
            self.refresh_button,
        ]

    def refresh(self) -> None:
        selected_key = None
        if self.selected_item:
            selected_key = f"{self.selected_item.category}:{self.selected_item.record_key}"
        review_items = list_migration_review_items(self.db_path)
        self.items = {f"{item.category}:{item.record_key}": item for item in review_items}
        self.tree.delete(*self.tree.get_children())
        unresolved = sum(1 for item in review_items if not item.decision)
        completed = completed_decision_count(self.db_path)
        self.summary_var.set(
            f"{unresolved} item(s) still need a decision. {completed} decision(s) have been recorded."
        )
        for item_id, item in self.items.items():
            status = item.decision.replace("_", " ").title() if item.decision else "Needs decision"
            self.tree.insert(
                "", "end", iid=item_id,
                values=(item.label, item.record_key, item.summary, status),
            )
        children = self.tree.get_children()
        if selected_key in self.items:
            self.tree.selection_set(selected_key)
            self._show_item(self.items[selected_key])
        elif children:
            self.tree.selection_set(children[0])
            self._show_item(self.items[children[0]])
        else:
            self.selected_item = None
            self._set_detail("No unresolved migration items remain.")
            self.recommendation_var.set("The customer has completed the migration review queue.")
            self._update_buttons()

    def _on_select(self, _event: object | None = None) -> None:
        selected = self.tree.selection()
        if selected and selected[0] in self.items:
            self._show_item(self.items[selected[0]])

    def _show_item(self, item: MigrationReviewItem) -> None:
        self.selected_item = item
        decision = item.decision.replace("_", " ").title() if item.decision else "Not decided"
        self._set_detail(f"{item.summary}\n\n{item.details}\n\nDecision: {decision}")
        self.recommendation_var.set(f"Recommended: {item.recommendation}")
        self._update_buttons()

    def _set_detail(self, text: str) -> None:
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", text)
        self.detail_text.configure(state="disabled")

    def _update_buttons(self) -> None:
        item = self.selected_item
        undecided = bool(item and not item.decision)
        category = item.category if item else ""
        for button in self.action_buttons:
            button.grid_remove()

        visible: list[tuple[ttk.Button, str]] = []
        if category == "missing_owner":
            if item and item.has_candidate:
                visible.append((self.restore_button, "normal" if undecided else "disabled"))
            visible.append((self.manual_button, "normal" if undecided else "disabled"))
            if item and item.current_lot_count == 0:
                visible.append((self.historical_button, "normal" if undecided else "disabled"))
                visible.append(
                    (self.delete_button, "normal" if undecided and item.can_delete else "disabled")
                )
        elif category == "x_lot_exclusion":
            visible.append((self.x_lot_button, "normal" if undecided else "disabled"))
        elif category == "owner_rounding":
            visible.extend(
                [
                    (self.lot_total_button, "normal" if undecided else "disabled"),
                    (self.dbase_total_button, "normal" if undecided else "disabled"),
                ]
            )
        visible.append((self.refresh_button, "normal"))
        for index, (button, state) in enumerate(visible):
            button.configure(state=state)
            button.grid(row=index // 4, column=index % 4, sticky="ew", padx=4, pady=4)

    def _selected(self, category: str) -> MigrationReviewItem | None:
        item = self.selected_item
        if item is None or item.category != category:
            messagebox.showinfo("Choose a review item", "Select the matching review item first.")
            return None
        return item

    def _run_action(self, title: str, action) -> None:
        try:
            backup = action()
        except Exception as exc:
            messagebox.showerror(f"{title} stopped", str(exc))
            return
        messagebox.showinfo(
            f"{title} complete",
            f"The decision was recorded.\n\nBackup created:\n{backup}",
        )
        self.refresh()

    def _restore_owner(self) -> None:
        item = self._selected("missing_owner")
        if not item:
            return
        if not messagebox.askyesno(
            "Restore suggested owner?",
            "Use the recoverable dBase owner record shown above?\n\n"
            "Review the restored name and address with the client afterward.",
        ):
            return
        self._run_action(
            "Owner restored", lambda: restore_suggested_owner(self.db_path, item.record_key)
        )

    def _complete_owner(self) -> None:
        item = self._selected("missing_owner")
        if item:
            OwnerReviewDialog(self, self.db_path, item.record_key, self.refresh)

    def _keep_historical(self) -> None:
        item = self._selected("missing_owner")
        if not item:
            return
        if not messagebox.askyesno(
            "Keep historical reference?",
            "Keep this code and its imported history, but mark it as non-current and unavailable for mail or cards?",
        ):
            return
        self._run_action(
            "Historical reference saved", lambda: keep_historical_owner(self.db_path, item.record_key)
        )

    def _delete_placeholder(self) -> None:
        item = self._selected("missing_owner")
        if not item:
            return
        if not messagebox.askyesno(
            "Delete unused placeholder?",
            "Delete this placeholder? This is permitted only when no records refer to it.",
        ):
            return
        self._run_action(
            "Placeholder deleted", lambda: delete_unused_placeholder(self.db_path, item.record_key)
        )

    def _accept_x_lot(self) -> None:
        item = self._selected("x_lot_exclusion")
        if not item:
            return
        if not messagebox.askyesno(
            "Accept X-lot exclusion?",
            "Confirm that this special X lot should remain outside the current assessment file?",
        ):
            return
        self._run_action(
            "X-lot decision saved", lambda: accept_x_lot_exclusion(self.db_path, item.record_key)
        )

    def _use_lot_total(self) -> None:
        item = self._selected("owner_rounding")
        if not item:
            return
        if not messagebox.askyesno(
            "Use lot balance total?",
            "Replace the owner-level total with the exact sum of the stored lot balances?",
        ):
            return
        self._run_action(
            "Balance reconciled", lambda: use_lot_balance_total(self.db_path, item.record_key)
        )

    def _keep_dbase_total(self) -> None:
        item = self._selected("owner_rounding")
        if not item:
            return
        if not messagebox.askyesno(
            "Keep dBase total?",
            "Keep the original owner-level total and record that the client accepted the rounding difference?",
        ):
            return
        self._run_action(
            "dBase total retained", lambda: keep_dbase_owner_total(self.db_path, item.record_key)
        )


class OwnerReviewDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        db_path: Path,
        owner_code: str,
        on_saved,
    ) -> None:
        super().__init__(parent)
        self.db_path = db_path
        self.owner_code = owner_code
        self.on_saved = on_saved
        self.title(f"Complete Owner {owner_code}")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.resizable(True, False)

        defaults = owner_review_defaults(db_path, owner_code)
        self.vars = {key: tk.StringVar(value=value) for key, value in defaults.items()}
        self.columnconfigure(1, weight=1)
        fields = [
            ("Owner code", "owner_code", True),
            ("Last name", "last_name", False),
            ("First name", "first_name", False),
            ("Address", "address", False),
            ("City", "city", False),
            ("State", "state", False),
            ("ZIP", "zip_code", False),
            ("Phone", "phone", False),
            ("Current owner (T/F)", "current_flag", False),
            ("Resident (Y/N)", "resident_flag", False),
            ("Hold mail (Y/N)", "hold_mail_flag", False),
            ("Ineligible for cards (Y/N)", "ineligible_flag", False),
        ]
        for row, (label, key, readonly) in enumerate(fields):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", padx=12, pady=5)
            ttk.Entry(
                self,
                textvariable=self.vars[key],
                state="readonly" if readonly else "normal",
                width=42,
            ).grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=5)
        buttons = ttk.Frame(self)
        buttons.grid(row=len(fields), column=0, columnspan=2, sticky="ew", padx=12, pady=12)
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        ttk.Button(buttons, text="Save Reviewed Owner", command=self._save).grid(
            row=0, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(buttons, text="Cancel", command=self.destroy).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )

    def _save(self) -> None:
        try:
            backup = complete_owner_manually(
                self.db_path,
                OwnerReviewUpdate(
                    owner_code=self.owner_code,
                    last_name=self.vars["last_name"].get(),
                    first_name=self.vars["first_name"].get(),
                    address=self.vars["address"].get(),
                    city=self.vars["city"].get(),
                    state=self.vars["state"].get(),
                    zip_code=self.vars["zip_code"].get(),
                    phone=self.vars["phone"].get(),
                    current_flag=self.vars["current_flag"].get(),
                    resident_flag=self.vars["resident_flag"].get(),
                    hold_mail_flag=self.vars["hold_mail_flag"].get(),
                    ineligible_flag=self.vars["ineligible_flag"].get(),
                ),
            )
        except Exception as exc:
            messagebox.showerror("Owner update stopped", str(exc), parent=self)
            return
        messagebox.showinfo(
            "Owner review complete",
            f"The owner was updated and the decision was recorded.\n\nBackup created:\n{backup}",
            parent=self,
        )
        self.destroy()
        self.on_saved()
