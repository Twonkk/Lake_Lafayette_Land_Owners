from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from src.db.connection import initialize_database
from src.db.repositories import OwnerRepository
from src.runtime import (
    APP_NAME,
    APP_VERSION,
    bootstrap_existing_local_database,
    ensure_runtime_dirs,
    resolve_app_paths,
    save_legacy_dir,
)
from src.services.import_service import (
    backfill_financial_import_if_empty,
    database_has_core_data,
    run_legacy_import,
    validate_legacy_directory,
)
from src.ui.assessments import AssessmentsFrame
from src.ui.cards_stickers import CardsStickersFrame
from src.ui.dashboard import DashboardFrame
from src.ui.financials import FinancialsFrame
from src.ui.import_setup import ImportSetupFrame
from src.ui.lien_collection import LienCollectionFrame
from src.ui.notices import NoticesFrame
from src.ui.owner_lot import OwnerLotFrame
from src.ui.payment_history import PaymentHistoryFrame
from src.ui.payments import PaymentsFrame
from src.ui.property_sales import PropertySalesFrame
from src.ui.reports import ReportsFrame
from src.ui.utilities import UtilitiesFrame


APP_TITLE = APP_NAME
APP_SIZE = "1280x800"


class LakeLotApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(APP_SIZE)
        self.minsize(1100, 700)

        self.paths = resolve_app_paths()
        ensure_runtime_dirs(self.paths)
        bootstrap_existing_local_database(self.paths)
        self.base_dir = self.paths.project_dir
        self.db_path = self.paths.db_path
        self.legacy_dir = self.paths.legacy_dir
        initialize_database(self.db_path)
        if self.legacy_dir.exists():
            backfill_financial_import_if_empty(self.legacy_dir, self.db_path)
        self.initial_setup_required = not database_has_core_data(self.db_path)
        self.owner_repository = OwnerRepository(self.db_path)
        self.screen_container: ttk.Frame | None = None
        self.sidebar: ttk.Frame | None = None
        self.screen_title_var = tk.StringVar(value="Modern desktop replacement")

        self.configure(background="#f3efe7")
        self.style = ttk.Style(self)
        self._configure_theme()
        self._build_shell()

    def _configure_theme(self) -> None:
        self.style.theme_use("clam")
        self.style.configure("App.TFrame", background="#f3efe7")
        self.style.configure(
            "Sidebar.TFrame",
            background="#1f3a5f",
        )
        self.style.configure(
            "Sidebar.TLabel",
            background="#1f3a5f",
            foreground="#ffffff",
            font=("TkDefaultFont", 12, "bold"),
        )
        self.style.configure(
            "Title.TLabel",
            background="#f3efe7",
            foreground="#1d2430",
            font=("TkDefaultFont", 24, "bold"),
        )
        self.style.configure(
            "CardTitle.TLabel",
            background="#ffffff",
            foreground="#1d2430",
            font=("TkDefaultFont", 12, "bold"),
        )
        self.style.configure(
            "Body.TLabel",
            background="#ffffff",
            foreground="#374151",
            font=("TkDefaultFont", 11),
        )
        self.style.configure(
            "Section.TLabel",
            background="#f3efe7",
            foreground="#1d2430",
            font=("TkDefaultFont", 13, "bold"),
        )
        self.style.configure(
            "Nav.TButton",
            background="#2f5d8c",
            foreground="#ffffff",
            padding=(12, 8),
        )

    def _build_shell(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        if self.sidebar is not None:
            self.sidebar.destroy()
        if self.screen_container is not None and self.screen_container.master is not None:
            self.screen_container.master.destroy()

        sidebar = ttk.Frame(self, style="Sidebar.TFrame", padding=24)
        sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar = sidebar
        content = ttk.Frame(self, style="App.TFrame", padding=24)
        content.grid(row=0, column=1, sticky="nsew")

        self.columnconfigure(0, weight=0, minsize=280)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)

        ttk.Label(sidebar, text="Lake Lot Manager", style="Sidebar.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
            pady=(0, 24),
        )
        ttk.Label(
            sidebar,
            text=f"v{APP_VERSION}",
            style="Sidebar.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(0, 18))

        if self.initial_setup_required:
            buttons = [("Initial Setup", self.show_import_setup)]
        else:
            buttons = [
                ("Dashboard", self.show_dashboard),
                ("Owners and Lots", self.show_owner_lot),
                ("Payments", self.show_payments),
                ("Property Sales", self.show_property_sales),
                ("Liens / Collection", self.show_liens_collection),
                ("Payment History", self.show_payment_history),
                ("Notices", self.show_notices),
                ("Assessments", self.show_assessments),
                ("Boat / ID Cards", self.show_cards_stickers),
                ("Financials", self.show_financials),
                ("Reports", self.show_reports),
                ("Utilities", self.show_utilities),
            ]

        for idx, (label, action) in enumerate(buttons, start=2):
            ttk.Button(sidebar, text=label, style="Nav.TButton", command=action).grid(
                row=idx,
                column=0,
                sticky="ew",
                pady=6,
            )

        header = ttk.Frame(content, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, textvariable=self.screen_title_var, style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        self.screen_container = ttk.Frame(content, style="App.TFrame")
        self.screen_container.grid(row=1, column=0, sticky="nsew")
        self.screen_container.columnconfigure(0, weight=1)
        self.screen_container.rowconfigure(0, weight=1)

        if self.initial_setup_required:
            self.show_import_setup()
        else:
            self.show_dashboard()

    def _set_screen(self, title: str, frame_factory) -> None:
        self.screen_title_var.set(title)
        if self.screen_container is None:
            return
        for child in self.screen_container.winfo_children():
            child.destroy()
        frame = frame_factory(self.screen_container)
        frame.grid(row=0, column=0, sticky="nsew")

    def show_dashboard(self) -> None:
        self._set_screen("Home", lambda parent: DashboardFrame(parent, self.db_path))

    def show_import_setup(self) -> None:
        self._set_screen(
            "Initial Setup",
            lambda parent: ImportSetupFrame(parent, self.legacy_dir, self.import_legacy_data),
        )

    def show_owner_lot(self) -> None:
        self._set_screen("Owners and Lots", lambda parent: OwnerLotFrame(parent, self.db_path))

    def show_payments(self) -> None:
        self._set_screen("Payments", lambda parent: PaymentsFrame(parent, self.db_path))

    def show_payment_history(self) -> None:
        self._set_screen(
            "Payment History",
            lambda parent: PaymentHistoryFrame(parent, self.db_path),
        )

    def show_property_sales(self) -> None:
        self._set_screen("Property Sales", lambda parent: PropertySalesFrame(parent, self.db_path))

    def show_liens_collection(self) -> None:
        self._set_screen("Liens / Collection", lambda parent: LienCollectionFrame(parent, self.db_path))

    def show_notices(self) -> None:
        self._set_screen("Notices", lambda parent: NoticesFrame(parent, self.db_path))

    def show_assessments(self) -> None:
        self._set_screen("Assessments", lambda parent: AssessmentsFrame(parent, self.db_path))

    def show_cards_stickers(self) -> None:
        self._set_screen("Boat / ID Cards", lambda parent: CardsStickersFrame(parent, self.db_path))

    def show_financials(self) -> None:
        self._set_screen("Financials", lambda parent: FinancialsFrame(parent, self.db_path))

    def show_reports(self) -> None:
        self._set_screen("Reports", lambda parent: ReportsFrame(parent, self.db_path))

    def show_utilities(self) -> None:
        self._set_screen(
            "Utilities",
            lambda parent: UtilitiesFrame(parent, self.db_path, self.refresh_from_legacy_data),
        )

    def show_placeholder(self) -> None:
        self._set_screen(
            "Coming next",
            lambda parent: DashboardFrame(parent),
        )

    def import_legacy_data(self, source_dir: Path | None = None) -> None:
        source_dir = (source_dir or self.legacy_dir).resolve()
        missing = validate_legacy_directory(source_dir)
        if missing:
            messagebox.showerror(
                "Legacy folder missing",
                "\n".join(
                    [
                        f"Could not use legacy folder:\n{source_dir}",
                        "",
                        "Missing required files:",
                        *missing,
                    ]
                ),
            )
            return

        try:
            result = run_legacy_import(source_dir, self.db_path)
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))
            return

        self.initial_setup_required = False
        self.legacy_dir = source_dir
        save_legacy_dir(self.paths.update_config_path, source_dir)
        self._build_shell()
        messagebox.showinfo(
            "Import complete",
            "\n".join(
                [
                    f"Database: {self.db_path}",
                    f"Source folder: {source_dir}",
                    f"Owners: {result.owners_imported}",
                    f"Lots: {result.lots_imported}",
                    f"Owner payments: {result.owner_payments_imported}",
                    f"Lot payments: {result.lot_payments_imported}",
                    f"Notes: {result.notes_imported}",
                    f"Financial accounts: {result.financial_accounts_imported}",
                    f"Financial monthly rows: {result.financial_monthly_imported}",
                    f"Financial transactions: {result.financial_transactions_imported}",
                ]
            ),
        )
        self.show_dashboard()

    def refresh_from_legacy_data(self) -> None:
        confirm = messagebox.askyesno(
            "Refresh From dBase",
            "This will re-import the current dBase data into the app database.\n\nUse this only while dBase is still the source of truth.",
        )
        if not confirm:
            return
        self.import_legacy_data(self.legacy_dir)


def launch() -> None:
    app = LakeLotApp()
    app.mainloop()
