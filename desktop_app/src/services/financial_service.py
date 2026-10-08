from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import shutil

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.units import inch
from reportlab.platypus import TableStyle

from src.db.connection import get_connection
from src.services.pdf_service import build_pdf_path, build_report_story, build_story_pdf, build_table


TRANSACTION_TYPES = {
    "Expense": "EX",
    "Revenue": "RR",
    "Transfer": "TF",
}


@dataclass(slots=True)
class FinancialTransactionRequest:
    account_code: str
    fiscal_year: str
    month_number: int
    transaction_date: str
    transaction_type: str
    amount: float
    payee: str
    memo: str
    counter_account_code: str = ""
    reference_number: str = ""
    check_number: str = ""
    payment_method: str = ""


@dataclass(slots=True)
class FinancialAccountRequest:
    account_code: str
    account_name: str
    category: str
    fiscal_year: str
    yearly_budget: float
    monthly_budget: float


@dataclass(slots=True)
class FinancialBudgetUpdateRequest:
    account_code: str
    fiscal_year: str
    fiscal_month: int
    monthly_budget: float
    yearly_budget: float


@dataclass(slots=True)
class MonthCloseResult:
    closed_year: str
    closed_month: int
    next_year: str
    next_month: int
    accounts_updated: int


def default_financial_date() -> str:
    return date.today().isoformat()


def _make_backup(db_path: Path, operation: str) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{db_path.stem}_financial_{operation}_{stamp}.sqlite3"
    shutil.copy2(db_path, backup_path)
    return backup_path


def active_fiscal_year(db_path: Path) -> str:
    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(fiscal_year), ''), '') AS fiscal_year
            FROM financial_accounts
            WHERE COALESCE(NULLIF(TRIM(fiscal_year), ''), '') <> ''
            ORDER BY fiscal_year DESC
            LIMIT 1
            """
        ).fetchone()
    return str(row["fiscal_year"] or date.today().year) if row is not None else str(date.today().year)


def active_fiscal_month(db_path: Path, fiscal_year: str | None = None) -> int:
    target_year = fiscal_year or active_fiscal_year(db_path)
    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT fiscal_month
            FROM financial_monthly
            WHERE file_status = 'A'
              AND COALESCE(fiscal_year, '') = ?
            ORDER BY fiscal_month
            LIMIT 1
            """,
            [target_year],
        ).fetchone()
        if row is not None:
            return int(row["fiscal_month"])
        row = connection.execute(
            """
            SELECT MIN(fiscal_month) AS fiscal_month
            FROM financial_monthly
            WHERE COALESCE(fiscal_year, '') = ?
            """,
            [target_year],
        ).fetchone()
    return int(row["fiscal_month"] or 1)


