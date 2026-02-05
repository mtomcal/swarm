# Test Quality Audit

**Created**: 2026-02-05
**Auditor**: Claude (task 6.4)

This document identifies low-quality patterns found in the swarm test suite during code review.

---

## Summary

| Category | Count | Severity | Fix Priority |
|----------|-------|----------|--------------|
| Timing-dependent tests | 40+ | Medium | Medium |
| Tests accessing real ~/.swarm | 20+ | High | High |
| Weak assertions (assert_called only) | 16 | Low | Low |
| Subprocess calls without timeout | Many | Medium | Medium |
| Global state modification | Proper | OK | N/A |

---

## 1. Timing-Dependent Tests (Flaky Risk)

Tests that use `time.sleep()` without mocking can be flaky depending on system load.

### Files with Real Sleep Calls

| File | Lines | Purpose |
|------|-------|---------|
| `test_lifecycle_tmux.py` | 129, 161 | Wait for state updates |
| `test_lifecycle_pid.py` | 132 | Wait for state updates |
| `test_kill_integration.py` | 105 | Wait for process death |
| `test_core_functions.py` | 60, 78, 94, 110 | Wait for process state |
| `test_respawn_config.py` | 102, 127 | Wait for respawn |
| `test_cmd_ralph.py` | 7368, 7477, 7594 | Wait for loop iterations |
| `tests/test_tmux_isolation.py` | 522, 797, 857, 880, 1080, 1280 | Wait for tmux operations |
| `tests/test_integration_workflow.py` | 256, 307, 1150, 1170 | Wait for workflow transitions |

### Recommended Fixes

1. Use polling with timeout instead of fixed sleep:
```python
# Instead of:
time.sleep(0.5)
state = self.get_state()

# Use:
def wait_for_state(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = self.get_state()
        if predicate(state):
            return state
        time.sleep(0.1)
    raise TimeoutError("State condition not met")
```

2. For unit tests, mock `time.sleep` (already done in many tests)

---

## 2. Tests Accessing Real ~/.swarm (Interference Risk)

Integration tests that directly access `Path.home() / ".swarm"` can interfere with real swarm state if run by a user with an active swarm setup.

### Affected Files

| File | Lines | Access Type |
|------|-------|-------------|
| `tests/test_integration_ralph.py` | 49, 123, 161, 229, 376, 403, 432, 481, 508 | Read/write ralph state |
| `tests/test_integration_workflow.py` | 159, 212, 252, 303, 375, 423, 464, 590, 637, 808, 867, 1067, 1136 | Read/write workflow state |

### Recommended Fixes

1. Use environment variable or monkeypatch to redirect SWARM_DIR during tests
2. The `TmuxIsolatedTestCase` has a skip decorator for this but it's not implemented:
   - See `tests/test_tmux_isolation.py:638`: `@unittest.skip("SWARM_DIR env var not yet implemented")`

3. Alternative: Use unique prefixes based on test socket to avoid collisions (partially done)

---

## 3. Weak Assertions

Tests using `mock.assert_called()` without verifying call arguments are weak - they only verify the function was called, not that it was called correctly.

### Occurrences

```
test_cmd_workflow.py:3493:        mock_save_ralph.assert_called()
test_cmd_workflow.py:3502:        mock_log.assert_called()
test_cmd_workflow.py:3599:        mock_save_hb.assert_called()
test_cmd_workflow.py:3632:        mock_save_hb.assert_called()
test_cmd_workflow.py:3858:        mock_save_ralph.assert_called()
test_cmd_workflow.py:3922:        mock_save_hb.assert_called()
test_cmd_workflow.py:5065:        mock_save.assert_called()
test_cmd_workflow.py:5322:        mock_sleep.assert_called()
test_cmd_workflow.py:5464:        mock_save.assert_called()
test_cmd_workflow.py:5548:        mock_save.assert_called()
test_cmd_workflow.py:5574:        mock_save.assert_called()
test_cmd_workflow.py:5645:        mock_save.assert_called()
test_cmd_workflow.py:5791:        mock_save.assert_called()
test_cmd_workflow.py:6748:            mock_run.assert_called()
test_cmd_ralph.py:3892:        mock_spawn.assert_called()
test_cmd_respawn.py:189:                            mock_kill.assert_called()
```

### Recommended Fixes

Replace `assert_called()` with `assert_called_with(...)` or `assert_called_once_with(...)`:
```python
# Weak:
mock_save.assert_called()

# Better:
mock_save.assert_called_once_with(expected_state)
# Or at minimum:
mock_save.assert_called_once()
```

---

## 4. Subprocess Calls Without Timeout

Many subprocess calls in tests don't specify a timeout, which could cause tests to hang indefinitely.

### High-Risk Patterns

