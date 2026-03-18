import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.services.import_service import validate_legacy_directory


class ImportSetupFrame(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        default_legacy_dir: Path,
        on_import,
    ) -> None:
        super().__init__(parent, style="App.TFrame")
        self.on_import = on_import
        self.legacy_dir_var = tk.StringVar(value=str(default_legacy_dir))

        self.columnconfigure(0, weight=1)
        self._build()

    def _build(self) -> None:
        ttk.Label(
            self,
            text="Initial Setup",
            style="Section.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        intro = (
            "Before this app can be used, import the current dBase data from the office system. "
            "This should be done once during setup, then refreshed manually from Utilities while "
            "dBase is still the source of truth."
        )
        ttk.Label(self, text=intro, wraplength=760).grid(row=1, column=0, sticky="w", pady=(0, 16))

        picker = ttk.Frame(self, style="App.TFrame")
        picker.grid(row=2, column=0, sticky="ew", pady=(0, 16))
        picker.columnconfigure(1, weight=1)
        ttk.Label(picker, text="Legacy dBase folder").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(picker, textvariable=self.legacy_dir_var).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(picker, text="Browse", command=self.browse_folder).grid(row=0, column=2, sticky="w")

        self.status_text = tk.Text(
            self,
            wrap="word",
            relief="flat",
            background="#ffffff",
            foreground="#1d2430",
            font=("TkDefaultFont", 11),
            padx=16,
            pady=16,
            height=14,
        )
        self.status_text.grid(row=3, column=0, sticky="nsew")
        self.status_text.insert(
            "1.0",
            "\n".join(
                [
                    "Expected legacy files:",
                    "  ONERFILE.DBF",
                    "  ASMTFILE.DBF",
                    "  OPAYFILE.DBF",
                    "  LPAYFILE.DBF",
                    "  NOTEFILE.DBF",
                    "  STDBUDFL.DBF",
                    "  INEXFILE.DBF",
                    "  TRANSFIL.DBF",
                ]
            ),
        )
        self.status_text.configure(state="disabled")

        actions = ttk.Frame(self, style="App.TFrame")
        actions.grid(row=4, column=0, sticky="w", pady=(16, 0))
        ttk.Button(actions, text="Check Folder", command=self.check_folder).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Start Import", command=self.start_import).grid(row=0, column=1)

    def browse_folder(self) -> None:
        selected = filedialog.askdirectory(
            title="Select the legacy dBase folder",
            initialdir=self.legacy_dir_var.get() or None,
        )
        if selected:
            self.legacy_dir_var.set(selected)

    def _set_status(self, text: str) -> None:
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", text)
        self.status_text.configure(state="disabled")

    def check_folder(self) -> None:
        source_dir = Path(self.legacy_dir_var.get().strip())
        if not source_dir.exists():
            self._set_status(f"Folder not found:\n{source_dir}")
            return
        missing = validate_legacy_directory(source_dir)
        if missing:
            self._set_status(
                "\n".join(
                    [
                        f"Folder checked: {source_dir}",
                        "",
                        "Missing required files:",
                        *[f"  {name}" for name in missing],
                    ]
                )
            )
            return
        self._set_status(
            "\n".join(
                [
                    f"Folder checked: {source_dir}",
                    "",
                    "All required legacy files were found.",
                    "",
                    "You can start the initial import now.",
                ]
            )
        )

    def start_import(self) -> None:
        source_dir = Path(self.legacy_dir_var.get().strip())
        if not source_dir.exists():
            messagebox.showerror("Folder missing", f"Could not find:\n{source_dir}")
            return
        missing = validate_legacy_directory(source_dir)
        if missing:
            messagebox.showerror(
                "Missing legacy files",
                "\n".join(["The selected folder is missing required files:", *missing]),
            )
            return
        self.on_import(source_dir)