def post_financial_transaction(db_path: Path, request: FinancialTransactionRequest) -> int:
    if request.transaction_type not in TRANSACTION_TYPES:
        raise ValueError("Choose a valid transaction type.")
    if request.amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    if request.month_number < 1 or request.month_number > 12:
        raise ValueError("Month must be between 1 and 12.")
    fiscal_year = request.fiscal_year.strip()
    if not fiscal_year:
        raise ValueError("Fiscal year is required.")

    main_account_code = request.account_code.strip().upper()
    counter_account_code = request.counter_account_code.strip().upper()
    if not main_account_code or not counter_account_code:
        raise ValueError("Choose both the main account and the funds/payment account.")
    if main_account_code == counter_account_code:
        raise ValueError("The two accounts must be different.")

    _make_backup(db_path, "transaction")
    with get_connection(db_path) as connection:
        for account_code in [main_account_code, counter_account_code]:
            account = connection.execute(
                "SELECT account_code FROM financial_accounts WHERE account_code = ?",
                [account_code],
            ).fetchone()
            if account is None:
                raise ValueError(f"Account code {account_code} was not found.")
            month_row = connection.execute(
                """
                SELECT 1 FROM financial_monthly
                WHERE account_code = ? AND fiscal_month = ?
                  AND COALESCE(fiscal_year, '') = ?
                """,
                [account_code, request.month_number, fiscal_year],
            ).fetchone()
            if month_row is None:
                raise ValueError(
                    f"Monthly account record {account_code} was not found for fiscal year {fiscal_year}."
                )

        next_number = connection.execute(
            """
            SELECT COALESCE(MAX(CAST(transaction_number AS INTEGER)), 0) + 1
            FROM financial_transactions
            """
        ).fetchone()[0]

        code = TRANSACTION_TYPES[request.transaction_type]
        if code == "EX":
            source_account_code = counter_account_code
            destination_account_code = main_account_code
            legs = [
                (main_account_code, "expense", request.amount, 0.0, request.amount, 0.0),
                (counter_account_code, "payment", request.amount, 0.0, -request.amount, request.amount),
            ]
        elif code == "RR":
            source_account_code = main_account_code
            destination_account_code = counter_account_code
            legs = [
                (main_account_code, "revenue", 0.0, request.amount, request.amount, 0.0),
                (counter_account_code, "deposit", 0.0, request.amount, request.amount, 0.0),
            ]
        else:
            source_account_code = main_account_code
            destination_account_code = counter_account_code
            legs = [
                (main_account_code, "transfer_from", request.amount, 0.0, -request.amount, request.amount),
                (counter_account_code, "transfer_to", 0.0, request.amount, request.amount, 0.0),
            ]

        connection.execute("BEGIN")
        connection.execute(
            """
            INSERT INTO financial_transactions (
                transaction_number,
                fiscal_year,
                month_number,
                entry_date,
                transaction_date,
                month_code,
                account_code,
                amount,
                payee,
                memo,
                reference_number,
                check_number,
                paper_check_flag,
                payment_method,
                pc_transaction_number,
                disposition,
                transaction_type,
                status,
                source_account_code,
                destination_account_code,
                source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'app')
            """,
            [
                str(next_number),
                fiscal_year,
                request.month_number,
                request.transaction_date,
                request.transaction_date,
                str(request.month_number),
                main_account_code,
                request.amount,
                request.payee.strip(),
                request.memo.strip(),
                request.reference_number.strip() or None,
                request.check_number.strip() or None,
                None,
                request.payment_method.strip() or None,
                None,
                counter_account_code,
                code,
                "C",
                source_account_code,
                destination_account_code,
            ],
        ).lastrowid
        transaction_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        for account_code, role, expense, deposit, ytd, budget in legs:
            _apply_financial_leg(
                connection,
                transaction_id=transaction_id,
                account_code=account_code,
                role=role,
                fiscal_year=fiscal_year,
                fiscal_month=request.month_number,
                month_expense_change=expense,
                month_deposit_change=deposit,
                year_to_date_change=ytd,
                budget_to_date_change=budget,
            )
        connection.commit()
    return int(next_number)


