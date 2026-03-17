#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-git@github.com:Twonkk/Lake_Lafayette_Land_Owners.git}"
COMMIT_MESSAGE="${1:-}"
TAG_NAME="${2:-}"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required."
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "No git repository found here."
  echo "Run: git init"
  exit 1
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  git remote add origin "$REPO_URL"
  echo "Added origin: $REPO_URL"
fi

CURRENT_BRANCH="$(git branch --show-current)"
if [[ -z "$CURRENT_BRANCH" ]]; then
  echo "Unable to determine current branch."
  exit 1
fi

if [[ -n "$(git status --short)" ]]; then
  if [[ -z "$COMMIT_MESSAGE" ]]; then
    echo "Working tree has changes."
    echo "Pass a commit message as the first argument to stage and commit before pushing."
    exit 1
  fi
  git add -A
  git commit -m "$COMMIT_MESSAGE"
fi

if [[ -n "$TAG_NAME" ]]; then
  if git rev-parse "$TAG_NAME" >/dev/null 2>&1; then
    echo "Tag already exists locally: $TAG_NAME"
  else
    git tag "$TAG_NAME"
    echo "Created tag: $TAG_NAME"
  fi
fi

git push -u origin "$CURRENT_BRANCH"

if [[ -n "$TAG_NAME" ]]; then
  git push origin "$TAG_NAME"
fi

echo "Push complete."
