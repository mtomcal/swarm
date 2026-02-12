Read CLAUDE.md, then read IMPLEMENTATION_PLAN.md and pick ONE incomplete task (marked with `[ ]`). Work in phase order.

RULES:

- Verify by reading actual code/files before changing anything
- Tightly coupled tasks within the same phase MAY be combined in a single iteration (e.g., 3.1+3.2+3.3, 4.1+4.2, 7.1+7.2+7.3)
- Mark each completed task `[x]` in IMPLEMENTATION_PLAN.md
- Commit and push when done
- Do NOT run `make test` — it crashes swarm workers

PHASE-SPECIFIC NOTES:

- Phase 1 (login/OAuth patterns): Add `Select login method` and `Paste code here` to the `not_ready_patterns` list in `wait_for_agent_ready()` (~line 3279). They join existing theme picker patterns. Then tests in `test_ready_patterns.py`.
- Phase 2 (corrupt state): Wrap `json.load()` in `load_ralph_state()` (~line 2604) with try/except for `json.JSONDecodeError`. On error: log warning, back up to `state.json.corrupted`, return fresh RalphState. Then tests.
- Phase 3 (screen change tracking): Add `last_screen_change: Optional[str] = None` to `RalphState` (~line 1997). In `detect_inactivity()` (~line 5963), when screen hash changes, set `ralph_state.last_screen_change = datetime.now(timezone.utc).isoformat()` and save state. In `cmd_ralph_status()` (~line 5579), parse the ISO timestamp and display `Last screen change: Ns ago`. Tasks 3.1-3.3 are tightly coupled — combine them.
- Phase 4 (stuck patterns): Define `STUCK_PATTERNS` dict near module constants. In `detect_inactivity()`, check screen content against stuck patterns each poll cycle and log `[WARN]` once per pattern per iteration. Tasks 4.1+4.2 are tightly coupled — combine them.
- Phase 5 (stuck status): In `cmd_ralph_status()`, if `last_screen_change` is >60s ago, append `(possibly stuck)` to Status line and show last 5 terminal lines. Depends on Phase 3.
- Phase 6 (pre-flight): After `send_prompt_to_worker()` on iteration 1 only, wait 10s, peek terminal, check against `STUCK_PATTERNS`. If stuck: log `[ERROR]`, print actionable error, kill worker, exit 1. Depends on Phase 4.
- Phase 7 (`--foreground`): Add `--foreground` arg. Default (no flag): start monitoring loop as background subprocess via `subprocess.Popen(['python3', 'swarm.py', 'ralph', 'run', name], start_new_session=True)`, print monitoring commands, return immediately. `--foreground`: block (current behavior). Store monitor PID in ralph state as `monitor_pid` for `--replace` cleanup. Tasks 7.1-7.4 are tightly coupled — combine them.

TESTING:

- After Phase 1 changes: `python3 -m unittest test_ready_patterns -v`
- After Phase 2 changes: `python3 -m unittest test_cmd_ralph -v`
- After Phase 3-6 changes: `python3 -m unittest test_cmd_ralph -v`
- After Phase 7 changes: `python3 -m unittest test_cmd_ralph -v`
- Phase 8 verification: `python3 -m unittest test_cmd_ralph test_ready_patterns test_cmd_spawn test_cmd_kill test_cmd_init test_cmd_heartbeat -v`

DONE SIGNAL:

If ALL tasks in IMPLEMENTATION_PLAN.md are `[x]`, output SWARM_DONE_X9K on its own line and stop.
