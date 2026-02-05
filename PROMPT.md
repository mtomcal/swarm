# Swarm Ralph Bug Fixes and Improvements

You are implementing bug fixes and features for the swarm CLI tool based on real user feedback.

## Instructions

1. Read `IMPLEMENTATION_PLAN.md` to understand the full project
2. Read `FEEDBACK.md` to understand the user problems being solved
3. Pick ONE incomplete task (marked with `[ ]`) - **work in phase order**
4. Read the relevant spec file before implementing
5. Implement the task following the spec
6. Add tests if the task involves code changes
7. Run tests: `python3 -m unittest test_cmd_ralph -v` (or relevant test file)
8. Mark the task complete in `IMPLEMENTATION_PLAN.md` (change `[ ]` to `[x]`)
9. Commit your changes with a descriptive message

## Important Guidelines

- **ONE task per iteration** - don't try to do multiple tasks
- **Phases are ordered** - complete Phase 1 before Phase 2, etc.
- **Read the spec first** - specs define the expected behavior
- **Update specs before code** - Phase 1 updates specs, Phase 2+ implements
- **Follow existing patterns** - look at how similar features are implemented
- **Test your changes** - run the relevant test file before committing
- **Keep commits focused** - one task = one commit

## Phase Order

1. **Phase 1: Spec Updates** - Update behavioral specs FIRST
2. **Phase 2: Bug Fixes** - Fix the 7 bugs (B1-B7)
3. **Phase 3: Features** - Add the 5 new features (F1-F5, F7)
4. **Phase 4: Testing** - Add comprehensive tests
5. **Phase 5: Documentation** - Update CLAUDE.md and help text
6. **Phase 6: Verification** - Manual testing

## Relevant Specs

| Feature | Spec File |
|---------|-----------|
| Ralph Loop | `specs/ralph-loop.md` |
| Kill Command | `specs/kill.md` |
| Spawn Command | `specs/spawn.md` |
| Worktree Isolation | `specs/worktree-isolation.md` |
| CLI Interface | `specs/cli-interface.md` |
| Data Structures | `specs/data-structures.md` |
| Logs Command | `specs/logs.md` |
| CLI Help Standards | `specs/cli-help-standards.md` |

## Bug Reference

| ID | Bug | Root Cause |
|----|-----|------------|
| B1 | Ralph state persists after `kill --rm-worktree` | `cmd_kill()` never deletes ralph state |
| B2 | Partial state on failed spawn | No transaction rollback |
| B3 | `git config core.bare = true` corruption | Poor error handling in `create_worktree()` |
| B4 | Status shows "killed" for successful completions | Always logs `reason=killed` |
| B5 | Monitor disconnects while worker runs | No worker-alive verification |
| B6 | `--tmux` flag errors for ralph spawn | Flag not accepted |
| B7 | 60s inactivity timeout too short | Hardcoded default |

## Feature Reference

| ID | Feature | Description |
|----|---------|-------------|
| F1 | `--replace` flag | Auto-clean existing worker before spawn |
| F2 | `ralph logs` command | View iteration history |
| F3 | ETA in status | Show estimated time remaining |
| F5 | `--clean-state` flag | Clear ralph state without killing worker |
| F7 | Best practices docs | Document test artifact prevention |

## Test Commands

```bash
# Run ralph-specific tests
python3 -m unittest test_cmd_ralph -v

# Run kill command tests
python3 -m unittest test_cmd_kill -v

# Run worktree tests
python3 -m unittest test_worktree_protection -v

# Run integration tests (requires tmux)
timeout 120 python3 -m unittest tests.test_integration_ralph -v

# WARNING: Do NOT run `make test` - it crashes swarm workers in this repo
# Run specific test files instead
```

## When Done

Say `/done` when you have completed and committed a task.
