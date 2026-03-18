# Architecture

## Chosen Stack

- Python 3
- `tkinter` / `ttk` for the desktop UI
- SQLite for local storage

## Why This Stack

- no server required
- no browser required
- built-in Python libraries cover the first phase
- simple packaging path for Windows
- suitable for a single-PC, one-user deployment

## Planned Modules

- `db/`: schema creation, connections, and repositories
- `importers/`: import legacy `.DBF` files into SQLite
- `services/`: business logic rewritten from dBase workflows
- `ui/`: operator-friendly desktop interface

## Initial Workflow Mapping

- Owners and lots
- Payments and payment history
- Assessments and delinquency updates
- Financial transactions and monthly reporting
- Notes, notices, liens, and ID/boat workflows
