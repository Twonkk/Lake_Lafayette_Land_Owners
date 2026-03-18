import tkinter as tk
from pathlib import Path
from tkinter import ttk

from src.services.dashboard_service import load_dashboard_snapshot


class DashboardFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, db_path: Path) -> None:
        super().__init__(parent, style="App.TFrame")
        self.db_path = db_path
        self.columnconfigure(0, weight=1)
        self._build()

    def _build(self) -> None:
        snapshot = load_dashboard_snapshot(self.db_path)

        ttk.Label(
            self,
            text="Home",
            style="Title.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        intro = tk.Label(
            self,
            text="Use this screen to see what needs attention and jump into the main workflows.",
            background="#f3efe7",
            foreground="#273142",
            anchor="w",
            justify="left",
            font=("TkDefaultFont", 11),
        )
        intro.grid(row=1, column=0, sticky="ew", pady=(0, 16))

        cards = ttk.Frame(self, style="App.TFrame")
        cards.grid(row=2, column=0, sticky="ew")
        for index in range(len(snapshot.metrics)):
            cards.columnconfigure(index % 3, weight=1)

        for idx, metric in enumerate(snapshot.metrics):
            row = idx // 3
            col = idx % 3
            card = tk.Frame(cards, background="#ffffff", bd=0, highlightthickness=0)
            card.grid(row=row, column=col, sticky="nsew", padx=(0, 16 if col < 2 else 0), pady=(0, 16))
            ttk.Label(card, text=metric.title, style="CardTitle.TLabel").grid(
                row=0, column=0, sticky="w", padx=18, pady=(18, 8)
            )
            tk.Label(
                card,
                text=metric.value,
                background="#ffffff",
                foreground="#174a7c",
                font=("TkDefaultFont", 20, "bold"),
            ).grid(row=1, column=0, sticky="w", padx=18)
            ttk.Label(
                card,
                text=metric.detail,
                style="Body.TLabel",
                wraplength=260,
                justify="left",
            ).grid(row=2, column=0, sticky="w", padx=18, pady=(8, 18))

        lower = ttk.Frame(self, style="App.TFrame")
        lower.grid(row=3, column=0, sticky="nsew")
        lower.columnconfigure(0, weight=1)
        lower.columnconfigure(1, weight=1)

        alerts_card = tk.Frame(lower, background="#ffffff", bd=0, highlightthickness=0)
        alerts_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ttk.Label(alerts_card, text="Alerts", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w", padx=18, pady=(18, 10)
        )
        if snapshot.alerts:
            for idx, alert in enumerate(snapshot.alerts, start=1):
                tk.Label(
                    alerts_card,
                    text=alert.title,
                    background="#ffffff",
                    foreground="#8a2d1f",
                    font=("TkDefaultFont", 11, "bold"),
                    anchor="w",
                    justify="left",
                ).grid(row=idx * 2 - 1, column=0, sticky="ew", padx=18)
                tk.Label(
                    alerts_card,
                    text=alert.detail,
                    background="#ffffff",
                    foreground="#374151",
                    font=("TkDefaultFont", 11),
                    anchor="w",
                    justify="left",
                    wraplength=420,
                ).grid(row=idx * 2, column=0, sticky="ew", padx=18, pady=(0, 10))
        else:
            tk.Label(
                alerts_card,
                text="No current alerts.",
                background="#ffffff",
                foreground="#374151",
                font=("TkDefaultFont", 11),
            ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 18))

        activity_card = tk.Frame(lower, background="#ffffff", bd=0, highlightthickness=0)
        activity_card.grid(row=0, column=1, sticky="nsew")
        ttk.Label(activity_card, text="Recent Activity", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w", padx=18, pady=(18, 10)
        )
        for idx, activity in enumerate(snapshot.activities, start=1):
            tk.Label(
                activity_card,
                text=activity.title,
                background="#ffffff",
                foreground="#1d2430",
                font=("TkDefaultFont", 11, "bold"),
                anchor="w",
                justify="left",
            ).grid(row=idx * 2 - 1, column=0, sticky="ew", padx=18)
            tk.Label(
                activity_card,
                text=activity.detail,
                background="#ffffff",
                foreground="#374151",
                font=("TkDefaultFont", 11),
                anchor="w",
                justify="left",
                wraplength=420,
            ).grid(row=idx * 2, column=0, sticky="ew", padx=18, pady=(0, 10))
