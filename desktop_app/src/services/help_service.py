from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScreenHelp:
    title: str
    summary: str
    actions: tuple[str, ...]


SCREEN_HELP: dict[str, ScreenHelp] = {
    "dashboard": ScreenHelp(
        title="Home",
        summary="Use this screen to see what needs attention before starting daily work.",
        actions=(
            "Review balances due, liens, freeze lots, and recent activity.",
            "Use the sidebar to jump into the task you need next.",
        ),
    ),
    "owners_lots": ScreenHelp(
        title="Owners and Lots",
        summary="Use this screen to find an owner or lot, review the record, and revise basic information.",
        actions=(
            "Search by owner name, owner code, or lot number.",
            "Save Owner Changes updates the owner contact and status fields.",
            "Save Lot Changes updates the selected lot detail fields.",
            "Save Note adds a new note to the selected owner record.",
        ),
    ),
    "payments": ScreenHelp(
        title="Payments",
        summary="Use this screen to post assessment payments for one owner.",
        actions=(
            "Select the owner, then check one or more lots.",
            "Enter the payment amount and review the allocations.",
            "Post Payment saves the payment and creates a backup first.",
        ),
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
    ),
    "liens_collection": ScreenHelp(
        title="Liens / Collection",
        summary="Use this screen to manage lien and collection flags on selected lots.",
        actions=(
            "Select the owner and check the lots you want to change.",
            "File Lien or Remove Lien updates lien status and dates.",
            "Assign To Collection or Remove From Collection updates collection flags.",
        ),
    ),
    "payment_history": ScreenHelp(
        title="Payment History",
        summary="Use this screen to review previously posted payments.",
        actions=(
            "Search by owner, lot, date, or check/reference number.",
            "Select a payment to review the full detail and audit values.",
        ),
    ),
    "notices": ScreenHelp(
        title="Notices",
        summary="Use this screen to prepare and print assessment notices as PDFs.",
        actions=(
            "Choose individual, all-owner, or lien-only notice mode.",
            "Create Selected PDF prints one owner notice.",
            "Create Batch PDF creates separate notice PDFs for the current batch.",
        ),
    ),
    "assessments": ScreenHelp(
        title="Assessments",
        summary="Use this screen to preview and post a new assessment across eligible lots.",
        actions=(
            "Preview Assessment Run shows what will change before you post it.",
            "Apply Assessment Update saves the run and creates a backup first.",
        ),
    ),
    "cards_stickers": ScreenHelp(
        title="Boat / ID Cards",
        summary="Use this screen to record boat sticker purchases and issue ID cards.",
        actions=(
            "Select the owner and the related lot.",
            "Record Boat Sticker Purchase saves the purchase and opens a receipt PDF.",
            "Issue ID Card saves the issue record and opens a receipt PDF.",
        ),
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
    ),
    "reports": ScreenHelp(
        title="Reports",
        summary="Use this screen to open owner, lot, and mailing-label PDF reports.",
        actions=(
            "Owner Report prints owner-level records.",
            "Lot Report prints lot-level records.",
            "Mailing Labels prints mailing label output from owner addresses.",
        ),
    ),
    "utilities": ScreenHelp(
        title="Utilities",
        summary="Use this screen for data checks and controlled refresh from dBase.",
        actions=(
            "Run Data Health Checks reviews duplicates, mismatches, and missing links.",
            "Refresh From dBase re-imports the legacy data while dBase is still the source of truth.",
            "Check for Updates looks for a newer Windows installer and can download it into the local updates folder.",
        ),
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
