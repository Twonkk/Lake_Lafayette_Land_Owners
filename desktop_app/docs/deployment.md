# Deployment

## Recommended Release Model

- Keep source code in GitHub.
- Build Windows releases from tagged versions.
- Publish packaged installers in GitHub Releases.
- Keep the SQLite database in the user's local app-data folder, separate from the installed program files.

## Runtime Data Location

On Windows, the app stores runtime data under:

- `%LOCALAPPDATA%\\LakeLotManager\\`

This includes:

- `lake_lot.sqlite3`
- `backups/`
- `generated_notices/`
- `generated_reports/`
- `update_config.json`
- `logs/`

## PDF Requirement

PDF output in the app is generated directly with ReportLab and does not require LibreOffice.

This affects:

- notices
- financial reports
- mailing labels
- property sale receipts
- boat sticker receipts
- ID card receipts

For the first install test on Windows, use:

- `Utilities` -> `Check PDF Setup`

If PDF setup is not available, the app will still run, but PDF-based printing and previews will fail until the app is reinstalled with its bundled Python dependencies intact.

## Build Steps

1. Install build dependencies.
2. Run:

```powershell
python -m PyInstaller --noconfirm --clean packaging/pyinstaller.spec
```

3. Package the output with Inno Setup using:

```powershell
ISCC packaging/installer.iss
```

## First Install Test

Recommended checklist for the first real install:

1. Install the packaged app on the target Windows PC.
2. Launch the app and confirm it creates `%LOCALAPPDATA%\\LakeLotManager\\`.
3. Use `Initial Setup` to import from `C:\\dbase`.
4. Open `Utilities` and run `Check PDF Setup`.
5. Test one write workflow from each major area:
   - payment
   - assessment
   - property sale and reverse sale
   - lien or collection action
   - financial transaction
6. Confirm backups appear under `backups/`.
7. Confirm logs appear under `logs/`.

## GitHub

You do not need a GitHub repo to keep building locally.

You do need a GitHub repo, or another release host, if you want the app to pull published updates automatically.

Current repository:

- `https://github.com/Twonkk/Lake_Lafayette_Land_Owners`

## Update Strategy

- publish a new installer for each version
- keep the database outside the install folder
- let the app check GitHub Releases from `Utilities` -> `Check for Updates`
- download the new installer into `%LOCALAPPDATA%\\LakeLotManager\\updates\\`
- run the downloaded installer over the existing install to update the app

## Suggested Next Step

- push the current codebase to:
  `https://github.com/Twonkk/Lake_Lafayette_Land_Owners`
- start publishing versioned releases once the app is stable enough for testing

## GitHub Actions

This repo now includes a Windows release workflow:

- `.github/workflows/windows-release.yml`

It will:

- build the Windows executable with PyInstaller
- build the installer with Inno Setup
- upload build artifacts
- publish the installer to GitHub Releases when you push a tag like `v0.1.0`
