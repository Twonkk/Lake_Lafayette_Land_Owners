# Lake Lot Manager Intro

This file explains what each main button in the app does today.

## Initial Setup

- `Initial Setup`: used on first launch to import the legacy dBase data into the new app database. During the transition period, this is also the pattern used for controlled refresh from dBase.

## Main Navigation

- `Dashboard`: shows high-level totals, alerts, and recent activity such as balances due, lien counts, freeze lots, recent payments, and the latest assessment run.
- `Owners and Lots`: search for an owner or lot, review owner and lot details, revise owner information, revise selected lot information, and add notes.
- `Payments`: record assessment payments for one owner, including one payment split across multiple lots.
- `Property Sales`: record a sale or purchase of property, print the sale receipt, review recent sales, and reverse a selected prior sale.
- `Liens / Collection`: file a lien, remove a lien, assign selected lots to collection, or remove selected lots from collection.
- `Payment History`: search previously posted payments by owner, lot, date, or check/reference number and review the full payment detail.
- `Notices`: prepare and print assessment notices as PDFs for one owner or for a batch run.
- `Assessments`: preview and post a new assessment amount across all eligible lots.
- `Boat / ID Cards`: record boat sticker purchases and ID card issues and open a PDF receipt for each one.
- `Financials`: manage financial transactions, budgets, account maintenance, reports, and fiscal year/month operations.
- `Reports`: open owner reports, lot reports, and mailing labels as PDFs.
- `Utilities`: run data-health checks and refresh the app database from the legacy dBase folder while dBase is still the source of truth.

## Screen Details

### Owners and Lots

- `Search`: finds owners by name, owner code, primary lot, or owned lot number.
- `Save Owner Changes`: saves edits to owner name, address, contact fields, and basic flags.
- `Save Lot Changes`: saves edits to the selected lot’s non-financial detail fields.
- `Save Note`: adds a new note to the selected owner record.

### Payments

- owner list: choose the owner receiving the payment
- lot list: check one or more lots for the payment
- `Post Payment`: saves the payment, updates balances, records audit history, and creates a backup first
- allocation cells: let the user type the amount applied to each selected lot

### Property Sales

- seller search: find the current owner/seller
- lot checkboxes: choose which lots are being transferred
- buyer search or `Buyer is a new owner`: select an existing buyer or create a new buyer
- `Record Sale / Purchase`: saves the transfer and opens the sale receipt PDF
- `Reverse Selected Sale`: undoes the selected recent sale group and moves the lots back to the seller

### Liens / Collection

- lot checkboxes: choose which lots the lien or collection action applies to
- `File Lien On Selected Lots`: marks the lots with lien information
- `Remove Lien From Selected Lots`: clears lien flags and stores the removal date
- `Assign Selected Lots To Collection`: marks the lots and owner as in collection
- `Remove Selected Lots From Collection`: clears collection flags from the selected lots

### Notices

- search: narrows notice candidates
- mode chooser: `individual`, `all`, or `liens`
- batch size: sets how many owner notices belong to a batch grouping
- `Create Selected PDF`: builds and opens a single notice PDF
- `Create Batch PDF`: builds and opens a per-owner batch notice PDF set

### Assessments

- `Preview Assessment Run`: shows what the next assessment run will do before anything is changed
- `Apply Assessment Update`: posts the assessment run, updates balances, and creates a backup first

### Boat / ID Cards

- owner search: selects the owner
- lot selector: ties the record to one of the owner’s lots when needed
- `Record Boat Sticker Purchase`: records the purchase and opens a PDF receipt
- `Issue ID Card`: records the ID card issue and opens a PDF receipt

### Financials

- `Refresh`: reloads the selected fiscal year/month
- `Close Month`: closes the selected fiscal month and activates the next period

Transactions tab:
- `Post Transaction`: records a normal transaction in the selected fiscal period
- `Record Earlier Transaction`: records an older-dated transaction into the selected fiscal period

Accounts / Budget tab:
- `Load Selected Account`: loads the highlighted account into the edit form
- `Save Name / Category`: updates account name and category
- `Update Budget`: saves monthly/yearly budget values
- `Add New Account`: creates a new account and its month rows
- `Delete Account`: deletes an inactive account
- `Create Next Fiscal Year`: creates a new fiscal year without deleting the old one

Monthly Report tab:
- `Monthly Report PDF`: opens the monthly financial report
- `Transaction Log PDF`: opens the transaction log report
- `Budget Report PDF`: opens the budget report
- `Year-End PDF`: opens the year-end financial summary

### Reports

- `Open Owner Report PDF`: owner listing/report
- `Open Lot Report PDF`: lot listing/report
- `Open Mailing Labels PDF`: mailing-label output based on owner address data

### Utilities

- `Run Data Health Checks`: checks for duplicates, mismatches, missing links, and total inconsistencies
- `Refresh From dBase`: re-imports the current legacy dBase data into the app database

## Notes

- Most write actions create a backup first.
- Most print/report actions save a PDF and open it immediately in the default viewer.
- While dBase is still being used in parallel, `Refresh From dBase` should be treated as the deliberate sync point.
