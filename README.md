# Lake Lot Management Modernization

This repository contains the legacy dBase system and the replacement desktop app that is being built to take over daily operations on a single Windows PC.

## Repository Contents

- `dbase/`: the legacy dBase application and data files
- `desktop_app/`: the replacement Windows desktop application
- `print_samples/`: sample printouts used to match legacy forms and reports
- `scripts/`: helper scripts for pushing and tagging releases

## Goal

Replace the DOS-era single-user dBase workflow with a native desktop app that:

- runs locally on one Windows 11 PC
- avoids DOS emulation
- keeps the workflow familiar for the current operator
- stores data in SQLite
- supports importing from the legacy `.DBF` files

## Current Status

The replacement app is well beyond scaffold stage. Core workflows that currently exist include:

- first-run legacy import and manual refresh from dBase
- dashboard with live counts, alerts, and recent activity
- owner and lot lookup with revise/edit support
- assessment posting
- payment posting and payment history
- property sale / purchase and reversal
- assessment notices with PDF output
- liens and collection assignment/removal
- financial transactions, budgets, reports, and fiscal year rollover
- mailing labels
- boat sticker purchase and ID card issue tracking
- utilities and data-health checks
- Windows packaging and release scaffolding

## Quick Start

```bash
cd desktop_app
python3 -m src.main
```

## Project Layout

- `desktop_app/src/main.py`: application entry point
- `desktop_app/src/app.py`: main app controller
- `desktop_app/src/db/`: SQLite setup and repositories
- `desktop_app/src/ui/`: desktop UI screens and shared widgets
- `desktop_app/src/services/`: application services and workflows
- `desktop_app/src/importers/`: legacy dBase import code
- `desktop_app/data/`: local SQLite database and generated files
- `desktop_app/docs/`: migration notes and roadmap

## Runtime Notes

- During development, many verification databases and generated files may appear under `desktop_app/data/`.
- The root `.gitignore` is set up to ignore local databases, generated PDFs, generated reports, and client sample print files.
- On a packaged Windows install, the app is intended to keep its live data under `%LOCALAPPDATA%\\LakeLotManager\\` so updates do not overwrite the working database.

## Documentation

- [`desktop_app/README.md`](/home/david/dev/dbase_update/desktop_app/README.md): app-specific setup notes
- [`desktop_app/docs/deployment.md`](/home/david/dev/dbase_update/desktop_app/docs/deployment.md): packaging and release notes
- [`Intro.md`](/home/david/dev/dbase_update/Intro.md): plain-language description of what each app button does