def _apply_financial_leg(
    connection,
    *,
    transaction_id: int,
    account_code: str,
    role: str,
    fiscal_year: str,
    fiscal_month: int,
    month_expense_change: float,
    month_deposit_change: float,
    year_to_date_change: float,
    budget_to_date_change: float,
) -> None:
    connection.execute(
        """
        UPDATE financial_monthly
        SET month_expense = ROUND(COALESCE(month_expense, 0) + ?, 2),
            month_deposit = ROUND(COALESCE(month_deposit, 0) + ?, 2),
            year_to_date = ROUND(COALESCE(year_to_date, 0) + ?, 2),
            budget_to_date = ROUND(COALESCE(budget_to_date, 0) + ?, 2)
        WHERE account_code = ? AND fiscal_month = ?
          AND COALESCE(fiscal_year, '') = ?
        """,
        [
            month_expense_change,
            month_deposit_change,
            year_to_date_change,
            budget_to_date_change,
            account_code,
            fiscal_month,
            fiscal_year,
        ],
    )
    connection.execute(
        """
        INSERT INTO financial_transaction_legs (
            transaction_id, account_code, role, month_expense_change,
            month_deposit_change, year_to_date_change, budget_to_date_change
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            transaction_id,
            account_code,
            role,
            round(month_expense_change, 2),
            round(month_deposit_change, 2),
            round(year_to_date_change, 2),
            round(budget_to_date_change, 2),
        ],
    )


def recode_financial_transaction(
    db_path: Path,
    transaction_number: str,
    new_account_code: str,
) -> int:
    number = transaction_number.strip()
    target_code = new_account_code.strip().upper()
    if not number:
        raise ValueError("Transaction number is required.")
    if not target_code:
        raise ValueError("Corrected account code is required.")
    _make_backup(db_path, "recode_transaction")
    with get_connection(db_path) as connection:
        original = connection.execute(
            """
            SELECT * FROM financial_transactions
            WHERE transaction_number = ?
            ORDER BY id DESC LIMIT 1
            """,
            [number],
        ).fetchone()
        if original is None:
            raise ValueError("Transaction number was not found.")
        if str(original["status"] or "").strip().upper() == "R":
            raise ValueError("That transaction has already been recoded.")
        old_code = str(original["account_code"] or "").strip().upper()
        if not old_code:
            raise ValueError("The original transaction has no account code to recode.")
        if target_code == old_code:
            raise ValueError("The corrected account is the same as the original account.")
        target = connection.execute(
            "SELECT 1 FROM financial_accounts WHERE account_code = ?",
            [target_code],
        ).fetchone()
        if target is None:
            raise ValueError("Corrected account code was not found.")

        year = str(original["fiscal_year"] or "").strip()
        month = int(original["month_number"] or 0)
        target_month = connection.execute(
            """
            SELECT 1 FROM financial_monthly
            WHERE account_code = ? AND fiscal_month = ? AND COALESCE(fiscal_year, '') = ?
            """,
            [target_code, month, year],
        ).fetchone()
        if target_month is None:
            raise ValueError("Corrected account does not have a row in that fiscal period.")

        original_leg = connection.execute(
            """
            SELECT * FROM financial_transaction_legs
            WHERE transaction_id = ? AND account_code = ?
            ORDER BY id LIMIT 1
            """,
            [original["id"], old_code],
        ).fetchone()
        amount = float(original["amount"] or 0)
        type_code = str(original["transaction_type"] or "").strip().upper()
        if original_leg is None:
            if type_code == "RR":
                changes = (0.0, amount, amount, 0.0)
                role = "revenue"
            else:
                changes = (amount, 0.0, amount if type_code == "EX" else -amount, 0.0)
                role = "expense" if type_code == "EX" else "transfer_from"
        else:
            changes = (
                float(original_leg["month_expense_change"] or 0),
                float(original_leg["month_deposit_change"] or 0),
                float(original_leg["year_to_date_change"] or 0),
                float(original_leg["budget_to_date_change"] or 0),
            )
            role = str(original_leg["role"] or "recode")

        next_number = int(
            connection.execute(
                "SELECT COALESCE(MAX(CAST(transaction_number AS INTEGER)), 0) + 1 FROM financial_transactions"
            ).fetchone()[0]
        )
        source_account_code = str(original["source_account_code"] or "").strip().upper()
        destination_account_code = str(original["destination_account_code"] or "").strip().upper()
        if type_code in {"RR", "TF"} and source_account_code == old_code:
            source_account_code = target_code
        if type_code == "EX" and destination_account_code == old_code:
            destination_account_code = target_code
        connection.execute("BEGIN")
        correction_id = connection.execute(
            """
            INSERT INTO financial_transactions (
                transaction_number, fiscal_year, month_number, entry_date,
                transaction_date, month_code, account_code, amount, payee, memo,
                transaction_type, status, source, source_account_code,
                destination_account_code, correction_of_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'C', 'app', ?, ?, ?)
            """,
            [
                str(next_number), year, month, date.today().isoformat(),
                original["transaction_date"], str(month), target_code, amount,
                f"RECODE NO {number}", f"OLD ACCOUNT CODE WAS {old_code}",
                type_code, source_account_code,
                destination_account_code, original["id"],
            ],
        ).lastrowid
        _apply_financial_leg(
            connection,
            transaction_id=correction_id,
            account_code=old_code,
            role="recode_from",
            fiscal_year=year,
            fiscal_month=month,
            month_expense_change=-changes[0],
            month_deposit_change=-changes[1],
            year_to_date_change=-changes[2],
            budget_to_date_change=-changes[3],
        )
        _apply_financial_leg(
            connection,
            transaction_id=correction_id,
            account_code=target_code,
            role=f"recode_to_{role}",
            fiscal_year=year,
            fiscal_month=month,
            month_expense_change=changes[0],
            month_deposit_change=changes[1],
            year_to_date_change=changes[2],
            budget_to_date_change=changes[3],
        )
        connection.execute(
            "UPDATE financial_transactions SET status = 'R' WHERE id = ?",
            [original["id"]],
        )
        connection.commit()
    return next_number


def add_financial_account(db_path: Path, request: FinancialAccountRequest) -> None:
    account_code = request.account_code.strip().upper()
    if len(account_code) != 2:
        raise ValueError("Account code must be exactly 2 characters.")
    if not request.account_name.strip():
        raise ValueError("Account name is required.")
    if not request.category.strip():
        raise ValueError("Category is required.")

    with get_connection(db_path) as connection:
        existing = connection.execute(
            "SELECT 1 FROM financial_accounts WHERE account_code = ?",
            [account_code],
        ).fetchone()
        if existing is not None:
            raise ValueError("That account code already exists.")

        _make_backup(db_path, "add_account")
        connection.execute("BEGIN")
        connection.execute(
            """
            INSERT INTO financial_accounts (
                account_code,
                account_name,
                category,
                fiscal_year,
                monthly_budget,
                yearly_budget,
                file_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                account_code,
                request.account_name.strip(),
                request.category.strip(),
                request.fiscal_year.strip(),
                request.monthly_budget,
                request.yearly_budget,
                "A",
            ],
        )
        for month in range(1, 13):
            active_month = active_fiscal_month(db_path, request.fiscal_year.strip())
            status = "A" if month == active_month else ("C" if month < active_month else "F")
            connection.execute(
                """
                INSERT INTO financial_monthly (
                    account_code,
                    fiscal_year,
                    fiscal_month,
                    calendar_month,
                    previous_balance,
                    month_expense,
                    month_deposit,
                    year_to_date,
                    budget_to_date,
                    monthly_budget,
                    yearly_budget,
                    file_status
                ) VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, ?, ?, ?)
                """,
                [
                    account_code,
                    request.fiscal_year.strip(),
                    month,
                    month,
                    request.monthly_budget,
                    request.yearly_budget,
                    status,
                ],
            )
        connection.commit()


