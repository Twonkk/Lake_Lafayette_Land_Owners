from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScreenHelp:
    title: str
    summary: str
    actions: tuple[str, ...]
    legacy_reference: str | None = None


SCREEN_HELP: dict[str, ScreenHelp] = {
    "menu": ScreenHelp(
        title="Menu",
        summary="Use the familiar dBase group and option numbers without typing commands.",
        actions=(
            "Choose Group 1 for owner, property, assessment, lien, card, and label work.",
            "Choose Group 2 for transactions, budgets, month closing, and financial reports.",
            "Choose Group 3 for record checks, dBase refresh, backups, and updates.",
        ),
        legacy_reference="This replaces the original dBase main MENU.PRG screen and preserves its 1, 2, and 3 group order.",
    ),
    "migration_review": ScreenHelp(
        title="Migration Review",
        summary="Use this screen with the client to decide how incomplete or inconsistent dBase records should be handled.",
        actions=(
            "Complete this review after the final dBase refresh; recorded decisions are protected from being overwritten by another refresh.",
            "Select an item to see the source evidence, explanation, and recommended decision.",
            "Restore Suggested Owner uses a recoverable deleted or backup owner record only after confirmation.",
            "Enter Owner Details lets the client supply a missing current owner's verified information.",
            "Keep as Historical preserves payment and property history without treating the code as a current owner.",
            "Accept X-Lot Exclusion records that a special frozen X lot should remain outside current assessments.",
            "Use Lot Balance Total or Keep dBase Owner Total resolves small legacy rounding differences.",
            "Delete is available only when no lot, payment, sale, note, or history record refers to the placeholder.",
        ),
        legacy_reference="This is a migration-safety screen added for records that the original dBase menus could hide or leave inconsistent.",
    ),
    "owners_lots": ScreenHelp(
        title="Owners and Lots",
        summary="Use this screen to find an owner or lot, review the record, and revise basic information.",
        actions=(
            "Search by owner name, owner code, or lot number.",
            "Open Payment History to see this owner's imported dBase and new-app payments.",
            "Open This Owner's History PDF creates a printable payment history for only the selected owner.",
            "Save Owner Changes updates the owner contact and status fields.",
            "Save Lot Changes updates the selected lot detail fields.",
            "Save Note adds a new note to the selected owner record.",
        ),
        legacy_reference="In dBase: Group 1, option 1 — Revise or Review Individual Owner Info or Lot Info.",
    ),
    "payments": ScreenHelp(
        title="Payments",
        summary="Use this screen to post assessment payments using the four familiar dBase categories.",
        actions=(
            "Select the owner and lot, then choose Distribute Selected Lot Payment.",
            "Enter current assessment, current interest, delinquent assessment, and delinquent interest amounts.",
            "For a full payment, enter Paid through and choose Fill Full Owner Balance.",
            "Post Payment saves the payment and creates a backup first.",
        ),
        legacy_reference="In dBase: Group 1, option 2 — Record Payment of Assessments.",
    ),
    "property_sales": ScreenHelp(
        title="Property Sales",
        summary="Use this screen to transfer lots from a seller to a buyer or reverse a prior sale.",
        actions=(
            "Select a seller and check the lots being sold.",
            "Choose an existing buyer or mark the buyer as a new owner.",
            "Record Sale / Purchase saves the transfer and opens the receipt PDF.",
            "Reverse Selected Sale undoes the highlighted recent sale group.",
        ),
        legacy_reference="In dBase: Group 1, options 5 and 6 — Record or Reverse a Property Sale.",
    ),
    "liens_collection": ScreenHelp(
        title="Liens / Collection",
        summary="Use this screen to manage lien and collection flags on selected lots.",
        actions=(
            "Select the owner and check the lots you want to change.",
            "File Lien or Remove Lien updates lien status and dates.",
            "Assign To Collection or Remove From Collection updates collection flags.",
        ),
        legacy_reference="In dBase: Group 1, options 8 and 9 — Liens and Collection Agency.",
    ),
    "payment_history": ScreenHelp(
        title="Payment History",
        summary="Use this screen to review complete owner payment history from dBase and this app.",
        actions=(
            "Search by owner name, owner code, payment date, form, or check/reference number.",
            "Select a payment to review the owner's owed amount, amount paid, and resulting balance.",
            "PDF for Selected Owner prints the complete payment history for only that owner.",
            "PDF for Current Results prints the rows shown on the active history tab.",
            "Payments recorded in this app also show the distribution across the owner's lots.",
        ),
        legacy_reference="In dBase: Group 1, option 10 — Display History Records.",
    ),
    "notices": ScreenHelp(
        title="Notices",
        summary="Use this screen to prepare and print assessment notices as PDFs.",
        actions=(
            "Choose individual, all-owner, or lien-only notice mode.",
            "Create Selected PDF prints one owner notice.",
            "Open Batch PDFs creates multi-page PDFs for every eligible owner, split by the batch size.",
        ),
        legacy_reference="In dBase: Group 1, option 4 — Print Assessment Notices.",
    ),
    "assessments": ScreenHelp(
        title="Assessments",
        summary="Use this screen to preview and post a new assessment across eligible lots.",
        actions=(
            "Preview Assessment Run shows what will change before you post it.",
            "Apply Assessment Update saves the run and creates a backup first.",
        ),
        legacy_reference="In dBase: Group 1, option 3 — Update All Records for a New Assessment Due.",
    ),
    "cards_stickers": ScreenHelp(
        title="Boat / ID Cards",
        summary="Use this screen to record boat sticker purchases and issue ID cards.",
        actions=(
            "Select the owner and the related lot.",
            "Record Boat Sticker Purchase saves the purchase and opens a receipt PDF.",
            "Issue ID Card saves the issue record and opens a receipt PDF.",
        ),
        legacy_reference="In dBase: Group 1, options 11 and 12 — Boat Stickers and ID Cards.",
    ),
    "financials": ScreenHelp(
        title="Financials",
        summary="Use this screen to manage financial transactions, accounts, budgets, and reports.",
        actions=(
            "Post Transaction saves a normal transaction in the selected fiscal period.",
            "Record Earlier Transaction posts an older-dated item into the selected fiscal period.",
            "Close Month marks the current fiscal month closed and rolls forward to the next one.",
            "Accounts / Budget handles account maintenance and budget edits.",
            "Monthly Report contains the financial PDF outputs.",
        ),
        legacy_reference="In dBase: Group 2, options 1–10 — Financial Records.",
    ),
    "reports": ScreenHelp(
        title="Reports",
        summary="Use this screen to open owner, lot, and mailing-label PDF reports.",
        actions=(
            "Owner Report prints owner-level records.",
            "Lot Report prints lot-level records.",
            "Mailing Labels prints mailing label output from owner addresses.",
        ),
        legacy_reference="In dBase: Group 1, options 7 and 13 — Reports and Mailing Labels.",
    ),
    "utilities": ScreenHelp(
        title="Utilities",
        summary="Use this screen for data checks and controlled refresh from dBase.",
        actions=(
            "Run Data Health Checks reviews duplicates, mismatches, and missing links.",
            "Browse and Refresh From dBase lets you choose and validate a newly copied dBase backup folder before importing it.",
            "Check for Updates looks for a newer Windows installer and can download it into the local updates folder.",
        ),
        legacy_reference="In dBase: Group 3 — Reindex All Files and Run File Test. SQLite handles indexes automatically; use record checks here.",
    ),
    "initial_setup": ScreenHelp(
        title="Initial Setup",
        summary="Use this screen on first launch to import the legacy dBase data into the new app.",
        actions=(
            "Confirm or browse to the legacy dBase folder.",
            "Run the import to populate the app database before daily use.",
        ),
    ),
}


def get_screen_help(screen_key: str) -> ScreenHelp | None:
    return SCREEN_HELP.get(screen_key)
