from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from html import escape
from pathlib import Path

from src.db.connection import get_connection
from src.services.pdf_service import convert_html_to_pdf


TRANSACTION_TYPES = {
    "Expense": "EX",
    "Revenue": "RR",
    "Transfer": "TF",
}


@dataclass(slots=True)
class FinancialTransactionRequest:
    account_code: str
    month_number: int
    transaction_date: str
    transaction_type: str
    amount: float
    payee: str
    memo: str
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

    with get_connection(db_path) as connection:
        account = connection.execute(
            """
            SELECT account_code
            FROM financial_accounts
            WHERE account_code = ?
            """,
            [request.account_code],
        ).fetchone()
        if account is None:
            raise ValueError("Account code was not found.")

        month_row = connection.execute(
            """
            SELECT *
            FROM financial_monthly
            WHERE account_code = ? AND fiscal_month = ?
              AND COALESCE(fiscal_year, '') = ?
            """,
            [request.account_code, request.month_number, str(request.transaction_date)[:4]],
        ).fetchone()
        if month_row is None:
            raise ValueError("Monthly account record was not found.")

        next_number = connection.execute(
            """
            SELECT COALESCE(MAX(CAST(transaction_number AS INTEGER)), 0) + 1
            FROM financial_transactions
            """
        ).fetchone()[0]

        month_expense = float(month_row["month_expense"] or 0)
        month_deposit = float(month_row["month_deposit"] or 0)
        year_to_date = float(month_row["year_to_date"] or 0)
        code = TRANSACTION_TYPES[request.transaction_type]

        if code in {"EX", "TF"}:
            month_expense = round(month_expense + request.amount, 2)
            year_to_date = round(year_to_date - request.amount, 2)
        else:
            month_deposit = round(month_deposit + request.amount, 2)
            year_to_date = round(year_to_date + request.amount, 2)

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
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(next_number),
                str(request.transaction_date)[:4],
                request.month_number,
                request.transaction_date,
                request.transaction_date,
                str(request.month_number),
                request.account_code,
                request.amount,
                request.payee.strip(),
                request.memo.strip(),
                request.reference_number.strip() or None,
                request.check_number.strip() or None,
                None,
                request.payment_method.strip() or None,
                None,
                None,
                code,
                "C",
            ],
        )
        connection.execute(
            """
            UPDATE financial_monthly
            SET month_expense = ?, month_deposit = ?, year_to_date = ?
            WHERE account_code = ? AND fiscal_month = ?
              AND COALESCE(fiscal_year, '') = ?
            """,
            [
                month_expense,
                month_deposit,
                year_to_date,
                request.account_code,
                request.month_number,
                str(request.transaction_date)[:4],
            ],
        )
        connection.commit()
    return int(next_number)


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
        connection.execute("BEGIN")
        connection.execute("DELETE FROM financial_monthly WHERE account_code = ?", [account_code])
        connection.execute("DELETE FROM financial_accounts WHERE account_code = ?", [account_code])
        connection.commit()


def update_financial_budget(db_path: Path, request: FinancialBudgetUpdateRequest) -> None:
    if request.monthly_budget < 0 or request.yearly_budget < 0:
        raise ValueError("Budget amounts cannot be negative.")
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


