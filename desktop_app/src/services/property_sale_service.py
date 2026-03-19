from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import shutil

from src.db.connection import get_connection
from src.services.pdf_service import build_pdf_path, write_preformatted_pages_pdf


@dataclass(slots=True)
class NewBuyerRequest:
    last_name: str
    first_name: str
    address: str
    city: str
    state: str
    zip_code: str
    phone: str = ""


@dataclass(slots=True)
class PropertySaleRequest:
    seller_owner_code: str
    lot_numbers: list[str]
    sale_date: str
    buyer_owner_code: str = ""
    new_buyer: NewBuyerRequest | None = None


@dataclass(slots=True)
class PropertySaleResult:
    backup_path: str
    seller_owner_code: str
    buyer_owner_code: str
    transferred_lots: list[str]


@dataclass(slots=True)
class PropertySaleReceiptLine:
    lot_number: str
    sale_date: str
    seller_owner_code: str
    buyer_owner_code: str
    seller_name: str
    buyer_name: str
    recorded_on: str
    seller_note: str
    buyer_note: str


@dataclass(slots=True)
class PropertySaleGroup:
    created_at: str
    sale_date: str
    seller_owner_code: str
    buyer_owner_code: str


@dataclass(slots=True)
class PropertySaleReverseResult:
    backup_path: str
    seller_owner_code: str
    buyer_owner_code: str
    returned_lots: list[str]


def default_sale_date() -> str:
    return date.today().isoformat()


def _make_backup(db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}_sale_{stamp}.sqlite3"
    shutil.copy2(db_path, backup_path)
    return backup_path


def _safe_float(value: object) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _next_owner_code(connection) -> str:
    row = connection.execute(
        """
        SELECT COALESCE(MAX(CAST(owner_code AS INTEGER)), 0) + 1 AS next_code
        FROM owners
        WHERE TRIM(owner_code) <> ''
        """
    ).fetchone()
    return str(int(row["next_code"] or 1))


def _owner_summary(connection, owner_code: str) -> tuple[int, float, str]:
    row = connection.execute(
        """
        SELECT
            COUNT(*) AS lot_count,
            COALESCE(SUM(total_due), 0) AS total_owed,
            MIN(lot_number) AS primary_lot
        FROM lots
        WHERE owner_code = ?
        """,
        [owner_code],
    ).fetchone()
    return (
        int(row["lot_count"] or 0),
        round(_safe_float(row["total_owed"]), 2),
        str(row["primary_lot"] or ""),
    )


