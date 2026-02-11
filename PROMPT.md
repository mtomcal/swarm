Read CLAUDE.md, then read IMPLEMENTATION_PLAN.md and pick ONE incomplete task (marked with `[ ]`). Work in phase order.

RULES:

- Verify by reading actual code/files before changing anything
- Phases 1-2 tasks that edit swarm.py are tightly coupled — you MAY combine multiple swarm.py tasks in a single iteration if they depend on each other (e.g., 2.1+2.2+2.3)
- Mark each completed task `[x]` in IMPLEMENTATION_PLAN.md
- Commit and push when done
- Do NOT run `make test` — it crashes swarm workers

PHASE-SPECIFIC NOTES:

- Phase 1 (ralph ls): Add `ls` subparser mirroring `list` parser in main() ralph subparsers (~line 3820), add `"ls"` dispatch in cmd_ralph() (~line 5035), then tests
- Phase 2 (ralph clean): Add `clean` subparser, implement cmd_ralph_clean(), add dispatch, then tests. Tasks 2.1-2.3 may be combined.
- Phase 3 (theme picker): Add not-ready patterns (`Choose the text style`, `looks best with your terminal`) to wait_for_agent_ready() (~line 3176). When matched, send Enter via tmux to dismiss, continue polling. Then tests in test_ready_patterns.py
- Phase 4 (done-pattern baseline): After send_prompt_to_worker() (~line 6009), capture pane line count. Store as `prompt_baseline_lines` in RalphState. In detect_inactivity() (~line 5786), skip lines before baseline when checking done pattern. Then tests.

TESTING:

- After Phase 1-2 changes: `python3 -m unittest test_cmd_ralph -v`
- After Phase 3 changes: `python3 -m unittest test_ready_patterns -v`
- After Phase 4 changes: `python3 -m unittest test_cmd_ralph -v`
- Phase 5 verification: `python3 -m unittest test_cmd_ralph test_ready_patterns test_cmd_spawn test_cmd_kill test_cmd_init test_cmd_heartbeat -v`

DONE SIGNAL:

If ALL tasks in IMPLEMENTATION_PLAN.md are `[x]`, output `/done` on its own line and stop.
