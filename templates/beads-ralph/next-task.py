#!/usr/bin/env python3
"""Pull the next ready task from beads, expanding raw tasks into 3 phases.

When the next ready task has no phase label (implementation, code-review,
test-review), it's a raw task. This script expands it into 3 child tasks
with blocking dependencies and returns the first child (implementation).

If the next ready task already has a phase label, it's returned as-is.
If no tasks are ready, exits 1.

Usage (called by PROMPT.md):
    id=$(python3 next-task.py)
    bd show "$id"

Expansion:
    Original task (closed as "expanded")
    +-- Implement: <title>     [implementation]  <- returned, ready
    +-- Code review: <title>   [code-review]     <- blocked by impl
    +-- Test review: <title>   [test-review]     <- blocked by review
"""

import json
import subprocess
import sys

PHASE_LABELS = {"implementation", "code-review", "test-review"}

# ---------------------------------------------------------------------------
# Phase description templates
#
# These get baked into each child task's description/acceptance/notes fields.
# The ralph worker reads these fields and follows them as instructions.
# ---------------------------------------------------------------------------

IMPLEMENTATION_DESCRIPTION = """\
Implement: {title}

{description}

## Approach

You are a senior engineer. Use first principles, test-driven development,
clean code, and best practices.

### Methodology
1. Read the last commit (`git log -1` and `git diff HEAD~1`) for context on
   recent changes that may affect this work.
2. Write failing tests FIRST that cover the acceptance criteria.
3. Implement the minimum code to make tests pass.
4. Refactor for clarity while keeping tests green.
5. Use the project's native build system scripts for testing, linting, and
   typechecking (e.g. `make test`, `npm test`, `poetry run pytest`). Do NOT
   use one-off commands like `npx` or complex shell pipelines.

### Quality Gates
- Run typecheck and linter from the project's build file.
- Run unit tests with coverage — all metrics (lines, branches, functions,
  statements) must be >90%.
- If integration tests exist, run them and verify they still pass.

### Out-of-Scope Issues
If you discover an issue outside the scope of this task, create a new beads
issue (`bd create`), add it as a blocker if it blocks this work, and note it.
Do not try to fix unrelated problems in this iteration.\
"""

IMPLEMENTATION_ACCEPTANCE = """\
{acceptance}

Additionally:
- All tests pass with >90% coverage on all metrics (lines, branches,
  functions, statements).
- Typecheck and linter pass with no new warnings.
- Code uses project conventions and idiomatic patterns.
- No debug artifacts, commented-out code, or TODOs left behind.\
"""

# ---

CODE_REVIEW_DESCRIPTION = """\
Code review: {title}

Review the implementation of "{title}" against its acceptance criteria and
engineering best practices. You are a senior engineer reviewing a colleague's
work. Fix issues directly — do not just report them.

## Review Process

1. Read the last commit(s) related to this feature:
   - `git log --oneline -5` to find relevant commits.
   - `git diff HEAD~1` (or appropriate range) to see the full diff.
2. Read the original implementation task's acceptance criteria (referenced in
   notes below).

### Acceptance Criteria Review
- Walk through EACH acceptance criterion and verify it is met by the code.
- Check that edge cases mentioned in the criteria are handled.
- Verify error handling covers the specified failure modes.

### Code Quality Review
- Run typecheck and linter from the project's build file.
- Review for best practices and idiomatic usage of the programming language.
- Check for clean code: meaningful names, small functions, single
  responsibility, no duplication.
- Look for security issues: injection, XSS, unsafe deserialization, hardcoded
  secrets, etc.
- Verify no dead code, debug artifacts, or commented-out code was left behind.

### Coverage Check
- Run unit tests with coverage. All metrics must be >90%.
- If integration tests exist, run them.

### Fixing Issues
- Fix problems directly in the code. Commit the fixes.
- If a fix is too large for this iteration, create a new beads issue
  (`bd create`) and note it.\
"""

CODE_REVIEW_ACCEPTANCE = """\
- All acceptance criteria from the implementation task are verified met.
- Typecheck and linter pass with no new warnings.
- No security issues found (or all found issues are fixed).
- Code follows existing project patterns and conventions.
- No dead code, debug artifacts, or TODOs left behind.
- Test coverage remains >90% on all metrics after any fixes.\
"""

# ---

TEST_REVIEW_DESCRIPTION = """\
Test review: {title}

Review all tests written for "{title}". You are a senior QA engineer. Your job
is to ensure every test assertion actually validates what the test name claims
to test. Fix issues directly — do not just report them.

## Review Process

1. Read the last commit(s) to identify which test files were added or changed.
2. Read the original implementation task's acceptance criteria (referenced in
   notes below).

### Assertion Quality (Critical)
Read each test carefully and check for these anti-patterns:

**Assertions don't match intent:**
- BAD:  test "should call addPlayer" / `assert(true).toBe(true)`
- GOOD: test "should call addPlayer" / `assert(addPlayer).toHaveBeenCalled(1)`

**Assertions are too vague for the intent:**
- BAD:  test "should call addPlayer" / `assert(() => addPlayer()).not.toThrow()`
- GOOD: test "should call addPlayer" / `assert(addPlayer).toHaveBeenCalled(1)`

**Other anti-patterns to catch:**
- Tests that only check "no error thrown" instead of checking return values.
- Tests that assert on mock implementation details instead of behavior.
- Tests with no assertions at all (relying on "it didn't throw").
- Snapshot tests used as a substitute for behavioral assertions.
- Tests that duplicate each other without adding coverage.

### Coverage Check
- Run unit tests with coverage from the project's build file.
- All metrics (lines, branches, functions, statements) must be >90%.
- Identify untested branches or edge cases and add tests for them.

### Integration Test Review
- If integration tests exist, verify they cover the acceptance criteria
  end-to-end.
- If acceptance criteria have scenarios not covered by integration tests,
  add them.

### Fixing Issues
- Rewrite bad assertions to match test intent.
- Add missing tests for uncovered branches/edge cases.
- Remove duplicate tests that add no value.
- If a fix is too large for this iteration, create a new beads issue
  (`bd create`) and note it.\
"""

