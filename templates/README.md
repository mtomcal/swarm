# Swarm Templates

Reusable prompt and script templates for common ralph workflows.

## beads-ralph/

Beads-driven task queue for ralph. Replaces `IMPLEMENTATION_PLAN.md` with beads as the task store. Each task auto-expands into 3 phases: implementation, code review, and test review.

| File | Purpose |
|------|---------|
| `PROMPT.md` | Ralph prompt — calls `next-task.py`, claims the task, dispatches by label |
| `next-task.py` | Middleware — pulls from `bd ready`, expands raw tasks into 3 phases with rich descriptions |

### Usage

```bash
# In your project
bd init
cp /path/to/swarm/templates/beads-ralph/PROMPT.md ./PROMPT.md
cp /path/to/swarm/templates/beads-ralph/next-task.py ./next-task.py

# Load tasks
bd create "Add feature X" -p P1 --description "..." --acceptance "..."

# Run
swarm ralph spawn --name worker --prompt-file ./PROMPT.md --max-iterations 100 \
    -- claude --dangerously-skip-permissions
```

See [docs/beads-ralph-queue.md](../docs/beads-ralph-queue.md) for the full guide.
