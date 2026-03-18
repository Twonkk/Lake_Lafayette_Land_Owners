# Repo Scripts

## `push_github.sh`

Helper to push the current branch to GitHub, optionally making a commit first and optionally creating a tag.

Default remote:

- `git@github.com:Twonkk/Lake_Lafayette_Land_Owners.git`

Examples:

```bash
./scripts/push_github.sh
./scripts/push_github.sh "Checkpoint commit"
./scripts/push_github.sh "Release prep" v0.1.0
```

If `origin` does not exist yet, the script adds it automatically.

## `release_tag.sh`

Helper to create and push a release tag for GitHub Actions / GitHub Releases.

Examples:

```bash
./scripts/release_tag.sh v0.1.0
./scripts/release_tag.sh v0.1.1 "Release 0.1.1"
```

This expects:

- a clean working tree
- an `origin` remote already configured
