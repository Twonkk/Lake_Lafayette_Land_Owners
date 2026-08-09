from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.db.connection import get_connection


@dataclass(slots=True)
class MigrationReconciliation:
    owners: int
    lots: int
    owner_lot_count_mismatches: int
    owner_total_mismatches: int
    lot_component_mismatches: int
    owner_total: float
    lot_total: float
    lot_component_total: float
    legacy_property_sales: int
    legacy_id_history: int
    legacy_collection_lots: int
    legacy_system_history: int

    @property
    def owner_lot_total_difference(self) -> float:
        return round(self.lot_total - self.owner_total, 2)

    @property
    def lot_component_difference(self) -> float:
        return round(self.lot_total - self.lot_component_total, 2)


def reconcile_migration(db_path: Path) -> MigrationReconciliation:
    """Return privacy-safe counts and totals for a migrated database."""
    with get_connection(db_path) as connection:
        owners = int(connection.execute("SELECT COUNT(*) FROM owners").fetchone()[0])
        lots = int(connection.execute("SELECT COUNT(*) FROM lots").fetchone()[0])
        lot_count_mismatches = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT o.owner_code
                    FROM owners o
                    LEFT JOIN lots l ON l.owner_code = o.owner_code
                    GROUP BY o.owner_code, o.number_lots
                    HAVING COALESCE(o.number_lots, 0) <> COUNT(l.lot_number)
                )
                """
            ).fetchone()[0]
        )
        owner_total_mismatches = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT o.owner_code
                    FROM owners o
                    LEFT JOIN lots l ON l.owner_code = o.owner_code
                    GROUP BY o.owner_code, o.total_owed
                    HAVING ROUND(COALESCE(o.total_owed, 0), 2)
                        <> ROUND(COALESCE(SUM(l.total_due), 0), 2)
                )
                """
            ).fetchone()[0]
        )
        lot_component_mismatches = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM lots
                WHERE ROUND(COALESCE(total_due, 0), 2) <> ROUND(
                    COALESCE(delinquent_assessment, 0)
                    + COALESCE(delinquent_interest, 0)
                    + COALESCE(current_assessment, 0)
                    + COALESCE(current_interest, 0), 2
                )
                """
            ).fetchone()[0]
        )

        def scalar(sql: str) -> float:
            return round(float(connection.execute(sql).fetchone()[0] or 0), 2)

        def count(table: str) -> int:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

        return MigrationReconciliation(
            owners=owners,
            lots=lots,
            owner_lot_count_mismatches=lot_count_mismatches,
            owner_total_mismatches=owner_total_mismatches,
            lot_component_mismatches=lot_component_mismatches,
            owner_total=scalar("SELECT SUM(total_owed) FROM owners"),
            lot_total=scalar("SELECT SUM(total_due) FROM lots"),
            lot_component_total=scalar(
                "SELECT SUM(COALESCE(delinquent_assessment, 0) + COALESCE(delinquent_interest, 0) "
                "+ COALESCE(current_assessment, 0) + COALESCE(current_interest, 0)) FROM lots"
            ),
            legacy_property_sales=count("legacy_property_sales"),
            legacy_id_history=count("legacy_id_history"),
            legacy_collection_lots=count("legacy_collection_lots"),
            legacy_system_history=count("legacy_system_history"),
        )
