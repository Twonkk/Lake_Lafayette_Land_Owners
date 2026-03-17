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
