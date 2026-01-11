---
date: 2026-01-11T12:00:00-08:00
researcher: Claude
topic: "Integration Test Topics for Swarm CLI"
tags: [research, testing, tmux, integration-tests, swarm]
status: complete
---

# Research: Integration Test Topics for Swarm CLI

**Date**: 2026-01-11
**Researcher**: Claude

## Research Question
What integration tests should be written to defend against discovered problems, particularly tmux session isolation issues where swarm opens windows inside existing user sessions?

## Summary

The research identified **three major problem categories** requiring integration test coverage:

1. **Tmux Session Isolation** - Swarm currently uses a hardcoded "swarm" session by default, but `create_tmux_window()` will create windows in existing sessions if they have the same name, interfering with user sessions.

2. **State/Reality Mismatch** - The `clean --all` command uses cached `w.status` from state.json instead of refreshing actual status, leading to workers being incorrectly filtered.

3. **Ready Detection Unreliability** - The `wait_for_agent_ready()` function has pattern matching issues and timing problems that need coverage.

## Detailed Findings

### 1. Tmux Session Isolation (Critical)

**Problem**: When a user runs swarm from inside an existing tmux session, swarm may create windows in their current session instead of a dedicated "swarm" session.

**Root Cause Analysis** (`swarm.py:202-215`):
```python
def ensure_tmux_session(session: str) -> None:
    """Create tmux session if it doesn't exist."""
    # Check if session exists
    result = subprocess.run(
        ["tmux", "has-session", "-t", shlex.quote(session)],
        capture_output=True,
    )
    if result.returncode != 0:
        # Create detached session
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session],
            ...
```

**Issue**: If the user is in a tmux session already named "swarm" (or the default matches their session), windows get added there. Also, `new-window -t session` (line 229) will select the session and add windows to it, potentially affecting the user's workflow.

**Integration Tests Needed**:

| Test ID | Test Name | Description |
|---------|-----------|-------------|
| ISO-1 | `test_spawn_creates_dedicated_session` | Verify spawn with `--tmux` creates a session named "swarm" (or custom `--session`) separate from any existing sessions |
| ISO-2 | `test_spawn_does_not_modify_existing_sessions` | When user has pre-existing tmux sessions, verify swarm does NOT add windows to them |
| ISO-3 | `test_spawn_from_inside_tmux_creates_separate_session` | Run swarm from inside an active tmux session; verify it creates workers in its own session, not the parent |
| ISO-4 | `test_session_name_collision_handling` | If user has a session named "swarm", test behavior (should error or use different name) |
| ISO-5 | `test_multiple_swarm_instances_isolation` | Two swarm processes running concurrently should not interfere with each other's sessions |
| ISO-6 | `test_cleanup_only_affects_swarm_sessions` | `swarm kill --all` should only kill windows in swarm-managed sessions |

### 2. State/Reality Mismatch Bug in `clean --all`

**Problem**: `cmd_clean()` filters workers by `w.status == "stopped"` from cached state before refreshing actual status.

**Root Cause** (`swarm.py:1120-1122`):
```python
if args.all:
    # Get all workers with status "stopped"
    workers_to_clean = [w for w in state.workers if w.status == "stopped"]
```

**Bug**: This uses stale `w.status` from state.json. A worker might:
- Show "running" in state but actually be dead (tmux window closed externally)
- Show "stopped" in state but process was somehow restarted

**Integration Tests Needed**:

| Test ID | Test Name | Description |
|---------|-----------|-------------|
| STATE-1 | `test_clean_all_with_externally_killed_worker` | Spawn worker, kill its tmux window externally (not via swarm), verify `clean --all` still cleans it |
| STATE-2 | `test_clean_all_skips_still_running_workers` | Spawn multiple workers, some running some stopped, verify only actually-stopped workers are cleaned |
| STATE-3 | `test_ls_reflects_actual_status` | Spawn worker, kill externally, verify `swarm ls` shows correct "stopped" status |
| STATE-4 | `test_status_refresh_accuracy` | Comprehensive test of `refresh_worker_status()` against various scenarios |

### 3. Ready Detection Reliability

**Problem**: `wait_for_agent_ready()` timeout issues and pattern matching unreliability.

**Root Cause** (`swarm.py:287-328`):
- Pattern matching may miss text due to terminal control characters
- Visible pane capture may not include full output
- Timing issues between pane rendering and capture

**Current Ready Patterns** (`swarm.py:305-311`):
```python
ready_patterns = [
    r"^> ",                          # Claude Code prompt
    r"bypass.permissions",           # Claude Code ready indicator (handles variations)
    r"Claude Code",                  # Claude Code startup banner
    r"^\$ ",                          # Shell prompt
    r"^>>> ",                         # Python REPL
]
```

