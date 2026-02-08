Read CLAUDE.md for project context.

## Your Task

Pull the next ready task and execute it.

### Step 1: Get next task

```bash
id=$(python3 next-task.py)
```

If the script exits non-zero (no output), all tasks are complete. Output `/done` on its own line and stop.

### Step 2: Claim the task

```bash
bd update "$id" --status in_progress
```

### Step 3: Read the full task

```bash
bd show "$id"
```

Read the **description**, **acceptance criteria**, **design**, and **notes** fields carefully. They contain your full instructions.

### Step 4: Determine work type from labels

```bash
bd show --json "$id" | jq -r '.labels[]'
```

The label tells you what kind of work to do:

- **`implementation`** — Write code. Follow the description and acceptance criteria exactly. Use TDD. Run tests after changes. Commit when done.
- **`code-review`** — Review the most recent implementation. Read the diff, check against acceptance criteria in the task description. Fix any issues directly, don't just report them. Commit fixes.
- **`test-review`** — Review tests for the most recent implementation. Check that assertions match test intent, no false positives, coverage is adequate. Fix any issues directly. Commit fixes.

### Step 5: Close the task

```bash
bd close "$id" --reason "done: <short summary of what you did>"
```

### Rules

- Do ONE task per iteration
- Do NOT assume anything is already done — verify by reading actual code/files
- Do NOT run `make test` if CLAUDE.md warns against it — run specific test files instead
- Commit and push when done
- If `next-task.py` returns nothing, output `/done` on its own line and stop
