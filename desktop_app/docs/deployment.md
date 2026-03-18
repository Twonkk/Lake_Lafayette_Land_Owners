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

## GitHub

You do not need a GitHub repo to keep building locally.

You do need a GitHub repo, or another release host, if you want the app to pull published updates automatically.

Current repository:

- `https://github.com/Twonkk/Lake_Lafayette_Land_Owners`

## Update Strategy

- publish a new installer for each version
- keep the database outside the install folder
- let the app check a release manifest later
- download and run the installer for updates

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