**Actual Claude Code Startup Screen** (v2.0.76):
```
➜  swarm git:(main) ✗ claude --dangerously-skip-permissions

 * ▐▛███▜▌ *   Claude Code v2.0.76
* ▝▜█████▛▘ *  Opus 4.5 · Claude Max
 *  ▘▘ ▝▝  *   ~/code/swarm

──────────────────────────────────────────────────────────────
> Try "refactor <filepath>"
──────────────────────────────────────────────────────────────
  [Opus 4.5] v2.0.76 ⎇ main ● ⏱ 1s
  ⏵⏵ bypass permissions on (shift+tab to cycle)
```

**Key Detection Points**:
1. `Claude Code v2.0.76` - Banner with version (current pattern matches this)
2. `> Try "refactor <filepath>"` - Prompt line with hint text
3. `⏵⏵ bypass permissions on` - Status line indicator (note: NOT "bypass.permissions")

**Pattern Match Analysis**:
| Pattern | Would Match? | Actual Text |
|---------|--------------|-------------|
| `r"^> "` | ✅ YES | `> Try "refactor <filepath>"` |
| `r"bypass.permissions"` | ❌ NO | Actual text is `bypass permissions on` (space, not dot; `.` in regex matches any char but anchoring may fail) |
| `r"Claude Code"` | ✅ YES | `Claude Code v2.0.76` |
| `r"^\$ "` | ❌ N/A | Not a shell |
| `r"^>>> "` | ❌ N/A | Not Python REPL |

**Integration Tests Needed**:

| Test ID | Test Name | Description |
|---------|-----------|-------------|
| READY-1 | `test_ready_wait_detects_claude_code_prompt` | Spawn claude with `--ready-wait`, verify it returns when Claude Code is ready |
| READY-2 | `test_ready_wait_timeout_handling` | Spawn slow process, verify timeout triggers appropriately |
| READY-3 | `test_ready_wait_with_ansi_escape_codes` | Verify pattern matching works with ANSI color codes in output |
| READY-4 | `test_ready_wait_scrollback_capture` | If prompt scrolls off visible area, detection should still work |

#### 3.1 Agent Text Pattern Detection Tests (NEW)

These tests specifically verify that each ready pattern is correctly detected in various scenarios:

| Test ID | Test Name | Description |
|---------|-----------|-------------|
| PATTERN-1 | `test_pattern_claude_code_prompt_basic` | Spawn process that outputs `> ` at line start, verify detection |
| PATTERN-2 | `test_pattern_claude_code_prompt_with_text` | Verify `> some text here` is detected (prompt with content) |
| PATTERN-3 | `test_pattern_bypass_permissions` | Spawn process that outputs "bypass permissions" text, verify detection |
| PATTERN-4 | `test_pattern_bypass_permissions_variants` | Test variations: "bypass.permissions", "bypass permissions", "Bypass Permissions" |
| PATTERN-5 | `test_pattern_claude_code_banner` | Spawn process that outputs "Claude Code" banner text, verify detection |
| PATTERN-6 | `test_pattern_shell_prompt` | Spawn process that outputs `$ ` at line start, verify detection |
| PATTERN-7 | `test_pattern_python_repl` | Spawn process that outputs `>>> ` at line start, verify detection |
| PATTERN-8 | `test_pattern_no_false_positives` | Verify patterns don't match mid-line (e.g., "echo > file" should NOT match `^> `) |
| PATTERN-9 | `test_pattern_multiple_patterns_first_wins` | Output contains multiple patterns, verify first match returns True |
| PATTERN-10 | `test_pattern_empty_output` | Verify graceful handling when pane capture returns empty string |
| PATTERN-11 | `test_pattern_claude_code_actual_startup` | Spawn mock that outputs actual Claude Code v2.0.76 startup screen, verify detection |
| PATTERN-12 | `test_pattern_bypass_permissions_with_unicode_prefix` | Verify `⏵⏵ bypass permissions on` text is detected |
| PATTERN-13 | `test_pattern_prompt_with_hint_text` | Verify `> Try "refactor <filepath>"` format is detected |

#### 3.2 Pattern Edge Cases

