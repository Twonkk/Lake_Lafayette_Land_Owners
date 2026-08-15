from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk


@dataclass(frozen=True, slots=True)
class ClassicMenuItem:
    number: int
    label: str
    destination: str


@dataclass(frozen=True, slots=True)
class ClassicMenuGroup:
    number: int
    title: str
    items: tuple[ClassicMenuItem, ...]


CLASSIC_MENU_GROUPS = (
    ClassicMenuGroup(
        number=1,
        title="Owners, Property, and Assessments",
        items=(
            ClassicMenuItem(1, "Revise or Review Owner / Lot", "owners_lots"),
            ClassicMenuItem(2, "Record Assessment Payment", "payments"),
            ClassicMenuItem(3, "Post a New Assessment", "assessments"),
            ClassicMenuItem(4, "Print Assessment Notices", "notices"),
            ClassicMenuItem(5, "Record Property Sale / Purchase", "property_sales"),
            ClassicMenuItem(6, "Reverse a Property Sale", "property_sales"),
            ClassicMenuItem(7, "Print Reports", "reports"),
            ClassicMenuItem(8, "File or Remove Liens", "liens_collection"),
            ClassicMenuItem(9, "Assign Accounts to Collection", "liens_collection"),
            ClassicMenuItem(10, "Display History Records", "payment_history"),
            ClassicMenuItem(11, "Record Boat Sticker Purchase", "cards_stickers"),
            ClassicMenuItem(12, "Issue ID Cards", "cards_stickers"),
            ClassicMenuItem(13, "Print Mailing Labels", "reports"),
        ),
    ),
    ClassicMenuGroup(
        number=2,
        title="Financial Records",
        items=(
            ClassicMenuItem(1, "Enter Transaction Data", "financials"),
            ClassicMenuItem(2, "Enter or Revise Budget Data", "financials"),
            ClassicMenuItem(3, "Print Monthly Financial Report", "financials"),
            ClassicMenuItem(4, "Print Budget", "financials"),
            ClassicMenuItem(5, "Display Transaction Data", "financials"),
            ClassicMenuItem(6, "Print Transaction Log", "financials"),
            ClassicMenuItem(7, "Close a Month", "financials"),
            ClassicMenuItem(8, "Add, Delete, or Rename Account", "financials"),
            ClassicMenuItem(9, "Record an Earlier Transaction", "financials"),
            ClassicMenuItem(10, "Print Year-End Summary", "financials"),
        ),
    ),
    ClassicMenuGroup(
        number=3,
        title="Utilities and Administration",
        items=(
            ClassicMenuItem(1, "Maintain or Refresh Records", "utilities"),
            ClassicMenuItem(2, "Run Data Health Checks", "utilities"),
        ),
    ),
)


class ClassicMenuFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, navigate: Callable[[str], None]) -> None:
        super().__init__(parent, style="App.TFrame")
        self.navigate = navigate
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build()

    def _build(self) -> None:
        intro = tk.Label(
            self,
            text=(
                "The familiar dBase menu, now point-and-click. The original group and option "
                "numbers are kept so you can use the same routine you already know."
            ),
            background="#e7f1fb",
            foreground="#183b62",
            anchor="w",
            justify="left",
            wraplength=920,
            padx=14,
            pady=8,
            font=("TkDefaultFont", 11),
        )
        intro.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        groups = ttk.Frame(self, style="App.TFrame")
        groups.grid(row=1, column=0, sticky="nsew")
        groups.rowconfigure(0, weight=1)
        for column in range(len(CLASSIC_MENU_GROUPS)):
            groups.columnconfigure(column, weight=1, uniform="classic_groups")

        for column, group in enumerate(CLASSIC_MENU_GROUPS):
            group_frame = ttk.LabelFrame(
                groups,
                text=f"Group {group.number} — {group.title}",
                padding=8,
            )
            group_frame.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0, 10 if column < len(CLASSIC_MENU_GROUPS) - 1 else 0),
            )
            group_frame.columnconfigure(0, weight=1)

            for row, item in enumerate(group.items):
                ttk.Button(
                    group_frame,
                    text=f"{item.number}.  {item.label}",
                    style="Classic.TButton",
                    command=lambda destination=item.destination: self.navigate(destination),
                ).grid(row=row, column=0, sticky="ew", pady=(0, 3))

            if group.number == 3:
                reminder = ttk.Label(
                    group_frame,
                    text=(
                        "Legacy note: Reindex All Files is no longer required. "
                        "Utilities provides safe refresh and record checks instead."
                    ),
                    wraplength=260,
                    justify="left",
                )
                reminder.grid(row=len(group.items), column=0, sticky="ew", pady=(10, 0))