def rename_financial_account(db_path: Path, account_code: str, account_name: str, category: str) -> None:
    if not account_name.strip():
        raise ValueError("Account name is required.")
    if not category.strip():
        raise ValueError("Category is required.")
    _make_backup(db_path, "edit_account")
    with get_connection(db_path) as connection:
        updated = connection.execute(
            """
            UPDATE financial_accounts
            SET account_name = ?, category = ?
            WHERE account_code = ?
            """,
            [account_name.strip(), category.strip(), account_code.strip().upper()],
        ).rowcount
        if updated == 0:
            raise ValueError("Account not found.")
        connection.commit()


def delete_financial_account(db_path: Path, account_code: str) -> None:
    account_code = account_code.strip().upper()
    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                COALESCE(SUM(yearly_budget), 0) AS yearly_budget,
                COALESCE(SUM(ABS(year_to_date)), 0) AS year_to_date
            FROM financial_monthly
            WHERE account_code = ?
            """,
            [account_code],
        ).fetchone()
        if row is None:
            raise ValueError("Account not found.")
        if float(row["yearly_budget"] or 0) != 0 or float(row["year_to_date"] or 0) != 0:
            raise ValueError("This account is active and may not be deleted.")
        _make_backup(db_path, "delete_account")
        connection.execute("BEGIN")
        connection.execute("DELETE FROM financial_monthly WHERE account_code = ?", [account_code])
        connection.execute("DELETE FROM financial_accounts WHERE account_code = ?", [account_code])
        connection.commit()


def update_financial_budget(db_path: Path, request: FinancialBudgetUpdateRequest) -> None:
    if request.monthly_budget < 0 or request.yearly_budget < 0:
        raise ValueError("Budget amounts cannot be negative.")
    _make_backup(db_path, "budget")
    with get_connection(db_path) as connection:
        updated = connection.execute(
            """
            UPDATE financial_monthly
            SET monthly_budget = ?, yearly_budget = ?
            WHERE account_code = ? AND fiscal_month = ? AND COALESCE(fiscal_year, '') = ?
            """,
            [
                request.monthly_budget,
                request.yearly_budget,
                request.account_code.strip().upper(),
                request.fiscal_month,
                request.fiscal_year.strip(),
            ],
        ).rowcount
        if updated == 0:
            raise ValueError("Monthly budget row not found.")
        connection.execute(
            """
            UPDATE financial_accounts
            SET monthly_budget = ?, yearly_budget = ?
            WHERE account_code = ?
            """,
            [
                request.monthly_budget,
                request.yearly_budget,
                request.account_code.strip().upper(),
            ],
        )
        connection.commit()


def update_financial_budget_distribution(
    db_path: Path,
    account_code: str,
    fiscal_year: str,
    monthly_amounts: list[float],
) -> None:
    if len(monthly_amounts) != 12:
        raise ValueError("Enter one budget amount for each of the 12 months.")
    if any(amount < 0 for amount in monthly_amounts):
        raise ValueError("Budget amounts cannot be negative.")
    code = account_code.strip().upper()
    year = fiscal_year.strip()
    total = round(sum(monthly_amounts), 2)
    _make_backup(db_path, "budget_distribution")
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT fiscal_month FROM financial_monthly
            WHERE account_code = ? AND COALESCE(fiscal_year, '') = ?
            ORDER BY fiscal_month
            """,
            [code, year],
        ).fetchall()
        if len(rows) != 12:
            raise ValueError("This account does not have all 12 fiscal-month rows.")
        connection.execute("BEGIN")
        for month, amount in enumerate(monthly_amounts, start=1):
            connection.execute(
                """
                UPDATE financial_monthly
                SET monthly_budget = ?, yearly_budget = ?
                WHERE account_code = ? AND fiscal_month = ?
                  AND COALESCE(fiscal_year, '') = ?
                """,
                [round(amount, 2), total, code, month, year],
            )
        connection.execute(
            """
            UPDATE financial_accounts
            SET monthly_budget = ?, yearly_budget = ?
            WHERE account_code = ?
            """,
            [round(total / 12, 2), total, code],
        )
        connection.commit()


