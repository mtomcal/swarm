# Project Onboarding

## Overview

Standard operating procedure for setting up a new project with the beads-ralph-sandbox autonomous development stack. Covers the full setup from zero to a self-healing ralph loop consuming a beads task queue, with optional Docker sandboxing for workers and native sandbox for a director. This spec is project-agnostic — it produces project-specific config files customized to the target project's toolchain.

## Dependencies

- External: `swarm` CLI (ralph, heartbeat), `bd` CLI (beads), `git`, `tmux`, `docker` (optional, for sandboxing), `bubblewrap` (optional, for director sandbox)
- Internal: `ralph-loop.md`, `heartbeat.md`, `spawn.md`, `worktree-isolation.md`

## Artifacts Produced

The onboarding process generates these files in the target project:

| File | Required | Purpose |
|------|----------|---------|
| `PROMPT.md` | Yes | Per-iteration instructions for ralph workers |
| `next-task.py` | Yes | Beads task expansion middleware (raw → 3-phase pipeline) |
| `Dockerfile.sandbox` | No (sandboxing) | Docker image with project toolchain |
| `sandbox.sh` | No (sandboxing) | Wrapper that runs `claude` inside Docker container |
| `setup-sandbox-network.sh` | No (sandboxing) | iptables allowlist for container network |
| `teardown-sandbox-network.sh` | No (sandboxing) | Cleanup for network rules |
| `ORCHESTRATOR.md` | No (director) | Monitoring runbook and progress log for director |
| `DIRECTOR_PROMPT.md` | No (director) | Ralph prompt for the autonomous director |
| `start-worker.sh` | Yes | Launch script for ralph worker(s) |
| `start-director.sh` | No (director) | Launch script for autonomous director |

## Behavior

### Phase 1: Prerequisites Check

**Description**: Verify the target project has the minimum requirements before generating config.

**Inputs**:
- `project_dir` (path, required): Root directory of the target project

**Checks**:
1. `bd stats` succeeds (beads initialized, `.beads/` exists)
2. `CLAUDE.md` or `AGENTS.md` exists (project context for the agent)
3. `git rev-parse --git-dir` succeeds (git repo)
4. `swarm --help` succeeds (swarm CLI available)
5. Project has a test command (e.g., `make test`, `npm test`, `go test ./...`)
6. Project has a lint command (e.g., `make lint`, `npm run lint`, `go vet ./...`)

**Outputs**:
- Success: All checks pass, proceed to Phase 2
- Failure: List missing prerequisites with install instructions

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| No `.beads/` directory | Print: "Run `bd init` to initialize beads" |
| No `CLAUDE.md` | Print: "Create CLAUDE.md with project context" |
| Not a git repo | Print: "Run `git init`" |
| `swarm` not in PATH | Print: install instructions |

### Phase 2: Project Analysis

**Description**: Read the project's CLAUDE.md and build system to determine the correct commands for testing, linting, typechecking, and building. These commands are baked into the generated config files.

**Inputs**:
- `CLAUDE.md` content
- `Makefile`, `package.json`, `go.mod`, or equivalent build files

**Outputs**: A project profile used to template all generated files:

```
project_profile:
  name: "stick-rumble"
  languages: ["typescript", "go"]
  test_command: "make test"
  test_client_command: "make test-client"
  test_server_command: "make test-server"
  lint_command: "make lint"
  typecheck_command: "make typecheck"
  build_command: "make build"
  coverage_command: "make test-coverage"
  integration_test_command: "make test-integration"
  runtime_deps: ["node:22-slim", "golang:1.25"]  # for Dockerfile
  extra_apt_packages: []
```

### Phase 3: Generate PROMPT.md

**Description**: Create the ralph prompt file. This is read fresh each iteration by the ralph loop.

**Design Principles**:
- Under 20 lines (maximize context for actual work)
- ONE task per iteration
- Verify before assuming (read code first)
- Commit and push each iteration
- Use `next-task.py` as the task source

