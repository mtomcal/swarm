# Beads + Ralph Task Queue

How to use [beads](https://github.com/your-org/beads) as a structured task queue for ralph workers, with automatic task expansion into implementation, code review, and test review phases.

## The Problem

The standard ralph workflow uses `IMPLEMENTATION_PLAN.md` — a markdown checklist that workers scan for the next `[ ]` task. This works for simple epics but has limitations:

- **No dependency tracking** — tasks are just a flat list
- **No review cycle** — the worker implements and moves on; nobody reviews the code or tests
- **No structured metadata** — task descriptions are a single line in a checklist
- **No priority ordering** — workers pick "the most important" task subjectively

## The Solution

Replace `IMPLEMENTATION_PLAN.md` with beads as the task store. A Python script (`next-task.py`) sits between `bd ready` and the ralph worker, automatically expanding raw tasks into a 3-phase pipeline:

```
You create:          bd create "Add OAuth" -p P1 --description "..." --acceptance "..."

next-task.py sees:   "Add OAuth" (no phase label, raw task)

next-task.py creates:
  ├── Implement: Add OAuth     [implementation]  ← returned first, ready
  ├── Code review: Add OAuth   [code-review]     ← blocked by implementation
  └── Test review: Add OAuth   [test-review]     ← blocked by code review

Original task:       closed as "expanded"
```

Each child task gets a rich description with full methodology instructions baked in. The worker reads `bd show <id>` and gets everything it needs — no skills or external dispatch logic required.

## How It Works

### The Cascade

When the implementation task is closed, beads automatically unblocks the code review task. When code review is closed, the test review unblocks. When all three are done, the next raw task in the queue is expanded. This continues until `bd ready` returns nothing.

```
Iteration 1:  next-task.py expands "Add OAuth" → returns impl task
              Worker implements, commits, closes impl task

Iteration 2:  next-task.py sees code-review task (already has label) → returns as-is
              Worker reviews code, fixes issues, closes review task

Iteration 3:  next-task.py sees test-review task → returns as-is
              Worker reviews tests, fixes issues, closes test-review task

Iteration 4:  next-task.py expands "Fix login bug" → returns impl task
              ...

Iteration N:  bd ready returns nothing → worker outputs /done → ralph stops
```

### What Each Phase Does

**Implementation** (label: `implementation`)
- Inherits the parent task's full description, acceptance criteria, design notes
- Instructions: TDD methodology, >90% coverage, typecheck + lint
- Uses project's native build system scripts (not one-off commands)
- Creates new beads issues for out-of-scope problems discovered during work

**Code Review** (label: `code-review`)
- Reviews the implementation commit against acceptance criteria
- Checks for security issues, clean code, idiomatic patterns
- Runs typecheck, linter, and coverage check
- Fixes issues directly (doesn't just report them)

**Test Review** (label: `test-review`)
- Checks that every assertion matches its test's stated intent
- Catches anti-patterns: `assert(true).toBe(true)`, vague `not.toThrow()` checks
- Verifies >90% coverage on all metrics (lines, branches, functions, statements)
- Adds missing tests for uncovered branches and edge cases

### Why Not Beads Molecules?

Beads has a [molecules system](https://github.com/your-org/beads) for template-based task expansion. A minimal molecule that creates 3 sequential tasks is ~20 lines of TOML + 1 command. Molecules win on **structural simplicity**.

But `next-task.py` wins on **context richness**:

| | Molecules | next-task.py |
|---|---|---|
| Define 3-task structure | 20 lines TOML | Built into script |
| Create tasks with deps | `bd mol pour` (1 command) | Automatic at pull time |
| Variable substitution | `{{name}}` in titles | Full field inheritance from parent |
| Rich phase instructions | Must be static in formula | Dynamic, built from parent's AC/description/design |
| Review tasks reference impl | Manual cross-reference | Automatic (parent task ID in notes) |
| Lazy expansion | No (expand at load time) | Yes (expand when task reaches front of queue) |

The key advantage: with `next-task.py`, you load tasks into beads with `bd create` using any amount of detail, and the expansion inherits all of it. With molecules, the template is static — you'd still need something like `next-task.py` to populate descriptions dynamically.

## Quick Start

```bash
# Prerequisites: beads CLI (bd) installed, repo initialized
bd init

# Load tasks with full descriptions
bd create "Add OAuth support" -p P1 \
    --description "Support Google and GitHub OAuth providers via passport.js" \
    --acceptance "- Google OAuth login works e2e
- GitHub OAuth login works e2e
- Existing password auth unaffected
- Tokens stored server-side only" \
    --design "Add OAuthProvider interface in src/auth/. Each provider implements authorize() and callback()."

bd create "Fix login timeout" -p P0 \
    --description "Redis connection times out under sustained load (>500 concurrent)" \
    --acceptance "- Login succeeds under 1000 concurrent connections
- p95 response time < 2s
- Circuit breaker prevents cascade failures"

# Copy templates into your project
cp /path/to/swarm/templates/beads-ralph/PROMPT.md ./PROMPT.md
cp /path/to/swarm/templates/beads-ralph/next-task.py ./next-task.py

# Launch ralph
swarm ralph spawn --name worker --prompt-file ./PROMPT.md --max-iterations 100 \
    -- claude --dangerously-skip-permissions
```

The P0 task ("Fix login timeout") surfaces first. `next-task.py` expands it into implement → review → test-review. After all 3 phases complete, the P1 task surfaces and the cycle repeats.

## File Layout

```
project/
├── CLAUDE.md                   # Project context (unchanged)
├── PROMPT.md                   # Beads-aware ralph prompt (from template)
├── next-task.py                # Task expansion middleware (from template)
└── .beads/                     # Beads data (auto-created by bd init)
    └── issues.jsonl
```

No `IMPLEMENTATION_PLAN.md` needed. Beads replaces it.

## Templates

The templates live in `swarm/templates/beads-ralph/`:

| File | Purpose |
|------|---------|
| `PROMPT.md` | Ralph prompt that calls `next-task.py`, claims the task, dispatches by label |
| `next-task.py` | Middleware: pulls from `bd ready`, expands raw tasks into 3 phases with rich descriptions |

Copy both into your project root before launching ralph.

## Customizing Phase Instructions

The phase descriptions are Python triple-quoted strings in `next-task.py`. Edit them to match your project's practices:

- `IMPLEMENTATION_DESCRIPTION` — TDD methodology, build system commands
- `CODE_REVIEW_DESCRIPTION` — review checklist, security checks
- `TEST_REVIEW_DESCRIPTION` — assertion anti-patterns, coverage thresholds

For example, if your project uses `make lint` instead of a generic "run the linter":

```python
IMPLEMENTATION_DESCRIPTION = """\
...
### Quality Gates
- Run `make lint` and `make typecheck`.
- Run `make test-coverage` — all metrics must be >90%.
...
"""
```

## Monitoring Progress

```bash
# Task counts
bd ready                           # What's next in the queue
bd list --status in_progress       # What's being worked on
bd list --status closed            # What's done

# Ralph iteration progress
swarm ralph status worker
swarm ralph logs worker --live

# Git commits from workers
git log --oneline -10
```

## Comparison to Other Patterns

| | IMPLEMENTATION_PLAN.md | Beads + next-task.py | Beads Molecules |
|---|---|---|---|
| Task store | Markdown checklist | Beads database | Beads database |
| Dependencies | None (flat list) | Blocking deps | Blocking deps |
| Priority ordering | Subjective | `bd ready` sort policy | `bd ready` sort policy |
| Review cycle | None | Automatic (3 phases) | Manual (define in formula) |
| Task detail | One line | Full description/AC/design | Template-static |
| Setup complexity | Zero | Copy 2 files + `bd init` | Write formula + `bd init` |
| Lazy expansion | N/A | Yes | No |

## Sandboxing

This pattern works with Docker sandboxing described in the [Autonomous Loop Guide](autonomous-loop-guide.md) and [Director Guide](sandboxed-director-guide.md). The only additional requirement is that `bd` (beads CLI) must be available inside the sandbox:

- **Docker sandbox**: Add `bd` to `Dockerfile.sandbox`
- **No sandbox**: Works as-is
