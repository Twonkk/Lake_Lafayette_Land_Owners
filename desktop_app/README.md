# Desktop App

This folder contains the new single-user desktop application that will replace the legacy dBase workflow.

## Principles

- local-first
- one-user friendly
- obvious navigation
- safe writes with backups
- minimal setup on Windows 11
- plain-language dBase refresh protection that explains what was protected and what to do next
- dBase-compatible assessment roll-forward and operator-controlled payment category distribution

## Run

```bash
python3 -m src.main
```

## Runtime Data

During development, the app now stores its working database and generated files in a per-user app-data folder instead of inside the install/project folder.

On Windows this will be:

```text
%LOCALAPPDATA%\LakeLotManager\
```

## Packaging

Packaging scaffolding is under `packaging/`:

- `packaging/pyinstaller.spec`
- `packaging/build_windows.ps1`
- `packaging/installer.iss`

Deployment notes are in `docs/deployment.md`.

## PDF Output

PDF output is generated directly by the app with ReportLab. LibreOffice is not required.

After install, use:

- `Utilities` -> `Check PDF Setup`

to confirm the PDF runtime is available before testing notice/report printing.

## Current Working Features

- creates a local SQLite database
- imports owner, lot, notes, and payment history from the legacy DBF files
- preserves missing legacy owner codes as safe, clearly marked review records instead of orphaning their lots or payment history
- provides a familiar Menu with the original dBase group and option numbers
- keeps the sidebar uncluttered with Menu and Migration Review buttons
- turns incomplete owner records, special X-lot exclusions, and legacy rounding differences into a client-facing decision queue
- restores recoverable deleted owners only after confirmation and records every migration decision with a backup
- prevents deletion when a placeholder is still connected to lots, payments, sales, notes, or history
- uses larger controls, Windows DPI awareness, maximized startup, and a scrollable Menu for scaled displays
- connects every main Help panel to the dBase option it replaces
- provides owner/lot search and the primary daily workflows after import
- includes owner/lot/property/ID/boat history, migration-readiness checks, and client-review PDFs
- creates a complete individual payment-history PDF from either the History screen or an owner's Payment History tab
- formats wide owner and lot reports in landscape with wrapped text, repeated headings, and page numbers
- keeps county land trust status separate from collection-agency status
- posts balanced financial transactions with searchable history and auditable recoding

Use the `Import Legacy Data` button in the app to load the current `../dbase` files.

## Near-Term Build Order

1. SQLite schema and legacy import
2. Read-only owner and lot search
3. Payment posting workflow
4. Assessment update workflow
5. Reports and print/export support
