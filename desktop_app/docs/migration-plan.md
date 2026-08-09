# Migration Plan

## Phase 1

- inventory legacy tables and fields
- define SQLite schema
- build read-only importer from `.DBF`
- build a shell desktop UI

## Phase 2

- implement owner and lot search
- implement payment entry and history review
- implement notes and history views

## Phase 3

- implement assessment update workflow
- implement financial transaction workflows
- recreate critical printed reports

## Phase 4

- validate outputs against legacy dBase
- package for Windows 11
- cut over to the desktop app

## Migration Safety and Reconciliation

- Keep all DBF files and archives outside Git. The repository ignores `dbase/` and `dbase*.zip`.
- Every full legacy import creates a timestamped SQLite backup first.
- A refresh is blocked after the replacement app has recorded payments, assessments,
  sales, boat/ID activity, or app-native financial transactions. At that point the
  databases must be deliberately reconciled instead of overwriting the app database.
- The importer archives `EXLOTFIL.DBF`, `IDFILE.DBF`, `CLTRUST.DBF`, and
  `PERMFILE.DBF` in dedicated `legacy_*` tables. These tables preserve historical
  records even when their old owner or lot references are no longer current.
- `src.services.migration_service.reconcile_migration` produces privacy-safe aggregate
  counts and totals suitable for migration verification without printing owner data.

### Validated Private Dataset Baseline

The August 2026 validation run produced the following expected imported counts:

- owners: 2,258
- lots: 1,556
- owner payments: 28,391
- lot payments: 51,454
- notes: 1,048
- financial accounts: 54
- financial month rows: 648
- financial transactions: 31
- legacy property sales: 4,182
- legacy ID/boat history: 6,107
- legacy collection lots: 243
- legacy system history: 3,313

The source contains 110 historical owners whose stored lot count is nonzero even
though no current lot is linked to them. It also contains 11 currently unassigned
lots with a combined balance of $1,081.69. Three owner totals differ from their
linked-lot totals by only a few cents, and four lots each contain a $38.56 difference
between `TOT_DUE` and their assessment/interest components. These are legacy-source
conditions and must not be silently normalized during import.