def create_new_fiscal_year(db_path: Path, source_year: str, target_year: str) -> int:
    source_year = source_year.strip()
    target_year = target_year.strip()
    if not source_year or not target_year:
        raise ValueError("Source year and target year are required.")
    if source_year == target_year:
        raise ValueError("Target year must be different from source year.")

    with get_connection(db_path) as connection:
        existing = connection.execute(
            """
            SELECT COUNT(*)
            FROM financial_monthly
            WHERE COALESCE(fiscal_year, '') = ?
            """,
            [target_year],
        ).fetchone()[0]
        if existing:
            raise ValueError(f"Fiscal year {target_year} already exists.")

        source_accounts = connection.execute(
            """
            SELECT
                a.account_code,
                a.account_name,
                a.category,
                COALESCE(m.monthly_budget, a.monthly_budget, 0) AS monthly_budget,
                COALESCE(m.yearly_budget, a.yearly_budget, 0) AS yearly_budget,
                COALESCE(m.year_to_date, 0) AS closing_balance
            FROM financial_accounts a
            LEFT JOIN financial_monthly m
              ON m.account_code = a.account_code
             AND COALESCE(m.fiscal_year, '') = ?
             AND m.fiscal_month = (
                SELECT MAX(m2.fiscal_month)
                FROM financial_monthly m2
                WHERE m2.account_code = a.account_code
                  AND COALESCE(m2.fiscal_year, '') = ?
             )
            ORDER BY a.account_code
            """,
            [source_year, source_year],
        ).fetchall()
        if not source_accounts:
            raise ValueError(f"No financial data found for fiscal year {source_year}.")

        _make_backup(db_path, "new_fiscal_year")
        connection.execute("BEGIN")
        inserted_rows = 0
        for account in source_accounts:
            account_code = account["account_code"]
            monthly_budget = float(account["monthly_budget"] or 0)
            yearly_budget = float(account["yearly_budget"] or 0)
            closing_balance = round(float(account["closing_balance"] or 0), 2)

            connection.execute(
                """
                UPDATE financial_accounts
                SET fiscal_year = ?, monthly_budget = ?, yearly_budget = ?
                WHERE account_code = ?
                """,
                [target_year, monthly_budget, yearly_budget, account_code],
            )

            for month in range(1, 13):
                previous_balance = closing_balance if month == 1 else 0
                year_to_date = closing_balance if month == 1 else 0
                file_status = "A" if month == 1 else "F"
                connection.execute(
                    """
                    INSERT INTO financial_monthly (
                        account_code,
                        fiscal_year,
                        fiscal_month,
                        calendar_month,
                        previous_balance,
                        month_expense,
                        month_deposit,
                        year_to_date,
                        budget_to_date,
                        monthly_budget,
                        yearly_budget,
                        file_status
                    ) VALUES (?, ?, ?, ?, ?, 0, 0, ?, 0, ?, ?, ?)
                    """,
                    [
                        account_code,
                        target_year,
                        month,
                        month,
                        previous_balance,
                        year_to_date,
                        monthly_budget,
                        yearly_budget,
                        file_status,
                    ],
                )
                inserted_rows += 1
        connection.commit()
    return inserted_rows


