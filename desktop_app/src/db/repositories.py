from pathlib import Path

from src.db.connection import get_connection
from src.services.notice_service import NoticeLotLine, NoticeOwner


class OwnerRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def search(self, query: str, limit: int = 5000) -> list[dict]:
        search_term = f"%{query.strip()}%" if query.strip() else "%"
        sql = """
            SELECT
                o.owner_code,
                o.last_name,
                o.first_name,
                o.address,
                o.city,
                o.state,
                o.zip,
                o.phone,
                o.total_owed,
                o.number_lots,
                o.primary_lot_number,
                COUNT(l.lot_number) AS lot_count
            FROM owners o
            LEFT JOIN lots l ON l.owner_code = o.owner_code
            WHERE
                o.owner_code LIKE ?
                OR o.last_name LIKE ?
                OR o.first_name LIKE ?
                OR o.primary_lot_number LIKE ?
                OR EXISTS (
                    SELECT 1
                    FROM lots l2
                    WHERE l2.owner_code = o.owner_code
                      AND l2.lot_number LIKE ?
                )
            GROUP BY
                o.owner_code,
                o.last_name,
                o.first_name,
                o.address,
                o.city,
                o.state,
                o.zip,
                o.phone,
                o.total_owed,
                o.number_lots,
                o.primary_lot_number
            ORDER BY o.last_name, o.first_name, o.owner_code
            LIMIT ?
        """
        params = [search_term, search_term, search_term, search_term, search_term, limit]
        with get_connection(self.db_path) as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_owner_detail(self, owner_code: str) -> dict | None:
        with get_connection(self.db_path) as connection:
            owner = connection.execute(
                """
                SELECT *
                FROM owners
                WHERE owner_code = ?
                """,
                [owner_code],
            ).fetchone()
            if owner is None:
                return None

            lots = connection.execute(
                """
                SELECT
                    lot_number,
                    total_due,
                    current_assessment,
                    delinquent_assessment,
                    delinquent_interest,
                    current_interest,
                    lien_flag,
                    collection_flag,
                    freeze_flag,
                    paid_through,
                    development_status,
                    lakefront_flag,
                    dock_flag,
                    appraised_value,
                    assessed_value,
                    previous_review_date,
                    last_review_date
                FROM lots
                WHERE owner_code = ?
                ORDER BY lot_number
                """,
                [owner_code],
            ).fetchall()

            notes = connection.execute(
                """
                SELECT note_text, review_date
                FROM notes
                WHERE owner_code = ?
                ORDER BY review_date DESC, id DESC
                LIMIT 10
                """,
                [owner_code],
            ).fetchall()

        return {
            "owner": dict(owner),
            "lots": [dict(row) for row in lots],
            "notes": [dict(row) for row in notes],
        }

    def counts(self) -> dict:
        with get_connection(self.db_path) as connection:
            owner_count = connection.execute("SELECT COUNT(*) FROM owners").fetchone()[0]
            lot_count = connection.execute("SELECT COUNT(*) FROM lots").fetchone()[0]
        return {"owners": owner_count, "lots": lot_count}

    def list_recent_property_sales(self, limit: int = 20) -> list[dict]:
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    s.created_at,
                    s.sale_date,
                    s.lot_number,
                    s.seller_owner_code,
                    s.buyer_owner_code,
                    ss.last_name AS seller_last_name,
                    ss.first_name AS seller_first_name,
                    bb.last_name AS buyer_last_name,
                    bb.first_name AS buyer_first_name
                FROM property_sales s
                LEFT JOIN owners ss ON ss.owner_code = s.seller_owner_code
                LEFT JOIN owners bb ON bb.owner_code = s.buyer_owner_code
                WHERE s.reversed_at IS NULL
                ORDER BY s.id DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()
        return [dict(row) for row in rows]

    def list_recent_property_sale_groups(self, limit: int = 50) -> list[dict]:
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    s.created_at,
                    s.sale_date,
                    s.seller_owner_code,
                    s.buyer_owner_code,
                    COUNT(*) AS lot_count,
                    GROUP_CONCAT(s.lot_number, ', ') AS lot_numbers,
                    MAX(COALESCE(s.new_buyer_flag, 'N')) AS new_buyer_flag,
                    ss.last_name AS seller_last_name,
                    ss.first_name AS seller_first_name,
                    bb.last_name AS buyer_last_name,
                    bb.first_name AS buyer_first_name
                FROM property_sales s
                LEFT JOIN owners ss ON ss.owner_code = s.seller_owner_code
                LEFT JOIN owners bb ON bb.owner_code = s.buyer_owner_code
                WHERE s.reversed_at IS NULL
                GROUP BY
                    s.created_at,
                    s.sale_date,
                    s.seller_owner_code,
                    s.buyer_owner_code,
                    ss.last_name,
                    ss.first_name,
                    bb.last_name,
                    bb.first_name
                ORDER BY s.created_at DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()
        return [dict(row) for row in rows]


class PaymentRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def search_history(self, query: str, limit: int = 500) -> list[dict]:
        search_term = f"%{query.strip()}%" if query.strip() else "%"
        sql = """
            SELECT
                p.id,
                p.created_at,
                p.payment_date,
                p.owner_code,
                p.lot_number,
                p.payment_amount,
                p.payment_form,
                p.check_number,
                p.note_text,
                p.previous_total_due,
                p.new_total_due,
                p.previous_owner_total,
                p.new_owner_total,
                p.backup_path,
                o.last_name,
                o.first_name
            FROM payment_audit p
            LEFT JOIN owners o ON o.owner_code = p.owner_code
            WHERE
                p.owner_code LIKE ?
                OR p.lot_number LIKE ?
                OR p.payment_date LIKE ?
                OR p.check_number LIKE ?
                OR o.last_name LIKE ?
                OR o.first_name LIKE ?
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT ?
        """
        params = [
            search_term,
            search_term,
            search_term,
            search_term,
            search_term,
            search_term,
            limit,
        ]
        with get_connection(self.db_path) as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_history_detail(self, audit_id: int) -> dict | None:
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT
                    p.*,
                    o.last_name,
                    o.first_name,
                    o.address,
                    o.city,
                    o.state,
                    o.zip
                FROM payment_audit p
                LEFT JOIN owners o ON o.owner_code = p.owner_code
                WHERE p.id = ?
                """,
                [audit_id],
            ).fetchone()
        return dict(row) if row is not None else None


class NoticeRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def list_notice_candidates(self, query: str = "") -> list[NoticeOwner]:
        search_term = f"%{query.strip()}%" if query.strip() else "%"
        sql = """
            SELECT
                o.owner_code,
                o.last_name,
                o.first_name,
                o.address,
                o.city,
                o.state,
                o.zip,
                o.total_owed,
                o.lien_flag,
                o.hold_mail_flag,
                o.current_flag,
                l.lot_number,
                l.delinquent_assessment,
                l.delinquent_interest,
                l.current_assessment,
                l.current_interest,
                l.total_due,
                l.collection_flag,
                l.freeze_flag
            FROM owners o
            LEFT JOIN lots l ON l.owner_code = o.owner_code
            WHERE
                o.owner_code LIKE ?
                OR o.last_name LIKE ?
                OR o.first_name LIKE ?
                OR l.lot_number LIKE ?
            ORDER BY o.last_name, o.first_name, o.owner_code, l.lot_number
        """
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                sql,
                [search_term, search_term, search_term, search_term],
            ).fetchall()

        owners: dict[str, NoticeOwner] = {}
        for row in rows:
            owner_code = row["owner_code"]
            if owner_code not in owners:
                owners[owner_code] = NoticeOwner(
                    owner_code=owner_code,
                    last_name=row["last_name"] or "",
                    first_name=row["first_name"] or "",
                    address=row["address"] or "",
                    city=row["city"] or "",
                    state=row["state"] or "",
                    zip_code=row["zip"] or "",
                    total_owed=float(row["total_owed"] or 0),
                    lien_flag=row["lien_flag"] or "",
                    hold_mail_flag=row["hold_mail_flag"] or "",
                    current_flag=row["current_flag"] or "",
                    lots=[],
                )
            if row["lot_number"]:
                owners[owner_code].lots.append(
                    NoticeLotLine(
                        lot_number=row["lot_number"],
                        delinquent_assessment=float(row["delinquent_assessment"] or 0),
                        delinquent_interest=float(row["delinquent_interest"] or 0),
                        current_assessment=float(row["current_assessment"] or 0),
                        current_interest=float(row["current_interest"] or 0),
                        total_due=float(row["total_due"] or 0),
                        collection_flag=row["collection_flag"] or "",
                        freeze_flag=row["freeze_flag"] or "",
                    )
                )
        return list(owners.values())


class FinancialRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def list_financial_years(self) -> list[str]:
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT fiscal_year
                FROM (
                    SELECT NULLIF(TRIM(fiscal_year), '') AS fiscal_year
                    FROM financial_monthly
                    UNION
                    SELECT NULLIF(TRIM(fiscal_year), '') AS fiscal_year
                    FROM financial_accounts
                    UNION
                    SELECT NULLIF(TRIM(fiscal_year), '') AS fiscal_year
                    FROM financial_transactions
                )
                WHERE fiscal_year IS NOT NULL
                ORDER BY fiscal_year DESC
                """
            ).fetchall()
        return [str(row["fiscal_year"]) for row in rows]

    def list_month_accounts(self, fiscal_month: int, fiscal_year: str) -> list[dict]:
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    a.account_code,
                    a.account_name,
                    a.category,
                    m.monthly_budget,
                    m.month_deposit,
                    m.month_expense,
                    m.year_to_date,
                    m.file_status
                FROM financial_accounts a
                LEFT JOIN financial_monthly m
                  ON m.account_code = a.account_code
                 AND COALESCE(m.fiscal_year, a.fiscal_year, '') = ?
                 AND m.fiscal_month = ?
                ORDER BY a.category, a.account_code
                """,
                [fiscal_year, fiscal_month],
            ).fetchall()
        return [dict(row) for row in rows]

    def list_month_transactions(self, fiscal_month: int, fiscal_year: str) -> list[dict]:
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM financial_transactions
                WHERE month_number = ?
                  AND COALESCE(fiscal_year, '') = ?
                ORDER BY CAST(transaction_number AS INTEGER), id
                """,
                [fiscal_month, fiscal_year],
            ).fetchall()
        return [dict(row) for row in rows]

    def month_summary(self, fiscal_month: int, fiscal_year: str) -> dict:
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS account_count,
                    COALESCE(SUM(month_deposit), 0) AS total_deposits,
                    COALESCE(SUM(month_expense), 0) AS total_expenses
                FROM financial_monthly
                WHERE fiscal_month = ?
                  AND COALESCE(fiscal_year, '') = ?
                """,
                [fiscal_month, fiscal_year],
            ).fetchone()
        total_deposits = float(row["total_deposits"] or 0)
        total_expenses = float(row["total_expenses"] or 0)
        return {
            "account_count": int(row["account_count"] or 0),
            "total_deposits": total_deposits,
            "total_expenses": total_expenses,
            "net": round(total_deposits - total_expenses, 2),
        }

    def get_account(self, account_code: str) -> dict | None:
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM financial_accounts
                WHERE account_code = ?
                """,
                [account_code],
            ).fetchone()
        return dict(row) if row is not None else None
