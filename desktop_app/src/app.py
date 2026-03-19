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
    has_seen_screen_help,
    reset_seen_screen_help,
    resolve_app_paths,
    save_seen_screen_help,
    save_legacy_dir,
    open_with_default_app,
)
from src.services.help_service import get_screen_help
from src.services.import_service import (
    backfill_financial_import_if_empty,
    database_has_core_data,
    run_legacy_import,
    validate_legacy_directory,
)
from src.services.logging_service import get_logger
from src.services.update_service import check_for_updates, download_update_asset
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
        self.logger = get_logger("app")
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
        self.current_help_key: str | None = None

        self.configure(background="#f3efe7")
        self.style = ttk.Style(self)
        self._configure_theme()
        self._build_shell()
        self.logger.info("Main window initialized")

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
        sidebar.rowconfigure(100, weight=1)
        self.sidebar = sidebar
        content = ttk.Frame(self, style="App.TFrame", padding=24)
        content.grid(row=0, column=1, sticky="nsew")

        self.columnconfigure(0, weight=0, minsize=280)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)

        ttk.Label(sidebar, text=APP_NAME, style="Sidebar.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
            pady=(0, 24),
        )

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

        ttk.Label(
            sidebar,
            text=f"v{APP_VERSION}",
            style="Sidebar.TLabel",
        ).grid(row=101, column=0, sticky="sw", pady=(18, 0))

        header = ttk.Frame(content, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, textvariable=self.screen_title_var, style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(header, text="Help", command=self.show_current_help).grid(row=0, column=1, sticky="e")

        self.screen_container = ttk.Frame(content, style="App.TFrame")
        self.screen_container.grid(row=1, column=0, sticky="nsew")
        self.screen_container.columnconfigure(0, weight=1)
        self.screen_container.rowconfigure(0, weight=1)

        if self.initial_setup_required:
            self.show_import_setup()
        else:
            self.show_dashboard()

    def _set_screen(self, title: str, frame_factory, help_key: str | None = None) -> None:
        self.screen_title_var.set(title)
        self.current_help_key = help_key
        self.logger.info("Open screen: %s", title)
        if self.screen_container is None:
            return
        for child in self.screen_container.winfo_children():
            child.destroy()
        frame = frame_factory(self.screen_container)
        frame.grid(row=0, column=0, sticky="nsew")
        if help_key and not has_seen_screen_help(self.paths.update_config_path, help_key):
            self.after(150, lambda: self.show_help(help_key, first_time=True))

    def show_dashboard(self) -> None:
        self._set_screen("Home", lambda parent: DashboardFrame(parent, self.db_path), help_key="dashboard")

    def show_import_setup(self) -> None:
        self._set_screen(
            "Initial Setup",
            lambda parent: ImportSetupFrame(parent, self.legacy_dir, self.import_legacy_data),
            help_key="initial_setup",
        )

    def show_owner_lot(self) -> None:
        self._set_screen("Owners and Lots", lambda parent: OwnerLotFrame(parent, self.db_path), help_key="owners_lots")

    def show_payments(self) -> None:
        self._set_screen("Payments", lambda parent: PaymentsFrame(parent, self.db_path), help_key="payments")

    def show_payment_history(self) -> None:
        self._set_screen(
            "Payment History",
            lambda parent: PaymentHistoryFrame(parent, self.db_path),
            help_key="payment_history",
        )

    def show_property_sales(self) -> None:
        self._set_screen("Property Sales", lambda parent: PropertySalesFrame(parent, self.db_path), help_key="property_sales")

    def show_liens_collection(self) -> None:
        self._set_screen("Liens / Collection", lambda parent: LienCollectionFrame(parent, self.db_path), help_key="liens_collection")

    def show_notices(self) -> None:
        self._set_screen("Notices", lambda parent: NoticesFrame(parent, self.db_path), help_key="notices")

    def show_assessments(self) -> None:
        self._set_screen("Assessments", lambda parent: AssessmentsFrame(parent, self.db_path), help_key="assessments")

    def show_cards_stickers(self) -> None:
        self._set_screen("Boat / ID Cards", lambda parent: CardsStickersFrame(parent, self.db_path), help_key="cards_stickers")

    def show_financials(self) -> None:
        self._set_screen("Financials", lambda parent: FinancialsFrame(parent, self.db_path), help_key="financials")

    def show_reports(self) -> None:
        self._set_screen("Reports", lambda parent: ReportsFrame(parent, self.db_path), help_key="reports")

    def show_utilities(self) -> None:
        self._set_screen(
            "Utilities",
            lambda parent: UtilitiesFrame(
                parent,
                self.db_path,
                self.refresh_from_legacy_data,
                self.reset_screen_tutorials,
                self.open_log_folder,
                self.check_for_updates,
            ),
            help_key="utilities",
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
            self.logger.exception("Legacy import failed from %s", source_dir)
            messagebox.showerror("Import failed", str(exc))
            return

        self.logger.info(
            "Legacy import completed from %s: owners=%s lots=%s owner_payments=%s lot_payments=%s notes=%s",
            source_dir,
            result.owners_imported,
            result.lots_imported,
            result.owner_payments_imported,
            result.lot_payments_imported,
            result.notes_imported,
        )
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

    def show_current_help(self) -> None:
        if self.current_help_key:
            self.show_help(self.current_help_key, first_time=False)

    def reset_screen_tutorials(self) -> None:
        self.logger.info("Reset screen tutorials")
        reset_seen_screen_help(self.paths.update_config_path)

    def open_log_folder(self) -> None:
        try:
            open_with_default_app(self.paths.logs_dir)
            self.logger.info("Opened log folder: %s", self.paths.logs_dir)
        except Exception as exc:
            self.logger.exception("Failed to open log folder")
            messagebox.showerror(
                "Open log folder failed",
                "\n".join(
                    [
                        "The log folder could not be opened automatically.",
                        str(self.paths.logs_dir),
                        "",
                        str(exc),
                    ]
                ),
            )

    def check_for_updates(self) -> None:
        try:
            result = check_for_updates(self.paths.update_config_path)
            self.logger.info(
                "Update check complete: current=%s latest=%s available=%s",
                result.current_version,
                result.latest_version,
                result.update_available,
            )
        except Exception as exc:
            self.logger.exception("Update check failed")
            messagebox.showerror("Update check failed", str(exc))
            return

        if not result.update_available:
            messagebox.showinfo(
                "No update available",
                "\n".join(
                    [
                        f"Current version: v{result.current_version}",
                        f"Latest version: v{result.latest_version}",
                        "",
                        "This install is already up to date.",
                    ]
                ),
            )
            return

        if result.installer_asset is None:
            messagebox.showerror(
                "Update unavailable",
                "\n".join(
                    [
                        f"Version v{result.latest_version} is available, but no Windows installer was found in the release assets.",
                        result.release_page_url,
                    ]
                ),
            )
            return

        confirm = messagebox.askyesno(
            "Update available",
            "\n".join(
                [
                    f"Current version: v{result.current_version}",
                    f"Latest version: v{result.latest_version}",
                    f"Installer: {result.installer_asset.name}",
                    "",
                    "Download the new installer now?",
                ]
            ),
        )
        if not confirm:
            return

        try:
            installer_path = download_update_asset(result.installer_asset, self.paths.updates_dir)
            self.logger.info("Downloaded update installer: %s", installer_path)
        except Exception as exc:
            self.logger.exception("Update download failed")
            messagebox.showerror("Update download failed", str(exc))
            return

        try:
            open_with_default_app(installer_path)
        except Exception as exc:
            self.logger.exception("Failed to launch downloaded installer")
            messagebox.showerror(
                "Installer launch failed",
                "\n".join(
                    [
                        "The installer was downloaded, but it could not be opened automatically.",
                        str(installer_path),
                        "",
                        str(exc),
                    ]
                ),
            )
            return

        messagebox.showinfo(
            "Update ready",
            "\n".join(
                [
                    f"The installer was downloaded to:",
                    str(installer_path),
                    "",
                    "Close the app before completing the update if the installer asks for it.",
                ]
            ),
        )

    def report_callback_exception(self, exc, val, tb) -> None:
        self.logger.error(
            "Tkinter callback exception",
            exc_info=(exc, val, tb),
        )
        messagebox.showerror(
            "Unexpected error",
            "\n".join(
                [
                    "The app hit an unexpected error.",
                    "A log entry was written to the log folder for support review.",
                ]
            ),
        )

    def show_help(self, help_key: str, first_time: bool) -> None:
        help_info = get_screen_help(help_key)
        if help_info is None:
            return

        dialog = tk.Toplevel(self)
        dialog.title(f"{help_info.title} Help")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(background="#f3efe7")
        dialog.resizable(False, False)

        body = ttk.Frame(dialog, style="App.TFrame", padding=18)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)

        ttk.Label(body, text=help_info.title, style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        summary = tk.Label(
            body,
            text=help_info.summary,
            background="#f3efe7",
            foreground="#1d2430",
            justify="left",
            anchor="w",
            wraplength=460,
            font=("TkDefaultFont", 11),
        )
        summary.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        for idx, line in enumerate(help_info.actions, start=2):
            bullet = tk.Label(
                body,
                text=f"- {line}",
                background="#f3efe7",
                foreground="#374151",
                justify="left",
                anchor="w",
                wraplength=460,
                font=("TkDefaultFont", 10),
            )
            bullet.grid(row=idx, column=0, sticky="ew", pady=(0, 4))

        dont_show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            body,
            text="Don't show this again for this screen",
            variable=dont_show_var,
        ).grid(row=len(help_info.actions) + 2, column=0, sticky="w", pady=(12, 10))

        def close_dialog() -> None:
            if first_time or dont_show_var.get():
                save_seen_screen_help(self.paths.update_config_path, help_key, True)
            dialog.destroy()

        ttk.Button(body, text="Close", command=close_dialog).grid(row=len(help_info.actions) + 3, column=0, sticky="e")


def launch() -> None:
    app = LakeLotApp()
    app.mainloop()