def close_financial_month(db_path: Path, fiscal_year: str, fiscal_month: int) -> MonthCloseResult:
    if not fiscal_year.strip():
        raise ValueError("Fiscal year is required.")
    if fiscal_month < 1 or fiscal_month > 12:
        raise ValueError("Fiscal month must be between 1 and 12.")

    if fiscal_month == 12:
        next_month = 1
        next_year = str(int(fiscal_year) + 1) if fiscal_year.isdigit() else fiscal_year
    else:
        next_month = fiscal_month + 1
        next_year = fiscal_year

    with get_connection(db_path) as connection:
        current_rows = connection.execute(
            """
            SELECT account_code, year_to_date, monthly_budget
            FROM financial_monthly
            WHERE fiscal_month = ? AND COALESCE(fiscal_year, '') = ?
            """,
            [fiscal_month, fiscal_year],
        ).fetchall()
        if not current_rows:
            raise ValueError("No monthly financial rows were found for the selected period.")

        next_rows = connection.execute(
            """
            SELECT account_code
            FROM financial_monthly
            WHERE fiscal_month = ? AND COALESCE(fiscal_year, '') = ?
            """,
            [next_month, next_year],
        ).fetchall()
        if not next_rows:
            raise ValueError(
                f"Next fiscal period {next_year} month {next_month} does not exist. Create the next fiscal year first if needed."
            )

        _make_backup(db_path, "close_month")
        connection.execute("BEGIN")
        connection.execute(
            """
            UPDATE financial_monthly
            SET file_status = 'C'
            WHERE fiscal_month = ? AND COALESCE(fiscal_year, '') = ?
            """,
            [fiscal_month, fiscal_year],
        )
        connection.execute(
            """
            UPDATE financial_monthly
            SET file_status = 'F'
            WHERE fiscal_month = ? AND COALESCE(fiscal_year, '') = ?
            """,
            [next_month, next_year],
        )

        updated_accounts = 0
        for row in current_rows:
            account_code = row["account_code"]
            closing_balance = round(float(row["year_to_date"] or 0), 2)
            budget_to_date = round(float(row["monthly_budget"] or 0) * next_month, 2)
            updated = connection.execute(
                """
                UPDATE financial_monthly
                SET
                    previous_balance = ?,
                    year_to_date = CASE
                        WHEN COALESCE(month_expense, 0) = 0 AND COALESCE(month_deposit, 0) = 0 THEN ?
                        ELSE year_to_date
                    END,
                    budget_to_date = ?,
                    file_status = 'A'
                WHERE account_code = ?
                  AND fiscal_month = ?
                  AND COALESCE(fiscal_year, '') = ?
                """,
                [
                    closing_balance,
                    closing_balance,
                    budget_to_date,
                    account_code,
                    next_month,
                    next_year,
                ],
            ).rowcount
            updated_accounts += updated
        connection.commit()

    return MonthCloseResult(
        closed_year=fiscal_year,
        closed_month=fiscal_month,
        next_year=next_year,
        next_month=next_month,
        accounts_updated=updated_accounts,
    )


