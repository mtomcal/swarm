# Ralph Loop

## Overview

The `swarm ralph spawn` command enables autonomous agent looping based on the "Ralph Wiggum" pattern. This creates an outer loop that continuously restarts an agent with fresh context windows, allowing long-running autonomous development workflows. Each iteration reads a prompt file from disk, spawns the agent, waits for completion or inactivity timeout, then restarts. This pattern enables agents to work through task lists (like IMPLEMENTATION_PLAN.md) across multiple context windows without human intervention.

Named after the [Ralph Wiggum technique](https://github.com/ghuntley/how-to-ralph-wiggum) for AI-driven development.

## Dependencies

- **External**:
  - tmux (required - ralph spawn always uses tmux mode)
  - Filesystem access for prompt files, logs, and state
- **Internal**:
  - `spawn.md` (worker creation)
  - `kill.md` (worker termination between iterations)
  - `ready-detection.md` (agent readiness and inactivity detection)
  - `tmux-integration.md` (pane capture for output monitoring)
  - `state-management.md` (worker and ralph state persistence)

## Behavior

### Ralph Spawn Command

**Description**: Spawn a new worker with ralph loop mode enabled. By default, automatically starts the monitoring loop.

**Command**:
```bash
swarm ralph spawn --name <name> --prompt-file <path> --max-iterations <n> -- <command>
```

**Inputs**:
- `--name` (str, required): Unique worker identifier
- `--prompt-file` (str, required): Path to prompt file read each iteration
- `--max-iterations` (int, required): Maximum number of loop iterations
- `--no-run` (bool, optional): Spawn worker but don't start monitoring loop (default: false)
- `--replace` (bool, optional): Auto-clean existing worker before spawn (default: false)
- `--clean-state` (bool, optional): Clear ralph state without affecting worker/worktree (default: false)
- `--tmux` (bool, optional): No-op for consistency with `swarm spawn` (ralph always uses tmux)
- `-- <command>` (required): Command to spawn (e.g., `claude`)

**Behavior**:
1. Validate prompt file exists and is readable
2. Automatically use tmux mode (ralph always uses tmux; `--tmux` accepted as no-op for consistency)
3. If `--replace` specified and worker exists: kill worker, remove worktree if present, remove ralph state
4. If `--clean-state` specified: remove ralph state directory (without affecting worker/worktree)
5. Create worker and ralph state
6. Warn if `--max-iterations` exceeds 50
7. **Auto-start loop**: Unless `--no-run` is specified, automatically start the monitoring loop after spawning

**Auto-start Behavior**:
- By default, `ralph spawn` both creates the worker AND starts monitoring
- The command blocks while the loop runs (use `&` or tmux to background)
- Use `--no-run` when you want to spawn now but run the loop later

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Prompt file not found | Exit 1 with "swarm: error: prompt file not found: <path>" |
| `--max-iterations` > 50 | Warning to stderr: "swarm: warning: high iteration count (>50) may consume significant resources" |
| `--tmux` flag used | Info message: "Note: Ralph workers always use tmux" (not an error, command proceeds) |

### Outer Loop Execution

**Description**: The main ralph loop that manages agent lifecycle.

**Inputs**:
- `--inactivity-timeout` (int, optional): Seconds of screen stability before restart (default: 180). Increase for repos with slow CI/pre-commit hooks.
- `--done-pattern` (str, optional): Regex pattern that stops the loop when matched in output
- `--check-done-continuous` (bool, optional): Check done pattern during monitoring, not just after exit (default: false)

**Behavior**:
1. **Initialize**: Create ralph state file, set iteration to 0
2. **Loop Start**:
   a. Increment iteration counter
   b. Read prompt file from disk (fresh read every iteration)
   c. Spawn agent with prompt content typed into tmux pane after ready detection
   d. Log iteration start with timestamp
3. **Monitor**:
   a. Wait for agent to exit OR inactivity timeout
   b. If `--check-done-continuous`, check done pattern every poll cycle
   c. If `--done-pattern` specified (without continuous), check output after exit
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
- `--inactivity-timeout` (int, optional): Seconds of screen stability before restart (default: 180)

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
3. Content is typed into the tmux pane after agent ready detection

**Prompt Injection Method**:
The prompt is typed into the tmux pane using `tmux send-keys` after the agent signals readiness. For Claude Code, this becomes the first user message in the conversation.

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Prompt file deleted mid-loop | Exit 1 with "swarm: error: prompt file not found: <path>" |
| Prompt file unreadable | Exit 1 with "swarm: error: cannot read prompt file: <path>" |

### Worktree Behavior

**Description**: How worktrees work with ralph mode.

**Behavior**:
- When `--worktree` is specified, the worktree is created once at spawn time
- The **same worktree is reused across all iterations**
- Work persists between iterations (agent commits/pushes, next iteration picks up)
- The worktree is NOT recreated or reset between iterations

This enables the core ralph pattern: each iteration builds on the previous one's committed work.

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
  "last_iteration_ended": "2024-01-15T12:50:00.000000",
  "iteration_durations": [342, 298, 315],
  "consecutive_failures": 0,
  "total_failures": 2,
  "done_pattern": "regex|null",
  "inactivity_timeout": 300,
  "check_done_continuous": false,
  "exit_reason": "done_pattern|max_iterations|killed|failed|monitor_disconnected|null"
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

### Ralph Logs Command

**Description**: View the ralph iteration history log without knowing the file path.

**Command**:
```bash
swarm ralph logs <name> [--live] [--lines N]
```

**Inputs**:
- `<name>` (str, required): Worker name
- `--live` (bool, optional): Tail the log file in real-time (like `tail -f`)
- `--lines N` (int, optional): Show last N entries (default: all)

**Behavior**:
1. Read iteration log from `~/.swarm/ralph/<name>/iterations.log`
2. If `--live`, stream new entries as they appear
3. If `--lines N`, show only last N lines
4. Output log entries to stdout

**Output Format** (same as iterations.log):
```
2024-01-15T10:30:00 [START] iteration 1/100
2024-01-15T10:35:42 [END] iteration 1 exit=0 duration=5m42s
2024-01-15T10:35:43 [START] iteration 2/100
2024-01-15T12:00:00 [DONE] loop complete after 2 iterations reason=done_pattern
```

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Worker not found | Exit 1 with "swarm: error: no ralph state found for worker '<name>'" |
| Log file not found | Exit 1 with "swarm: error: no iteration log found for worker '<name>'" |

### Done Pattern Detection

**Description**: Stop the loop when a pattern is matched in agent output.

**Inputs**:
- `--done-pattern` (str, optional): Regex pattern to match
- `--check-done-continuous` (bool, optional): Check done pattern during monitoring, not just after exit (default: false)

**Default Behavior** (without `--check-done-continuous`):
1. After each agent exit, capture recent output
2. Match regex against output
3. If matched, stop loop with success

**Continuous Checking** (with `--check-done-continuous`):
1. During the inactivity detection polling loop (every 2 seconds)
2. Check captured output against done pattern
3. If matched, immediately stop loop (don't wait for exit or timeout)
4. Useful when you want to stop as soon as "All tasks complete" appears

**WARNING — Self-Match Footgun**: When using `--check-done-continuous`, the done pattern is checked against the full tmux pane buffer. Since `send_prompt_to_worker()` types the prompt content into the terminal via `tmux send-keys`, **any done pattern that appears literally in the prompt file will self-match immediately**, stopping the loop before the agent does any work.

Example: If PROMPT.md contains `Output /done on its own line` and the done pattern is `/done`, the loop stops after ~26 seconds with `exit_reason: done_pattern` because the prompt text itself matches.

**Mitigation** (required when using `--check-done-continuous`):
1. **Mark a baseline buffer position** after sending the prompt via `tmux send-keys`. Only check for done patterns in output that appears AFTER the prompt was sent. Clear the terminal after prompt injection (`tmux send-keys -t ... C-l`) or record the pane line count as a baseline.
2. **Use a done signal that cannot appear in prose**. Split the signal across string concatenation so the literal pattern never appears in the prompt:
   ```
   python3 -c "print('SWARM'+'_DONE'+'_X9K')"
   ```
   Then use `--done-pattern "SWARM_DONE_X9K"`.
3. **Grace period**: Skip done-pattern checks for the first N seconds after sending the prompt.

**Common Patterns**:
- `"All tasks complete"` - Simple string match
- `"IMPLEMENTATION_PLAN.md.*100%"` - Plan completion
- `"No remaining tasks"` - Task list empty
- `"SWARM_DONE_X9K"` - Unique signal that won't appear in prompt text (recommended for `--check-done-continuous`)

### Monitor Disconnect Handling

**Description**: Handle cases where the monitoring loop process stops while the worker continues running.

**Problem**: The ralph monitoring process (the `swarm ralph spawn` command or `swarm ralph run` background process) can crash, lose connection, or be killed while the tmux worker continues running. This leaves the worker orphaned - still working, but not being monitored for restarts.

**Detection**:
After `detect_inactivity()` returns or before each loop iteration:
1. Verify worker is still alive via `swarm status <name>`
2. If worker running but monitor stopping: set `exit_reason: monitor_disconnected`
3. Log the disconnect reason

**Status Display**:
When `exit_reason` is `monitor_disconnected`, status shows:
```
Ralph Loop: agent
Status: stopped
Exit reason: monitor_disconnected (worker still running)
Worker status: running
```

**Recovery**:
```bash
# Check if worker is still running
swarm status <name>

# Resume monitoring if worker alive
swarm ralph resume <name>
```

**Prevention**:
- Use heartbeat to periodically nudge workers: `--heartbeat 4h`
- Run the monitor in a persistent tmux session or screen
- Use `nohup` when backgrounding: `nohup swarm ralph spawn ... &`

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

### Mid-Iteration Intervention

**Description**: Send messages to the agent during an iteration.

**Command**:
```bash
swarm send <name> "message"
```

Since ralph workers are tmux workers, the standard `swarm send` command works. Use this to:
- Redirect the agent: `swarm send agent "skip that approach, try X instead"`
- Request wrap-up: `swarm send agent "please wrap up and commit your changes"`
- Provide information: `swarm send agent "the API endpoint changed to /v2/users"`

The message is typed into the tmux pane and becomes part of the agent's input.

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

## Prompt Design Principles

Good ralph prompts follow these principles:

| Principle | Rationale |
|-----------|-----------|
| **Small** | Less prompt = more context for actual work. Keep under 20 lines. |
| **Pick one task** | Each iteration should focus on ONE task. Don't overwhelm. |
| **Verify first** | Agent should read code before assuming state. Don't hallucinate. |
| **Commit each iteration** | Work must be committed/pushed to persist across context windows. |
| **Update the plan** | Mark tasks done so next iteration knows what's left. |

### Anti-patterns to Avoid

- Long prompts that consume context
- Multiple tasks per iteration (leads to partial completion)
- Assuming code state without reading it
- Forgetting to commit (work lost on next iteration)
- Not updating IMPLEMENTATION_PLAN.md (agent redoes completed work)

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
Iteration: 7/100 (avg 5m12s/iter, ~48m remaining)
Started: 2024-01-15 10:30:00
Current iteration started: 2024-01-15 12:45:00
Consecutive failures: 0
Total failures: 2
Inactivity timeout: 180s
Done pattern: All tasks complete
Exit reason: (none - still running)
```

**Status when stopped shows exit reason**:
```
Ralph Loop: agent
Status: stopped
Iteration: 10/10
Exit reason: max_iterations
Started: 2024-01-15 10:30:00
Last iteration ended: 2024-01-15 15:30:00
Total duration: 5h 0m
```

**Exit Reason Values**:
| Reason | Description |
|--------|-------------|
| `done_pattern` | Done pattern matched in agent output |
| `max_iterations` | Reached maximum iteration count |
| `killed` | Stopped via `swarm kill` or `swarm ralph pause` |
| `failed` | 5 consecutive failures |
| `monitor_disconnected` | Monitor process lost connection (worker may still be running) |

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
swarm ralph spawn --name agent --prompt-file ./PROMPT.md --max-iterations 100 -- claude \
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

### Ralph Spawn Arguments

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `--name` | str | Yes | - | Unique worker identifier |
| `--prompt-file` | str | Yes | - | Path to prompt file |
| `--max-iterations` | int | Yes | - | Maximum loop iterations |
| `--inactivity-timeout` | int | No | 180 | Screen stability timeout (seconds). Increase for repos with slow CI hooks. |
| `--done-pattern` | str | No | null | Regex to stop loop |
| `--check-done-continuous` | bool | No | false | Check done pattern during monitoring |
| `--no-run` | bool | No | false | Spawn only, don't start loop |
| `--replace` | bool | No | false | Auto-clean existing worker/worktree/state before spawn |
| `--clean-state` | bool | No | false | Clear ralph state without affecting worker/worktree |
| `--tmux` | bool | No | (no-op) | Accepted for consistency with `swarm spawn`, but ralph always uses tmux |
| `--worktree` | bool | No | false | Create isolated git worktree |

### Ralph Management Subcommands

| Command | Description |
|---------|-------------|
| `swarm ralph spawn --name <n> --prompt-file <f> --max-iterations <n> -- <cmd>` | Spawn ralph worker and start loop |
| `swarm ralph spawn --no-run ...` | Spawn ralph worker without starting loop |
| `swarm ralph run <name>` | Run the monitoring loop for existing worker |
| `swarm ralph pause <name>` | Pause ralph loop |
| `swarm ralph resume <name>` | Resume ralph loop |
| `swarm ralph status <name>` | Show ralph loop status |
| `swarm ralph list` | List all ralph workers |
| `swarm ralph ls` | Alias for `swarm ralph list` (consistency with `swarm ls`) |
| `swarm ralph logs <name>` | Show iteration history log |
| `swarm ralph logs <name> --live` | Tail iteration log |
| `swarm ralph logs <name> --lines N` | Show last N entries |
| `swarm ralph clean <name>` | Remove ralph state for a worker |
| `swarm ralph clean --all` | Remove ralph state for all workers |
| `swarm ralph init` | Create PROMPT.md template |
| `swarm ralph template` | Output template to stdout |

### Ralph Clean Command

**Description**: Remove ralph state for one or all workers without killing the worker process or removing worktrees.

**Commands**:
- `swarm ralph clean <name>` - Remove ralph state for a specific worker
- `swarm ralph clean --all` - Remove ralph state for all workers

**Behavior**:
1. Remove ralph state directory (`~/.swarm/ralph/<name>/`)
2. Does NOT kill the worker process (use `swarm kill` for that)
3. Does NOT remove worktrees (use `swarm kill --rm-worktree` for that)
4. `--all` iterates over all subdirectories in `~/.swarm/ralph/`

**Use Cases**:
- Clean up orphaned ralph state after manual worker cleanup
- Reset ralph state without affecting the running worker
- Bulk cleanup of all ralph state directories

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| No ralph state for worker | Exit 1 with "swarm: error: no ralph state found for worker '<name>'" |
| `--all` with no ralph state | No-op, exit 0 |
| Worker still running | Warning: "swarm: warning: worker '<name>' is still running (only ralph state removed)" |

### Ralph Ls Alias

**Description**: `swarm ralph ls` is accepted as an alias for `swarm ralph list`, for consistency with `swarm ls`.

**Behavior**: Identical to `swarm ralph list` in all respects (same arguments, same output).

### Docker Sandbox Caveats

**Description**: Known issues when using ralph with Docker-sandboxed workers (e.g., `sandbox.sh` wrapping `docker run ... claude`).

#### Docker TTY Requirement

When using `docker run` to wrap the agent command, the `-it` flags (interactive + TTY) are required. Without them, tmux provides a TTY to `sandbox.sh` but Docker does not pass it through to the container. The agent inside Docker gets no TTY and exits immediately.

**Symptom**: Worker tmux window dies silently after spawn. `send_prompt_to_worker()` fails with exit status 1.

**Fix**: Ensure `docker run --rm -it` (not just `docker run --rm`) in `sandbox.sh`.

#### Theme Picker Blocking

Fresh Docker containers without Claude Code preferences hit an interactive theme picker on first launch. This blocks all input — the prompt sent by `send_prompt_to_worker()` goes into the theme picker instead of the Claude prompt.

**Mitigations**:
1. Pre-configure theme in Docker image: `RUN mkdir -p /home/loopuser/.claude && echo '{"theme":"dark"}' > /home/loopuser/.claude/settings.local.json`
2. Mount full `~/.claude/` directory (not just credentials and settings) so the container inherits all preferences
3. Set `CLAUDE_THEME=dark` environment variable if supported

#### Worktree + Docker Incompatibility

`--worktree` is incompatible with Docker-sandboxed workers. The worktree is created on the host at a path like `/home/user/code/.worktrees/worker/`, and Docker mounts `$(pwd):/workspace`. The worktree path is visible inside Docker, but the Docker container provides its own filesystem isolation, making worktrees redundant and potentially confusing.

**Guideline**: Omit `--worktree` when using Docker sandbox. The Docker container provides isolation. Use `--worktree` only with native (non-Docker) workers.

#### Ralph Run Backgrounding

`swarm ralph run <name>` must run in a real terminal. Backgrounding it from within another agent session (`swarm ralph run worker &`) causes the monitoring loop to exit immediately with no output, because the double-backgrounded process loses its stdio connection.

**Workarounds**:
- The worker continues running in tmux regardless of the monitor — check on it with `swarm ralph status` and `tmux capture-pane`
- Run `ralph run` in its own tmux window or use `nohup`
- Use `ralph spawn` (which auto-starts the monitor) instead of the two-step `spawn --no-run` + `run` workflow

## Scenarios

### Scenario: Basic ralph loop (auto-start)
- **Given**: Prompt file exists at `./PROMPT.md`
- **When**: `swarm ralph spawn --name agent --prompt-file ./PROMPT.md --max-iterations 10 -- claude`
- **Then**:
  - Worker spawned in tmux mode
  - Monitoring loop starts automatically
  - Command blocks while loop runs
  - Output: "spawned agent (tmux: swarm:agent) [ralph mode: iteration 1/10]"
  - Ralph state created at `~/.swarm/ralph/agent/state.json`

### Scenario: Spawn without running loop
- **Given**: Prompt file exists at `./PROMPT.md`
- **When**: `swarm ralph spawn --name agent --prompt-file ./PROMPT.md --max-iterations 10 --no-run -- claude`
- **Then**:
  - Worker spawned in tmux mode
  - Monitoring loop NOT started
  - Command returns immediately
  - User must run `swarm ralph run agent` separately

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
- **Given**: Ralph worker with default `--inactivity-timeout 180`, agent idle for 180s
- **When**: Inactivity timeout expires
- **Then**:
  - Current agent killed
  - Log: "[ralph] agent: inactivity timeout (180s), restarting"
  - New iteration started

### Scenario: Done pattern stops loop (after exit)
- **Given**: Ralph worker with `--done-pattern "All tasks complete"`
- **When**: Agent exits and output contains "All tasks complete"
- **Then**:
  - Log: "[ralph] agent: done pattern matched, stopping loop"
  - Loop exits with code 0
  - Ralph state status set to "stopped"

### Scenario: Continuous done pattern checking
- **Given**: Ralph worker with `--done-pattern "All tasks complete" --check-done-continuous`
- **When**: Agent output contains "All tasks complete" (agent still running)
- **Then**:
  - Pattern detected during monitoring poll
  - Log: "[ralph] agent: done pattern matched, stopping loop"
  - Loop exits immediately (doesn't wait for agent exit)
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
- **Given**: Ralph worker "agent" running, iteration 7/10, previous iterations averaged 5m12s
- **When**: `swarm ralph status agent`
- **Then**:
  - Output shows:
    ```
    Ralph Loop: agent
    Status: running
    Iteration: 7/10 (avg 5m12s/iter, ~16m remaining)
    Started: 2024-01-15 10:30:00
    Current iteration started: 2024-01-15 12:45:00
    Consecutive failures: 0
    Total failures: 2
    Exit reason: (none - still running)
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
- **When**: `swarm ralph spawn --name agent --prompt-file ./missing.md --max-iterations 10 -- claude`
- **Then**:
  - Exit code 1
  - Error: "swarm: error: prompt file not found: ./missing.md"

### Scenario: Mid-iteration intervention
- **Given**: Ralph worker "agent" running, iteration 3/10
- **When**: `swarm send agent "please wrap up and commit"`
- **Then**:
  - Message typed into agent's tmux pane
  - Agent receives message as input
  - Agent can respond to the intervention

### Scenario: Worktree reuse across iterations
- **Given**: Ralph worker spawned with `--worktree`
- **When**: Iteration 1 completes, iteration 2 starts
- **Then**:
  - Same worktree directory used
  - Any committed changes from iteration 1 are present
  - Worktree is NOT reset or recreated

### Scenario: Replace existing worker with --replace
- **Given**: Ralph worker "agent" exists with worktree and ralph state
- **When**: `swarm ralph spawn --name agent --replace --prompt-file ./PROMPT.md --max-iterations 10 -- claude`
- **Then**:
  - Existing worker killed
  - Worktree removed
  - Ralph state directory removed (`~/.swarm/ralph/agent/`)
  - New worker spawned fresh
  - Output: "replaced existing worker agent"

### Scenario: Clean state only with --clean-state
- **Given**: Ralph state exists for "agent" (old settings), no running worker
- **When**: `swarm ralph spawn --name agent --clean-state --prompt-file ./PROMPT.md --max-iterations 10 -- claude`
- **Then**:
  - Ralph state directory removed
  - Worker spawned with new settings
  - Worktree preserved (if it existed)

### Scenario: --tmux flag accepted as no-op
- **Given**: User runs ralph spawn with --tmux flag
- **When**: `swarm ralph spawn --name agent --tmux --prompt-file ./PROMPT.md --max-iterations 10 -- claude`
- **Then**:
  - Info message: "Note: Ralph workers always use tmux"
  - Worker spawns normally
  - No error

### Scenario: View ralph logs
- **Given**: Ralph worker "agent" has run 3 iterations
- **When**: `swarm ralph logs agent`
- **Then**:
  - Outputs iteration log from `~/.swarm/ralph/agent/iterations.log`
  - Shows all entries

### Scenario: View ralph logs with line limit
- **Given**: Ralph worker "agent" has run 10 iterations
- **When**: `swarm ralph logs agent --lines 5`
- **Then**:
  - Outputs last 5 entries from iteration log

### Scenario: Monitor disconnect detected
- **Given**: Ralph worker "agent" running, monitor process killed
- **When**: Monitor process exits unexpectedly
- **Then**:
  - Ralph state set: `exit_reason: monitor_disconnected`
  - Worker continues running in tmux
  - `swarm ralph status agent` shows: "Exit reason: monitor_disconnected (worker still running)"

### Scenario: Done pattern self-matches prompt content
- **Given**: PROMPT.md contains "Output /done on its own line and stop"
- **When**: `swarm ralph spawn --name agent --prompt-file ./PROMPT.md --done-pattern "/done" --check-done-continuous -- claude`
- **Then**:
  - Prompt typed into tmux pane via `send-keys`
  - Done pattern `/done` matches the prompt text in the pane buffer
  - Loop stops after ~26 seconds with `exit_reason: done_pattern`
  - Agent never performed any work
  - **This is a known footgun** — use a unique signal pattern that doesn't appear in the prompt

### Scenario: Ralph ls alias
- **Given**: Ralph workers exist
- **When**: `swarm ralph ls`
- **Then**:
  - Output identical to `swarm ralph list`
  - Shows NAME, RALPH_STATUS, WORKER_STATUS, ITERATION, FAILURES columns

### Scenario: Clean ralph state for specific worker
- **Given**: Ralph state exists for "agent"
- **When**: `swarm ralph clean agent`
- **Then**:
  - Ralph state directory removed (`~/.swarm/ralph/agent/`)
  - Output: "cleaned ralph state for agent"
  - Worker process and worktree unaffected

### Scenario: Clean all ralph state
- **Given**: Ralph state exists for "agent" and "builder"
- **When**: `swarm ralph clean --all`
- **Then**:
  - Both ralph state directories removed
  - Output: "cleaned ralph state for agent", "cleaned ralph state for builder"
  - Worker processes and worktrees unaffected

### Scenario: Docker sandbox without -it flags
- **Given**: `sandbox.sh` uses `docker run --rm` (no `-it`)
- **When**: Ralph spawns worker with `-- ./sandbox.sh --dangerously-skip-permissions`
- **Then**:
  - tmux window created, `sandbox.sh` starts
  - Docker container starts but Claude gets no TTY
  - Claude exits immediately with "Input must be provided either through stdin or as a prompt argument when using --print"
  - tmux window dies silently
  - `send_prompt_to_worker()` fails with exit status 1

### Scenario: Docker container hits theme picker
- **Given**: Fresh Docker container with no Claude Code preferences
- **When**: `claude` starts inside container
- **Then**:
  - Interactive theme picker displayed
  - Prompt sent by ralph goes into theme picker, not Claude
  - Worker appears stuck, eventually times out
  - **Fix**: Pre-configure theme in Docker image

## Edge Cases

- Worker name reused across iterations (same name, iteration tracked in metadata)
- Prompt file can be absolute or relative path (resolved at spawn time)
- Empty prompt file is allowed (agent receives empty input)
- `--done-pattern` uses Python regex syntax
- Backoff timer does not count toward inactivity timeout
- Pausing during backoff wait immediately stops the wait
- Resume after pause continues iteration count (does not reset)
- Multiple ralph workers can run concurrently with different names
- Ralph state persists across swarm restarts (can resume after crash)
- Killing a ralph worker also stops the loop (state set to "stopped")
- `--ready-wait` is implicit in ralph mode (always waits for ready)
- Worktree mode (`--worktree`) is compatible with ralph mode - same worktree reused
- `--no-run` returns immediately after spawn, useful for scripting

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
swarm ralph spawn --name <name> --prompt-file ./PROMPT.md --max-iterations 200 -- claude
```

### Clean up ralph state

```bash
# Option 1: Use --clean-state on next spawn (recommended)
swarm ralph spawn --name <name> --clean-state --prompt-file ./PROMPT.md --max-iterations 10 -- claude

# Option 2: Use --replace to kill worker and clean everything
swarm ralph spawn --name <name> --replace --prompt-file ./PROMPT.md --max-iterations 10 -- claude

# Option 3: Manual cleanup
rm -rf ~/.swarm/ralph/<name>/

# Clean all ralph state
rm -rf ~/.swarm/ralph/
```

### Monitor disconnected, worker still running

```bash
# Check worker status
swarm status <name>

# If worker is running, resume monitoring
swarm ralph resume <name>

# View what the worker has been doing
swarm logs <name>

# View ralph iteration history
swarm ralph logs <name>
```

## Best Practices

### Preventing Test Artifacts

A common issue is agents creating test files (e.g., `test.txt`, `new.txt`) during verification that get accidentally committed. Prevent this with:

**Prompt Guidelines**:
- Include in your PROMPT.md: "Do NOT create test files. Use the existing test suite for verification."
- Specify exact test commands: "Run `npm test` to verify changes"
- Discourage exploratory file creation: "Verify by reading existing code, not by creating new files"

**Example PROMPT.md Section**:
```markdown
IMPORTANT:
- Do NOT create test files like test.txt, new.txt, temp.txt, etc.
- Verify changes by running the existing test suite: `npm test`
- If you need to test something, add a proper test to the test suite
- Clean up any temporary files before committing
```

**.gitignore Patterns**:
Add these to prevent accidental commits of test artifacts:
```gitignore
# Test artifacts
test.txt
new.txt
temp.txt
*.tmp
temp/
.test-output/
```

**Post-Loop Verification**:
Before merging ralph-generated commits:
```bash
git log --oneline --name-only HEAD~10..HEAD  # Check what files were added
git diff main..HEAD -- '*.txt'               # Look for unexpected text files
```

### Prompt Size Guidelines

Keep prompts minimal to preserve context for actual work:
- **Target**: Under 20 lines
- **Focus**: One task per iteration
- **Essential elements only**: task source, verification method, commit reminder

**Bad** (too verbose):
```markdown
You are a helpful AI assistant. Your job is to improve this codebase.
Please read through the implementation plan carefully and select an
appropriate task to work on. When you're done, make sure to update
the plan and commit your changes...
[50 more lines of instructions]
```

**Good** (minimal):
```markdown
Read IMPLEMENTATION_PLAN.md. Pick ONE incomplete task.
Verify by reading code first. Run tests. Update plan. Commit.
```

## Implementation Notes

- **Tmux requirement**: Ralph requires tmux for pane capture, ready detection, and output monitoring. Process mode is not supported.
- **Prompt injection**: The prompt file content is typed into the tmux pane via `tmux send-keys` after the agent signals readiness. For Claude Code, this becomes the first user message.
- **State file locking**: Ralph state files should use fcntl locking to prevent race conditions.
- **Iteration logging**: Each iteration is logged with timestamps to enable debugging and analysis.
- **Graceful shutdown**: SIGTERM to the ralph process should pause the loop and allow current agent to complete.
- **Resource management**: Each iteration creates a fresh agent with a new context window, consuming API tokens.
- **Auto-start default**: `ralph spawn` runs the loop by default for simpler UX. Use `--no-run` for the legacy two-command workflow.
- **Worktree persistence**: When using `--worktree`, the same worktree is reused across all iterations. Work persists via git commits.
