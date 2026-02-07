Read CLAUDE.md, then read IMPLEMENTATION_PLAN.md and pick ONE incomplete task (marked with `[ ]`). Work in phase order.

IMPORTANT:

- Do NOT assume anything is already done -- verify by reading the actual code/files
- Phase 1 tasks (1.1-1.5) all edit swarm.py -- do them in order, one per iteration
- Phase 2 tasks (2.1-2.2) DELETE entire test files -- use `rm` in bash
- Phase 3 tasks (3.1-3.2) delete spec file and update README
- Phase 4 tasks (4.1-4.3) are doc updates
- Phase 5 tasks (5.1-5.2) clean up remaining references
- Phase 6 tasks (6.1-6.3) are verification -- run tests, grep for stale references
- When deleting code from swarm.py, be careful not to break surrounding code (check indentation, function boundaries)
- After code changes, run relevant tests: `python3 -m unittest test_cmd_spawn test_cmd_kill test_cmd_ralph test_cmd_init test_cmd_heartbeat -v`
- Do NOT run `make test` -- it crashes swarm workers
- Mark the task `[x]` in IMPLEMENTATION_PLAN.md when done
- Commit and push when done