def render_monthly_financial_report_pdf(
    db_path: Path,
    fiscal_month: int,
    fiscal_year: str,
    output_dir: Path,
) -> Path:
    with get_connection(db_path) as connection:
        result_rows = connection.execute(
            """
            SELECT
                a.category,
                a.account_code,
                a.account_name,
                m.yearly_budget,
                m.budget_to_date,
                m.month_expense,
                m.month_deposit,
                m.year_to_date
            FROM financial_accounts a
            JOIN financial_monthly m
              ON m.account_code = a.account_code
            WHERE m.fiscal_month = ?
              AND COALESCE(m.fiscal_year, a.fiscal_year, '') = ?
            ORDER BY a.category, a.account_code
            """,
            [fiscal_month, fiscal_year],
        ).fetchall()

    output_path = build_pdf_path(
        output_dir,
        f"financial_month_{fiscal_year}_{fiscal_month}_{date.today().strftime('%m-%d-%y')}",
    )
    table_rows: list[list[object]] = [[
        "Code",
        "Account",
        "Annual Budget",
        "Budget To Date",
        "Month Expense",
        "Month Deposit",
        "Year To Date",
    ]]
    current_category = None
    for row in result_rows:
        if row["category"] != current_category:
            current_category = row["category"]
            table_rows.append([f"Category: {current_category or ''}", "", "", "", "", "", ""])
        table_rows.append(
            [
                str(row["account_code"] or ""),
                str(row["account_name"] or ""),
                f"{float(row['yearly_budget'] or 0):,.2f}",
                f"{float(row['budget_to_date'] or 0):,.2f}",
                f"{float(row['month_expense'] or 0):,.2f}",
                f"{float(row['month_deposit'] or 0):,.2f}",
                f"{float(row['year_to_date'] or 0):,.2f}",
            ]
        )

    story = build_report_story(
        "Monthly Financial Report",
        [f"Fiscal year: {fiscal_year}", f"Fiscal month: {fiscal_month}"],
    )
    table = build_table(
        table_rows,
        [0.55 * inch, 2.15 * inch, 1.15 * inch, 1.15 * inch, 1.1 * inch, 1.1 * inch, 1.1 * inch],
        wrap_cells=True,
        column_alignments=["LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT"],
        font_size=8,
    )
    category_rows = [index for index, row in enumerate(table_rows) if row[1] == "" and index > 0]
    styles = [("ALIGN", (2, 1), (6, -1), "RIGHT")]
    for index in category_rows:
        styles.extend(
            [
                ("SPAN", (0, index), (-1, index)),
                ("BACKGROUND", (0, index), (-1, index), colors.HexColor("#e5ecf6")),
                ("FONTNAME", (0, index), (-1, index), "Helvetica-Bold"),
            ]
        )
    table.setStyle(TableStyle(styles))
    story.append(table)
    return build_story_pdf(
        output_path,
        story,
        title="Monthly Financial Report",
        footer_text="Lake Lafayette Landowners Association - Monthly Financial Report",
        page_size=landscape(LETTER),
    )


def render_transaction_log_pdf(
    db_path: Path,
    fiscal_month: int,
    fiscal_year: str,
    output_dir: Path,
) -> Path:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                transaction_number,
                transaction_date,
                transaction_type,
                account_code,
                amount,
                payee,
                memo,
                check_number,
                reference_number
            FROM financial_transactions
            WHERE month_number = ?
              AND COALESCE(fiscal_year, '') = ?
            ORDER BY CAST(transaction_number AS INTEGER), id
            """,
            [fiscal_month, fiscal_year],
        ).fetchall()

    output_path = build_pdf_path(
        output_dir,
        f"financial_transactions_{fiscal_year}_{fiscal_month}_{date.today().strftime('%m-%d-%y')}",
    )
    table_rows: list[list[object]] = [[
        "#",
        "Date",
        "Type",
        "Acct",
        "Amount",
        "Payee",
        "Memo",
        "Check",
        "Ref",
    ]]
    for row in rows:
        table_rows.append(
            [
                str(row["transaction_number"] or ""),
                str(row["transaction_date"] or ""),
                str(row["transaction_type"] or ""),
                str(row["account_code"] or ""),
                f"{float(row['amount'] or 0):,.2f}",
                str(row["payee"] or ""),
                str(row["memo"] or ""),
                str(row["check_number"] or ""),
                str(row["reference_number"] or ""),
            ]
        )

    story = build_report_story(
        "Transaction Log",
        [f"Fiscal year: {fiscal_year}", f"Fiscal month: {fiscal_month}"],
    )
    table = build_table(
        table_rows,
        [0.42 * inch, 0.78 * inch, 0.5 * inch, 0.48 * inch, 0.72 * inch, 1.5 * inch, 2.75 * inch, 0.72 * inch, 0.72 * inch],
        wrap_cells=True,
        column_alignments=["LEFT", "LEFT", "LEFT", "LEFT", "RIGHT", "LEFT", "LEFT", "LEFT", "LEFT"],
        font_size=7.5,
    )
    table.setStyle(TableStyle([("ALIGN", (4, 1), (4, -1), "RIGHT")]))
    story.append(table)
    return build_story_pdf(
        output_path,
        story,
        title="Transaction Log",
        footer_text="Lake Lafayette Landowners Association - Transaction Log",
        page_size=landscape(LETTER),
    )


def render_year_end_financial_report_pdf(db_path: Path, fiscal_year: str, output_dir: Path) -> Path:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                a.category,
                a.account_code,
                a.account_name,
                MAX(m.yearly_budget) AS yearly_budget,
                MAX(m.year_to_date) AS year_to_date
            FROM financial_accounts a
            JOIN financial_monthly m ON m.account_code = a.account_code
            WHERE COALESCE(m.fiscal_year, a.fiscal_year, '') = ?
            GROUP BY a.category, a.account_code, a.account_name
            ORDER BY a.category, a.account_code
            """,
            [fiscal_year],
        ).fetchall()

    output_path = build_pdf_path(
        output_dir,
        f"financial_year_end_{fiscal_year}_{date.today().strftime('%m-%d-%y')}",
    )
    table_rows: list[list[object]] = [["Code", "Account", "Annual Budget", "Year To Date"]]
    current_category = None
    for row in rows:
        if row["category"] != current_category:
            current_category = row["category"]
            table_rows.append([f"Category: {current_category or ''}", "", "", ""])
        table_rows.append(
            [
                str(row["account_code"] or ""),
                str(row["account_name"] or ""),
                f"{float(row['yearly_budget'] or 0):,.2f}",
                f"{float(row['year_to_date'] or 0):,.2f}",
            ]
        )

    story = build_report_story("Year-End Financial Summary", [f"Fiscal year: {fiscal_year}"])
    table = build_table(
        table_rows,
        [0.7 * inch, 3.1 * inch, 1.15 * inch, 1.15 * inch],
        wrap_cells=True,
        column_alignments=["LEFT", "LEFT", "RIGHT", "RIGHT"],
    )
    category_rows = [index for index, row in enumerate(table_rows) if row[1] == "" and index > 0]
    styles = [("ALIGN", (2, 1), (3, -1), "RIGHT")]
    for index in category_rows:
        styles.extend(
            [
                ("SPAN", (0, index), (-1, index)),
                ("BACKGROUND", (0, index), (-1, index), colors.HexColor("#e5ecf6")),
                ("FONTNAME", (0, index), (-1, index), "Helvetica-Bold"),
            ]
        )
    table.setStyle(TableStyle(styles))
    story.append(table)
    return build_story_pdf(
        output_path,
        story,
        title="Year-End Financial Summary",
        footer_text="Lake Lafayette Landowners Association - Year-End Financial Summary",
    )