| Test ID | Test Name | Description |
|---------|-----------|-------------|
| EDGE-1 | `test_pattern_with_leading_whitespace` | Verify `^> ` doesn't match if there's leading whitespace before `>` |
| EDGE-2 | `test_pattern_with_ansi_before_prompt` | ANSI codes like `\x1b[32m> ` before prompt - currently will NOT match `^> ` |
| EDGE-3 | `test_pattern_multiline_output` | Verify pattern found on line N of multi-line output is detected |
| EDGE-4 | `test_pattern_carriage_return_handling` | Lines with `\r` embedded (terminal overwrites) are handled correctly |
| EDGE-5 | `test_pattern_unicode_in_output` | Non-ASCII characters in output don't break pattern matching |
| EDGE-6 | `test_pattern_very_long_lines` | Lines exceeding terminal width (wrapped) are handled correctly |
| EDGE-7 | `test_pattern_rapid_output_capture` | Pattern appears then scrolls away quickly - capture timing |

#### 3.3 Pattern Matching Bug Analysis

**Known Issues**:

1. **ANSI escape codes break `^` anchor** (`swarm.py:306`):
   - Pattern `r"^> "` won't match `\x1b[0m> ` because `^` anchors to actual line start
   - Real terminals often emit color codes before prompts
   - **Fix needed**: Strip ANSI codes before matching, or use pattern `r"(?:^|\x1b\[[0-9;]*m)> "`

2. **"bypass.permissions" pattern mismatch** (`swarm.py:307`):
   - Current regex `r"bypass.permissions"` uses `.` which matches any character
   - Actual Claude Code output: `⏵⏵ bypass permissions on` (space between words, not dot)
   - The `.` in regex DOES match a space, so this works - but only by accident
   - The pattern also doesn't account for leading `⏵⏵ ` Unicode characters
   - **Risk**: If Claude Code changes the text format, pattern may silently fail
   - **Fix needed**: More explicit pattern `r"bypass\s+permissions"` or `r"bypass permissions on"`

3. **"Claude Code" is too broad** (`swarm.py:308`):
   - Matches any line containing "Claude Code" including error messages
   - Could cause false positive early detection before actual ready state
   - Actual banner: `Claude Code v2.0.76`
   - **Fix needed**: More specific pattern like `r"Claude Code v\d+\.\d+"`

4. **Status line indicators have Unicode prefix**:
   - Actual text: `⏵⏵ bypass permissions on (shift+tab to cycle)`
   - The `⏵⏵` (U+23F5 BLACK MEDIUM RIGHT-POINTING TRIANGLE) precedes the text
   - Pattern should account for this or use substring match

**Actual Claude Code v2.0.76 Ready Indicators** (in order of appearance):
1. `Claude Code v2.0.76` - Banner (appears first, ~0.5s after launch)
2. `> Try "refactor..."` - Prompt with hint (appears when UI ready)
3. `⏵⏵ bypass permissions on` - Status line (confirms permissions mode)

**Suggested Pattern Improvements**:
```python
ready_patterns = [
    r"(?:^|\x1b\[[0-9;]*m)> ",       # Claude Code prompt (ANSI-aware)
    r"bypass\s+permissions\s+on",    # Explicit "bypass permissions on" text
    r"Claude Code v\d+\.\d+",        # Versioned banner (more specific)
    r"(?:^|\x1b\[[0-9;]*m)\$ ",      # Shell prompt (ANSI-aware)
    r"(?:^|\x1b\[[0-9;]*m)>>> ",     # Python REPL (ANSI-aware)
]
```

**Most Reliable Detection Strategy**:
For Claude Code specifically, the `> ` prompt line is the most reliable indicator because:
- It appears only when the UI is fully ready for input
- It's at the start of a line (after banner/chrome)
- It's consistent across versions

### 4. Process Lifecycle Integration Tests

**Additional tests for overall robustness**:

| Test ID | Test Name | Description |
|---------|-----------|-------------|
| LIFE-1 | `test_full_lifecycle_tmux_worker` | spawn -> status -> send -> logs -> kill -> clean full cycle |
| LIFE-2 | `test_full_lifecycle_pid_worker` | Same for non-tmux background process |
| LIFE-3 | `test_respawn_preserves_config` | Respawn maintains original command, env, tags, cwd |
| LIFE-4 | `test_concurrent_operations` | Multiple swarm commands running simultaneously don't corrupt state |
| LIFE-5 | `test_state_file_corruption_recovery` | Behavior when state.json is malformed or missing |

## Code References

- `swarm.py:202-215` - `ensure_tmux_session()` - Session creation logic
- `swarm.py:218-236` - `create_tmux_window()` - Window creation with `-a` flag
- `swarm.py:287-328` - `wait_for_agent_ready()` - Ready detection with patterns
- `swarm.py:383-403` - `refresh_worker_status()` - Status refresh logic
- `swarm.py:1113-1170` - `cmd_clean()` - Clean command with state filtering bug
- `swarm.py:1120-1122` - Bug: uses `w.status` instead of refreshed status

