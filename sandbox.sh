#!/bin/bash
# sandbox.sh — Run Claude Code inside a sandboxed Docker container.
# Usage: ./sandbox.sh [claude args...]
# Example: ./sandbox.sh --dangerously-skip-permissions
#
# Swarm integration:
#   swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 \
#       -- ./sandbox.sh --dangerously-skip-permissions
#
# Git auth: Uses GH_TOKEN (GitHub CLI token) over HTTPS. No SSH keys mounted.
#   Requires: gh auth login (once on host), repo cloned via HTTPS or remote
#   set to HTTPS (git remote set-url origin https://github.com/user/repo.git).
#
# Environment overrides:
#   SANDBOX_IMAGE=sandbox-loop    Docker image name
#   SANDBOX_NETWORK=sandbox-net   Docker network name
#   MEMORY_LIMIT=8g               Container memory cap
#   CPU_LIMIT=4                   Container CPU cap
#   PIDS_LIMIT=512                Container PID cap

set -euo pipefail

IMAGE="${SANDBOX_IMAGE:-sandbox-loop}"
NETWORK="${SANDBOX_NETWORK:-sandbox-net}"
MEMORY="${MEMORY_LIMIT:-8g}"
CPUS="${CPU_LIMIT:-4}"
PIDS="${PIDS_LIMIT:-512}"

# Auto-build image if missing
if ! docker image inspect "$IMAGE" &>/dev/null; then
    echo "Image '$IMAGE' not found — building..." >&2
    docker build \
        --build-arg USER_ID="$(id -u)" \
        --build-arg GROUP_ID="$(id -g)" \
        -t "$IMAGE" \
        -f Dockerfile.sandbox . >&2
fi

# Resolve symlinked settings (Claude often symlinks settings.json)
CLAUDE_SETTINGS=$(readlink -f "$HOME/.claude/settings.json" 2>/dev/null || echo "$HOME/.claude/settings.json")

# Git auth via short-lived GitHub token (no SSH keys in the container).
# Falls back to gh auth token, then GITHUB_TOKEN env var, then warns.
GH_TOKEN="${GH_TOKEN:-}"
if [ -z "$GH_TOKEN" ] && command -v gh &>/dev/null; then
    GH_TOKEN=$(gh auth token 2>/dev/null || true)
fi
if [ -z "$GH_TOKEN" ]; then
    echo "warning: no GH_TOKEN found. git push will fail inside the container." >&2
    echo "  fix: run 'gh auth login' or export GH_TOKEN=ghp_..." >&2
fi

# --- Claude auth ---
# Priority: ANTHROPIC_API_KEY (direct API key, no expiry)
#         > CLAUDE_CODE_OAUTH_TOKEN (explicit OAuth token)
#         > auto-extract from ~/.claude/.credentials.json (subscription users)
#
# OAuth tokens expire after ~8h but sandbox.sh re-extracts each iteration.
# For long sessions, ANTHROPIC_API_KEY is more reliable.
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
    CREDS="$HOME/.claude/.credentials.json"
    if [ -f "$CREDS" ]; then
        CLAUDE_CODE_OAUTH_TOKEN=$(python3 -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get('claudeAiOauth', {}).get('accessToken', ''))
except Exception:
    pass
" "$CREDS" 2>/dev/null || true)
        export CLAUDE_CODE_OAUTH_TOKEN
    fi
    if [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
        echo "warning: no Claude auth found. Worker will show login prompt." >&2
        echo "  fix: export ANTHROPIC_API_KEY=sk-ant-... or run 'claude login' on host." >&2
    fi
fi

exec docker run --rm -it \
    --memory="$MEMORY" \
    --memory-swap="$MEMORY" \
    --cpus="$CPUS" \
    --pids-limit="$PIDS" \
    --network="$NETWORK" \
    -v "$(pwd):/workspace" \
    -v "$CLAUDE_SETTINGS:/home/loopuser/.claude/settings.json:ro" \
    -v "$HOME/.claude/projects:/home/loopuser/.claude/projects" \
    -e ANTHROPIC_API_KEY \
    -e CLAUDE_CODE_OAUTH_TOKEN \
    -e DISABLE_AUTOUPDATER=1 \
    -e "GH_TOKEN=$GH_TOKEN" \
    -w /workspace \
    "$IMAGE" \
    claude "$@"
