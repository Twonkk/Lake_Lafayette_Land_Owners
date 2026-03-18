#!/usr/bin/env bash
set -euo pipefail

TAG_NAME="${1:-}"
MESSAGE="${2:-}"

if [[ -z "$TAG_NAME" ]]; then
  echo "Usage: ./scripts/release_tag.sh v0.1.0 [message]"
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is required."
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "No git repository found here."
  exit 1
fi

if [[ -n "$(git status --short)" ]]; then
  echo "Working tree is not clean. Commit or stash changes before tagging."
  exit 1
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "Remote 'origin' is not configured."
  exit 1
fi

if git rev-parse "$TAG_NAME" >/dev/null 2>&1; then
  echo "Tag already exists locally: $TAG_NAME"
  exit 1
fi

if [[ -n "$MESSAGE" ]]; then
  git tag -a "$TAG_NAME" -m "$MESSAGE"
else
  git tag "$TAG_NAME"
fi

git push origin "$TAG_NAME"

echo "Release tag pushed: $TAG_NAME"