def record_property_sale(db_path: Path, request: PropertySaleRequest) -> PropertySaleResult:
    seller_owner_code = request.seller_owner_code.strip()
    if not seller_owner_code:
        raise ValueError("Select a seller first.")
    lot_numbers = sorted({lot.strip().upper() for lot in request.lot_numbers if lot.strip()})
    if not lot_numbers:
        raise ValueError("Select at least one lot to transfer.")
    if not request.sale_date.strip():
        raise ValueError("Sale date is required.")

    use_new_buyer = request.new_buyer is not None
    if use_new_buyer:
        buyer_owner_code = ""
    else:
        buyer_owner_code = request.buyer_owner_code.strip()
        if not buyer_owner_code:
            raise ValueError("Select a buyer or enter a new buyer.")
    if buyer_owner_code and buyer_owner_code == seller_owner_code:
        raise ValueError("Buyer and seller cannot be the same owner.")

    backup_path = _make_backup(db_path)

    with get_connection(db_path) as connection:
        seller = connection.execute(
            "SELECT * FROM owners WHERE owner_code = ?",
            [seller_owner_code],
        ).fetchone()
        if seller is None:
            raise ValueError("Seller was not found.")

        connection.execute("BEGIN")
        timestamp = datetime.now().isoformat(timespec="seconds")

        if use_new_buyer:
            buyer = request.new_buyer
            assert buyer is not None
            if not buyer.last_name.strip():
                raise ValueError("New buyer last name is required.")
            buyer_owner_code = _next_owner_code(connection)
            connection.execute(
                """
                INSERT INTO owners (
                    owner_code,
                    last_name,
                    first_name,
                    address,
                    city,
                    state,
                    zip,
                    phone,
                    current_flag,
                    number_lots,
                    primary_lot_number,
                    total_owed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Y', 0, '', 0)
                """,
                [
                    buyer_owner_code,
                    buyer.last_name.strip().upper(),
                    buyer.first_name.strip().upper(),
                    buyer.address.strip().upper(),
                    buyer.city.strip().upper(),
                    buyer.state.strip().upper(),
                    buyer.zip_code.strip(),
                    buyer.phone.strip(),
                ],
            )
        else:
            buyer_row = connection.execute(
                "SELECT * FROM owners WHERE owner_code = ?",
                [buyer_owner_code],
            ).fetchone()
            if buyer_row is None:
                raise ValueError("Buyer was not found.")

        for lot_number in lot_numbers:
            lot = connection.execute(
                """
                SELECT lot_number, owner_code
                FROM lots
                WHERE lot_number = ?
                """,
                [lot_number],
            ).fetchone()
            if lot is None:
                raise ValueError(f"Lot {lot_number} was not found.")
            if str(lot["owner_code"] or "") != seller_owner_code:
                raise ValueError(f"Lot {lot_number} does not belong to the selected seller.")

        for lot_number in lot_numbers:
            connection.execute(
                """
                UPDATE lots
                SET owner_code = ?
                WHERE lot_number = ?
                """,
                [buyer_owner_code, lot_number],
            )
            connection.execute(
                """
                INSERT INTO property_sales (
                    created_at,
                    sale_date,
                    lot_number,
                    seller_owner_code,
                    buyer_owner_code,
                    new_buyer_flag,
                    backup_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    timestamp,
                    request.sale_date.strip(),
                    lot_number,
                    seller_owner_code,
                    buyer_owner_code,
                    "Y" if use_new_buyer else "N",
                    str(backup_path),
                ],
            )

        seller_lot_count, seller_total_owed, seller_primary_lot = _owner_summary(connection, seller_owner_code)
        buyer_lot_count, buyer_total_owed, buyer_primary_lot = _owner_summary(connection, buyer_owner_code)

        connection.execute(
            """
            UPDATE owners
            SET
                number_lots = ?,
                total_owed = ?,
                primary_lot_number = ?,
                sale_date = ?,
                current_flag = ?,
                plat = CASE
                    WHEN ? <> '' THEN SUBSTR(?, 1, 1)
                    ELSE ''
                END
            WHERE owner_code = ?
            """,
            [
                seller_lot_count,
                seller_total_owed,
                seller_primary_lot,
                request.sale_date.strip(),
                "Y" if seller_lot_count > 0 else "N",
                seller_primary_lot,
                seller_primary_lot,
                seller_owner_code,
            ],
        )
        connection.execute(
            """
            UPDATE owners
            SET
                number_lots = ?,
                total_owed = ?,
                primary_lot_number = ?,
                sale_date = '',
                current_flag = 'Y',
                plat = CASE
                    WHEN ? <> '' THEN SUBSTR(?, 1, 1)
                    ELSE plat
                END
            WHERE owner_code = ?
            """,
            [
                buyer_lot_count,
                buyer_total_owed,
                buyer_primary_lot,
                buyer_primary_lot,
                buyer_primary_lot,
                buyer_owner_code,
            ],
        )
        connection.commit()

    return PropertySaleResult(
        backup_path=str(backup_path),
        seller_owner_code=seller_owner_code,
        buyer_owner_code=buyer_owner_code,
        transferred_lots=lot_numbers,
    )


def build_property_sale_receipt_lines(db_path: Path, sale_result: PropertySaleResult) -> list[PropertySaleReceiptLine]:
    with get_connection(db_path) as connection:
        seller = connection.execute(
            "SELECT owner_code, first_name, last_name, number_lots FROM owners WHERE owner_code = ?",
            [sale_result.seller_owner_code],
        ).fetchone()
        buyer = connection.execute(
            "SELECT owner_code, first_name, last_name, number_lots FROM owners WHERE owner_code = ?",
            [sale_result.buyer_owner_code],
        ).fetchone()
        sales = connection.execute(
            """
            SELECT created_at, sale_date, lot_number
            FROM property_sales
            WHERE seller_owner_code = ? AND buyer_owner_code = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            [sale_result.seller_owner_code, sale_result.buyer_owner_code, len(sale_result.transferred_lots)],
        ).fetchall()

    seller_name = " ".join(part for part in [seller["first_name"], seller["last_name"]] if part).strip() if seller else sale_result.seller_owner_code
    buyer_name = " ".join(part for part in [buyer["first_name"], buyer["last_name"]] if part).strip() if buyer else sale_result.buyer_owner_code
    seller_note = "SELLER OWNS NO MORE LOTS" if int(seller["number_lots"] or 0) == 0 else "SELLER STILL OWNS PROPERTY"
    buyer_note = "BUYER IS FIRST-TIME OWNER" if int(buyer["number_lots"] or 0) <= len(sale_result.transferred_lots) else "BUYER HAS OWNED OTHER LOTS"

    lines: list[PropertySaleReceiptLine] = []
    sales_by_lot = {row["lot_number"]: row for row in sales}
    for lot_number in sale_result.transferred_lots:
        sale = sales_by_lot.get(lot_number)
        created_at = str(sale["created_at"] or "") if sale else ""
        recorded_on = created_at[:10] if len(created_at) >= 10 else ""
        lines.append(
            PropertySaleReceiptLine(
                lot_number=lot_number,
                sale_date=str(sale["sale_date"] or "") if sale else "",
                seller_owner_code=sale_result.seller_owner_code,
                buyer_owner_code=sale_result.buyer_owner_code,
                seller_name=seller_name.upper(),
                buyer_name=buyer_name.upper(),
                recorded_on=recorded_on,
                seller_note=seller_note,
                buyer_note=buyer_note,
            )
        )
    return lines


