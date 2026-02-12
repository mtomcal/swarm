Read CLAUDE.md, then read IMPLEMENTATION_PLAN.md and pick ONE incomplete task (marked with `[ ]`). Work in phase order.

RULES:

- Verify by reading actual code/files before changing anything
- Tightly coupled tasks within the same phase MAY be combined in a single iteration (e.g., 1.1+1.2, 2.1+2.2, 3.1+3.2)
- Mark each completed task `[x]` in IMPLEMENTATION_PLAN.md
- Commit and push when done
- Do NOT run `make test` — it crashes swarm workers

PHASE-SPECIFIC NOTES:

- Phase 1 (`swarm peek`): The underlying helpers already exist. `tmux_capture_pane()` is at ~line 3200, `tmux_window_exists()` at ~line 3196, `State.get_worker()` at ~line 2801. Follow the pattern of `cmd_status()` for error handling and exit codes. Add `peek_p = subparsers.add_parser("peek", ...)` after the `status` parser (~line 3601). Implement `cmd_peek(args)` near the other `cmd_*` functions. For `--all`, filter to running tmux workers and print `=== worker-name ===` headers. Exit codes: 0=success, 1=error, 2=not found. Tasks 1.1+1.2 are tightly coupled — combine them.
- Phase 2 (env propagation): In `create_tmux_window()` (~line 3153), add an `env: Optional[dict[str, str]] = None` parameter. When env is non-empty, prepend `env KEY1=VAL1 KEY2=VAL2` to `cmd_str` using `shlex.quote()` on keys and values. Then thread env through callers: `cmd_spawn()` (~line 4190), `_do_ralph_spawn()`, `cmd_respawn()`. Tasks 2.1+2.2 are tightly coupled — combine them.
- Phase 3 (transactional rollback): See `_rollback_ralph_spawn()` (~line 5203) for the pattern. Track `created_worktree`, `created_tmux`, `spawned_pid` as local vars in `cmd_spawn()`. Wrap tmux/process creation and state add in try/except. On failure, call `_rollback_spawn()` which cleans in reverse order: kill window/process, remove worktree. Print `"swarm: warning: spawn failed, cleaning up partial state"`. Tasks 3.1+3.2 are tightly coupled — combine them.
- Phase 4 (corrupt state): Wrap `json.load(f)` in `State._load()` (~line 2774) with try/except `json.JSONDecodeError`. On error: print `"swarm: warning: corrupt state file, resetting"` to stderr, back up to `~/.swarm/state.json.corrupted`, set `self.workers = []`. Same pattern as `load_ralph_state()` corrupt recovery (~line 2643).

TESTING:

- After Phase 1 changes: `python3 -m unittest test_cmd_peek -v`
- After Phase 2 changes: `python3 -m unittest test_cmd_spawn -v`
- After Phase 3 changes: `python3 -m unittest test_cmd_spawn -v`
- After Phase 4 changes: `python3 -m unittest test_state_file_locking -v`
- Phase 5 verification: `python3 -m unittest test_cmd_peek test_cmd_spawn test_state_file_locking test_cmd_ralph test_cmd_kill test_cmd_init test_cmd_heartbeat -v`

DONE SIGNAL:

If ALL tasks in IMPLEMENTATION_PLAN.md are `[x]`, output /done on its own line and stop.