**Template**:

```markdown
Read CLAUDE.md for project context.

## Your Task

Pull the next ready task and execute it.

### Step 1: Get next task

\`\`\`bash
id=$(python3 next-task.py)
\`\`\`

If the script exits non-zero (no output), all tasks are complete. Output `/done` on its own line and stop.

### Step 2: Claim the task

\`\`\`bash
bd update "$id" --status in_progress
\`\`\`

### Step 3: Read the full task

\`\`\`bash
bd show "$id"
\`\`\`

Read the **description**, **acceptance criteria**, **design**, and **notes** fields carefully. They contain your full instructions.

### Step 4: Determine work type from labels

\`\`\`bash
bd show --json "$id" | jq -r '.labels[]'
\`\`\`

The label tells you what kind of work to do:

- **`implementation`** — Write code. Follow the description and acceptance criteria exactly. Use TDD. Run tests after changes. Commit when done.
- **`code-review`** — Review the most recent implementation. Read the diff, check against acceptance criteria in the task description. Fix any issues directly, don't just report them. Commit fixes.
- **`test-review`** — Review tests for the most recent implementation. Check that assertions match test intent, no false positives, coverage is adequate. Fix any issues directly. Commit fixes.

### Step 5: Close the task

\`\`\`bash
bd close "$id" --reason "done: <short summary of what you did>"
\`\`\`

### Rules

- Do ONE task per iteration
- Do NOT assume anything is already done — verify by reading actual code/files
- Commit and push when done
- If `next-task.py` returns nothing, output `/done` on its own line and stop
```

**Customization points**:
- The "Rules" section should reference project-specific test commands if `make test` is problematic (e.g., slow, flaky). Use `CLAUDE.md` warnings as guidance.

### Phase 4: Generate next-task.py

**Description**: Copy the template from `swarm/templates/beads-ralph/next-task.py` and customize the phase description templates for the target project's toolchain.

**Customization points in phase templates**:

**IMPLEMENTATION_DESCRIPTION**:
- Replace generic "run typecheck and linter from the project's build file" with actual commands:
  - e.g., `make lint && make typecheck` for stick-rumble
- Replace generic "run unit tests with coverage" with actual command:
  - e.g., `make test-coverage` for stick-rumble
- Add project-specific methodology notes:
  - e.g., "Use the root-level Makefile — do NOT cd into subdirectories"
  - e.g., "Run `make test-client` for TypeScript changes, `make test-server` for Go changes"

**CODE_REVIEW_DESCRIPTION**:
- Same command substitutions as implementation
- Add project-specific review criteria:
  - e.g., "Check that new WebSocket message types follow the events-schema pattern"
  - e.g., "Verify Go code uses `any` instead of `interface{}`"

**TEST_REVIEW_DESCRIPTION**:
- Same command substitutions
- Add project-specific test patterns:
  - e.g., "Visual regression tests are required for ALL rendering-related changes"
  - e.g., "Integration tests require both client and server running"

### Phase 5: Generate Sandbox Files (Optional)

**Description**: Create Docker sandbox infrastructure for isolated worker execution. Skip this phase for unsandboxed setups.

#### Dockerfile.sandbox

