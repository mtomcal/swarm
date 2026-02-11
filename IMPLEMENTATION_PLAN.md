# Implementation Plan: Round 2 Spec Changes (Docker Sandbox + Ralph UX)

**Created**: 2026-02-11
**Status**: COMPLETE
**Goal**: Implement code changes specified in the Round 2 spec updates — new `ralph clean` and `ralph ls` commands, theme picker detection in ready-detection, and done-pattern self-match mitigation.

---

## Context

Round 2 feedback from real-world Docker sandbox usage surfaced several issues. The specs and docs have already been updated (see `FEEDBACK.md` Round 2). One code fix has already been applied (`SANDBOX_SH_TEMPLATE` now has `-it` flags). The remaining items require implementation in `swarm.py` and new tests.

---

## Tasks

### Phase 1: `ralph ls` Alias

- [x] **1.1 Add `ls` subparser under ralph subparsers**
  - Add `ralph_subparsers.add_parser("ls", ...)` mirroring `ralph list` parser
  - File: `swarm.py` (in `main()` argparse setup, near ralph subparsers ~line 3729)

- [x] **1.2 Add dispatch in `cmd_ralph()`**
  - Add `"ls"` case in `cmd_ralph()` that calls `cmd_ralph_list(args)`
  - File: `swarm.py` (~line 5017-5034)

- [x] **1.3 Add unit tests for `ralph ls`**
  - Test that `ralph ls` produces identical output to `ralph list`
  - Test that `ralph ls` accepts same arguments (`--format`, `--status`)
  - File: `test_cmd_ralph.py`

### Phase 2: `ralph clean` Command

- [x] **2.1 Add `clean` subparser under ralph subparsers**
  - Positional `name` (optional), `--all` flag
  - Validate: one of `name` or `--all` required
  - File: `swarm.py` (in `main()` argparse setup)

- [x] **2.2 Implement `cmd_ralph_clean(args)` function**
  - If `name`: remove `~/.swarm/ralph/<name>/` directory
  - If `--all`: iterate `~/.swarm/ralph/*/` and remove each
  - Check if worker still running → print warning
  - Error if no ralph state found for named worker (exit 1)
  - `--all` with no state → no-op, exit 0
  - Output: "cleaned ralph state for <name>"
  - File: `swarm.py`

- [x] **2.3 Add dispatch in `cmd_ralph()`**
  - Add `"clean"` case in `cmd_ralph()` that calls `cmd_ralph_clean(args)`
  - File: `swarm.py`

- [x] **2.4 Add unit tests for `ralph clean`**
  - Test: clean specific worker removes state dir
  - Test: clean specific worker prints warning if worker still running
  - Test: clean non-existent worker → exit 1 with error message
  - Test: `--all` removes all ralph state dirs
  - Test: `--all` with no ralph state → no-op, exit 0
  - Test: neither name nor --all → error
  - File: `test_cmd_ralph.py`

### Phase 3: Theme Picker Not-Ready Detection

- [x] **3.1 Add not-ready patterns to `wait_for_agent_ready()`**
  - Add patterns: `Choose the text style`, `looks best with your terminal`
  - When a not-ready pattern matches, do NOT return True
  - Optionally: send Enter via `tmux send-keys` to dismiss theme picker, continue polling
  - File: `swarm.py` (~line 3199-3233, `wait_for_agent_ready()`)

- [x] **3.2 Add unit tests for theme picker detection**
  - Test: theme picker text does not trigger ready detection
  - Test: theme picker followed by real ready pattern eventually succeeds
  - File: `test_ready_patterns.py`

### Phase 4: Done Pattern Self-Match Mitigation

- [x] **4.1 Record baseline buffer position after prompt injection**
  - In `send_prompt_to_worker()` or immediately after, capture the current pane line count
  - Store as `prompt_baseline_lines` in ralph state or as a return value
  - File: `swarm.py`

- [x] **4.2 Filter baseline from done-pattern checking**
  - In `detect_inactivity()` when `check_done_continuous` is True:
    - Capture full pane content
    - Skip lines up to `prompt_baseline_lines`
    - Only match done pattern against lines AFTER the baseline
  - File: `swarm.py` (~line 5786-5888)