def reverse_property_sale(db_path: Path, sale_group: PropertySaleGroup) -> PropertySaleReverseResult:
    backup_path = _make_backup(db_path)

    with get_connection(db_path) as connection:
        connection.execute("BEGIN")
        rows = connection.execute(
            """
            SELECT lot_number
            FROM property_sales
            WHERE
                created_at = ?
                AND sale_date = ?
                AND seller_owner_code = ?
                AND buyer_owner_code = ?
                AND reversed_at IS NULL
            ORDER BY lot_number
            """,
            [
                sale_group.created_at,
                sale_group.sale_date,
                sale_group.seller_owner_code,
                sale_group.buyer_owner_code,
            ],
        ).fetchall()
        if not rows:
            raise ValueError("That property sale could not be found or was already reversed.")

        lot_numbers = [str(row["lot_number"] or "") for row in rows]
        for lot_number in lot_numbers:
            lot = connection.execute(
                "SELECT owner_code FROM lots WHERE lot_number = ?",
                [lot_number],
            ).fetchone()
            if lot is None:
                raise ValueError(f"Lot {lot_number} was not found.")
            if str(lot["owner_code"] or "") != sale_group.buyer_owner_code:
                raise ValueError(
                    f"Lot {lot_number} is no longer owned by buyer {sale_group.buyer_owner_code}."
                )

        for lot_number in lot_numbers:
            connection.execute(
                """
                UPDATE lots
                SET owner_code = ?
                WHERE lot_number = ?
                """,
                [sale_group.seller_owner_code, lot_number],
            )

        seller_lot_count, seller_total_owed, seller_primary_lot = _owner_summary(
            connection, sale_group.seller_owner_code
        )
        buyer_lot_count, buyer_total_owed, buyer_primary_lot = _owner_summary(
            connection, sale_group.buyer_owner_code
        )

        connection.execute(
            """
            UPDATE owners
            SET
                number_lots = ?,
                total_owed = ?,
                primary_lot_number = ?,
                current_flag = ?,
                plat = CASE
                    WHEN ? <> '' THEN SUBSTR(?, 1, 1)
                    ELSE ''
                END
            WHERE owner_code = ?
            """,
            [
                seller_lot_count,
                seller_total_owed,
                seller_primary_lot,
                "Y" if seller_lot_count > 0 else "N",
                seller_primary_lot,
                seller_primary_lot,
                sale_group.seller_owner_code,
            ],
        )
        connection.execute(
            """
            UPDATE owners
            SET
                number_lots = ?,
                total_owed = ?,
                primary_lot_number = ?,
                current_flag = ?,
                plat = CASE
                    WHEN ? <> '' THEN SUBSTR(?, 1, 1)
                    ELSE ''
                END
            WHERE owner_code = ?
            """,
            [
                buyer_lot_count,
                buyer_total_owed,
                buyer_primary_lot,
                "Y" if buyer_lot_count > 0 else "N",
                buyer_primary_lot,
                buyer_primary_lot,
                sale_group.buyer_owner_code,
            ],
        )
        connection.execute(
            """
            UPDATE property_sales
            SET
                reversed_at = ?,
                reversal_backup_path = ?
            WHERE
                created_at = ?
                AND sale_date = ?
                AND seller_owner_code = ?
                AND buyer_owner_code = ?
                AND reversed_at IS NULL
            """,
            [
                datetime.now().isoformat(timespec="seconds"),
                str(backup_path),
                sale_group.created_at,
                sale_group.sale_date,
                sale_group.seller_owner_code,
                sale_group.buyer_owner_code,
            ],
        )
        connection.commit()

    return PropertySaleReverseResult(
        backup_path=str(backup_path),
        seller_owner_code=sale_group.seller_owner_code,
        buyer_owner_code=sale_group.buyer_owner_code,
        returned_lots=lot_numbers,
    )


def render_property_sale_receipt_pdf(
    receipt_lines: list[PropertySaleReceiptLine],
    output_dir: Path,
    file_stem: str,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = build_pdf_path(output_dir, f"{file_stem}_{timestamp}")
    pages: list[list[str]] = []
    for line in receipt_lines:
        seller_prefix = f"    SELLER: {line.seller_owner_code:<8} "
        buyer_prefix = f"    BUYER:  {line.buyer_owner_code:<8} "
        note_column = 52
        seller_gap = max(2, note_column - len(seller_prefix) - len(line.seller_name))
        buyer_gap = max(2, note_column - len(buyer_prefix) - len(line.buyer_name))
        row1 = (
            f"LOT NO: {line.lot_number:<4}         "
            f"SALE DATE: {line.sale_date:<15}"
            f"RECORDED ON: {line.recorded_on:<12}"
        )
        row2 = (
            f"{seller_prefix}"
            f"{line.seller_name}"
            f"{' ' * seller_gap}{line.seller_note}"
        )
        row3 = (
            f"{buyer_prefix}"
            f"{line.buyer_name}"
            f"{' ' * buyer_gap}{line.buyer_note}"
        )
        pages.append([row1, row2, row3])
    return write_preformatted_pages_pdf(
        output_path,
        pages,
        left_margin=0.05 * 72,
        top_margin=0.55 * 72,
        font_size=11,
        line_height=12.65,
        title="Property Sale Receipt",
    )