TEST_REVIEW_ACCEPTANCE = """\
- Every test assertion matches the test's stated intent (name/description).
- No false-positive tests (tests that pass for the wrong reason).
- No overly vague assertions (not.toThrow, toBeTruthy) where specific
  checks are possible.
- Coverage >90% on ALL metrics: lines, branches, functions, statements.
- Integration tests (if they exist) cover acceptance criteria scenarios.
- No duplicate tests that add no additional coverage.\
"""


def run(cmd: list[str], check: bool = True) -> str:
    """Run a command and return stripped stdout."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


def bd(*args: str, check: bool = True) -> str:
    """Run a bd command."""
    return run(["bd", *args], check=check)


def get_ready_task() -> dict | None:
    """Get the top ready task as a dict, or None if queue is empty."""
    raw = bd("ready", "--limit", "1", "--json", check=False)
    if not raw or raw in ("[]", "null"):
        return None
    tasks = json.loads(raw)
    if not tasks:
        return None
    return tasks[0]


def get_task_details(task_id: str) -> dict:
    """Get full task details including labels."""
    raw = bd("show", "--json", task_id)
    return json.loads(raw)


def has_phase_label(details: dict) -> bool:
    """Check if a task already has a phase label."""
    labels = set(details.get("labels", []) or [])
    return bool(labels & PHASE_LABELS)


def extract_field(details: dict, field: str) -> str:
    """Extract a field from task details, returning empty string for null/missing."""
    val = details.get("issue", {}).get(field)
    if val is None:
        return ""
    return str(val)


def create_task(title: str, label: str, priority: str,
                description: str, acceptance: str,
                notes: str = "") -> str:
    """Create a beads task and return its ID."""
    args = [
        "create", title,
        "--type", "task",
        "--labels", label,
        "-p", priority,
        "--description", description,
        "--acceptance", acceptance,
        "--silent",
    ]
    if notes:
        args.extend(["--notes", notes])
    return bd(*args)


def expand_task(details: dict) -> str:
    """Expand a raw task into 3 phases. Returns the implementation task ID."""
    issue = details.get("issue", {})
    task_id = issue.get("id", "")
    title = issue.get("title", "")
    description = issue.get("description", "") or ""
    acceptance = issue.get("acceptance_criteria", "") or ""
    design = issue.get("design", "") or ""
    notes = issue.get("notes", "") or ""
    priority = str(issue.get("priority", 2))

    # Build implementation notes from parent fields
    impl_notes_parts = []
    if design:
        impl_notes_parts.append(f"## Design\n{design}")
    if notes:
        impl_notes_parts.append(f"## Prior Notes\n{notes}")
    impl_notes = "\n\n".join(impl_notes_parts)

    # Reference notes for reviewers
    review_notes = f"Parent task: {task_id}\nReview the work done for: Implement: {title}"

    # 1. Implementation task — inherits full parent content
    impl_id = create_task(
        title=f"Implement: {title}",
        label="implementation",
        priority=priority,
        description=IMPLEMENTATION_DESCRIPTION.format(
            title=title, description=description,
        ),
        acceptance=IMPLEMENTATION_ACCEPTANCE.format(acceptance=acceptance),
        notes=impl_notes,
    )

    # 2. Code review task
    review_id = create_task(
        title=f"Code review: {title}",
        label="code-review",
        priority=priority,
        description=CODE_REVIEW_DESCRIPTION.format(title=title),
        acceptance=CODE_REVIEW_ACCEPTANCE,
        notes=review_notes,
    )
    bd("dep", "add", review_id, impl_id, "--type", "blocks")

    # 3. Test review task
    test_review_id = create_task(
        title=f"Test review: {title}",
        label="test-review",
        priority=priority,
        description=TEST_REVIEW_DESCRIPTION.format(title=title),
        acceptance=TEST_REVIEW_ACCEPTANCE,
        notes=review_notes,
    )
    bd("dep", "add", test_review_id, review_id, "--type", "blocks")

    # Close parent — it's been expanded
    bd("close", task_id,
       "--reason", f"Expanded into {impl_id}, {review_id}, {test_review_id}")

    print(f"Expanded {task_id} -> {impl_id}, {review_id}, {test_review_id}",
          file=sys.stderr)

    return impl_id


def main() -> None:
    ready = get_ready_task()
    if not ready:
        sys.exit(1)

    task_id = ready["issue"]["id"]
    details = get_task_details(task_id)

    if has_phase_label(details):
        # Already a phase task — return as-is
        print(task_id)
    else:
        # Raw task — expand and return implementation child
        impl_id = expand_task(details)
        print(impl_id)


if __name__ == "__main__":
    main()
