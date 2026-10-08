from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.units import inch

from src.db.connection import get_connection
from src.services.pdf_service import build_pdf_path, build_report_story, build_story_pdf, build_table


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
            WHERE UPPER(TRIM(COALESCE(o.current_flag, ''))) IN ('T', 'Y', 'TRUE')
              AND NOT EXISTS (
                  SELECT 1 FROM migration_review_decisions d
                  WHERE d.category = 'x_lot_exclusion'
                    AND d.record_key = o.owner_code
              )
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
            WHERE owner_code IS NULL
               OR TRIM(owner_code) = ''
               OR owner_code NOT IN (SELECT owner_code FROM owners)
            """
        ).fetchall()
        placeholder_owners = connection.execute(
            """
            SELECT owner_code, number_lots, total_owed
            FROM owners
            WHERE status = 'IMPORT REVIEW REQUIRED'
            ORDER BY owner_code
            """
        ).fetchall()
        owner_total_mismatches = connection.execute(
            """
            SELECT o.owner_code, o.total_owed, COALESCE(SUM(l.total_due), 0) AS actual_total
            FROM owners o
            LEFT JOIN lots l ON l.owner_code = o.owner_code
            WHERE NOT EXISTS (
                SELECT 1 FROM migration_review_decisions d
                WHERE d.category = 'owner_rounding'
                  AND d.record_key = o.owner_code
            )
            GROUP BY o.owner_code, o.total_owed
            HAVING ROUND(COALESCE(o.total_owed, 0), 2) <> ROUND(COALESCE(SUM(l.total_due), 0), 2)
            """
        ).fetchall()
        lot_component_mismatches = connection.execute(
            """
            SELECT lot_number, total_due,
                   COALESCE(delinquent_assessment, 0) + COALESCE(delinquent_interest, 0)
                   + COALESCE(current_assessment, 0) + COALESCE(current_interest, 0) AS component_total
            FROM lots
            WHERE ROUND(COALESCE(total_due, 0), 2) <> ROUND(
                COALESCE(delinquent_assessment, 0) + COALESCE(delinquent_interest, 0)
                + COALESCE(current_assessment, 0) + COALESCE(current_interest, 0), 2
            )
            """
        ).fetchall()

    return [
        UtilityCheckResult(
            title="Duplicate owner codes",
            issue_count=len(duplicate_owner_codes),
            details=[f"{row['owner_code']} ({row['cnt']})" for row in duplicate_owner_codes[:25]],
        ),
        UtilityCheckResult(
            title="Current-owner lot-count mismatches",
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
            title="Placeholder owners requiring migration review",
            issue_count=len(placeholder_owners),
            details=[
                f"{row['owner_code']}: {row['number_lots']} current lot(s), ${float(row['total_owed'] or 0):,.2f} due"
                for row in placeholder_owners[:25]
            ],
        ),
        UtilityCheckResult(
            title="Owner total mismatches",
            issue_count=len(owner_total_mismatches),
            details=[
                f"{row['owner_code']}: owner {float(row['total_owed'] or 0):,.2f}, lots {float(row['actual_total'] or 0):,.2f}"
                for row in owner_total_mismatches[:25]
            ],
        ),
        UtilityCheckResult(
            title="Lot balance-component mismatches",
            issue_count=len(lot_component_mismatches),
            details=[
                f"{row['lot_number']}: stored {float(row['total_due'] or 0):,.2f}, components {float(row['component_total'] or 0):,.2f}"
                for row in lot_component_mismatches[:25]
            ],
        ),
    ]


def render_migration_readiness_pdf(db_path: Path, output_dir: Path) -> Path:
    results = run_data_health_checks(db_path)
    total_issues = sum(result.issue_count for result in results)
    story = build_report_story(
        "Lake Lafayette Migration Readiness Report",
        [
            f"<b>Checks with items to review:</b> {sum(1 for result in results if result.issue_count)}",
            f"<b>Total review items:</b> {total_issues}",
            (
                "Items below come from the imported dBase backup. Review them with the "
                "client before final cutover; the app does not silently rewrite source records."
            ),
        ],
    )
    rows: list[list[object]] = [["Check", "Record / result"]]
    for result in results:
        if result.details:
            for index, detail in enumerate(result.details):
                rows.append(
                    [
                        f"{result.title}\n({result.issue_count} item{'s' if result.issue_count != 1 else ''})"
                        if index == 0
                        else "",
                        detail,
                    ]
                )
        else:
            rows.append([f"{result.title}\n(0 items)", "OK - no issues found"])
    story.append(
        build_table(
            rows,
            [2.2 * inch, 5.0 * inch],
            wrap_cells=True,
            column_alignments=["LEFT", "LEFT"],
            font_size=8.5,
        )
    )
    output_path = build_pdf_path(output_dir, "migration_readiness_report")
    return build_story_pdf(
        output_path,
        story,
        title="Migration Readiness Report",
        footer_text="Lake Lafayette Landowners Association - Migration Readiness",
    )
