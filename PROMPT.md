Read CLAUDE.md, then read IMPLEMENTATION_PLAN.md and pick ONE incomplete task (marked with `[ ]`). Work in phase order.

RULES:

- Verify by reading actual code/files before changing anything
- Tightly coupled tasks within the same phase MAY be combined in a single iteration (see phase notes below)
- Mark each completed task `[x]` in IMPLEMENTATION_PLAN.md
- Commit and push when done
- Do NOT run `make test` — it crashes swarm workers

PHASE-SPECIFIC NOTES:

- Phase 1 (fatal pattern detection): Tasks 1.1+1.2+1.3 are tightly coupled — combine them all. Add a `FATAL_PATTERNS = ["Compacting conversation"]` constant near the existing `STUCK_PATTERNS`. In `detect_inactivity()` (~line 6307), after capturing pane content, check `if any(p in content for p in FATAL_PATTERNS): return "compaction"`. In the ralph outer loop (~line 7010), handle `"compaction"` return: SIGTERM the worker, log `[FATAL] iteration N -- compaction detected, killing`, set `exit_reason: "compaction"` in RalphState, do NOT count as consecutive failure, proceed to next iteration. Add unit tests in `test_cmd_ralph.py`.

- Phase 2 (done-pattern auto-enable): Tasks 2.1+2.2 — combine them. Change `--check-done-continuous` (~line 4011) from `action="store_true"` to `action=argparse.BooleanOptionalAction, default=None`. This gives `--check-done-continuous` and `--no-check-done-continuous`. After argparse, in `cmd_ralph_spawn()`, if `args.done_pattern` is set and `args.check_done_continuous is None`, set `args.check_done_continuous = True`. Add unit tests in `test_cmd_ralph.py`.

- Phase 3 (pre-clear in tmux_send): Tasks 3.1+3.2+3.3+3.4 — combine them all. Modify `tmux_send()` (~line 3235) to add `pre_clear: bool = True`. When True: send `Escape` key, send `C-u` key, then send literal text, then Enter if requested. Add `--raw` flag to send subparser (~line 3680), pass `pre_clear=not args.raw` in `cmd_send()`. **CRITICAL**: grep for ALL existing `tmux_send(` calls and add `pre_clear=False` to internal callers: `send_prompt_to_worker()`, `run_heartbeat_monitor()`, `cmd_interrupt()`, `cmd_eof()`, and any others. Only `cmd_send()` should use pre-clear. Add tests.

- Phase 4 (max-context): Tasks 4.1+4.2+4.3+4.4 — combine them. Add `--max-context` to ralph spawn argparse (`type=int, default=None`). Add `max_context: Optional[int] = None` to `RalphState` dataclass. In `detect_inactivity()`, when `max_context` is set, scan last 3 lines of pane content for `r'(\d+)%'` regex. Return `"context_nudge"` at threshold (first time only — use a `context_nudge_sent` flag), `"context_threshold"` at threshold+15. In the monitor loop: on `"context_nudge"`, send nudge via `tmux_send(pre_clear=False)`: `"You're at {n}% context. Commit WIP and /exit NOW."`. On `"context_threshold"`, SIGTERM + log `[FATAL] context threshold exceeded` + set `exit_reason: "context_threshold"`. Add tests in `test_cmd_ralph.py`.

- Phase 5 (CLI defaults & aliases): Tasks 5.1-5.5 — combine all. Change `--max-iterations` (~line 4002) from `required=True` to `default=50`. Change `--worktree` (~line 4030) from `action="store_true"` to `action=argparse.BooleanOptionalAction, default=True` (gives `--no-worktree`). Add `ralph stop` subparser that delegates to `cmd_kill()`. Add `heartbeat ls` subparser as alias for `heartbeat list`. **Watch for test breakage**: existing tests may assume `--max-iterations` is required or `--worktree` defaults to False — update test fixtures. Add tests in `test_cmd_ralph.py` and `test_cmd_heartbeat.py`.

- Phase 6+7 (crash-safe writes + window loss): Tasks 6.1+6.2+7.1+7.2 — combine all. In `State._save()` (~line 2848), `save_ralph_state()`, and `save_heartbeat_state()`: write to a temp file in the same directory, then `os.replace()` to the target path (atomic on POSIX). For window loss: in `detect_inactivity()` `CalledProcessError` handler, check done pattern against `last_content` before returning — if matched, return `"done"` instead of `"exited"`, log `[END] iteration N -- tmux window lost`. Add tests in `test_state_file_locking.py` and `test_cmd_ralph.py`.

- Phase 8 (help text & metadata): Tasks 8.1+8.2+8.3 — combine all. Add disambiguation notes: `STATUS_HELP_DESCRIPTION` mention `swarm ralph status`, `LOGS_HELP_DESCRIPTION` mention `swarm ralph logs`, `CLEAN_HELP_DESCRIPTION` mention `swarm ralph clean`, `RALPH_STATUS_HELP_EPILOG` mention `swarm status`. In `cmd_respawn()` (~line 5168), preserve `metadata` field — include it in the saved fields dict and pass to new Worker creation. Add test in `test_cmd_spawn.py`.

- Phase 9 (verification): Run all unit tests: `python3 -m unittest test_cmd_ralph test_cmd_spawn test_cmd_heartbeat test_state_file_locking test_cmd_peek test_cmd_kill test_cmd_init -v`. Verify CLI: `python3 swarm.py ralph spawn --help`, `python3 swarm.py send --help`, `python3 swarm.py ralph stop --help`, `python3 swarm.py heartbeat ls`. Run full suite: `python3 -m unittest discover -s . -p 'test_*.py' -v`.

- Phase 10 (smoke tests): Each task is ONE smoke test — pick ONE `[ ]` task from Phase 10. Write a bash script or run commands inline that: (1) spawns a test worker via `python3 swarm.py` with a unique `smoke-fbN` name and `--no-worktree`, (2) polls status/logs with sleep loops waiting for expected behavior, (3) asserts expected strings in output (grep for them), (4) cleans up with `python3 swarm.py kill` + `python3 swarm.py ralph clean`. If all assertions pass, mark the task `[x]` and commit. If an assertion fails, do NOT mark `[x]` — leave for next iteration. **Always clean up test workers even on failure.** These tests require tmux.

TESTING:

- After Phase 1 changes: `python3 -m unittest test_cmd_ralph -v`
- After Phase 2 changes: `python3 -m unittest test_cmd_ralph -v`
- After Phase 3 changes: `python3 -m unittest test_cmd_spawn -v`
- After Phase 4 changes: `python3 -m unittest test_cmd_ralph -v`
- After Phase 5 changes: `python3 -m unittest test_cmd_ralph test_cmd_heartbeat -v`
- After Phase 6+7 changes: `python3 -m unittest test_state_file_locking test_cmd_ralph -v`
- After Phase 8 changes: `python3 -m unittest test_cmd_spawn -v`
- Phase 9: `python3 -m unittest discover -s . -p 'test_*.py' -v`
- Phase 10: no separate test command — the task IS the test

DONE SIGNAL:

If ALL tasks in IMPLEMENTATION_PLAN.md are `[x]` (Phases 1-10), output /done on its own line and stop.
