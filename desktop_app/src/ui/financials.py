import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from src.db.repositories import FinancialRepository
from src.runtime import open_with_default_app
from src.services.financial_service import (
    TRANSACTION_TYPES,
    FinancialAccountRequest,
    FinancialBudgetUpdateRequest,
    FinancialTransactionRequest,
    add_financial_account,
    active_fiscal_year,
    active_fiscal_month,
    close_financial_month,
    create_new_fiscal_year,
    default_financial_date,
    delete_financial_account,
    post_financial_transaction,
    rename_financial_account,
    render_budget_report_pdf,
    render_monthly_financial_report_pdf,
    render_transaction_log_pdf,
    render_year_end_financial_report_pdf,
    update_financial_budget,
)


class FinancialsFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, db_path: Path) -> None:
        super().__init__(parent, style="App.TFrame")
        self.db_path = db_path
        self.repository = FinancialRepository(db_path)
        initial_year = active_fiscal_year(db_path)
        self.year_var = tk.StringVar(value=initial_year)
        self.month_var = tk.StringVar(value=str(active_fiscal_month(db_path, initial_year)))
        self.account_var = tk.StringVar()
        self.date_var = tk.StringVar(value=default_financial_date())
        self.type_var = tk.StringVar(value="Expense")
        self.amount_var = tk.StringVar()
        self.payee_var = tk.StringVar()
        self.memo_var = tk.StringVar()
        self.reference_var = tk.StringVar()
        self.check_var = tk.StringVar()
        self.selected_account_code: str | None = None
        self.new_account_code_var = tk.StringVar()
        self.new_account_name_var = tk.StringVar()
        self.new_category_var = tk.StringVar()
        self.new_fiscal_year_var = tk.StringVar(value="2026")
        self.next_fiscal_year_var = tk.StringVar(value=str(int(initial_year) + 1))
        self.monthly_budget_var = tk.StringVar()
        self.yearly_budget_var = tk.StringVar()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self._build()
        self.refresh_month()

    def _open_created_file(self, path: Path, title: str) -> None:
        try:
            open_with_default_app(path)
        except Exception as exc:
            messagebox.showerror(
                title,
                "\n".join(
                    [
                        "The report file was created, but it could not be opened automatically.",
                        str(path),
                        "",
                        str(exc),
                    ]
                ),
            )

    def _build(self) -> None:
        controls = ttk.Frame(self, style="App.TFrame")
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(controls, text="Fiscal year").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.year_box = ttk.Combobox(
            controls,
            textvariable=self.year_var,
            values=[],
            state="readonly",
            width=10,
        )
        self.year_box.grid(row=0, column=1, sticky="w", padx=(0, 12))
        self.year_box.bind("<<ComboboxSelected>>", self.refresh_month)
        ttk.Label(controls, text="Fiscal month").grid(row=0, column=2, sticky="w", padx=(0, 8))
        month_box = ttk.Combobox(
            controls,
            textvariable=self.month_var,
            values=[str(i) for i in range(1, 13)],
            state="readonly",
            width=6,
        )
        month_box.grid(row=0, column=3, sticky="w", padx=(0, 12))
        month_box.bind("<<ComboboxSelected>>", self.refresh_month)
        ttk.Button(controls, text="Refresh", command=self.refresh_month).grid(row=0, column=4, sticky="w")
        ttk.Button(controls, text="Close Month", command=self.close_month).grid(row=0, column=5, sticky="w", padx=(8, 0))

        notebook = ttk.Notebook(self)
        notebook.grid(row=2, column=0, sticky="nsew")

        trans_tab = ttk.Frame(notebook, style="App.TFrame", padding=12)
        manage_tab = ttk.Frame(notebook, style="App.TFrame", padding=12)
        report_tab = ttk.Frame(notebook, style="App.TFrame", padding=12)
        notebook.add(trans_tab, text="Transactions")
        notebook.add(manage_tab, text="Accounts / Budget")
        notebook.add(report_tab, text="Monthly Report")

        trans_tab.columnconfigure(0, weight=1)
        trans_tab.rowconfigure(0, weight=1)

        split = ttk.Panedwindow(trans_tab, orient="horizontal")
        split.grid(row=0, column=0, sticky="nsew")

        left = ttk.Frame(split, style="App.TFrame", padding=(0, 0, 12, 0))
        right = ttk.Frame(split, style="App.TFrame")
        split.add(left, weight=3)
        split.add(right, weight=2)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        left.rowconfigure(3, weight=1)
        right.columnconfigure(1, weight=1)

        ttk.Label(left, text="Monthly accounts", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.account_tree = ttk.Treeview(
            left,
            columns=("account", "name", "budget", "deposits", "expenses", "ytd"),
            show="headings",
            height=14,
        )
        for name, width in [
            ("account", 70),
            ("name", 200),
            ("budget", 90),
            ("deposits", 90),
            ("expenses", 90),
            ("ytd", 90),
        ]:
            self.account_tree.heading(name, text=name.title())
            self.account_tree.column(name, width=width, anchor="w")
        self.account_tree.grid(row=1, column=0, sticky="nsew")
        self.account_tree.bind("<<TreeviewSelect>>", self._on_account_select)
        ttk.Label(left, text="Transactions for selected month", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=(12, 8))
        self.transaction_tree = ttk.Treeview(
            left,
            columns=("number", "date", "type", "account", "amount", "payee"),
            show="headings",
            height=10,
        )
        for name, width in [
            ("number", 70),
            ("date", 90),
            ("type", 70),
            ("account", 70),
            ("amount", 90),
            ("payee", 180),
        ]:
            self.transaction_tree.heading(name, text=name.title())
            self.transaction_tree.column(name, width=width, anchor="w")
        self.transaction_tree.grid(row=3, column=0, sticky="nsew")

        ttk.Label(right, text="Enter transaction", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        fields = [
            ("Account code", self.account_var),
            ("Date", self.date_var),
            ("Type", self.type_var),
            ("Amount", self.amount_var),
            ("Payee", self.payee_var),
            ("Memo", self.memo_var),
            ("Reference", self.reference_var),
            ("Check #", self.check_var),
        ]
        for idx, (label, variable) in enumerate(fields, start=1):
            ttk.Label(right, text=label).grid(row=idx, column=0, sticky="w", padx=(0, 8), pady=6)
            if label == "Type":
                widget = ttk.Combobox(
                    right,
                    textvariable=variable,
                    values=list(TRANSACTION_TYPES.keys()),
                    state="readonly",
                )
            else:
                widget = ttk.Entry(right, textvariable=variable)
            widget.grid(row=idx, column=1, sticky="ew", pady=6)

        action_row = ttk.Frame(right, style="App.TFrame")
        action_row.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="ew", pady=(12, 12))
        ttk.Button(action_row, text="Post Transaction", command=self.post_transaction).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(action_row, text="Record Earlier Transaction", command=self.post_earlier_transaction).grid(row=0, column=1, sticky="ew")

        self.summary_text = tk.Text(
            right,
            wrap="word",
            relief="flat",
            background="#ffffff",
            foreground="#1d2430",
            font=("TkDefaultFont", 11),
            padx=14,
            pady=14,
            height=12,
        )
        self.summary_text.grid(row=len(fields) + 2, column=0, columnspan=2, sticky="nsew")
        self.summary_text.configure(state="disabled")

        self._build_manage_tab(manage_tab)
        self._build_report_tab(report_tab)

    def _build_manage_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        row = 0
        ttk.Label(parent, text="Selected account code").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=self.account_var).grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        ttk.Label(parent, text="Account name").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=self.new_account_name_var).grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        ttk.Label(parent, text="Category").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=self.new_category_var).grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        ttk.Label(parent, text="Fiscal year").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=self.new_fiscal_year_var).grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        ttk.Label(parent, text="Monthly budget").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=self.monthly_budget_var).grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        ttk.Label(parent, text="Yearly budget").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=self.yearly_budget_var).grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        ttk.Label(parent, text="New account code").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=self.new_account_code_var).grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        ttk.Label(parent, text="Next fiscal year").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=self.next_fiscal_year_var).grid(row=row, column=1, sticky="ew", pady=6)
        row += 1

        actions = ttk.Frame(parent)
        actions.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(12, 12))
        ttk.Button(actions, text="Load Selected Account", command=self.load_selected_account).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Save Name / Category", command=self.save_account_edits).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text="Update Budget", command=self.save_budget_edits).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(actions, text="Add New Account", command=self.add_account).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(actions, text="Delete Account", command=self.delete_account).grid(row=0, column=4)
        ttk.Button(actions, text="Create Next Fiscal Year", command=self.create_next_fiscal_year).grid(row=0, column=5, padx=(8, 0))

    def _build_report_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        ttk.Label(
            parent,
            text="Create financial report files for the selected fiscal month.",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))
        actions = ttk.Frame(parent)
        actions.grid(row=1, column=0, sticky="w")
        ttk.Button(actions, text="Monthly Report PDF", command=self.create_monthly_report_pdf).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Transaction Log PDF", command=self.create_transaction_log_pdf).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text="Budget Report PDF", command=self.create_budget_report_pdf).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(actions, text="Year-End PDF", command=self.create_year_end_report_pdf).grid(row=0, column=3, padx=(0, 8))

    def refresh_month(self, _event: object | None = None) -> None:
        years = self.repository.list_financial_years()
        if not years:
            years = [self.year_var.get() or str(active_fiscal_year(self.db_path))]
        self.year_box.configure(values=years)
        if self.year_var.get() not in years:
            self.year_var.set(years[0])

        year = self.year_var.get().strip()
        if year.isdigit():
            self.next_fiscal_year_var.set(str(int(year) + 1))
        month = int(self.month_var.get())
        accounts = self.repository.list_month_accounts(month, year)
        transactions = self.repository.list_month_transactions(month, year)
        summary = self.repository.month_summary(month, year)

        self.account_tree.delete(*self.account_tree.get_children())
        for row in accounts:
            self.account_tree.insert(
                "",
                "end",
                iid=row["account_code"],
                values=(
                    row["account_code"],
                    row["account_name"],
                    f"${float(row['monthly_budget'] or 0):,.2f}",
                    f"${float(row['month_deposit'] or 0):,.2f}",
                    f"${float(row['month_expense'] or 0):,.2f}",
                    f"${float(row['year_to_date'] or 0):,.2f}",
                ),
            )

        self.transaction_tree.delete(*self.transaction_tree.get_children())
        for row in transactions:
            self.transaction_tree.insert(
                "",
                "end",
                values=(
                    row["transaction_number"],
                    row["transaction_date"] or "",
                    row["transaction_type"] or "",
                    row["account_code"] or "",
                    f"${float(row['amount'] or 0):,.2f}",
                    row["payee"] or "",
                ),
            )

        self._set_summary(
            "\n".join(
                [
                    f"Fiscal year: {year}",
                    f"Fiscal month: {month}",
                    f"Accounts in month: {summary['account_count']}",
                    f"Monthly deposits: ${summary['total_deposits']:,.2f}",
                    f"Monthly expenses: ${summary['total_expenses']:,.2f}",
                    f"Net movement: ${summary['net']:,.2f}",
                    "",
                    "Select an account on the left to load its code into the entry form.",
                ]
            )
        )

        children = self.account_tree.get_children()
        if children:
            self.account_tree.selection_set(children[0])
            self._on_account_select()

    def _set_summary(self, text: str) -> None:
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", "end")
        self.summary_text.insert("1.0", text)
        self.summary_text.configure(state="disabled")

    def _on_account_select(self, _event: object | None = None) -> None:
        selected = self.account_tree.selection()
        if selected:
            self.selected_account_code = selected[0]
            self.account_var.set(self.selected_account_code)

    def load_selected_account(self) -> None:
        if not self.account_var.get().strip():
            messagebox.showerror("No account", "Select or enter an account code first.")
            return
        account = self.repository.get_account(self.account_var.get().strip().upper())
        if account is None:
            messagebox.showerror("Not found", "Account code was not found.")
            return
        self.new_account_name_var.set(account["account_name"] or "")
        self.new_category_var.set(account["category"] or "")
        self.new_fiscal_year_var.set(self.year_var.get().strip())
        self.monthly_budget_var.set(str(float(account["monthly_budget"] or 0)))
        self.yearly_budget_var.set(str(float(account["yearly_budget"] or 0)))

    def save_account_edits(self) -> None:
        try:
            rename_financial_account(
                self.db_path,
                self.account_var.get(),
                self.new_account_name_var.get(),
                self.new_category_var.get(),
            )
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        messagebox.showinfo("Saved", "Account name/category updated.")
        self.refresh_month()

    def save_budget_edits(self) -> None:
        try:
            monthly_budget = float(self.monthly_budget_var.get())
            yearly_budget = float(self.yearly_budget_var.get())
        except ValueError:
            messagebox.showerror("Invalid budget", "Enter valid monthly and yearly budget amounts.")
            return
        try:
            update_financial_budget(
                self.db_path,
                FinancialBudgetUpdateRequest(
                    account_code=self.account_var.get(),
                    fiscal_year=self.year_var.get().strip(),
                    fiscal_month=int(self.month_var.get()),
                    monthly_budget=monthly_budget,
                    yearly_budget=yearly_budget,
                ),
            )
        except Exception as exc:
            messagebox.showerror("Budget update failed", str(exc))
            return
        messagebox.showinfo("Budget updated", "Budget values saved for the selected month and account.")
        self.refresh_month()

    def add_account(self) -> None:
        try:
            monthly_budget = float(self.monthly_budget_var.get() or 0)
            yearly_budget = float(self.yearly_budget_var.get() or 0)
        except ValueError:
            messagebox.showerror("Invalid budget", "Enter valid monthly and yearly budget amounts.")
            return
        try:
            add_financial_account(
                self.db_path,
                FinancialAccountRequest(
                    account_code=self.new_account_code_var.get(),
                    account_name=self.new_account_name_var.get(),
                    category=self.new_category_var.get(),
                    fiscal_year=self.new_fiscal_year_var.get(),
                    yearly_budget=yearly_budget,
                    monthly_budget=monthly_budget,
                ),
            )
        except Exception as exc:
            messagebox.showerror("Add failed", str(exc))
            return
        messagebox.showinfo("Account added", "New financial account created.")
        self.new_account_code_var.set("")
        self.refresh_month()

    def delete_account(self) -> None:
        account_code = self.account_var.get().strip()
        if not account_code:
            messagebox.showerror("No account", "Select or enter an account code first.")
            return
        confirm = messagebox.askyesno(
            "Delete account",
            f"Delete account {account_code}? This only works for inactive accounts.",
        )
        if not confirm:
            return
        try:
            delete_financial_account(self.db_path, account_code)
        except Exception as exc:
            messagebox.showerror("Delete failed", str(exc))
            return
        messagebox.showinfo("Deleted", "Account deleted.")
        self.account_var.set("")
        self.refresh_month()

    def create_next_fiscal_year(self) -> None:
        source_year = self.year_var.get().strip()
        target_year = self.next_fiscal_year_var.get().strip()
        if not source_year or not target_year:
            messagebox.showerror("Missing year", "Choose the current year and enter the next fiscal year.")
            return
        confirm = messagebox.askyesno(
            "Create next fiscal year",
            f"Create fiscal year {target_year} from fiscal year {source_year}?\n\nThis keeps the old year intact and creates 12 new month rows.",
        )
        if not confirm:
            return
        try:
            inserted_rows = create_new_fiscal_year(self.db_path, source_year, target_year)
        except Exception as exc:
            messagebox.showerror("Year setup failed", str(exc))
            return
        self.year_var.set(target_year)
        self.month_var.set("1")
        self.refresh_month()
        messagebox.showinfo(
            "Fiscal year created",
            f"Fiscal year {target_year} was created with {inserted_rows} monthly account rows.",
        )

    def create_monthly_report(self) -> None:
        self.create_monthly_report_pdf()

    def create_monthly_report_pdf(self) -> None:
        month = int(self.month_var.get())
        year = self.year_var.get().strip()
        output_dir = self.db_path.parent / "generated_reports"
        try:
            pdf_output = render_monthly_financial_report_pdf(self.db_path, month, year, output_dir)
        except Exception as exc:
            messagebox.showerror("Report failed", str(exc))
            return
        self._open_created_file(pdf_output, "Monthly report preview failed")

    def create_transaction_log(self) -> None:
        self.create_transaction_log_pdf()

    def create_transaction_log_pdf(self) -> None:
        month = int(self.month_var.get())
        year = self.year_var.get().strip()
        output_dir = self.db_path.parent / "generated_reports"
        try:
            pdf_output = render_transaction_log_pdf(self.db_path, month, year, output_dir)
        except Exception as exc:
            messagebox.showerror("Report failed", str(exc))
            return
        self._open_created_file(pdf_output, "Transaction log preview failed")

    def create_budget_report_pdf(self) -> None:
        output_dir = self.db_path.parent / "generated_reports"
        year = self.year_var.get().strip()
        try:
            pdf_output = render_budget_report_pdf(self.db_path, year, output_dir)
        except Exception as exc:
            messagebox.showerror("Report failed", str(exc))
            return
        self._open_created_file(pdf_output, "Budget report preview failed")

    def create_year_end_report(self) -> None:
        self.create_year_end_report_pdf()

    def create_year_end_report_pdf(self) -> None:
        output_dir = self.db_path.parent / "generated_reports"
        year = self.year_var.get().strip()
        try:
            pdf_output = render_year_end_financial_report_pdf(self.db_path, year, output_dir)
        except Exception as exc:
            messagebox.showerror("Report failed", str(exc))
            return
        self._open_created_file(pdf_output, "Year-end report preview failed")

    def post_transaction(self) -> None:
        self._post_transaction_common(earlier_mode=False)

    def post_earlier_transaction(self) -> None:
        self._post_transaction_common(earlier_mode=True)

    def _post_transaction_common(self, earlier_mode: bool) -> None:
        try:
            amount = float(self.amount_var.get())
        except ValueError:
            messagebox.showerror("Invalid amount", "Enter a valid amount.")
            return

        request = FinancialTransactionRequest(
            account_code=self.account_var.get().strip().upper(),
            month_number=int(self.month_var.get()),
            transaction_date=self.date_var.get().strip(),
            transaction_type=self.type_var.get().strip(),
            amount=amount,
            payee=self.payee_var.get().strip(),
            memo=self.memo_var.get().strip(),
            reference_number=self.reference_var.get().strip(),
            check_number=self.check_var.get().strip(),
        )
        if earlier_mode:
            confirm = messagebox.askyesno(
                "Record earlier transaction",
                "\n".join(
                    [
                        f"Fiscal year: {self.year_var.get().strip()}",
                        f"Fiscal month: {self.month_var.get()}",
                        f"Transaction date: {request.transaction_date}",
                        "",
                        "This will post an earlier-dated transaction into the selected fiscal period.",
                    ]
                ),
            )
            if not confirm:
                return
        try:
            transaction_number = post_financial_transaction(self.db_path, request)
        except Exception as exc:
            messagebox.showerror("Transaction failed", str(exc))
            return

        title = "Earlier transaction posted" if earlier_mode else "Transaction posted"
        messagebox.showinfo(title, f"Transaction #{transaction_number} was saved.")
        self.amount_var.set("")
        self.payee_var.set("")
        self.memo_var.set("")
        self.reference_var.set("")
        self.check_var.set("")
        self.refresh_month()

    def close_month(self) -> None:
        year = self.year_var.get().strip()
        month = int(self.month_var.get())
        confirm = messagebox.askyesno(
            "Close month",
            "\n".join(
                [
                    f"Close fiscal year {year}, month {month}?",
                    "",
                    "This will mark the selected month closed and roll balances into the next fiscal period.",
                ]
            ),
        )
        if not confirm:
            return
        try:
            result = close_financial_month(self.db_path, year, month)
        except Exception as exc:
            messagebox.showerror("Close month failed", str(exc))
            return
        self.year_var.set(result.next_year)
        self.month_var.set(str(result.next_month))
        self.refresh_month()
        messagebox.showinfo(
            "Month closed",
            "\n".join(
                [
                    f"Closed: {result.closed_year} month {result.closed_month}",
                    f"Next active period: {result.next_year} month {result.next_month}",
                    f"Accounts rolled forward: {result.accounts_updated}",
                ]
            ),
        )