def render_monthly_financial_report_html(
    db_path: Path,
    fiscal_month: int,
    fiscal_year: str,
    output_dir: Path,
) -> Path:
    with get_connection(db_path) as connection:
        rows = connection.execute(
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

    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"financial_month_{fiscal_year}_{fiscal_month}_{date.today().strftime('%m-%d-%y')}.html"
    lines = []
    current_category = None
    for row in rows:
        if row["category"] != current_category:
            current_category = row["category"]
            lines.append(f"<tr class='category'><td colspan='7'>{escape(current_category or '')}</td></tr>")
        lines.append(
            "<tr>"
            f"<td>{escape(row['account_code'] or '')}</td>"
            f"<td>{escape(row['account_name'] or '')}</td>"
            f"<td class='num'>{float(row['yearly_budget'] or 0):,.2f}</td>"
            f"<td class='num'>{float(row['budget_to_date'] or 0):,.2f}</td>"
            f"<td class='num'>{float(row['month_expense'] or 0):,.2f}</td>"
            f"<td class='num'>{float(row['month_deposit'] or 0):,.2f}</td>"
            f"<td class='num'>{float(row['year_to_date'] or 0):,.2f}</td>"
            "</tr>"
        )

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>Monthly Financial Report</title>
      <style>
        body {{ font-family: Georgia, serif; margin: 24px; color: #111827; }}
        h1 {{ margin-bottom: 4px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 18px; }}
        th, td {{ border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; font-size: 13px; }}
        .num {{ text-align: right; }}
        .category td {{ background: #e5ecf6; font-weight: bold; }}
      </style>
    </head>
    <body>
      <h1>Monthly Financial Report</h1>
      <div>Fiscal year: {escape(fiscal_year)}</div>
      <div>Fiscal month: {fiscal_month}</div>
      <table>
        <thead>
          <tr>
            <th>Code</th>
            <th>Account</th>
            <th>Annual Budget</th>
            <th>Budget To Date</th>
            <th>Month Expense</th>
            <th>Month Deposit</th>
            <th>Year To Date</th>
          </tr>
        </thead>
        <tbody>
          {''.join(lines)}
        </tbody>
      </table>
    </body>
    </html>
    """
    file_path.write_text(html, encoding="utf-8")
    return file_path


def render_transaction_log_html(
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

    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"financial_transactions_{fiscal_year}_{fiscal_month}_{date.today().strftime('%m-%d-%y')}.html"
    lines = []
    for row in rows:
        lines.append(
            "<tr>"
            f"<td>{escape(row['transaction_number'] or '')}</td>"
            f"<td>{escape(row['transaction_date'] or '')}</td>"
            f"<td>{escape(row['transaction_type'] or '')}</td>"
            f"<td>{escape(row['account_code'] or '')}</td>"
            f"<td class='num'>{float(row['amount'] or 0):,.2f}</td>"
            f"<td>{escape(row['payee'] or '')}</td>"
            f"<td>{escape(row['memo'] or '')}</td>"
            f"<td>{escape(row['check_number'] or '')}</td>"
            f"<td>{escape(row['reference_number'] or '')}</td>"
            "</tr>"
        )

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>Transaction Log</title>
      <style>
        body {{ font-family: Georgia, serif; margin: 24px; color: #111827; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 18px; }}
        th, td {{ border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; font-size: 12px; }}
        .num {{ text-align: right; }}
      </style>
    </head>
    <body>
      <h1>Transaction Log</h1>
      <div>Fiscal year: {escape(fiscal_year)}</div>
      <div>Fiscal month: {fiscal_month}</div>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Date</th>
            <th>Type</th>
            <th>Acct</th>
            <th>Amount</th>
            <th>Payee</th>
            <th>Memo</th>
            <th>Check</th>
            <th>Ref</th>
          </tr>
        </thead>
        <tbody>
          {''.join(lines)}
        </tbody>
      </table>
    </body>
    </html>
    """
    file_path.write_text(html, encoding="utf-8")
    return file_path


def render_year_end_financial_report_html(db_path: Path, fiscal_year: str, output_dir: Path) -> Path:
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

    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"financial_year_end_{fiscal_year}_{date.today().strftime('%m-%d-%y')}.html"
    lines = []
    current_category = None
    for row in rows:
        if row["category"] != current_category:
            current_category = row["category"]
            lines.append(f"<tr class='category'><td colspan='4'>{escape(current_category or '')}</td></tr>")
        lines.append(
            "<tr>"
            f"<td>{escape(row['account_code'] or '')}</td>"
            f"<td>{escape(row['account_name'] or '')}</td>"
            f"<td class='num'>{float(row['yearly_budget'] or 0):,.2f}</td>"
            f"<td class='num'>{float(row['year_to_date'] or 0):,.2f}</td>"
            "</tr>"
        )

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>Year-End Financial Summary</title>
      <style>
        body {{ font-family: Georgia, serif; margin: 24px; color: #111827; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 18px; }}
        th, td {{ border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; font-size: 13px; }}
        .num {{ text-align: right; }}
        .category td {{ background: #e5ecf6; font-weight: bold; }}
      </style>
    </head>
    <body>
      <h1>Year-End Financial Summary</h1>
      <div>Fiscal year: {escape(fiscal_year)}</div>
      <table>
        <thead>
          <tr>
            <th>Code</th>
            <th>Account</th>
            <th>Annual Budget</th>
            <th>Year To Date</th>
          </tr>
        </thead>
        <tbody>
          {''.join(lines)}
        </tbody>
      </table>
    </body>
    </html>
    """
    file_path.write_text(html, encoding="utf-8")
    return file_path


def render_budget_report_html(db_path: Path, fiscal_year: str, output_dir: Path) -> Path:
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

    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"financial_budget_{fiscal_year}_{date.today().strftime('%m-%d-%y')}.html"
    lines = []
    current_category = None
    for row in rows:
        if row["category"] != current_category:
            current_category = row["category"]
            lines.append(f"<tr class='category'><td colspan='4'>{escape(current_category or '')}</td></tr>")
        lines.append(
            "<tr>"
            f"<td>{escape(row['account_code'] or '')}</td>"
            f"<td>{escape(row['account_name'] or '')}</td>"
            f"<td class='num'>{float(row['monthly_budget'] or 0):,.2f}</td>"
            f"<td class='num'>{float(row['yearly_budget'] or 0):,.2f}</td>"
            "</tr>"
        )

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>Budget Report</title>
      <style>
        body {{ font-family: Georgia, serif; margin: 24px; color: #111827; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 18px; }}
        th, td {{ border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; font-size: 13px; }}
        .num {{ text-align: right; }}
        .category td {{ background: #e5ecf6; font-weight: bold; }}
      </style>
    </head>
    <body>
      <h1>Budget Report</h1>
      <div>Fiscal year: {escape(fiscal_year)}</div>
      <table>
        <thead>
          <tr>
            <th>Code</th>
            <th>Account</th>
            <th>Monthly Budget</th>
            <th>Yearly Budget</th>
          </tr>
        </thead>
        <tbody>{''.join(lines)}</tbody>
      </table>
    </body>
    </html>
    """
    file_path.write_text(html, encoding="utf-8")
    return file_path


def convert_financial_report_to_pdf(html_path: Path) -> Path:
    return convert_html_to_pdf(html_path, "Failed to convert report to PDF.")
