# Desktop App

This folder contains the new single-user desktop application that will replace the legacy dBase workflow.

## Principles

- local-first
- one-user friendly
- obvious navigation
- safe writes with backups
- minimal setup on Windows 11

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

PDF output currently depends on LibreOffice being installed on the target machine.

After install, use:

- `Utilities` -> `Check PDF Setup`

to confirm the PDF runtime is available before testing notice/report printing.

## Current Working Features

- creates a local SQLite database
- imports owner, lot, notes, and payment history from the legacy DBF files
- provides a first owner/lot search screen after import

Use the `Import Legacy Data` button in the app to load the current `../dbase` files.

## Near-Term Build Order

1. SQLite schema and legacy import
2. Read-only owner and lot search
3. Payment posting workflow
4. Assessment update workflow
5. Reports and print/export support
