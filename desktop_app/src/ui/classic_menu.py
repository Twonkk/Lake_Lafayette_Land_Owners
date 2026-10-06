from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk


MENU_SIDEBAR_LABEL = "Menu"


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
        self.content.rowconfigure(1, weight=1)
        self.content_window = self.canvas.create_window(
            (0, 0),
            window=self.content,
            anchor="nw",
        )
        self.content.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._resize_content)
        self.canvas.bind("<Enter>", lambda _event: self.canvas.focus_set())
        self.canvas.bind("<MouseWheel>", self._scroll_with_wheel)
        self.canvas.bind("<Button-4>", lambda _event: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda _event: self.canvas.yview_scroll(1, "units"))
        self.canvas.bind("<Prior>", lambda _event: self.canvas.yview_scroll(-1, "pages"))
        self.canvas.bind("<Next>", lambda _event: self.canvas.yview_scroll(1, "pages"))
        self._build(self.content)
        self._bind_scroll_controls(self.content)

    def _build(self, parent: ttk.Frame) -> None:
        self.intro = tk.Label(
            parent,
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
            font=("TkDefaultFont", 12),
        )
        self.intro.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        groups = ttk.Frame(parent, style="App.TFrame")
        groups.grid(row=1, column=0, sticky="nsew")
        groups.columnconfigure(0, weight=1, uniform="classic_groups")
        groups.columnconfigure(1, weight=1, uniform="classic_groups")

        placements = ((0, 0, 2), (0, 1, 1), (1, 1, 1))
        for group, (row, column, rowspan) in zip(CLASSIC_MENU_GROUPS, placements):
            group_frame = ttk.LabelFrame(
                groups,
                text=f"Group {group.number} — {group.title}",
                padding=10,
            )
            padx = (0, 7) if column == 0 else (7, 0)
            pady = (0, 0) if group.number == 1 else ((0, 7) if group.number == 2 else (7, 0))
            group_frame.grid(
                row=row,
                column=column,
                rowspan=rowspan,
                sticky="nsew",
                padx=padx,
                pady=pady,
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

    def _update_scroll_region(self, _event: tk.Event | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _bind_scroll_controls(self, widget: tk.Misc) -> None:
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

    def _resize_content(self, event: tk.Event) -> None:
        self.intro.configure(wraplength=max(event.width - 28, 320))
        requested_height = self.content.winfo_reqheight()
        self.canvas.itemconfigure(
            self.content_window,
            width=event.width,
            height=max(event.height, requested_height),
        )

    def _scroll_with_wheel(self, event: tk.Event) -> str:
        direction = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(direction * 3, "units")
        return "break"