- [x] **4.3 Add unit tests for done-pattern baseline**
  - Test: done pattern in prompt text (before baseline) does NOT match
  - Test: done pattern in agent output (after baseline) DOES match
  - Test: baseline is recorded after prompt injection
  - File: `test_cmd_ralph.py`

### Phase 5: Verify

- [x] **5.1 Run unit tests**
  - `python3 -m unittest test_cmd_ralph -v`
  - `python3 -m unittest test_ready_patterns -v`
  - `python3 -m unittest test_cmd_spawn -v`

- [x] **5.2 Verify CLI**
  - `python3 swarm.py ralph ls --help` → shows list help
  - `python3 swarm.py ralph clean --help` → shows clean help
  - `python3 swarm.py ralph --help` → shows ls and clean in subcommands

- [x] **5.3 Run full test suite (carefully)**
  - `python3 -m unittest discover -s . -p 'test_*.py' -v`
  - Note: may crash swarm workers per CLAUDE.md caveat — run in isolation

---

## Files Modified

| File | Change |
|------|--------|
| `swarm.py` | Add `ralph ls` alias, `ralph clean` command, theme picker not-ready patterns, done-pattern baseline filtering |
| `test_cmd_ralph.py` | Tests for `ralph ls`, `ralph clean`, done-pattern baseline |
| `test_ready_patterns.py` | Tests for theme picker not-ready detection |

---

## Spec References

All spec changes are already committed in the current diff:
- `specs/ralph-loop.md` — Ralph Clean, Ralph Ls, Docker Sandbox Caveats, Done Pattern Self-Match warning
- `specs/cli-interface.md` — Ralph Clean Arguments, Ralph Spawn Caveats, ralph ls/clean in subcommand table
- `specs/ready-detection.md` — Not-Ready States (theme picker), scenario for theme picker
- `specs/project-onboarding.md` — sandbox.sh uses `-it`, Dockerfile pre-configures theme

---

## Complexity Notes

- **Phase 1 (ralph ls)**: Trivial — alias dispatch, 30 min
- **Phase 2 (ralph clean)**: Straightforward — file deletion with validation, 1-2 hours
- **Phase 3 (theme picker)**: Moderate — need to add negative pattern matching without breaking existing ready detection, 1-2 hours
- **Phase 4 (done-pattern baseline)**: Most complex — threading baseline line count through prompt injection → inactivity detection, 2-3 hours

---

## Execution Stats

**Method**: Docker-sandboxed `loop.sh` (`SANDBOX=1 ./loop.sh 20`)
**Date**: 2026-02-11
**Total time**: ~31 minutes (20:22–20:53)
**Iterations**: 4 of 20 budget
**Model**: Opus
**Container resources**: 8 GiB memory, 4 CPUs, 512 PIDs

| Iter | Phase | Commit | Duration | Tasks | Tests Added |
|------|-------|--------|----------|-------|-------------|
| 1 | Phase 1 (ralph ls) | `cd4b823` | ~3 min | 1.1, 1.2, 1.3 | ralph ls alias tests |
| 2 | Phase 2 (ralph clean) | `e39763a` | ~10 min | 2.1, 2.2, 2.3, 2.4 | 17 tests (4 classes) |
| 3 | Phase 3 (theme picker) | `5bf33e9` | ~4 min | 3.1, 3.2 | 6 tests |
| 4 | Phase 4 + 5 (baseline + verify) | `073509d` | ~14 min | 4.1, 4.2, 4.3, 5.1, 5.2, 5.3 | 10 tests |

**Final test count**: 551 tests passing across test_cmd_ralph, test_ready_patterns, test_cmd_spawn, test_cmd_init, test_cmd_heartbeat.

**Notes**:
- All phases completed faster than estimated (31 min actual vs 4.5–7.5 hr estimated)
- Worker combined tightly-coupled tasks within phases (e.g., 2.1-2.4 in one iteration)
- Phase 4 was the longest iteration (~14 min) due to cross-cutting changes requiring mock updates across 48 existing tests
- Auth fix required: `loop.sh` volume mounts needed `/home/node/` instead of `/home/loopuser/` (container user mismatch)
