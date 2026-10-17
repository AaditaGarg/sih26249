#!/usr/bin/env bash
# Usage: ./push_to_github.sh [repo-name] [public|private]
# Requires GitHub CLI: https://cli.github.com  (run `gh auth login` once)
set -euo pipefail
NAME="${1:-sih26249-sustainiq}"; VIS="${2:-public}"
git init -b main >/dev/null 2>&1 || true
git add -A && git commit -qm "feat(backend): SustainIQ MVP backend" || true
gh repo create "$NAME" --"$VIS" --source=. --remote=origin --push
