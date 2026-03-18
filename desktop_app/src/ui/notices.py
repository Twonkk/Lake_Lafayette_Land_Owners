import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from src.db.repositories import NoticeRepository
from src.runtime import open_with_default_app
from src.services.notice_service import (
    build_notice_batches,
    build_notice_file_stem,
    convert_notice_html_to_pdf,
    owner_display_name,
    owner_has_collection_lots,
    owner_notice_total,
    render_notice_html,
    should_omit_notice,
)


class NoticesFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, db_path: Path) -> None:
        super().__init__(parent, style="App.TFrame")
        self.repository = NoticeRepository(db_path)
        self.search_var = tk.StringVar()
        self.batch_size_var = tk.StringVar(value="100")
        self.mode_var = tk.StringVar(value="all")
        self.notice_owners = []
        self.filtered_owners = []
        self.output_dir = db_path.parent / "generated_notices"

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self._build()
        self.refresh_candidates()

    def _build(self) -> None:
        intro = ttk.Label(
            self,
            text="Prepare assessment notice runs. This matches the legacy choices for individual, all-owner, and lien-only notice batches.",
        )
        intro.grid(row=0, column=0, sticky="w", pady=(0, 10))

        controls = ttk.Frame(self, style="App.TFrame")
        controls.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(5, weight=1)

        ttk.Label(controls, text="Search").grid(row=0, column=0, sticky="w", padx=(0, 8))
        search = ttk.Entry(controls, textvariable=self.search_var)
        search.grid(row=0, column=1, sticky="ew", padx=(0, 12))
        search.bind("<Return>", self.refresh_candidates)

        ttk.Label(controls, text="Batch size").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Entry(controls, textvariable=self.batch_size_var, width=8).grid(
            row=0, column=3, sticky="w", padx=(0, 12)
        )

        ttk.Label(controls, text="Mode").grid(row=0, column=4, sticky="w", padx=(0, 8))
        mode = ttk.Combobox(
            controls,
            textvariable=self.mode_var,
            values=["individual", "all", "liens"],
            state="readonly",
            width=14,
        )
        mode.grid(row=0, column=5, sticky="w", padx=(0, 12))
        mode.bind("<<ComboboxSelected>>", self.refresh_candidates)

        ttk.Button(controls, text="Refresh", command=self.refresh_candidates).grid(
            row=0, column=6, sticky="w"
        )

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

        ttk.Label(left, text="Notice candidates", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        self.owner_tree = ttk.Treeview(
            left,
            columns=("owner_code", "name", "lots", "notice_total", "lien", "omit"),
            show="headings",
        )
        for name, width in [
            ("owner_code", 85),
            ("name", 220),
            ("lots", 55),
            ("notice_total", 100),
            ("lien", 55),
            ("omit", 60),
        ]:
            self.owner_tree.heading(name, text=name.replace("_", " ").title())
            self.owner_tree.column(name, width=width, anchor="w")
        self.owner_tree.grid(row=1, column=0, sticky="nsew")
        self.owner_tree.bind("<<TreeviewSelect>>", self._on_select_owner)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.owner_tree.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.owner_tree.configure(yscrollcommand=scroll.set)

        ttk.Label(right, text="Notice preview", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        self.preview_text = tk.Text(
            right,
            wrap="word",
            relief="flat",
            background="#ffffff",
            foreground="#1d2430",
            font=("TkDefaultFont", 11),
            padx=16,
            pady=16,
        )
        self.preview_text.grid(row=1, column=0, sticky="nsew")
        self.preview_text.configure(state="disabled")

        self.summary_label = ttk.Label(self, text="")
        self.summary_label.grid(row=3, column=0, sticky="w", pady=(12, 0))

        actions = ttk.Frame(self, style="App.TFrame")
        actions.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="Open Selected PDF", command=self.pdf_selected_notice).grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Button(actions, text="Open Batch PDFs", command=self.pdf_batch_run).grid(
            row=0, column=1, sticky="w"
        )

    def refresh_candidates(self, _event: object | None = None) -> None:
        self.notice_owners = self.repository.list_notice_candidates(self.search_var.get())
        mode = self.mode_var.get()
        lien_only = mode == "liens"

        if mode == "individual" and self.search_var.get().strip():
            candidates = [
                owner
                for owner in self.notice_owners
                if not should_omit_notice(owner, lien_only=False)
            ]
        else:
            candidates = [
                owner
                for owner in self.notice_owners
                if not should_omit_notice(owner, lien_only=lien_only)
            ]

        self.filtered_owners = candidates
        self.owner_tree.delete(*self.owner_tree.get_children())
        for owner in candidates:
            omit = "Y" if should_omit_notice(owner, lien_only=lien_only) else ""
            self.owner_tree.insert(
                "",
                "end",
                iid=owner.owner_code,
                values=(
                    owner.owner_code,
                    owner_display_name(owner),
                    len(owner.lots),
                    f"${owner_notice_total(owner):,.2f}",
                    owner.lien_flag,
                    omit,
                ),
            )

        try:
            batch_size = int(self.batch_size_var.get())
        except ValueError:
            batch_size = 100
        batches = build_notice_batches(candidates, max(batch_size, 1)) if candidates else []
        self.summary_label.configure(
            text=(
                f"{len(candidates)} notice candidates in {len(batches)} batch(es). "
                f"Mode: {mode}."
            )
        )

        children = self.owner_tree.get_children()
        if children:
            self.owner_tree.selection_set(children[0])
            self._show_preview(children[0])
        else:
            self._set_preview("No matching notice candidates found.")

    def _on_select_owner(self, _event: object | None = None) -> None:
        selected = self.owner_tree.selection()
        if selected:
            self._show_preview(selected[0])

    def _show_preview(self, owner_code: str) -> None:
        owner = next((item for item in self.filtered_owners if item.owner_code == owner_code), None)
        if owner is None:
            self._set_preview("Owner preview not found.")
            return

        lines = [
            f"Owner code: {owner.owner_code}",
            f"Name: {owner_display_name(owner)}",
            f"Address: {owner.address}",
            f"City/State/ZIP: {owner.city}, {owner.state} {owner.zip_code}".strip(),
            f"Notice total: ${owner_notice_total(owner):,.2f}",
            f"Lien flag: {owner.lien_flag or 'N'}",
            "",
            "Lots:",
        ]

        has_freeze = any(lot.freeze_flag == "Y" for lot in owner.lots)
        for lot in owner.lots:
            total_display = lot.current_assessment if has_freeze else lot.total_due
            marker = "**" if owner_has_collection_lots(owner) and lot.collection_flag == "Y" else ""
            lines.append(
                f"  {lot.lot_number} {marker} delinquent ${lot.delinquent_assessment:,.2f} "
                f"interest ${lot.delinquent_interest + lot.current_interest:,.2f} "
                f"current ${lot.current_assessment:,.2f} total ${total_display:,.2f}"
            )

        if has_freeze:
            lines.append("")
            lines.append("Freeze note: This owner has a freeze on at least one lot. Legacy notices show the current assessment total in that case.")
        if owner_has_collection_lots(owner):
            lines.append("")
            lines.append("Collection note: Lots marked with ** are in collection / county-taken status and need the special warning text from the legacy notices.")

        self._set_preview("\n".join(lines))

    def _set_preview(self, text: str) -> None:
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.preview_text.configure(state="disabled")

    def _season_label(self) -> str:
        return "Temporary Notice Layout"

    def _open_created_file(self, path: Path, title: str, detail_lines: list[str]) -> None:
        try:
            open_with_default_app(path)
        except Exception as exc:
            detail_lines.extend(["", "Preview could not be opened automatically.", str(exc)])
            messagebox.showerror(title, "\n".join(detail_lines))

    def _render_notice_pdf(self, owners: list[object], season_label: str, file_stem: str) -> Path:
        html_output = render_notice_html(
            owners=owners,
            output_dir=self.output_dir,
            season_label=season_label,
            file_stem=file_stem,
        )
        try:
            return convert_notice_html_to_pdf(html_output)
        finally:
            html_output.unlink(missing_ok=True)

    def pdf_selected_notice(self) -> None:
        selected = self.owner_tree.selection()
        if not selected:
            messagebox.showerror("No selection", "Select one owner notice first.")
            return
        owner = next((item for item in self.filtered_owners if item.owner_code == selected[0]), None)
        if owner is None:
            messagebox.showerror("Missing owner", "The selected owner could not be found.")
            return
        try:
            pdf_output = self._render_notice_pdf(
                owners=[owner],
                season_label=self._season_label(),
                file_stem=build_notice_file_stem(owner),
            )
        except Exception as exc:
            messagebox.showerror("PDF creation failed", str(exc))
            return
        self._open_created_file(
            pdf_output,
            "Notice PDF failed",
            ["PDF saved to:", str(pdf_output)],
        )

    def pdf_batch_run(self) -> None:
        if not self.filtered_owners:
            messagebox.showerror("No notices", "There are no current notice candidates to export.")
            return
        try:
            batch_size = int(self.batch_size_var.get())
        except ValueError:
            messagebox.showerror("Invalid batch size", "Batch size must be a whole number.")
            return
        batches = build_notice_batches(self.filtered_owners, max(batch_size, 1))
        if not batches:
            messagebox.showerror("No batches", "No notice batches could be created.")
            return
        first_batch = batches[0]
        created_files: list[str] = []
        try:
            for owner in first_batch.owners:
                pdf_output = self._render_notice_pdf(
                    owners=[owner],
                    season_label=f"{self._season_label()} - Batch {first_batch.batch_number}",
                    file_stem=build_notice_file_stem(owner),
                )
                created_files.append(str(pdf_output))
        except Exception as exc:
            messagebox.showerror("PDF creation failed", str(exc))
            return
        if created_files:
            self._open_created_file(
                Path(created_files[0]),
                "Batch PDF preview failed",
                [
                    f"Batch {first_batch.batch_number}: {first_batch.start_name} to {first_batch.end_name}",
                    f"Created {len(created_files)} individual PDF files.",
                    "Example:",
                    created_files[0],
                ],
            )
            return
        messagebox.showerror("Batch PDF creation failed", "No PDF files were created.")
