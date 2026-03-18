from __future__ import annotations

from html import escape
from pathlib import Path

from src.db.connection import get_connection


def render_owner_report_html(db_path: Path, output_dir: Path) -> Path:
    with get_connection(db_path) as connection:
        owners = connection.execute(
            """
            SELECT
                o.owner_code,
                o.last_name,
                o.first_name,
                o.address,
                o.city,
                o.state,
                o.zip,
                o.phone,
                o.number_lots,
                o.total_owed,
                o.lien_flag,
                o.resident_flag
            FROM owners o
            ORDER BY o.last_name, o.first_name, o.owner_code
            """
        ).fetchall()
        rows = []
        for owner in owners:
            lots = connection.execute(
                """
                SELECT lot_number, total_due, lien_flag, collection_flag
                FROM lots
                WHERE owner_code = ?
                ORDER BY lot_number
                """,
                [owner["owner_code"]],
            ).fetchall()
            lot_list = ", ".join(row["lot_number"] for row in lots)
            rows.append(
                "<tr>"
                f"<td>{escape(owner['owner_code'] or '')}</td>"
                f"<td>{escape((owner['last_name'] or '') + ' ' + (owner['first_name'] or ''))}</td>"
                f"<td>{escape(owner['address'] or '')}</td>"
                f"<td>{escape((owner['city'] or '') + ', ' + (owner['state'] or '') + ' ' + (owner['zip'] or ''))}</td>"
                f"<td>{escape(owner['phone'] or '')}</td>"
                f"<td>{int(owner['number_lots'] or 0)}</td>"
                f"<td>{escape(owner['resident_flag'] or '')}</td>"
                f"<td>{escape(owner['lien_flag'] or '')}</td>"
                f"<td>{escape(lot_list)}</td>"
                f"<td class='num'>{float(owner['total_owed'] or 0):,.2f}</td>"
                "</tr>"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / "owner_report.html"
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>Owner Report</title>
      <style>
        body {{ font-family: Georgia, serif; margin: 24px; color: #111827; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 18px; }}
        th, td {{ border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; font-size: 12px; }}
        .num {{ text-align: right; }}
      </style>
    </head>
    <body>
      <h1>Owner Report</h1>
      <table>
        <thead>
          <tr>
            <th>Code</th>
            <th>Name</th>
            <th>Address</th>
            <th>City/State/ZIP</th>
            <th>Phone</th>
            <th>Lots</th>
            <th>Resident</th>
            <th>Lien</th>
            <th>Owned Lots</th>
            <th>Total Owed</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </body>
    </html>
    """
    file_path.write_text(html, encoding="utf-8")
    return file_path


def render_lot_report_html(db_path: Path, output_dir: Path) -> Path:
    with get_connection(db_path) as connection:
        lots = connection.execute(
            """
            SELECT
                l.lot_number,
                l.owner_code,
                o.last_name,
                o.first_name,
                o.address,
                o.phone,
                l.lien_flag,
                l.collection_flag,
                l.total_due,
                l.current_assessment,
                l.delinquent_assessment,
                l.delinquent_interest,
                l.current_interest
            FROM lots l
            LEFT JOIN owners o ON o.owner_code = l.owner_code
            ORDER BY l.lot_number
            """
        ).fetchall()
        rows = []
        for lot in lots:
            rows.append(
                "<tr>"
                f"<td>{escape(lot['lot_number'] or '')}</td>"
                f"<td>{escape(lot['owner_code'] or '')}</td>"
                f"<td>{escape((lot['last_name'] or '') + ' ' + (lot['first_name'] or ''))}</td>"
                f"<td>{escape(lot['address'] or '')}</td>"
                f"<td>{escape(lot['phone'] or '')}</td>"
                f"<td>{escape(lot['lien_flag'] or '')}</td>"
                f"<td>{escape(lot['collection_flag'] or '')}</td>"
                f"<td class='num'>{float(lot['delinquent_assessment'] or 0):,.2f}</td>"
                f"<td class='num'>{float(lot['delinquent_interest'] or 0):,.2f}</td>"
                f"<td class='num'>{float(lot['current_assessment'] or 0):,.2f}</td>"
                f"<td class='num'>{float(lot['current_interest'] or 0):,.2f}</td>"
                f"<td class='num'>{float(lot['total_due'] or 0):,.2f}</td>"
                "</tr>"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / "lot_report.html"
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>Lot Report</title>
      <style>
        body {{ font-family: Georgia, serif; margin: 24px; color: #111827; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 18px; }}
        th, td {{ border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; font-size: 12px; }}
        .num {{ text-align: right; }}
      </style>
    </head>
    <body>
      <h1>Lot Report</h1>
      <table>
        <thead>
          <tr>
            <th>Lot</th>
            <th>Owner Code</th>
            <th>Owner</th>
            <th>Address</th>
            <th>Phone</th>
            <th>Lien</th>
            <th>Collection</th>
            <th>Delinq. Assess.</th>
            <th>Delinq. Interest</th>
            <th>Current Assess.</th>
            <th>Current Interest</th>
            <th>Total Due</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </body>
    </html>
    """
    file_path.write_text(html, encoding="utf-8")
    return file_path


def render_mailing_labels_html(db_path: Path, output_dir: Path) -> Path:
    with get_connection(db_path) as connection:
        owners = connection.execute(
            """
            SELECT
                owner_code,
                primary_lot_number,
                last_name,
                first_name,
                address,
                city,
                state,
                zip
            FROM owners
            WHERE TRIM(COALESCE(address, '')) <> ''
            ORDER BY last_name, first_name, owner_code
            """
        ).fetchall()

    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / "mailing_labels.html"

    blocks: list[str] = []
    for owner in owners:
        name = " ".join(part for part in [owner["first_name"], owner["last_name"]] if part).strip().upper()
        address = str(owner["address"] or "").strip().upper()
        city = str(owner["city"] or "").strip().upper()
        state = str(owner["state"] or "").strip().upper()
        zip_code = str(owner["zip"] or "").strip().upper()
        top_line = f"{str(owner['primary_lot_number'] or '').strip().upper():<8}{str(owner['owner_code'] or '').strip().upper():>10}".rstrip()
        city_line = " ".join(part for part in [city, state, zip_code] if part).strip()
        blocks.append(
            "<div class='label-block'>"
            f"<pre>{escape(top_line)}\n{escape(name)}\n{escape(address)}\n{escape(city_line)}</pre>"
            "</div>"
        )

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>Mailing Labels</title>
      <style>
        @page {{ size: letter; margin: 0.28in 0.35in 0.28in 0.10in; }}
        body {{
          font-family: "Courier New", Courier, monospace;
          background: white;
          color: #1f2937;
          margin: 0;
        }}
        .page {{
          width: 100%;
          page-break-after: always;
        }}
        .label-block {{
          width: 3.35in;
          height: 0.97in;
          padding-top: 0.05in;
          box-sizing: border-box;
        }}
        .label-block pre {{
          margin: 0;
          white-space: pre;
          font-size: 11pt;
          line-height: 1.0;
          letter-spacing: 0.01em;
        }}
      </style>
    </head>
    <body>{''.join(blocks)}</body>
    </html>
    """
    file_path.write_text(html, encoding="utf-8")
    return file_path
