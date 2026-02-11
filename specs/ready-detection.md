# Ready Detection

## Overview

Swarm provides `--ready-wait` functionality that blocks after spawning a worker until the agent CLI is ready to receive input. This enables orchestration scripts to send prompts immediately after spawn without risking lost input. Ready detection works by polling tmux pane output and matching against known agent prompt patterns.

## Dependencies

- **External**:
  - tmux (for pane capture)
  - re (regex module - standard library)
- **Internal**:
  - `tmux-integration.md` (tmux_capture_pane function)

## Behavior

### Wait For Agent Ready

**Description**: Polls tmux pane output until a ready pattern is detected or timeout expires.

**Inputs**:
- `session` (str, required): Tmux session name
- `window` (str, required): Tmux window name
- `timeout` (int, optional): Maximum seconds to wait (default: 30)
- `socket` (str, optional): Tmux socket name for isolated sessions

**Outputs**:
- `True`: Agent became ready (pattern detected)
- `False`: Timeout expired without detecting ready pattern

**Algorithm**:
1. Record start time
2. Loop while elapsed time < timeout:
   a. Capture pane content via `tmux_capture_pane`
   b. Split into lines
   c. For each line, check against all ready patterns
   d. If any pattern matches, return True
   e. Sleep 0.5 seconds
3. Return False (timeout)

**Side Effects**: None (read-only polling)

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| tmux window doesn't exist | CalledProcessError caught, continues polling |
| Timeout expires | Returns False |
| Pattern matched | Returns True immediately |

### Ready Pattern Definitions

**Description**: Regex patterns that indicate various agent CLIs are ready for input.

**Pattern Categories**:

#### Claude Code Permission Mode Indicators (Most Reliable)
| Pattern | Description | Example Match |
|---------|-------------|---------------|
| `bypass\s+permissions` | Permission mode text | "bypass permissions on" |
| `permissions?\s+mode` | Permission mode variants | "permission mode" |
| `shift\+tab\s+to\s+cycle` | UI hint in permission line | "shift+tab to cycle" |

#### Claude Code Version Banner
| Pattern | Description | Example Match |
|---------|-------------|---------------|
| `Claude\s+Code\s+v\d+` | Version banner | "Claude Code v2.1.4" |

#### Claude Code Prompt Patterns (ANSI-Aware)
| Pattern | Description | Example Match |
|---------|-------------|---------------|
| `(?:^\|\x1b\[[0-9;]*m)>\s` | "> " prompt with optional ANSI | "> ", "\x1b[32m> " |
| `\u2771\s` | Unicode prompt character | "❯ " |

#### OpenCode CLI Patterns
| Pattern | Description | Example Match |
|---------|-------------|---------------|
| `opencode\s+v\d+` | Version banner | "opencode v1.0.115" |
| `tab\s+switch\s+agent` | UI hint at bottom | "tab switch agent" |
| `ctrl\+p\s+commands` | UI hint at bottom | "ctrl+p commands" |

#### Generic CLI Prompts (ANSI-Aware)
| Pattern | Description | Example Match |
|---------|-------------|---------------|
| `(?:^\|\x1b\[[0-9;]*m)\$\s` | Shell "$ " prompt | "$ ", "\x1b[34m$ " |
| `(?:^\|\x1b\[[0-9;]*m)>>>\s` | Python REPL ">>> " | ">>> " |

### Not-Ready States (Blocking Indicators)

**Description**: Patterns that indicate the agent is NOT ready and is blocked on an interactive prompt that prevents normal operation. When detected, these should NOT be treated as "ready" — the agent cannot accept prompts in these states.

#### Claude Code Theme Picker
| Pattern | Description | Example Match |
|---------|-------------|---------------|
| `Choose the text style` | First-time theme picker | "Choose the text style that looks best" |
| `looks best with your terminal` | Theme picker subtitle | "looks best with your terminal" |

**Problem**: Fresh Docker containers (or any environment without cached Claude Code preferences) display an interactive theme picker on first launch. This blocks all input — any prompt sent via `tmux send-keys` is consumed by the theme picker, not the Claude Code prompt.

**Detection Behavior**:
- If a not-ready pattern is detected during `wait_for_agent_ready()`, the function should NOT return True
- Optionally, send Enter to dismiss the theme picker (accepting the default theme) and continue waiting for a real ready pattern

**Prevention**:
- Pre-configure theme in Docker images: `mkdir -p ~/.claude && echo '{"theme":"dark"}' > ~/.claude/settings.local.json`
- Mount the host's `~/.claude/` directory into the container
- Set `CLAUDE_THEME=dark` environment variable if supported

### Spawn with Ready Wait

**Description**: The `spawn` command's `--ready-wait` flag integrates ready detection.

**Inputs**:
- `--ready-wait` (flag): Enable ready detection
- `--ready-timeout` (int, optional): Timeout in seconds (default: 120)

