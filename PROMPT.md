# Swarm Implementation Task

You are implementing features for the swarm CLI tool.

## Instructions

1. Read `IMPLEMENTATION_PLAN.md` to understand the full project
2. Read `specs/README.md` to find relevant behavioral specs
3. Pick ONE incomplete task (marked with `[ ]`)
4. Implement the task following the spec
5. Add tests if the task involves code changes (follow patterns in existing `test_*.py` files)
6. Run tests after changes: `python3 -m unittest <test_file> -v`
7. Mark the task complete in `IMPLEMENTATION_PLAN.md` (change `[ ]` to `[x]`)
8. Commit and push your changes

## Important Guidelines

- **ONE task per iteration** - don't try to do multiple tasks
- **Read the spec first** - specs define the expected behavior
- **Follow existing patterns** - look at how similar features are implemented
- **Test your changes** - run the relevant test file before committing
- **Keep commits focused** - one task = one commit

## Relevant Specs

| Feature | Spec File |
|---------|-----------|
| Heartbeat | `specs/heartbeat.md` |
| Workflow | `specs/workflow.md` |
| CLI Help | `specs/cli-help-standards.md` |
| Ralph Loop | `specs/ralph-loop.md` |
| State Management | `specs/state-management.md` |
| Data Structures | `specs/data-structures.md` |

## Test Commands

```bash
# Run specific test file
python3 -m unittest test_cmd_ralph -v
python3 -m unittest test_cmd_spawn -v

# Run all tests (WARNING: may crash swarm workers in this repo)
# Only use for final verification
make test
```

## When Done

Say `/done` when you have completed and committed a task.
