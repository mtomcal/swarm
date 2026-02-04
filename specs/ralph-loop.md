# Ralph Loop

## Overview

The `--ralph` flag enables autonomous agent looping based on the "Ralph Wiggum" pattern. This creates an outer loop that continuously restarts an agent with fresh context windows, allowing long-running autonomous development workflows. Each iteration reads a prompt file from disk, spawns the agent, waits for completion or inactivity timeout, then restarts. This pattern enables agents to work through task lists (like IMPLEMENTATION_PLAN.md) across multiple context windows without human intervention.

Named after the [Ralph Wiggum technique](https://github.com/ghuntley/how-to-ralph-wiggum) for AI-driven development.

## Dependencies

- **External**:
  - tmux (required - ralph implies tmux mode)
  - Filesystem access for prompt files, logs, and state
- **Internal**:
  - `spawn.md` (worker creation)
  - `kill.md` (worker termination between iterations)
  - `ready-detection.md` (agent readiness and inactivity detection)
  - `tmux-integration.md` (pane capture for output monitoring)
  - `state-management.md` (worker and ralph state persistence)

## Behavior

### Ralph Mode Activation

**Description**: Enable ralph loop mode for a worker.

**Inputs**:
- `--ralph` (flag, required): Enable ralph loop mode
- `--prompt-file` (str, required): Path to prompt file read each iteration
- `--max-iterations` (int, required): Maximum number of loop iterations

**Behavior**:
1. Validate `--ralph` is used with required flags
2. Automatically enable `--tmux` mode (ralph requires tmux)
3. Validate prompt file exists and is readable
4. Warn if `--max-iterations` exceeds 50

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| `--ralph` without `--prompt-file` | Exit 1 with "swarm: error: --ralph requires --prompt-file" |
| `--ralph` without `--max-iterations` | Exit 1 with "swarm: error: --ralph requires --max-iterations" |
| Prompt file not found | Exit 1 with "swarm: error: prompt file not found: <path>" |
| `--max-iterations` > 50 | Warning to stderr: "swarm: warning: high iteration count (>50) may consume significant resources" |

### Outer Loop Execution

**Description**: The main ralph loop that manages agent lifecycle.

**Inputs**:
- `--inactivity-timeout` (int, optional): Seconds of screen stability before restart (default: 60)
- `--done-pattern` (str, optional): Regex pattern that stops the loop when matched in output

**Behavior**:
1. **Initialize**: Create ralph state file, set iteration to 0
2. **Loop Start**:
   a. Increment iteration counter
   b. Read prompt file from disk (fresh read every iteration)
   c. Spawn agent with prompt content piped to stdin or via `--append-system-prompt`
   d. Log iteration start with timestamp
3. **Monitor**:
   a. Wait for agent to exit OR inactivity timeout
   b. If `--done-pattern` specified, check output for match
4. **Evaluate**:
   a. If done pattern matched → stop loop, exit 0
   b. If max iterations reached → stop loop, exit 0
   c. If agent exited → continue to restart
   d. If inactivity timeout → kill agent, continue to restart
5. **Handle Failures**:
   a. Track consecutive failures (non-zero exit codes)
   b. Apply exponential backoff: 1s, 2s, 4s, 8s, ... up to 5 min max
   c. After 5 consecutive failures → stop loop, exit 1
6. **Restart**:
   a. Kill current worker
   b. Return to Loop Start

**Side Effects**:
- Creates/updates ralph state file at `~/.swarm/ralph/<worker-name>/state.json`
- Logs each iteration to `~/.swarm/ralph/<worker-name>/iterations.log`
- Worker metadata includes current iteration count

### Inactivity Detection

**Description**: Detect when an agent has become inactive using screen-stable detection (inspired by Playwright's `networkidle` pattern).

**Inputs**:
- `--inactivity-timeout` (int, optional): Seconds of screen stability before restart (default: 60)

**Algorithm**:
1. Capture last 20 lines of tmux pane every 2 seconds
2. Strip ANSI escape codes to normalize content
3. Hash the normalized content (MD5)
4. If hash unchanged for `--inactivity-timeout` seconds, trigger restart
5. Any screen change resets the timer

**Behavior**:
1. Poll screen content every 2 seconds
2. Compare normalized content hash to previous
3. If unchanged, accumulate stable time
4. If changed, reset stable time to 0
5. When stable time >= timeout, trigger restart

### Prompt File Handling

**Description**: Read and inject prompt content each iteration.

**Behavior**:
1. Read prompt file from disk at start of each iteration
2. File is re-read every time (allows editing mid-loop)
3. Content is passed to the agent command

**Prompt Injection Methods**:
- Pipe to stdin: `cat PROMPT.md | claude`
- The exact method depends on the command being spawned

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Prompt file deleted mid-loop | Exit 1 with "swarm: error: prompt file not found: <path>" |
| Prompt file unreadable | Exit 1 with "swarm: error: cannot read prompt file: <path>" |

### Ralph State Management

**Description**: Persist ralph loop state between iterations.

**State File Location**: `~/.swarm/ralph/<worker-name>/state.json`

**State Schema**:
```json
{
  "worker_name": "string",
  "prompt_file": "/absolute/path/to/PROMPT.md",
  "max_iterations": 100,
  "current_iteration": 5,
  "status": "running|paused|stopped|failed",
  "started": "2024-01-15T10:30:00.000000",
  "last_iteration_started": "2024-01-15T12:45:00.000000",
  "consecutive_failures": 0,
  "total_failures": 2,
  "done_pattern": "regex|null",
  "inactivity_timeout": 300
}
```

**Worker Metadata**:
The worker record includes ralph iteration in metadata:
```json
{
  "name": "worker-1",
  "metadata": {
    "ralph": true,
    "ralph_iteration": 5
  }
}
```

### Pause and Resume

**Description**: Pause and resume ralph loop execution.

**Commands**:
- `swarm ralph pause <name>` - Pause the loop
- `swarm ralph resume <name>` - Resume the loop

**Pause Behavior**:
1. Set ralph state status to "paused"
2. Current worker continues running
3. When worker exits, loop does not restart
4. Agent receives pause signal (implementation-specific)

**Resume Behavior**:
1. Set ralph state status to "running"
2. Continue from current iteration count
3. If worker not running, spawn fresh agent
4. If worker running, wait for exit then continue loop

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Pause non-ralph worker | Exit 1 with "swarm: error: worker '<name>' is not a ralph worker" |
| Pause already paused | Warning: "swarm: warning: worker '<name>' is already paused" |
| Resume non-paused | Warning: "swarm: warning: worker '<name>' is not paused" |

### Done Pattern Detection

**Description**: Stop the loop when a pattern is matched in agent output.

**Inputs**:
- `--done-pattern` (str, optional): Regex pattern to match

**Behavior**:
1. After each agent exit, capture recent output
2. Match regex against output
3. If matched, stop loop with success

**Common Patterns**:
- `"All tasks complete"` - Simple string match
- `"IMPLEMENTATION_PLAN.md.*100%"` - Plan completion
- `"No remaining tasks"` - Task list empty

### Failure Handling with Backoff

**Description**: Handle repeated failures with exponential backoff.

**Behavior**:
1. Track consecutive non-zero exit codes
2. On failure, wait before retry:
   - 1st failure: 1 second
   - 2nd failure: 2 seconds
   - 3rd failure: 4 seconds
   - 4th failure: 8 seconds
   - 5th failure: stop loop, exit 1
3. Max backoff delay capped at 5 minutes
4. Consecutive failure count resets on successful iteration (exit 0)

**Backoff Formula**: `min(2^(n-1), 300)` seconds where n = consecutive failure count

### Success Output

**Description**: Output format for ralph operations.

**Spawn with Ralph**:
```
spawned <name> (tmux: <session>:<window>) [ralph mode: iteration 1/100]
```

**Iteration Start**:
```
[ralph] <name>: starting iteration 5/100
```

**Iteration End**:
```
[ralph] <name>: iteration 5 completed (exit: 0, duration: 3m 42s)
```

**Loop Complete**:
```
[ralph] <name>: loop complete after 47 iterations
```

**Failure with Backoff**:
```
[ralph] <name>: iteration 5 failed (exit: 1), retrying in 4s (attempt 3/5)
```

**Done Pattern Matched**:
```
[ralph] <name>: done pattern matched, stopping loop
```

## Prompt Template Generation

### Overview

Swarm provides commands to generate a starter PROMPT.md file containing the essential instructions for a successful ralph loop. The template encodes best practices from the Ralph Wiggum methodology.

### Commands

**Initialize prompt file in current directory**:
```bash
swarm ralph init
```
- Creates `PROMPT.md` in current directory
- Fails if file already exists (use `--force` to overwrite)

**Output template to stdout**:
```bash
swarm ralph template
```
- Prints template to stdout
- Useful for piping: `swarm ralph template > my-custom-prompt.md`
- Useful for agents to inspect or modify programmatically

### Template Content

The generated PROMPT.md is intentionally minimal and direct. No headers, no bureaucracy - just instructions the agent needs:

```markdown
study specs/README.md
study CLAUDE.md and pick the most important incomplete task

IMPORTANT:

- do not assume anything is implemented - verify by reading code
- update IMPLEMENTATION_PLAN.md when the task is done
- if tests are missing, add them (choose unit/integration/property as appropriate, follow existing patterns)
- run tests after changes
- commit and push when you are done
```

### Template Design Principles

| Principle | Rationale |
|-----------|-----------|
| **Minimal** | Less prompt = more context for actual work |
| **Direct** | Imperative instructions, no fluff |
| **Project-agnostic** | References common conventions (specs/, CLAUDE.md) |
| **Customizable** | User should edit for their project (add test commands, deployment steps, etc.) |

### What Users Should Customize

The template is a starting point. Users should add project-specific details:

```markdown
study specs/README.md
study CLAUDE.md and pick the most important incomplete task

IMPORTANT:

- do not assume anything is implemented - verify by reading code
- update IMPLEMENTATION_PLAN.md when the task is done
- validate changes work via `npm test` AND manual testing
- if tests are missing, add them (follow existing patterns in __tests__/)
- commit and push when you are done
- if you need to deploy to troubleshoot: `./deploy.sh staging`
```

### Key Elements to Include

When customizing, ensure these are covered:

1. **What to study** - specs, plan file, project docs
2. **Task selection** - where to find tasks, how to pick one
3. **Verification method** - how to test (commands, manual steps)
4. **Plan update** - remind agent to mark task done
5. **Commit/push** - persist work across iterations

### CLI Arguments

| Command | Flags | Description |
|---------|-------|-------------|
| `swarm ralph init` | `--force` | Create PROMPT.md (overwrite if exists) |
| `swarm ralph template` | (none) | Output template to stdout |

### Scenarios

#### Scenario: Initialize prompt file
- **Given**: Current directory has no PROMPT.md
- **When**: `swarm ralph init`
- **Then**:
  - PROMPT.md created with template content
  - Output: "created PROMPT.md"
  - Exit code 0

#### Scenario: Init refuses to overwrite
- **Given**: PROMPT.md already exists
- **When**: `swarm ralph init`
- **Then**:
  - Exit code 1
  - Error: "swarm: error: PROMPT.md already exists (use --force to overwrite)"

#### Scenario: Init with force flag
- **Given**: PROMPT.md already exists
- **When**: `swarm ralph init --force`
- **Then**:
  - PROMPT.md overwritten with template
  - Output: "created PROMPT.md (overwritten)"
  - Exit code 0

#### Scenario: Output template to stdout
- **Given**: Agent wants to customize template
- **When**: `swarm ralph template`
- **Then**:
  - Template printed to stdout
  - No files created
  - Exit code 0

#### Scenario: Pipe template to custom file
- **Given**: User wants different filename
- **When**: `swarm ralph template > BUILD_PROMPT.md`
- **Then**:
  - Template written to BUILD_PROMPT.md
  - Can be used with `--prompt-file BUILD_PROMPT.md`

## Human Monitoring

### Live Agent View

**Attach to tmux session**:
```bash
swarm attach <name>
```
- Shows live agent output as it works
- Interactive - you can see prompts, tool calls, responses
- Detach with `Ctrl-B D` (or your tmux prefix + D)

### Ralph Loop Status

**Check iteration progress**:
```bash
swarm ralph status <name>
```
Output:
```
Ralph Loop: agent
Status: running
Iteration: 7/100
Started: 2024-01-15 10:30:00
Current iteration started: 2024-01-15 12:45:00
Consecutive failures: 0
Total failures: 2
Inactivity timeout: 60s
Done pattern: All tasks complete
```

### Log Streaming

**Follow agent output**:
```bash
swarm logs <name> --follow
```
- Streams tmux pane output
- Shows what the agent is doing in real-time
- Non-interactive (view only)

**Follow iteration events**:
```bash
tail -f ~/.swarm/ralph/<name>/iterations.log
```
Example output:
```
2024-01-15T10:30:00 [START] iteration 1/100
2024-01-15T10:35:42 [END] iteration 1 exit=0 duration=5m42s
2024-01-15T10:35:43 [START] iteration 2/100
2024-01-15T10:41:15 [END] iteration 2 exit=0 duration=5m32s
2024-01-15T10:41:16 [START] iteration 3/100
```

### Quick Status Check

**Is the worker running?**:
```bash
swarm status <name>
```

**List all ralph workers**:
```bash
swarm ls --format json | jq '.[] | select(.metadata.ralph == true)'
```

### Dashboard View (Multiple Workers)

**Watch multiple ralph workers**:
```bash
watch -n 5 'for w in $(swarm ls --format names); do echo "=== $w ==="; swarm ralph status $w 2>/dev/null || swarm status $w; done'
```

### Notifications (Advanced)

To get notified when ralph completes or fails, wrap the spawn:
```bash
swarm spawn --name agent --ralph --prompt-file ./PROMPT.md --max-iterations 100 -- claude \
  && notify-send "Ralph complete" \
  || notify-send "Ralph failed"
```

Or monitor the iteration log:
```bash
tail -f ~/.swarm/ralph/agent/iterations.log | grep --line-buffered "FAIL\|complete" | while read line; do
  notify-send "Ralph: $line"
done
```

## CLI Arguments

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `--ralph` | flag | No | false | Enable ralph loop mode |
| `--prompt-file` | str | If ralph | - | Path to prompt file |
| `--max-iterations` | int | If ralph | - | Maximum loop iterations |
| `--inactivity-timeout` | int | No | 60 | Screen stability timeout (seconds) |
| `--done-pattern` | str | No | null | Regex to stop loop |

### Ralph Subcommands

| Command | Description |
|---------|-------------|
| `swarm ralph pause <name>` | Pause ralph loop |
| `swarm ralph resume <name>` | Resume ralph loop |
| `swarm ralph status <name>` | Show ralph loop status |

## Scenarios

### Scenario: Basic ralph loop
- **Given**: Prompt file exists at `./PROMPT.md`
- **When**: `swarm spawn --name agent --ralph --prompt-file ./PROMPT.md --max-iterations 10 -- claude`
- **Then**:
  - Worker spawned in tmux mode
  - Prompt file read and passed to claude
  - Output: "spawned agent (tmux: swarm:agent) [ralph mode: iteration 1/10]"
  - Ralph state created at `~/.swarm/ralph/agent/state.json`

### Scenario: Iteration restart on agent exit
- **Given**: Ralph worker "agent" running, iteration 3/10
- **When**: Agent exits with code 0
- **Then**:
  - Log: "[ralph] agent: iteration 3 completed (exit: 0, duration: 5m 12s)"
  - Prompt file re-read from disk
  - New agent spawned
  - Log: "[ralph] agent: starting iteration 4/10"
  - Worker metadata updated: `ralph_iteration: 4`

### Scenario: Inactivity timeout triggers restart
- **Given**: Ralph worker with `--inactivity-timeout 60`, agent idle for 60s
- **When**: Inactivity timeout expires
- **Then**:
  - Current agent killed
  - Log: "[ralph] agent: inactivity timeout (60s), restarting"
  - New iteration started

### Scenario: Done pattern stops loop
- **Given**: Ralph worker with `--done-pattern "All tasks complete"`
- **When**: Agent output contains "All tasks complete"
- **Then**:
  - Log: "[ralph] agent: done pattern matched, stopping loop"
  - Loop exits with code 0
  - Ralph state status set to "stopped"

### Scenario: Max iterations reached
- **Given**: Ralph worker at iteration 10/10
- **When**: Iteration 10 completes
- **Then**:
  - Log: "[ralph] agent: loop complete after 10 iterations"
  - Loop exits with code 0
  - Ralph state status set to "stopped"

### Scenario: Consecutive failures trigger backoff
- **Given**: Ralph worker, agent exits with code 1
- **When**: 3 consecutive failures occur
- **Then**:
  - After 1st: wait 1s, retry
  - After 2nd: wait 2s, retry
  - After 3rd: wait 4s, retry
  - Log: "[ralph] agent: iteration N failed (exit: 1), retrying in 4s (attempt 3/5)"

### Scenario: Five consecutive failures stops loop
- **Given**: Ralph worker with 4 consecutive failures
- **When**: 5th consecutive failure occurs
- **Then**:
  - Log: "[ralph] agent: 5 consecutive failures, stopping loop"
  - Loop exits with code 1
  - Ralph state status set to "failed"

### Scenario: Pause ralph loop
- **Given**: Ralph worker "agent" running, iteration 5/10
- **When**: `swarm ralph pause agent`
- **Then**:
  - Output: "paused ralph loop for agent"
  - Ralph state status set to "paused"
  - Current agent continues running
  - When agent exits, loop does not restart

### Scenario: Resume paused ralph loop
- **Given**: Ralph worker "agent" paused at iteration 5/10, agent not running
- **When**: `swarm ralph resume agent`
- **Then**:
  - Output: "resumed ralph loop for agent"
  - Ralph state status set to "running"
  - New agent spawned for iteration 6
  - Log: "[ralph] agent: starting iteration 6/10"

### Scenario: Ralph status check
- **Given**: Ralph worker "agent" running, iteration 7/10
- **When**: `swarm ralph status agent`
- **Then**:
  - Output shows:
    ```
    Ralph Loop: agent
    Status: running
    Iteration: 7/10
    Started: 2024-01-15 10:30:00
    Current iteration started: 2024-01-15 12:45:00
    Consecutive failures: 0
    Total failures: 2
    ```

### Scenario: Prompt file edited mid-loop
- **Given**: Ralph worker running, PROMPT.md contains "Do task A"
- **When**: User edits PROMPT.md to "Do task B", iteration restarts
- **Then**:
  - New iteration reads updated prompt
  - Agent receives "Do task B" content

### Scenario: High iteration warning
- **Given**: User spawns with `--max-iterations 100`
- **When**: Command executed
- **Then**:
  - Warning: "swarm: warning: high iteration count (>50) may consume significant resources"
  - Worker still spawns successfully

### Scenario: Missing prompt file
- **Given**: `--prompt-file ./missing.md` specified
- **When**: `swarm spawn --ralph --prompt-file ./missing.md --max-iterations 10 -- claude`
- **Then**:
  - Exit code 1
  - Error: "swarm: error: prompt file not found: ./missing.md"

### Scenario: Ralph requires tmux
- **Given**: User attempts ralph without explicit tmux
- **When**: `swarm spawn --name agent --ralph --prompt-file ./PROMPT.md --max-iterations 10 -- claude`
- **Then**:
  - `--tmux` automatically enabled
  - Worker created in tmux mode

## Edge Cases

- Worker name reused across iterations (same name, iteration tracked in metadata)
- Prompt file can be absolute or relative path (resolved at spawn time)
- Empty prompt file is allowed (agent receives empty input)
- `--done-pattern` uses Python regex syntax
- Backoff timer does not count toward inactivity timeout
- Pausing during backoff wait immediately stops the wait
- Resume after pause continues iteration count (does not reset)
- Multiple `--ralph` workers can run concurrently with different names
- Ralph state persists across swarm restarts (can resume after crash)
- Killing a ralph worker also stops the loop (state set to "stopped")
- `--ready-wait` is implicit in ralph mode (always waits for ready)
- Worktree mode (`--worktree`) is compatible with ralph mode

## Recovery Procedures

### Ralph loop crashed mid-iteration

```bash
# Check ralph state
swarm ralph status <name>

# If state shows "running" but no worker
swarm ralph resume <name>
```

### Stuck in backoff

```bash
# Pause to stop backoff
swarm ralph pause <name>

# Fix the issue (edit prompt, etc.)

# Resume
swarm ralph resume <name>
```

### Want to change max-iterations mid-loop

```bash
# Edit state file directly
vim ~/.swarm/ralph/<name>/state.json
# Change "max_iterations" value

# Or pause, kill, respawn with new value
swarm ralph pause <name>
swarm kill <name>
swarm spawn --name <name> --ralph --prompt-file ./PROMPT.md --max-iterations 200 -- claude
```

### Clean up ralph state

```bash
# Remove ralph state for a worker
rm -rf ~/.swarm/ralph/<name>/

# Clean all ralph state
rm -rf ~/.swarm/ralph/
```

## Implementation Notes

- **Tmux requirement**: Ralph requires tmux for pane capture, ready detection, and output monitoring. Process mode is not supported.
- **Prompt injection**: The prompt file content should be piped to the agent or passed via appropriate CLI flags depending on the target agent.
- **State file locking**: Ralph state files should use fcntl locking to prevent race conditions.
- **Iteration logging**: Each iteration is logged with timestamps to enable debugging and analysis.
- **Graceful shutdown**: SIGTERM to the ralph process should pause the loop and allow current agent to complete.
- **Resource management**: Each iteration creates a fresh agent with a new context window, consuming API tokens.