**Behavior**:
1. Spawn worker normally
2. If `--ready-wait` and worker is tmux:
   a. Call `wait_for_agent_ready(session, window, timeout, socket)`
   b. If returns False, print warning to stderr
3. Worker is created regardless of ready detection result

**Outputs**:
- Always spawns worker (exit 0)
- Warning to stderr if timeout: `"swarm: warning: agent '<name>' did not become ready within <N>s"`

## Scenarios

### Scenario: Claude Code prompt detected immediately
- **Given**: A tmux worker running Claude Code
- **When**: Claude Code outputs "> " prompt
- **Then**:
  - `wait_for_agent_ready` returns True
  - Spawn command returns immediately

### Scenario: Claude Code banner detected
- **Given**: A tmux worker starting Claude Code
- **When**: Output shows "Claude Code v2.0.76"
- **Then**:
  - `wait_for_agent_ready` returns True
  - Detection happens on version banner before prompt

### Scenario: Permission mode indicator detected
- **Given**: A tmux worker running Claude Code
- **When**: Output shows "bypass permissions on"
- **Then**:
  - `wait_for_agent_ready` returns True
  - Most reliable detection method

### Scenario: OpenCode version banner detected
- **Given**: A tmux worker running OpenCode
- **When**: Output shows "opencode v1.0.115"
- **Then**:
  - `wait_for_agent_ready` returns True

### Scenario: OpenCode UI hints detected
- **Given**: A tmux worker running OpenCode
- **When**: Output shows "tab switch agent" or "ctrl+p commands"
- **Then**:
  - `wait_for_agent_ready` returns True

### Scenario: Timeout with no ready pattern
- **Given**: A worker that never outputs a ready pattern
- **When**: `swarm spawn --ready-wait --ready-timeout 2 -- sleep 300`
- **Then**:
  - Waits for 2 seconds
  - Returns False
  - Worker still created
  - Warning printed to stderr

### Scenario: ANSI escape codes before prompt
- **Given**: Output with ANSI color codes like "\x1b[32m> \x1b[0m"
- **When**: Ready detection runs
- **Then**:
  - Pattern still matches (ANSI-aware regex)
  - Returns True

### Scenario: Multi-line output with prompt on later line
- **Given**: Output like "Starting...\nLoading...\n> "
- **When**: Ready detection runs
- **Then**:
  - Each line checked separately
  - Matches on line containing "> "

### Scenario: Tmux window doesn't exist yet
- **Given**: Worker just spawned, tmux window still initializing
- **When**: `tmux_capture_pane` fails
- **Then**:
  - CalledProcessError caught
  - Continues polling
  - Eventually succeeds when window exists

### Scenario: Theme picker detected in Docker container
- **Given**: A tmux worker running Claude Code in a fresh Docker container
- **When**: Output shows "Choose the text style that looks best with your terminal"
- **Then**:
  - `wait_for_agent_ready` does NOT return True
  - Theme picker is a blocking state, not a ready state
  - Optionally: send Enter to dismiss, continue waiting for real ready pattern

## Edge Cases

### False Positive Prevention
- `echo > file` does NOT match (> not at line start)
- `price is $100` does NOT match ($ not at line start)
- `Installing package v2.3.4...` does NOT match (no "opencode" or "Claude Code" prefix)
- Leading whitespace before `> ` does NOT match (e.g., `   > `)

### Whitespace Handling
- `bypass permissions` matches with any whitespace (spaces, tabs, mixed)
- `bypass.permissions` does NOT match (dot is not whitespace)

### Pattern Priority
- First matching pattern wins (no priority order needed)
- Multiple patterns can match same output (any triggers return)

### Scrollback
- Current implementation captures visible pane only by default
- Prompt must appear in visible output during poll window
- Detection usually happens quickly (0.5s poll interval)

## Recovery Procedures

### Timeout on legitimate agent
If spawn times out but agent is actually ready:
```bash
# Increase timeout for slow-starting agents
swarm spawn --ready-wait --ready-timeout 180 -- claude

# Or skip ready-wait and add manual delay
swarm spawn --tmux -- claude
sleep 5
swarm send worker-name "prompt"
```

### Pattern not matching new agent version
If a new Claude Code version changes output format:
1. Capture actual output: `swarm logs worker-name`
2. Identify new ready indicator
3. Add pattern to `ready_patterns` list in swarm.py
4. Submit PR to update patterns

## Implementation Notes

- **Polling interval**: 0.5 seconds balances responsiveness with CPU usage
- **Default timeout**: 120 seconds accounts for slow Claude Code startup (API key validation, model loading)
- **Pattern design**: Prefer version-independent patterns (permission mode) over version-specific (banner text)
- **ANSI handling**: Patterns use `(?:^|\x1b\[[0-9;]*m)` to match line start OR after ANSI escape
- **Line-by-line matching**: Each line tested independently for reliable anchored patterns