## Architecture Insights

### Current Tmux Session Strategy

1. Default session name is "swarm" (configurable via `--session`)
2. `ensure_tmux_session()` checks if session exists, creates if not
3. `create_tmux_window()` adds window with `-a` flag to append after current window
4. No mechanism to prevent collision with user sessions of same name

### Recommended Test Isolation Strategy

Based on research of [tmux-test](https://github.com/tmux-plugins/tmux-test) and best practices:

1. **Use unique tmux socket per test** (`tmux -L $TEST_ID`) - Creates completely isolated tmux server
2. **Random session names** - Prevent collision with any existing sessions
3. **Cleanup via `tmux -L $TEST_ID kill-server`** - Ensures complete teardown
4. **Test in isolated environment** - Consider Vagrant/container for CI

Example test setup pattern:
```python
import uuid

class TmuxIsolatedTest:
    def setUp(self):
        self.test_socket = f"swarm-test-{uuid.uuid4().hex[:8]}"
        self.test_session = f"test-session-{uuid.uuid4().hex[:8]}"

    def tearDown(self):
        subprocess.run(["tmux", "-L", self.test_socket, "kill-server"],
                      capture_output=True)
```

### State Management Pattern

The state file (`~/.swarm/state.json`) is the source of truth, but actual process/tmux status must be refreshed before operations. This pattern should be consistent across all commands.

## Proposed Solutions

### Solution 1: Production Session Isolation (Hash Suffix)

**Decision**: Use a **consistent hash** based on swarm state directory path for default session names.

**Rationale**:
- Same user gets consistent session name across invocations (predictable for debugging)
- Different users/environments get different sessions (isolation)
- Not random UUID each time (easier to find/attach)

**Implementation**:
```python
import hashlib

def get_default_session_name() -> str:
    """Generate default session name with hash suffix for isolation."""
    h = hashlib.sha256(str(SWARM_DIR).encode()).hexdigest()[:8]
    return f"swarm-{h}"
```

**Changes to swarm.py**:
1. Add `import hashlib` at top
2. Add `get_default_session_name()` function after `ensure_dirs()`
3. Change `--session` default from `"swarm"` to `None`
4. In `cmd_spawn()`: If `args.session is None`, use `get_default_session_name()`

**Result**: Sessions like `swarm-a1b2c3d4` instead of `swarm`

### Solution 2: Test Isolation (Socket-Based)

**Decision**: Use unique tmux sockets (`tmux -L socket_name`) for integration tests.

**Rationale**:
- Creates completely separate tmux server per test
- Zero chance of collision with user sessions
- Single `kill-server` cleans up everything

**Implementation**:
```python
import uuid
import subprocess

class TmuxIsolatedTestCase(unittest.TestCase):
    """Base class for tests requiring real tmux isolation."""

    def setUp(self):
        super().setUp()
        self.tmux_socket = f"swarm-test-{uuid.uuid4().hex[:8]}"

    def tearDown(self):
        # Kill entire tmux server for this socket
        subprocess.run(
            ["tmux", "-L", self.tmux_socket, "kill-server"],
            capture_output=True
        )
        super().tearDown()

    def tmux_cmd(self, *args):
        """Run tmux command with isolated socket."""
        return subprocess.run(
            ["tmux", "-L", self.tmux_socket] + list(args),
            capture_output=True, text=True
        )

    def list_sessions(self):
        """List sessions in isolated tmux server."""
        result = self.tmux_cmd("list-sessions", "-F", "#{session_name}")
        if result.returncode != 0:
            return []
        return [s for s in result.stdout.strip().split('\n') if s]
```

**New file**: `test_tmux_isolation.py` with integration tests using this base class.

## Failure Modes & Mitigations

### Solution 1: Production Hash Suffix - Failure Modes

| Failure Mode | Risk | Mitigation |
|--------------|------|------------|
| **Hash collision** | Low | 8 hex chars = 4 billion combinations; acceptable for user-level isolation |
| **SWARM_DIR not created yet** | Low | Hash the path string, not the directory itself - works before creation |
| **Symlink inconsistency** | Medium | Use `Path.resolve()` to normalize path before hashing |
| **Tests break** | High | ~35+ tests hardcode `session="swarm"` - must update or mock `get_default_session_name()` |
| **Backward compatibility** | High | Existing users with workers in "swarm" session can't manage them after upgrade |

**Mitigation for backward compatibility**:
```python
def get_default_session_name() -> str:
    """Generate default session name with hash suffix for isolation."""
    # Check if legacy "swarm" session has active workers first
    # Or: provide migration command
    h = hashlib.sha256(str(SWARM_DIR.resolve()).encode()).hexdigest()[:8]
    return f"swarm-{h}"
```

**Alternative**: Keep `--session` default as `"swarm"` but add `--session-isolate` flag that triggers hash behavior. Less breaking, opt-in isolation.

### Solution 2: Test Isolation - Failure Modes

| Failure Mode | Risk | Mitigation |
|--------------|------|------------|
| **Socket file cleanup** | Medium | Use `atexit` handler as backup; check for orphans in CI |
| **swarm.py can't use isolated socket** | **Critical** | Must add `--tmux-socket` arg or patch subprocess calls |
| **CI environment lacks tmux** | Medium | Skip tests with `@unittest.skipUnless(shutil.which('tmux'), 'tmux required')` |
| **Race conditions / crashes** | Medium | Use `try/finally` in tests; add socket cleanup to CI scripts |
| **Permission issues** | Low | Use `tempfile.gettempdir()` which should be writable |

### Critical Gap: swarm.py Socket Injection

**Problem**: `TmuxIsolatedTestCase` creates isolated tmux server, but swarm.py has no way to use it.

**Current tmux calls in swarm.py** (all hardcoded, no socket option):
- `swarm.py:206` - `["tmux", "has-session", "-t", ...]`
- `swarm.py:212` - `["tmux", "new-session", "-d", "-s", ...]`
- `swarm.py:225-232` - `["tmux", "new-window", ...]`
- `swarm.py:244-250` - `["tmux", "send-keys", ...]`
- `swarm.py:258-261` - `["tmux", "has-session", ...]`
- `swarm.py:277-283` - `["tmux", "capture-pane", ...]`
- ... and ~10 more locations

**Options to fix**:

1. **Add `--tmux-socket` argument** (Recommended)
   - Add to spawn command, store in TmuxInfo
   - All tmux functions accept optional socket parameter
   - Production code change but clean and testable

2. **Environment variable `SWARM_TMUX_SOCKET`**
   - Check env var in all tmux functions
   - No CLI change needed
   - Implicit/hidden behavior

3. **Patch subprocess at test level**
   - Complex mock that intercepts all subprocess.run calls
   - Fragile, hard to maintain

**Recommended approach**: Option 1 - Add `--tmux-socket` to CLI

```python
# In argparse setup
spawn_p.add_argument("--tmux-socket", default=None,
                    help="Tmux socket name (for testing/isolation)")

# Store in TmuxInfo
@dataclass
class TmuxInfo:
    session: str
    window: str
    socket: Optional[str] = None  # NEW

# Helper to build tmux command prefix
def tmux_cmd_prefix(socket: Optional[str] = None) -> list[str]:
    if socket:
        return ["tmux", "-L", socket]
    return ["tmux"]
```

## Remaining Open Questions

1. **Concurrent access** - State file needs locking for concurrent swarm processes
2. **Exit code detection** - Can we capture exit codes from tmux windows for test assertions?
3. **Migration path** - How to handle existing users with workers in "swarm" session?

## Recommended Test Priority

**P0 (Critical - Session Isolation)**:
- ISO-2: `test_spawn_does_not_modify_existing_sessions`
- ISO-3: `test_spawn_from_inside_tmux_creates_separate_session`

**P1 (High - Bug Fixes)**:
- STATE-1: `test_clean_all_with_externally_killed_worker`
- STATE-2: `test_clean_all_skips_still_running_workers`
- EDGE-2: `test_pattern_with_ansi_before_prompt` (blocks real-world usage)

**P2 (Medium - Robustness)**:
- LIFE-1 through LIFE-5: Full lifecycle tests
- ISO-1, ISO-4-6: Additional isolation tests
- PATTERN-1 through PATTERN-7: Core pattern detection tests
- PATTERN-8: False positive prevention

**P3 (Lower - Ready Detection)**:
- READY-1 through READY-4: Ready detection (complex to test reliably)
- PATTERN-9, PATTERN-10: Multiple pattern and edge cases
- EDGE-1, EDGE-3 through EDGE-7: Additional edge cases

## Sources

- [tmux-test GitHub](https://github.com/tmux-plugins/tmux-test) - Framework for isolated tmux plugin testing
- [Using tmux to test console applications](https://www.drmaciver.com/2015/05/using-tmux-to-test-your-console-applications/) - Unique socket technique for test isolation
- [Isolated environments in Tmux](https://hoop.dev/blog/isolated-environments-in-tmux/) - Session independence and stability patterns