Must include:
1. Base image appropriate for the project's primary runtime
2. All language runtimes the project uses
3. `tmux`, `git`, `jq`, `openssh-client`, `ca-certificates`, `make`, `procps`
4. `claude` CLI (`npm install -g @anthropic-ai/claude-code`)
5. `bd` CLI ([beads](https://github.com/steveyegge/beads) — `go install github.com/steveyegge/beads/cmd/bd@latest`)
6. Non-root user matching host UID/GID
7. `WORKDIR /workspace`
8. `DISABLE_AUTOUPDATER=1` environment variable

**Example for a Go + TypeScript project** (stick-rumble):

```dockerfile
FROM node:22-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tmux git jq openssh-client ca-certificates \
        python3 make procps curl \
    && rm -rf /var/lib/apt/lists/*

# Go runtime
ARG GO_VERSION=1.25
RUN curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" \
    | tar -C /usr/local -xzf -
ENV PATH="/usr/local/go/bin:${PATH}"

# Claude CLI
RUN npm install -g @anthropic-ai/claude-code

# Beads CLI (https://github.com/steveyegge/beads)
ENV GOPATH="/usr/local/gopath"
RUN go install github.com/steveyegge/beads/cmd/bd@latest
ENV PATH="/usr/local/gopath/bin:${PATH}"

# Non-root user matching host UID
ARG USER_ID=1000
ARG GROUP_ID=1000
RUN groupadd -g $GROUP_ID worker && \
    useradd -m -u $USER_ID -g $GROUP_ID worker

ENV DISABLE_AUTOUPDATER=1

# Pre-configure Claude Code to skip first-time theme picker
RUN mkdir -p /home/worker/.claude && \
    echo '{"theme":"dark"}' > /home/worker/.claude/settings.local.json && \
    chown -R $USER_ID:$GROUP_ID /home/worker/.claude

USER worker
WORKDIR /workspace
```

#### sandbox.sh

Wrapper script that runs `claude` inside the Docker container. All arguments after `sandbox.sh` are passed through to `claude`.

**Critical design decisions**:
- No SSH keys mounted — use `GH_TOKEN` over HTTPS for git auth
- Claude credentials mounted read-only
- Only `~/.claude/projects/` is read-write (Claude needs this for project memory)
- No `.gitconfig` mounted — credential helper baked into image or use `GH_TOKEN`
- Container is `--rm` (disposable)

```bash
#!/usr/bin/env bash
set -euo pipefail

# Resolve symlinks for bind mounts
CLAUDE_SETTINGS=$(readlink -f ~/.claude/settings.json 2>/dev/null || echo ~/.claude/settings.json)

exec docker run --rm -it \
    --name "swarm-worker-$$" \
    --memory="${MEMORY_LIMIT:-8g}" \
    --memory-swap="${MEMORY_LIMIT:-8g}" \
    --cpus="${CPU_LIMIT:-4}" \
    --pids-limit="${PIDS_LIMIT:-512}" \
    --network="${SANDBOX_NETWORK:-sandbox-net}" \
    -v "$(pwd):/workspace" \
    -v "$HOME/.claude/.credentials.json:/home/worker/.claude/.credentials.json:ro" \
    -v "$CLAUDE_SETTINGS:/home/worker/.claude/settings.json:ro" \
    -v "$HOME/.claude/projects:/home/worker/.claude/projects" \
    -e ANTHROPIC_API_KEY \
    -e GH_TOKEN \
    -e DISABLE_AUTOUPDATER=1 \
    -w /workspace \
    "${SANDBOX_IMAGE:-sandbox-loop}" \
    claude "$@"
```

#### setup-sandbox-network.sh / teardown-sandbox-network.sh

Copy from `swarm/docs/sandbox-loop-spec.md` verbatim. These are project-agnostic.

**Additional domains to allow** (project-specific):
- If the project uses `npm install` inside the container: add `registry.npmjs.org`
- If the project uses `go mod download`: add `proxy.golang.org`, `sum.golang.org`
- If the project uses other package registries: add those domains

### Phase 6: Generate Launch Scripts

**Description**: Create convenience scripts for starting workers and optionally a director.

#### start-worker.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

NAME="${1:-worker}"

# If already running, attach
if swarm ralph list 2>/dev/null | grep -q "$NAME.*running"; then
    echo "Worker '$NAME' already running, attaching..."
    swarm attach "$NAME"
    exit 0
fi

swarm ralph spawn --name "$NAME" \
    --prompt-file ./PROMPT.md \
    --max-iterations 100 \
    --inactivity-timeout 14400 \
    --done-pattern "/done" \
    --check-done-continuous \
    --heartbeat 30m \
    --heartbeat-expire 24h \
    --worktree \
    -- claude --dangerously-skip-permissions
```

**For sandboxed workers**, replace the `claude` command with `./sandbox.sh`:

```bash
    -- ./sandbox.sh --dangerously-skip-permissions
```

#### start-director.sh (Optional)

```bash
#!/usr/bin/env bash
set -euo pipefail

# If already running, attach
if swarm ralph list 2>/dev/null | grep -q "director.*running"; then
    echo "Director already running, attaching..."
    swarm attach director
    exit 0
fi

swarm ralph spawn --name director \
    --prompt-file ./DIRECTOR_PROMPT.md \
    --max-iterations 200 \
    --inactivity-timeout 14400 \
    --heartbeat 30m \
    --heartbeat-expire 48h \
    -- claude --dangerously-skip-permissions
```

### Phase 7: Generate Director Files (Optional)

**Description**: Create the autonomous director's prompt and orchestrator runbook.

#### DIRECTOR_PROMPT.md

```markdown
Read ORCHESTRATOR.md. You are the director.

FIRST: run `swarm ralph list` and `swarm ls` to see what's already running.
- If workers exist and are running, monitor them. Do NOT spawn duplicates.
- If no workers exist, spawn them per ORCHESTRATOR.md instructions.
- If a worker is stuck (same task for 2+ iterations in `swarm ralph logs`), intervene.
- If `bd ready` returns nothing and no tasks are in_progress, all work is done — output /done.

Check progress: `bd stats`, `bd list --status=in_progress`, `git log --oneline -5`.
Before exiting, update ORCHESTRATOR.md with a progress note and commit.
```

#### ORCHESTRATOR.md

```markdown
# [Project Name] — Director Runbook

## Workers

| Name | Type | Prompt | Notes |
|------|------|--------|-------|
| worker | ralph + beads queue | PROMPT.md | Main implementation worker |

### Spawn Command

\`\`\`bash
./start-worker.sh
\`\`\`

### Monitor

\`\`\`bash
swarm ralph status worker
swarm ralph logs worker
bd stats
bd list --status=in_progress
git log --oneline -10
\`\`\`

### Intervene When Stuck

- Worker loops on same task 2+ iterations → read the task (`bd show <id>`), update notes with hints (`bd update <id> --notes "Try approach X"`)
- Worker OOM (exit 137) → bump memory: `MEMORY_LIMIT=12g`
- Worker rate limited → heartbeat should recover; if not, `swarm ralph pause worker` and wait

## Progress Log

<!-- Director appends progress notes here each iteration -->
```

### Phase 8: Load Initial Tasks

**Description**: Create beads issues for the work to be done. This is project-specific and done by the human or a planning agent.

**Task quality checklist** (each task should have):
- `--title`: Clear, imperative summary (e.g., "Add weapon pickup collision detection")
- `--description`: Why this task exists and what needs to be done
- `--acceptance`: Bullet list of verifiable criteria
- `--priority`: 0-4 (0=critical, 4=backlog)
- `--type`: task, bug, or feature

**Example**:
```bash
bd create --title "Add weapon pickup collision detection" \
    --description "Players should be able to walk over weapon crates to pick them up. Currently weapon crates spawn but have no collision detection." \
    --acceptance "- Player walking over a weapon crate triggers pickup\n- Weapon state updates on pickup\n- Crate disappears after pickup\n- Server validates pickup (anti-cheat)" \
    --type feature \
    --priority 2
```

Tasks with no phase labels are automatically expanded by `next-task.py` into the 3-phase pipeline (implement → code-review → test-review) when they reach the front of the queue.

### Phase 9: Verify Setup

**Description**: Dry-run verification before launching the full autonomous loop.

**Verification steps**:

1. **next-task.py works**: `python3 next-task.py` returns a task ID (or exits 1 if queue empty)
2. **PROMPT.md is readable**: `cat PROMPT.md` shows the prompt
3. **Beads has tasks**: `bd ready` shows at least one task
4. **Git is clean**: `git status` shows no unexpected uncommitted changes
5. **Docker image builds** (if sandboxing): `docker build -t sandbox-loop -f Dockerfile.sandbox .`
6. **Network rules applied** (if sandboxing): `sudo ./setup-sandbox-network.sh`
7. **Single-iteration test**: Run one ralph iteration manually and verify it picks up a task, does work, commits, and closes the task:

```bash
swarm ralph spawn --name test-run \
    --prompt-file ./PROMPT.md \
    --max-iterations 1 \
    --worktree \
    -- claude --dangerously-skip-permissions
```

Check: `bd list --status=closed` shows the task was closed. `git log --oneline -3` shows a commit from the worker.

## Scenarios

### Scenario: Fresh project with beads, no sandboxing

- **Given**: A git repo with `.beads/`, `CLAUDE.md`, and a working `make test`
- **When**: Onboarding is run with sandboxing disabled
- **Then**:
  - `PROMPT.md`, `next-task.py`, `start-worker.sh` are generated
  - `next-task.py` phase templates reference the project's actual test/lint commands
  - `start-worker.sh` uses `claude` directly (no sandbox.sh)
  - Worker can be launched with `./start-worker.sh`

### Scenario: Fresh project with Docker sandboxing

- **Given**: A git repo with `.beads/`, `CLAUDE.md`, Docker installed
- **When**: Onboarding is run with sandboxing enabled
- **Then**:
  - All files from the unsandboxed scenario are generated, plus:
  - `Dockerfile.sandbox` with project-specific runtime deps
  - `sandbox.sh` wrapper
  - `setup-sandbox-network.sh` and `teardown-sandbox-network.sh`
  - `start-worker.sh` uses `./sandbox.sh` instead of bare `claude`
  - Docker image builds successfully
  - Network rules can be applied

### Scenario: Full autonomous stack (director + workers)

- **Given**: A project set up per the sandboxed scenario
- **When**: Director files are also generated
- **Then**:
  - `DIRECTOR_PROMPT.md` and `ORCHESTRATOR.md` are generated
  - `start-director.sh` launches the director as a ralph loop
  - Director checks for existing workers before spawning
  - Director monitors worker progress and intervenes if stuck
  - Both director and workers have heartbeat for rate limit recovery

### Scenario: Task expansion cascade

- **Given**: A running ralph worker, 3 raw tasks in the beads queue
- **When**: Worker processes the queue over multiple iterations
- **Then**:
  - First raw task is expanded into implement → code-review → test-review
  - Worker implements (iteration 1), reviews code (iteration 2), reviews tests (iteration 3)
  - Second raw task is expanded only after all 3 phases of the first are closed
  - After all 9 phases (3 tasks x 3 phases) complete, worker outputs `/done`
  - Ralph loop terminates

### Scenario: Worker hits rate limit

- **Given**: A running ralph worker with `--inactivity-timeout 14400 --heartbeat 30m`
- **When**: Claude API rate limit is hit mid-iteration
- **Then**:
  - Screen freezes (rate limit message displayed)
  - Heartbeat sends "continue" nudge after 30 minutes
  - If rate limit has lifted, worker resumes work
  - If still limited, next heartbeat nudge in 30 minutes
  - Ralph does NOT restart the worker (14400s timeout not reached)
  - Worker eventually recovers and completes the task

### Scenario: Worker OOM in Docker sandbox

- **Given**: A sandboxed worker with `--memory=8g`
- **When**: Test suite exhausts container memory
- **Then**:
  - Kernel cgroup OOM-killer fires, container killed (exit 137)
  - `--rm` cleans up the dead container
  - Ralph logs "iteration ended" and starts next iteration
  - Committed work preserved (bind-mounted repo)
  - Uncommitted work lost (acceptable — worker retries the task)

## Edge Cases

- **Empty beads queue at start**: `next-task.py` exits 1, worker outputs `/done`, ralph stops after 1 iteration. This is correct behavior — no work to do.
- **Task has no description or acceptance criteria**: `next-task.py` still expands it, but the phase descriptions will have empty `{description}` and `{acceptance}` placeholders. The worker may produce low-quality output. Recommendation: always populate these fields.
- **Multiple workers on same queue**: Beads `in_progress` status prevents two workers from claiming the same task. `bd ready` only returns tasks not already claimed. Workers can safely run in parallel on separate worktrees.
- **next-task.py crashes mid-expansion**: Partial state: some child tasks may be created but parent not yet closed. Recovery: manually close the parent (`bd close <id> --reason "manual cleanup"`) or delete orphaned children.
- **Worker modifies next-task.py**: Since the worker's worktree is isolated, modifications only affect that worktree. The main branch's `next-task.py` is unaffected. However, if the worker commits and pushes changes to `next-task.py`, the next iteration will use the modified version.
- **PROMPT.md edited mid-loop**: Ralph reads PROMPT.md fresh each iteration, so edits take effect on the next iteration. This is intentional and useful for steering workers.

## Recovery Procedures

### Worker is stuck on a task

```bash
# Check what it's doing
swarm ralph status worker
swarm attach worker  # watch live, Ctrl-B D to detach

# Send a nudge
swarm send worker "please wrap up and commit what you have"

# Force restart (kills current iteration, starts fresh)
swarm ralph pause worker
swarm ralph resume worker
```

### All iterations burned (max_iterations reached)

```bash
# Check how many iterations were used
swarm ralph status worker

# Reset and restart with higher ceiling
swarm ralph spawn --name worker --replace \
    --prompt-file ./PROMPT.md \
    --max-iterations 200 \
    --inactivity-timeout 14400 \
    --heartbeat 30m \
    --heartbeat-expire 24h \
    --worktree \
    -- claude --dangerously-skip-permissions
```

### Docker image is stale

```bash
# Rebuild
docker build --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) \
    -t sandbox-loop -f Dockerfile.sandbox .

# Verify
docker run --rm sandbox-loop claude --version
docker run --rm sandbox-loop go version  # if Go project
docker run --rm sandbox-loop node --version  # if Node project
```

### Network rules expired (DNS rotation)

```bash
sudo ./teardown-sandbox-network.sh
sudo ./setup-sandbox-network.sh
```

### Beads queue is stuck (blocked tasks with no path forward)

```bash
# Check what's blocked
bd blocked

# See what's blocking
bd show <blocked-id>

# Remove a bad dependency
bd dep remove <blocked-id> <blocker-id>

# Or close the blocker manually
bd close <blocker-id> --reason "unblocking: <reason>"
```

## Implementation Notes

- `next-task.py` uses `bd create ... --silent` which returns only the created task ID on stdout. This is required for the script to capture IDs for dependency setup.
- `bd dep add <child> <parent> --type blocks` means "parent blocks child" — the child cannot start until parent is closed. The argument order is: the issue being modified, then the issue it depends on.
- The `--check-done-continuous` flag on ralph makes it check for the `/done` pattern continuously during monitoring, not just after agent exit. This is important because the worker may output `/done` and then sit idle waiting for the next prompt — without continuous checking, ralph would wait for the full inactivity timeout before noticing.
- `--worktree` creates an isolated git branch and working directory. Workers should always use worktrees to avoid conflicting with the main branch or other workers. The worktree persists across ralph iterations (only the agent process restarts).
- The `--replace` flag on `swarm ralph spawn` cleans up existing worker state (kills process, removes ralph state, removes worktree) before spawning. Use this for clean restarts.
- Phase templates in `next-task.py` use Python f-string-compatible `{field}` placeholders. The `.format()` call substitutes parent task fields into the child descriptions.
