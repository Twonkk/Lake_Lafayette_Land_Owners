from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.db.connection import get_connection


@dataclass(slots=True)
class DashboardMetric:
    title: str
    value: str
    detail: str


@dataclass(slots=True)
class DashboardAlert:
    title: str
    detail: str


@dataclass(slots=True)
class DashboardActivity:
    title: str
    detail: str


@dataclass(slots=True)
class DashboardSnapshot:
    metrics: list[DashboardMetric]
    alerts: list[DashboardAlert]
    activities: list[DashboardActivity]


def load_dashboard_snapshot(db_path: Path) -> DashboardSnapshot:
    with get_connection(db_path) as connection:
        owners_due = connection.execute(
            "SELECT COUNT(*) FROM owners WHERE COALESCE(total_owed, 0) > 0"
        ).fetchone()[0]
        lots_due = connection.execute(
            "SELECT COUNT(*) FROM lots WHERE COALESCE(total_due, 0) > 0"
        ).fetchone()[0]
        total_due = connection.execute(
            "SELECT COALESCE(SUM(total_due), 0) FROM lots"
        ).fetchone()[0]
        lien_lots = connection.execute(
            "SELECT COUNT(*) FROM lots WHERE lien_flag = 'Y'"
        ).fetchone()[0]
        freeze_lots = connection.execute(
            "SELECT COUNT(*) FROM lots WHERE freeze_flag = 'Y'"
        ).fetchone()[0]
        recent_payments = connection.execute(
            """
            SELECT owner_code, lot_number, payment_amount, payment_date
            FROM payment_audit
            ORDER BY created_at DESC, id DESC
            LIMIT 5
            """
        ).fetchall()
        latest_assessment = connection.execute(
            """
            SELECT created_at, assessment_amount, lots_updated, owners_updated
            FROM assessment_runs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        lot_count_mismatches = connection.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT o.owner_code
                FROM owners o
                LEFT JOIN lots l ON l.owner_code = o.owner_code
                GROUP BY o.owner_code, o.number_lots
                HAVING COALESCE(o.number_lots, 0) <> COUNT(l.lot_number)
            )
            """
        ).fetchone()[0]

    metrics = [
        DashboardMetric(
            title="Owners With Balance Due",
            value=str(int(owners_due)),
            detail="Owners who currently owe money across one or more lots.",
        ),
        DashboardMetric(
            title="Lots With Balance Due",
            value=str(int(lots_due)),
            detail="Lots carrying a current total due balance.",
        ),
        DashboardMetric(
            title="Total Outstanding",
            value=f"${float(total_due or 0):,.2f}",
            detail="Current sum of all lot balances.",
        ),
        DashboardMetric(
            title="Lots With Liens",
            value=str(int(lien_lots)),
            detail="Lots currently marked with a lien.",
        ),
        DashboardMetric(
            title="Freeze Lots",
            value=str(int(freeze_lots)),
            detail="Lots under freeze/installment handling.",
        ),
    ]

    alerts: list[DashboardAlert] = []
    if int(lot_count_mismatches) > 0:
        alerts.append(
            DashboardAlert(
                title="Owner Lot-Count Mismatches",
                detail=f"{int(lot_count_mismatches)} owner records have a stored lot count that does not match the lot table.",
            )
        )
    if int(lien_lots) > 0:
        alerts.append(
            DashboardAlert(
                title="Lien Review Needed",
                detail=f"{int(lien_lots)} lots are flagged with liens.",
            )
        )
    if int(freeze_lots) > 0:
        alerts.append(
            DashboardAlert(
                title="Freeze Accounts Present",
                detail=f"{int(freeze_lots)} lots require freeze-aware handling for notices and assessments.",
            )
        )

    activities: list[DashboardActivity] = []
    for row in recent_payments:
        activities.append(
            DashboardActivity(
                title=f"Payment {row['payment_date'] or ''}",
                detail=f"Owner {row['owner_code']} lot {row['lot_number']} paid ${float(row['payment_amount'] or 0):,.2f}.",
            )
        )
    if latest_assessment is not None:
        activities.append(
            DashboardActivity(
                title="Latest Assessment Run",
                detail=(
                    f"{latest_assessment['created_at']}: "
                    f"${float(latest_assessment['assessment_amount'] or 0):,.2f} assessment, "
                    f"{int(latest_assessment['lots_updated'] or 0)} lots, "
                    f"{int(latest_assessment['owners_updated'] or 0)} owners."
                ),
            )
        )

    if not activities:
        activities.append(
            DashboardActivity(
                title="No Recent Activity",
                detail="Payments and assessment runs will show up here after they are posted.",
            )
        )

    return DashboardSnapshot(metrics=metrics, alerts=alerts, activities=activities)