| File | Lines | Risk |
|------|-------|------|
| `test_core_functions.py` | 142 | `subprocess.Popen(["sleep", "10"])` without timeout |
| `test_worktree_protection.py` | Multiple | Git commands without timeout |
| Integration tests | Multiple | `subprocess.Popen` for workflow/ralph without timeout |

### Recommended Fixes

1. Add `timeout` parameter to all `subprocess.run()` calls:
```python
subprocess.run(cmd, capture_output=True, text=True, timeout=30)
```

2. For `subprocess.Popen`, use `proc.wait(timeout=30)` or `proc.communicate(timeout=30)`

3. Add `@unittest.timeout(60)` decorator to integration tests (requires `unittest-timeout` package or custom implementation)

---

## 5. Global State Modification (OK - Properly Handled)

Tests that modify module-level variables (`swarm.SWARM_DIR`, etc.) are correctly saving original values in `setUp()` and restoring in `tearDown()`.

### Pattern Used (Correct)

```python
def setUp(self):
    self.original_swarm_dir = swarm.SWARM_DIR
    swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"

def tearDown(self):
    swarm.SWARM_DIR = self.original_swarm_dir
```

This pattern is consistently used across:
- `test_cmd_workflow.py` (88 occurrences)
- `test_cmd_ralph.py` (252 occurrences)
- `test_cmd_heartbeat.py` (66 occurrences)
- `test_cmd_init.py` (14 occurrences)

**Status**: No action needed.

---

## 6. Tests with Hardcoded Paths

Some tests use hardcoded `/tmp` paths which may cause issues in environments where `/tmp` is not available or has different permissions.

### Occurrences

```
test_cmd_workflow.py: cwd="/tmp/test" (lines 5030, 5076, 5141, 5385, 5677, 5727)
test_kill_cmd.py: path="/tmp/worktrees/..." (lines 172, 174, 203, 312, 314)
test_cmd_ralph.py: prompt_file='/tmp/PROMPT.md' (lines 5464, 5504, 5581)
test_cmd_respawn.py: cwd="/tmp/worktree" (line 352)
test_cmd_ls.py: path="/tmp/project-worktrees/..." (lines 168, 170, 181)
```

### Assessment

These are mock values in unit tests (not actually accessing the filesystem), so they are acceptable. The paths are used as data in mocked Worker objects.

**Status**: Low priority - only fix if cross-platform compatibility becomes important.

---

## 7. Tests Without Assertions (None Found)

No tests were found that consist of only `pass` or have no assertions.

**Status**: No action needed.

---

## 8. Over-Mocked Tests

Some tests mock so many components that they may be testing mocks rather than actual code. This is a subjective assessment.

### Potential Concerns

In `test_cmd_workflow.py` and `test_cmd_ralph.py`, some tests mock 5+ functions. While this is sometimes necessary for complex integration points, it can make tests fragile and less valuable.

### Recommendations

1. Consider integration tests for complex workflows rather than heavily-mocked unit tests
2. Use `@patch.object` instead of string-based patching when possible for better refactoring safety

---

## 9. Missing Test Timeouts (Hanging Risk)

Integration tests that spawn subprocesses could hang indefinitely if something goes wrong.

### Affected Test Classes

- `TestFullLifecyclePid` in `test_lifecycle_pid.py`
- `TestFullLifecycleTmux` in `test_lifecycle_tmux.py`
- `TestRespawnPreservesConfig` in `test_respawn_config.py`
- `TestRalphSpawn` in `tests/test_integration_ralph.py`
- Workflow integration tests in `tests/test_integration_workflow.py`

### Recommended Fix

Add timeout wrapper to test runner:
```bash
# Run integration tests with timeout
timeout 300 python3 -m unittest tests.test_integration_ralph -v
```

Or add `@timeout_decorator.timeout(60)` to individual tests.

---

## Summary of Action Items

### High Priority
1. [x] Implement SWARM_DIR environment variable support to isolate integration tests
   - **DONE**: Added `os.environ.get("SWARM_DIR", ...)` support in swarm.py line 27
2. [ ] Add timeouts to subprocess calls in integration tests

### Medium Priority
3. [ ] Replace fixed `time.sleep()` with polling in integration tests
4. [ ] Add test timeout decorators to prevent hanging tests

### Low Priority
5. [x] Strengthen weak `assert_called()` assertions to include argument verification
   - **DONE**: Fixed 16 weak assertions in test_cmd_workflow.py, test_cmd_ralph.py, and test_cmd_respawn.py
   - Changed `assert_called()` to `assert_called_once()` where appropriate
   - Added `call_count >= 1` checks with argument verification for multi-call scenarios
6. [ ] Consider reducing mock depth in heavily-mocked tests

---

## Test Coverage Notes

Current coverage is 84% with 513 lines missing. The patterns identified in this audit are primarily about test quality rather than coverage gaps.

To reach 90%+ coverage:
- Focus on tasks 6.1-6.3 (add tests for uncovered paths)
- The quality improvements in this audit will make existing tests more reliable

