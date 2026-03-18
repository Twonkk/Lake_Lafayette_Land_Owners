from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.db.connection import get_connection


@dataclass(slots=True)
class UtilityCheckResult:
    title: str
    issue_count: int
    details: list[str]


def run_data_health_checks(db_path: Path) -> list[UtilityCheckResult]:
    with get_connection(db_path) as connection:
        duplicate_owner_codes = connection.execute(
            """
            SELECT owner_code, COUNT(*) AS cnt
            FROM owners
            GROUP BY owner_code
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        owner_lot_mismatches = connection.execute(
            """
            SELECT o.owner_code, o.number_lots, COUNT(l.lot_number) AS actual_lots
            FROM owners o
            LEFT JOIN lots l ON l.owner_code = o.owner_code
            GROUP BY o.owner_code, o.number_lots
            HAVING COALESCE(o.number_lots, 0) <> COUNT(l.lot_number)
            """
        ).fetchall()
        duplicate_lot_numbers = connection.execute(
            """
            SELECT lot_number, COUNT(*) AS cnt
            FROM lots
            GROUP BY lot_number
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        orphan_lots = connection.execute(
            """
            SELECT lot_number, owner_code
            FROM lots
            WHERE owner_code IS NOT NULL
              AND owner_code <> ''
              AND owner_code NOT IN (SELECT owner_code FROM owners)
            """
        ).fetchall()
        owner_total_mismatches = connection.execute(
            """
            SELECT o.owner_code, o.total_owed, COALESCE(SUM(l.total_due), 0) AS actual_total
            FROM owners o
            LEFT JOIN lots l ON l.owner_code = o.owner_code
            GROUP BY o.owner_code, o.total_owed
            HAVING ROUND(COALESCE(o.total_owed, 0), 2) <> ROUND(COALESCE(SUM(l.total_due), 0), 2)
            """
        ).fetchall()

    return [
        UtilityCheckResult(
            title="Duplicate owner codes",
            issue_count=len(duplicate_owner_codes),
            details=[f"{row['owner_code']} ({row['cnt']})" for row in duplicate_owner_codes[:25]],
        ),
        UtilityCheckResult(
            title="Owner lot-count mismatches",
            issue_count=len(owner_lot_mismatches),
            details=[
                f"{row['owner_code']}: stored {row['number_lots']}, actual {row['actual_lots']}"
                for row in owner_lot_mismatches[:25]
            ],
        ),
        UtilityCheckResult(
            title="Duplicate lot numbers",
            issue_count=len(duplicate_lot_numbers),
            details=[f"{row['lot_number']} ({row['cnt']})" for row in duplicate_lot_numbers[:25]],
        ),
        UtilityCheckResult(
            title="Lots with missing owners",
            issue_count=len(orphan_lots),
            details=[f"{row['lot_number']} -> {row['owner_code']}" for row in orphan_lots[:25]],
        ),
        UtilityCheckResult(
            title="Owner total mismatches",
            issue_count=len(owner_total_mismatches),
            details=[
                f"{row['owner_code']}: owner {float(row['total_owed'] or 0):,.2f}, lots {float(row['actual_total'] or 0):,.2f}"
                for row in owner_total_mismatches[:25]
            ],
        ),
    ]
