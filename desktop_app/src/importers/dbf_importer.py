from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sqlite3
import struct


class LegacyImportError(RuntimeError):
    """Raised when legacy dBase import work cannot proceed."""


def _decode_text(raw: bytes) -> str:
    return raw.decode("cp437", "ignore").rstrip(" \x00")


def _parse_numeric(raw: bytes) -> int | float | None:
    text = raw.replace(b"\x00", b"").decode("ascii", "ignore").strip()
    if not text:
        return None
    if "." in text:
        return float(text)
    return int(text)


def _parse_date(raw: bytes) -> str | None:
    text = raw.replace(b"\x00", b"").decode("ascii", "ignore").strip()
    if not text or text == "00000000":
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").date().isoformat()
    except ValueError:
        return text


def _parse_char_date(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    for fmt in ("%m/%d/%y", "%m-%d-%y", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def _parse_logical(raw: bytes) -> str | None:
    text = raw.decode("ascii", "ignore").strip().upper()
    return text or None


def _read_dbf(path: Path) -> list[dict]:
    if not path.exists():
        raise LegacyImportError(f"Missing legacy DBF file: {path}")

    with path.open("rb") as handle:
        header = handle.read(32)
        if len(header) < 32:
            raise LegacyImportError(f"Invalid DBF header: {path}")

        record_count = struct.unpack("<I", header[4:8])[0]
        header_length = struct.unpack("<H", header[8:10])[0]
        record_length = struct.unpack("<H", header[10:12])[0]

        fields: list[tuple[str, str, int, int]] = []
        while True:
            descriptor = handle.read(32)
            if not descriptor:
                raise LegacyImportError(f"Unexpected end of header in {path}")
            if descriptor[0] == 0x0D:
                break
            name = descriptor[:11].split(b"\x00", 1)[0].decode("ascii", "ignore")
            field_type = chr(descriptor[11])
            field_length = descriptor[16]
            decimals = descriptor[17]
            fields.append((name, field_type, field_length, decimals))

        handle.seek(header_length)
        records: list[dict] = []
        for _ in range(record_count):
            raw_record = handle.read(record_length)
            if not raw_record or raw_record[0:1] == b"*":
                continue

            position = 1
            parsed: dict[str, object] = {}
            for name, field_type, field_length, _decimals in fields:
                raw_value = raw_record[position : position + field_length]
                position += field_length

                if field_type == "C":
                    value = _decode_text(raw_value)
                elif field_type == "N":
                    value = _parse_numeric(raw_value)
                elif field_type == "D":
                    value = _parse_date(raw_value)
                elif field_type == "L":
                    value = _parse_logical(raw_value)
                else:
                    value = _decode_text(raw_value)

                parsed[name] = value
            records.append(parsed)

    return records


def _as_money(value: object) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _as_text(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip()


def _owner_code(value: object) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _default_financial_year(financial_accounts: list[dict], financial_transactions: list[dict]) -> str:
    years: list[str] = []
    for row in financial_transactions:
        for field_name in ("TRANSDATE", "ENTRYDATE"):
            parsed = _parse_char_date(_as_text(row.get(field_name)) or "")
            if parsed and len(parsed) >= 4:
                years.append(parsed[:4])
                break
    if years:
        return max(years)
    for row in financial_accounts:
        year = _as_text(row.get("FISYEAR")) or ""
        if year.strip():
            return year.strip()
    return str(datetime.now().year)


def import_legacy_directory(source_dir: Path, sqlite_path: Path) -> dict[str, int]:
    source_dir = source_dir.resolve()
    sqlite_path = sqlite_path.resolve()

    owners = _read_dbf(source_dir / "ONERFILE.DBF")
    lots = _read_dbf(source_dir / "ASMTFILE.DBF")
    owner_payments = _read_dbf(source_dir / "OPAYFILE.DBF")
    lot_payments = _read_dbf(source_dir / "LPAYFILE.DBF")
    notes = _read_dbf(source_dir / "NOTEFILE.DBF")
    financial_accounts = _read_dbf(source_dir / "STDBUDFL.DBF")
    financial_monthly = _read_dbf(source_dir / "INEXFILE.DBF")
    financial_transactions = _read_dbf(source_dir / "TRANSFIL.DBF")
    default_financial_year = _default_financial_year(financial_accounts, financial_transactions)

    started_at = datetime.now().isoformat(timespec="seconds")
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(sqlite_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        run_id = connection.execute(
            """
            INSERT INTO import_runs (
                started_at,
                source_dir,
                status
            ) VALUES (?, ?, ?)
            """,
            [started_at, str(source_dir), "running"],
        ).lastrowid

        for table in [
            "property_sales",
            "payment_audit",
            "assessment_runs",
            "owner_payments",
            "lot_payments",
            "notes",
            "lots",
            "owners",
            "financial_transactions",
            "financial_monthly",
            "financial_accounts",
        ]:
            connection.execute(f"DELETE FROM {table}")

        owner_map: dict[str, tuple] = {}
        owner_note_lookup: dict[int, str] = {}
        for row in owners:
            owner_code = _owner_code(row.get("OWNR_CODE"))
            if not owner_code:
                continue
            note_number = row.get("NOTENUMBR")
            if isinstance(note_number, float):
                note_number = int(note_number)
            if isinstance(note_number, int) and note_number:
                owner_note_lookup[note_number] = owner_code

            existing = owner_map.get(owner_code)
            candidate = (
                owner_code,
                _as_text(row.get("LAST_NAME")),
                _as_text(row.get("FIRST_NAME")),
                _as_text(row.get("SECND_OWNR")),
                note_number,
                _as_text(row.get("ADDRESS")),
                _as_text(row.get("CITY")),
                _as_text(row.get("STATE")),
                _as_text(row.get("ZIP")),
                _as_text(row.get("PHONE")),
                _as_text(row.get("STATUS")),
                _as_text(row.get("RESIDENT")),
                _as_text(row.get("PLAT")),
                _as_text(row.get("CURRENT")),
                _parse_char_date(_as_text(row.get("SALE_DATE")) or ""),
                _as_text(row.get("HOLD_MAIL")),
                _as_text(row.get("INEL")),
                _as_text(row.get("COLL")),
                _as_text(row.get("COLLDATE")),
                _as_text(row.get("LIEN")),
                int(row.get("NUMBR_LOTS") or 0),
                _as_text(row.get("LOT_NUMBER")),
                _as_money(row.get("TOTAL_OWED")),
            )
            if existing is None:
                owner_map[owner_code] = candidate
                continue

            existing_lot = existing[21]
            candidate_lot = candidate[21]
            owner_map[owner_code] = (
                owner_code,
                existing[1] or candidate[1],
                existing[2] or candidate[2],
                existing[3] or candidate[3],
                existing[4] or candidate[4],
                existing[5] or candidate[5],
                existing[6] or candidate[6],
                existing[7] or candidate[7],
                existing[8] or candidate[8],
                existing[9] or candidate[9],
                existing[10] or candidate[10],
                existing[11] or candidate[11],
                existing[12] or candidate[12],
                existing[13] or candidate[13],
                existing[14] or candidate[14],
                existing[15] or candidate[15],
                existing[16] or candidate[16],
                existing[17] or candidate[17],
                existing[18] or candidate[18],
                existing[19] or candidate[19],
                max(existing[20], candidate[20]),
                existing_lot or candidate_lot,
                max(existing[22], candidate[22]),
            )

        owner_rows = list(owner_map.values())

        connection.executemany(
            """
            INSERT INTO owners (
                owner_code,
                last_name,
                first_name,
                secondary_owner_flag,
                note_number,
                address,
                city,
                state,
                zip,
                phone,
                status,
                resident_flag,
                plat,
                current_flag,
                sale_date,
                hold_mail_flag,
                ineligible_flag,
                collection_flag,
                collection_date,
                lien_flag,
                number_lots,
                primary_lot_number,
                total_owed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            owner_rows,
        )
        valid_owner_codes = {row[0] for row in owner_rows}

        lot_rows = []
        for row in lots:
            owner_code = _owner_code(row.get("OWNR_CODE"))
            if owner_code not in valid_owner_codes:
                owner_code = None
            lot_rows.append(
                (
                    _as_text(row.get("LOT_NUMBER")),
                    owner_code,
                    _as_money(row.get("CURR_ASMT")),
                    _as_money(row.get("DELIN_ASMT")),
                    _as_money(row.get("DELIN_INT")),
                    _as_money(row.get("CURR_INT")),
                    _as_money(row.get("TOT_DUE")),
                    _as_money(row.get("PAYMENT")),
                    _parse_char_date(_as_text(row.get("P_REV_DATE")) or ""),
                    _parse_char_date(_as_text(row.get("L_REV_DATE")) or ""),
                    _parse_char_date(_as_text(row.get("PAY_DATE")) or ""),
                    _as_text(row.get("PAID_THRU")),
                    _as_text(row.get("PMT_FORM")),
                    _as_text(row.get("LIEN")),
                    _as_text(row.get("LAKEFRONT")),
                    _as_text(row.get("DOCK")),
                    _as_text(row.get("DEVEL_STAT")),
                    _as_text(row.get("CLT")),
                    _as_text(row.get("FREEZE")),
                    _as_money(row.get("APPVALUE")),
                    _as_money(row.get("ASSDVALUE")),
                    int(row.get("NOTENUMBR") or 0),
                    _as_money(row.get("LIEN_AMNT")),
                    _as_text(row.get("LIEN_ON")),
                    _as_text(row.get("LIEN_OFF")),
                    _as_text(row.get("LN_BOOKPG")),
                    int(row.get("LIEN_BOOK") or 0),
                    int(row.get("LIEN_PAGE") or 0),
                )
            )

        connection.executemany(
            """
            INSERT INTO lots (
                lot_number,
                owner_code,
                current_assessment,
                delinquent_assessment,
                delinquent_interest,
                current_interest,
                total_due,
                payment_amount,
                previous_review_date,
                last_review_date,
                pay_date,
                paid_through,
                payment_form,
                lien_flag,
                lakefront_flag,
                dock_flag,
                development_status,
                collection_flag,
                freeze_flag,
                appraised_value,
                assessed_value,
                note_number,
                lien_amount,
                lien_on_date,
                lien_off_date,
                lien_book_page,
                lien_book,
                lien_page
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            lot_rows,
        )
        valid_lot_numbers = {row[0] for row in lot_rows if row[0]}

        owner_payment_rows = []
        for row in owner_payments:
            owner_code = _owner_code(row.get("OWNR_CODE"))
            if not owner_code or owner_code not in valid_owner_codes:
                continue
            owner_payment_rows.append(
                (
                    owner_code,
                    _as_money(row.get("PAY_AMT")),
                    _as_money(row.get("TOTAL_OWED")),
                    _parse_char_date(_as_text(row.get("PAY_DATE")) or ""),
                    _as_text(row.get("PMT_FORM")),
                    _as_text(row.get("CHKNO")),
                )
            )

        connection.executemany(
            """
            INSERT INTO owner_payments (
                owner_code,
                payment_amount,
                total_owed,
                payment_date,
                payment_form,
                check_number
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            owner_payment_rows,
        )

        lot_payment_rows = []
        for row in lot_payments:
            owner_code = _owner_code(row.get("OWNR_CODE"))
            lot_number = _as_text(row.get("LOT_NUMBER"))
            if not lot_number or lot_number not in valid_lot_numbers:
                continue
            if owner_code not in valid_owner_codes:
                owner_code = None
            lot_payment_rows.append(
                (
                    lot_number,
                    owner_code,
                    _as_money(row.get("PAY_AMT")),
                    _parse_char_date(_as_text(row.get("PAY_DATE")) or ""),
                    _as_text(row.get("PMT_FORM")),
                    _as_text(row.get("CHKNO")),
                    int(row.get("NMBR_LOTS") or 0),
                    _as_money(row.get("DEL_ASMT1")),
                    _as_money(row.get("DEL_INT1")),
                    _as_money(row.get("CUR_ASMT1")),
                    _as_money(row.get("CUR_INT1")),
                    _as_money(row.get("DEL_ASMT2")),
                    _as_money(row.get("DEL_INT2")),
                    _as_money(row.get("CUR_ASMT2")),
                    _as_money(row.get("CUR_INT2")),
                    _as_money(row.get("TOTPD")),
                    _as_text(row.get("POST")),
                    _as_text(row.get("PMETH")),
                )
            )

        connection.executemany(
            """
            INSERT INTO lot_payments (
                lot_number,
                owner_code,
                payment_amount,
                payment_date,
                payment_form,
                check_number,
                number_lots,
                delinquent_assessment_1,
                delinquent_interest_1,
                current_assessment_1,
                current_interest_1,
                delinquent_assessment_2,
                delinquent_interest_2,
                current_assessment_2,
                current_interest_2,
                total_posted,
                posted_flag,
                payment_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            lot_payment_rows,
        )

        note_rows = []
        for row in notes:
            note_number = int(row.get("NOTENUMBR") or 0)
            note_rows.append(
                (
                    owner_note_lookup.get(note_number),
                    note_number,
                    _as_text(row.get("NOTETEXT")) or "",
                    _as_text(row.get("REVDATE")),
                )
            )

        connection.executemany(
            """
            INSERT INTO notes (
                owner_code,
                note_number,
                note_text,
                review_date
            ) VALUES (?, ?, ?, ?)
            """,
            note_rows,
        )

        account_rows = []
        account_year_map: dict[str, str] = {}
        for row in financial_accounts:
            account_code = _as_text(row.get("ACTCODE"))
            fiscal_year = _as_text(row.get("FISYEAR")) or default_financial_year
            account_rows.append(
                (
                    account_code,
                    _as_text(row.get("ACTNAME")) or "",
                    _as_text(row.get("CATGY")),
                    fiscal_year,
                    _as_money(row.get("BUDMO")),
                    _as_money(row.get("BUDYR")),
                    _as_text(row.get("BUDCHNG")) or _as_text(row.get("EVENDIST")),
                )
            )
            if account_code:
                account_year_map[account_code] = fiscal_year
        connection.executemany(
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
            account_rows,
        )
        valid_account_codes = {row[0] for row in account_rows if row[0]}

        monthly_rows = []
        for row in financial_monthly:
            account_code = _as_text(row.get("ACTCODE"))
            if account_code not in valid_account_codes:
                continue
            monthly_rows.append(
                (
                    account_code,
                    account_year_map.get(account_code, ""),
                    int(row.get("FISMNTH") or 0),
                    int(row.get("CALMNTH") or 0),
                    _as_money(row.get("PRV")),
                    _as_money(row.get("MTDX")),
                    _as_money(row.get("MTDD")),
                    _as_money(row.get("YTD")),
                    _as_money(row.get("BUDTD")),
                    _as_money(row.get("BUDMO")),
                    _as_money(row.get("BUDYR")),
                    _as_text(row.get("FILESTAT")),
                )
            )
        connection.executemany(
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            monthly_rows,
        )

        transaction_rows = []
        for row in financial_transactions:
            account_code = _as_text(row.get("ACTCODE"))
            if account_code not in valid_account_codes:
                continue
            entry_date = _parse_char_date(_as_text(row.get("ENTRYDATE")) or "")
            transaction_date = _parse_char_date(_as_text(row.get("TRANSDATE")) or "")
            fiscal_year = ""
            if transaction_date and len(transaction_date) >= 4:
                fiscal_year = transaction_date[:4]
            elif entry_date and len(entry_date) >= 4:
                fiscal_year = entry_date[:4]
            else:
                fiscal_year = account_year_map.get(account_code, default_financial_year)
            transaction_rows.append(
                (
                    _as_text(row.get("TRANSNMBR")),
                    fiscal_year,
                    int(row.get("MONTH") or 0),
                    entry_date,
                    transaction_date,
                    _as_text(row.get("MONTH")),
                    account_code,
                    _as_money(row.get("AMOUNT")),
                    _as_text(row.get("PAIDTO")),
                    _as_text(row.get("FOR")),
                    _as_text(row.get("REFNMBR")),
                    _as_text(row.get("CHKNMBR")),
                    _as_text(row.get("PARCHK")),
                    _as_text(row.get("HOWPAID")),
                    _as_text(row.get("PCTRANSNBR")),
                    _as_text(row.get("DISP")),
                    _as_text(row.get("TYPE")),
                    _as_text(row.get("TRANSTAT")),
                )
            )
        connection.executemany(
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
            transaction_rows,
        )

        connection.execute(
            """
            UPDATE import_runs
            SET
                status = ?,
                owners_imported = ?,
                lots_imported = ?,
                owner_payments_imported = ?,
                lot_payments_imported = ?,
                notes_imported = ?,
                finished_at = ?
            WHERE id = ?
            """,
            [
                "completed",
                len(owner_rows),
                len(lot_rows),
                len(owner_payment_rows),
                len(lot_payment_rows),
                len(note_rows),
                datetime.now().isoformat(timespec="seconds"),
                run_id,
            ],
        )
        connection.commit()

    return {
        "owners_imported": len(owner_rows),
        "lots_imported": len(lot_rows),
        "owner_payments_imported": len(owner_payment_rows),
        "lot_payments_imported": len(lot_payment_rows),
        "notes_imported": len(note_rows),
        "financial_accounts_imported": len(account_rows),
        "financial_monthly_imported": len(monthly_rows),
        "financial_transactions_imported": len(transaction_rows),
    }


def import_legacy_financials_only(source_dir: Path, sqlite_path: Path) -> dict[str, int]:
    source_dir = source_dir.resolve()
    sqlite_path = sqlite_path.resolve()

    financial_accounts = _read_dbf(source_dir / "STDBUDFL.DBF")
    financial_monthly = _read_dbf(source_dir / "INEXFILE.DBF")
    financial_transactions = _read_dbf(source_dir / "TRANSFIL.DBF")
    default_financial_year = _default_financial_year(financial_accounts, financial_transactions)

    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("DELETE FROM financial_transactions")
        connection.execute("DELETE FROM financial_monthly")
        connection.execute("DELETE FROM financial_accounts")

        account_rows = []
        account_year_map: dict[str, str] = {}
        for row in financial_accounts:
            account_code = _as_text(row.get("ACTCODE"))
            fiscal_year = _as_text(row.get("FISYEAR")) or default_financial_year
            account_rows.append(
                (
                    account_code,
                    _as_text(row.get("ACTNAME")) or "",
                    _as_text(row.get("CATGY")),
                    fiscal_year,
                    _as_money(row.get("BUDMO")),
                    _as_money(row.get("BUDYR")),
                    _as_text(row.get("BUDCHNG")) or _as_text(row.get("EVENDIST")),
                )
            )
            if account_code:
                account_year_map[account_code] = fiscal_year
        connection.executemany(
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
            account_rows,
        )
        valid_account_codes = {row[0] for row in account_rows if row[0]}

        monthly_rows = []
        for row in financial_monthly:
            account_code = _as_text(row.get("ACTCODE"))
            if account_code not in valid_account_codes:
                continue
            monthly_rows.append(
                (
                    account_code,
                    account_year_map.get(account_code, ""),
                    int(row.get("FISMNTH") or 0),
                    int(row.get("CALMNTH") or 0),
                    _as_money(row.get("PRV")),
                    _as_money(row.get("MTDX")),
                    _as_money(row.get("MTDD")),
                    _as_money(row.get("YTD")),
                    _as_money(row.get("BUDTD")),
                    _as_money(row.get("BUDMO")),
                    _as_money(row.get("BUDYR")),
                    _as_text(row.get("FILESTAT")),
                )
            )
        connection.executemany(
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            monthly_rows,
        )

        transaction_rows = []
        for row in financial_transactions:
            account_code = _as_text(row.get("ACTCODE"))
            if account_code not in valid_account_codes:
                continue
            entry_date = _parse_char_date(_as_text(row.get("ENTRYDATE")) or "")
            transaction_date = _parse_char_date(_as_text(row.get("TRANSDATE")) or "")
            fiscal_year = ""
            if transaction_date and len(transaction_date) >= 4:
                fiscal_year = transaction_date[:4]
            elif entry_date and len(entry_date) >= 4:
                fiscal_year = entry_date[:4]
            else:
                fiscal_year = account_year_map.get(account_code, default_financial_year)
            transaction_rows.append(
                (
                    _as_text(row.get("TRANSNMBR")),
                    fiscal_year,
                    int(row.get("MONTH") or 0),
                    entry_date,
                    transaction_date,
                    _as_text(row.get("MONTH")),
                    account_code,
                    _as_money(row.get("AMOUNT")),
                    _as_text(row.get("PAIDTO")),
                    _as_text(row.get("FOR")),
                    _as_text(row.get("REFNMBR")),
                    _as_text(row.get("CHKNMBR")),
                    _as_text(row.get("PARCHK")),
                    _as_text(row.get("HOWPAID")),
                    _as_text(row.get("PCTRANSNBR")),
                    _as_text(row.get("DISP")),
                    _as_text(row.get("TYPE")),
                    _as_text(row.get("TRANSTAT")),
                )
            )
        connection.executemany(
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
            transaction_rows,
        )
        connection.commit()

    return {
        "financial_accounts_imported": len(account_rows),
        "financial_monthly_imported": len(monthly_rows),
        "financial_transactions_imported": len(transaction_rows),
    }
