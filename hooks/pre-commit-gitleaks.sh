#!/usr/bin/env bash
# Git pre-commit hook: block commits that introduce secrets.
#
# Install (per clone — git hooks are not committed into .git/):
#     git config core.hooksPath hooks
# ...then ensure this file is the active pre-commit. The simplest setup is:
#     ln -sf pre-commit-gitleaks.sh hooks/pre-commit   # (hooks/ must be on core.hooksPath)
# or copy it to .git/hooks/pre-commit.
#
# Requires gitleaks on PATH, or the repo-local binary at .tooling/gitleaks.

set -euo pipefail

# Resolve the repo-local tooling dir relative to THIS script, not the CWD git
# invokes the hook from (the git root may differ from the project subdir).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if command -v gitleaks >/dev/null 2>&1; then
  GL="gitleaks"
elif [ -x "$PROJECT_DIR/.tooling/gitleaks" ]; then
  GL="$PROJECT_DIR/.tooling/gitleaks"
else
  echo "pre-commit: gitleaks not found (PATH or .tooling/gitleaks). Skipping secret scan." >&2
  echo "            Install gitleaks to enable the secret-leak guardrail." >&2
  exit 0
fi

# Scan only what is staged for this commit by feeding the staged diff to
# gitleaks. This is git-aware (gitignored files like .env are never in the
# diff) and works regardless of where git invokes the hook from.
if ! git diff --cached | "$GL" stdin --redact -v; then
  echo "" >&2
  echo "pre-commit: gitleaks found a potential secret in your staged changes." >&2
  echo "            Remove the secret (move it to .env) and re-stage, or, if this" >&2
  echo "            is a confirmed false positive, add an allowlist entry to .gitleaks.toml." >&2
  exit 1
fi

exit 0