def render_budget_report_pdf(db_path: Path, fiscal_year: str, output_dir: Path) -> Path:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                a.category,
                a.account_code,
                a.account_name,
                MAX(m.monthly_budget) AS monthly_budget,
                MAX(m.yearly_budget) AS yearly_budget
            FROM financial_accounts a
            JOIN financial_monthly m ON m.account_code = a.account_code
            WHERE COALESCE(m.fiscal_year, a.fiscal_year, '') = ?
            GROUP BY a.category, a.account_code, a.account_name
            ORDER BY a.category, a.account_code
            """,
            [fiscal_year],
        ).fetchall()

    output_path = build_pdf_path(
        output_dir,
        f"financial_budget_{fiscal_year}_{date.today().strftime('%m-%d-%y')}",
    )
    table_rows: list[list[object]] = [["Code", "Account", "Monthly Budget", "Yearly Budget"]]
    current_category = None
    for row in rows:
        if row["category"] != current_category:
            current_category = row["category"]
            table_rows.append([f"Category: {current_category or ''}", "", "", ""])
        table_rows.append(
            [
                str(row["account_code"] or ""),
                str(row["account_name"] or ""),
                f"{float(row['monthly_budget'] or 0):,.2f}",
                f"{float(row['yearly_budget'] or 0):,.2f}",
            ]
        )

    story = build_report_story("Budget Report", [f"Fiscal year: {fiscal_year}"])
    table = build_table(
        table_rows,
        [0.7 * inch, 3.1 * inch, 1.15 * inch, 1.15 * inch],
        wrap_cells=True,
        column_alignments=["LEFT", "LEFT", "RIGHT", "RIGHT"],
    )
    category_rows = [index for index, row in enumerate(table_rows) if row[1] == "" and index > 0]
    styles = [("ALIGN", (2, 1), (3, -1), "RIGHT")]
    for index in category_rows:
        styles.extend(
            [
                ("SPAN", (0, index), (-1, index)),
                ("BACKGROUND", (0, index), (-1, index), colors.HexColor("#e5ecf6")),
                ("FONTNAME", (0, index), (-1, index), "Helvetica-Bold"),
            ]
        )
    table.setStyle(TableStyle(styles))
    story.append(table)
    return build_story_pdf(
        output_path,
        story,
        title="Budget Report",
        footer_text="Lake Lafayette Landowners Association - Budget Report",
    )
