# Workflow

## Overview

Workflow enables multi-stage agent pipelines defined in YAML. Stages execute sequentially, with support for scheduling, heartbeats, and configurable failure handling. This allows complex tasks like "plan → build → validate" to run unattended overnight.

## Dependencies

- External: tmux, git (for worktrees), filesystem
- Internal: `spawn.md`, `ralph-loop.md`, `heartbeat.md`, `send.md`, `state-management.md`

## Concepts

### Stage Types

| Type | Description | Completion Detection |
|------|-------------|---------------------|
| `worker` | Single-run agent (like `swarm spawn`) | Done pattern or timeout |
| `ralph` | Looping agent (like `swarm ralph spawn`) | Ralph loop completion or max iterations |

### Workflow Lifecycle

```
created → scheduled → running → completed
                  ↓         ↓
               failed    cancelled
```

### Storage Locations

- **Global workflows**: `~/.swarm/workflows/`
- **Repo-local workflows**: `.swarm/workflows/` (overrides global)
- **Workflow state**: `~/.swarm/workflows/<name>/state.json`
- **Workflow logs**: `~/.swarm/workflows/<name>/logs/`

## Data Structures

### Workflow Definition (YAML)

```yaml
# Workflow metadata
name: feature-build                    # Required: unique identifier
description: Build and validate feature # Optional: human description

# Scheduling (all optional)
schedule: "02:00"                      # Start at time (HH:MM, 24h format)
delay: "4h"                            # Or: start after delay

# Global settings (apply to all stages, can override per-stage)
heartbeat: 4h                          # Nudge interval for rate limit recovery
heartbeat-expire: 24h                  # Stop heartbeat after duration
heartbeat-message: "continue"          # Message to send on heartbeat
worktree: true                         # Use git worktrees for isolation
cwd: ./                                # Working directory

# Stage definitions (execute in order)
stages:
  - name: plan                         # Required: stage identifier
    type: worker                       # Required: worker | ralph

    # Prompt (exactly one required)
    prompt: |                          # Inline prompt (for short prompts)
      Review TASK.md and create a plan.
      Write to PLAN.md, then say /done.
    # OR
    prompt-file: ./prompts/plan.md     # File path (for complex prompts)

    # Completion detection
    done-pattern: "/done|COMPLETE"     # Regex to detect completion
    timeout: 2h                        # Max time before moving on

    # Failure handling
    on-failure: stop                   # stop | retry | skip
    max-retries: 3                     # Attempts if on-failure: retry

    # Stage-specific overrides
    heartbeat: 2h                      # Override global heartbeat
    worktree: false                    # Override global worktree
    env:                               # Environment variables
      DEBUG: "true"
    tags:                              # Worker tags
      - planning

    # Next stage control
    on-complete: next                  # next | stop | goto:<stage-name>

  - name: build
    type: ralph                        # Ralph loop stage
    prompt-file: ./prompts/build.md

    # Ralph-specific options
    max-iterations: 50                 # Required for ralph type
    inactivity-timeout: 60             # Seconds (default: 60)
    check-done-continuous: true        # Check pattern during monitoring

    on-failure: retry
    max-retries: 2
    on-complete: next

  - name: validate
    type: ralph
    prompt: |
      Review the implementation against PLAN.md.
      Run all tests. Fix any failures.
      Say /done when all tests pass.
    max-iterations: 20
    done-pattern: "/done"
    on-complete: stop                  # End workflow after this stage
```

### WorkflowState

Stored in `~/.swarm/workflows/<name>/state.json`:

```json
{
  "name": "feature-build",
  "status": "running",
  "current_stage": "build",
  "current_stage_index": 1,
  "created_at": "2026-02-04T02:00:00Z",
  "started_at": "2026-02-04T02:00:00Z",
  "scheduled_for": null,
  "completed_at": null,
  "stages": {
    "plan": {
      "status": "completed",
      "started_at": "2026-02-04T02:00:00Z",
      "completed_at": "2026-02-04T02:45:00Z",
      "worker_name": "feature-build-plan",
      "attempts": 1,
      "exit_reason": "done_pattern"
    },
    "build": {
      "status": "running",
      "started_at": "2026-02-04T02:45:00Z",
      "worker_name": "feature-build-build",
      "attempts": 1
    },
    "validate": {
      "status": "pending"
    }
  },
  "workflow_file": "/home/user/project/workflow.yaml",
  "workflow_hash": "abc123..."
}
```

### StageStatus

| Status | Description |
|--------|-------------|
| `pending` | Not yet started |
| `running` | Currently executing |
| `completed` | Finished successfully |
| `failed` | Failed (exhausted retries) |
| `skipped` | Skipped due to `on-failure: skip` |

### WorkflowStatus

| Status | Description |
|--------|-------------|
| `created` | Parsed but not started |
| `scheduled` | Waiting for scheduled time |
| `running` | Currently executing stages |
| `completed` | All stages finished successfully |
| `failed` | Stage failed and `on-failure: stop` |
| `cancelled` | Manually cancelled |

## Behavior

### Run Workflow

**Description**: Execute a workflow from a YAML definition.

**Inputs**:
- `workflow_file` (path, required): Path to YAML file
- `--at` (time, optional): Schedule start time (HH:MM)
- `--in` (duration, optional): Schedule start delay
- `--name` (string, optional): Override workflow name

**Outputs**:
- Success: "Workflow '<name>' started" or "Workflow '<name>' scheduled for <time>"
- Failure: Validation error with details

**Side Effects**:
- Creates workflow state in `~/.swarm/workflows/<name>/`
- Spawns workers for each stage
- Manages heartbeats per configuration

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Invalid YAML | "Error: invalid workflow YAML: <details>" (exit 1) |
| Missing required field | "Error: stage '<name>' missing required field '<field>'" (exit 1) |
| Duplicate workflow name | "Error: workflow '<name>' already exists (use --force)" (exit 1) |
| Invalid schedule time | "Error: invalid time format '<value>' (use HH:MM)" (exit 1) |
| Prompt file not found | "Error: prompt file not found: <path>" (exit 1) |

### Workflow Status

**Description**: Show status of a workflow.

**Inputs**:
- `name` (string, required): Workflow name

**Outputs**:
- Detailed status showing: overall status, current stage, stage statuses, timing

### List Workflows

**Description**: List all workflows.

**Inputs**: None

**Outputs**:
- Table showing: name, status, current stage, started, source file

### Cancel Workflow

**Description**: Stop a running workflow.

**Inputs**:
- `name` (string, required): Workflow name
- `--force` (flag, optional): Kill workers without graceful shutdown

**Outputs**:
- Success: "Workflow '<name>' cancelled"

**Side Effects**:
- Sets status to "cancelled"
- Kills current stage worker
- Stops heartbeats

### Resume Workflow

**Description**: Resume a failed or paused workflow.

**Inputs**:
- `name` (string, required): Workflow name
- `--from` (stage, optional): Resume from specific stage

**Outputs**:
- Success: "Workflow '<name>' resumed from stage '<stage>'"

## CLI Interface

```
swarm workflow run <file> [--at TIME] [--in DURATION] [--name NAME] [--force]
swarm workflow status <name>
swarm workflow list
swarm workflow cancel <name> [--force]
swarm workflow resume <name> [--from STAGE]
swarm workflow logs <name> [--stage STAGE]
swarm workflow validate <file>
```

### Help Text

```
usage: swarm workflow [-h] {run,status,list,cancel,resume,logs,validate} ...

Multi-stage agent pipelines with scheduling and rate limit recovery.

Workflow orchestrates sequential agent stages (plan → build → validate)
defined in YAML. Each stage can be a one-shot worker or a ralph loop.
Workflows support scheduling, heartbeats for rate limit recovery, and
configurable failure handling.

positional arguments:
  {run,status,list,cancel,resume,logs,validate}
    run                 Run a workflow from YAML file
    status              Show workflow status
    list                List all workflows
    cancel              Cancel a running workflow
    resume              Resume a failed/paused workflow
    logs                View workflow logs
    validate            Validate workflow YAML without running

options:
  -h, --help            show this help message and exit

Quick Start:
  1. Create workflow.yaml (see: swarm workflow run --help for format)
  2. Run: swarm workflow run workflow.yaml
  3. Monitor: swarm workflow status my-workflow

Scheduling:
  # Run at 2am tonight
  swarm workflow run workflow.yaml --at "02:00"

  # Run in 4 hours
  swarm workflow run workflow.yaml --in 4h

Rate Limit Recovery:
  Set heartbeat in workflow.yaml to automatically nudge agents when
  they might be stuck on rate limits:

    heartbeat: 4h           # Nudge every 4 hours
    heartbeat-expire: 24h   # Stop after 24 hours

Storage:
  Workflow state: ~/.swarm/workflows/<name>/
  Repo-local definitions: .swarm/workflows/ (searched first)
  Global definitions: ~/.swarm/workflows/

Examples:
  swarm workflow run ./build-feature.yaml
  swarm workflow run ./overnight-work.yaml --at "02:00"
  swarm workflow status feature-build
  swarm workflow cancel feature-build
  swarm workflow resume feature-build --from validate

Director Pattern (Agent-in-the-Loop):
  For monitored workflows, spawn a separate "director" agent that watches
  and intervenes using existing swarm commands:

    # Start workflow in background
    swarm workflow run build.yaml &

    # Spawn director to monitor
    swarm spawn --name director --tmux -- claude
    swarm send director "Monitor 'feature-build', intervene if stages fail"

  The director uses: workflow status, send, attach, pause, resume, cancel.
  See: swarm workflow run --help (Director Pattern section)
```

### Run Help Text

```
usage: swarm workflow run [-h] [--at TIME] [--in DURATION] [--name NAME]
                          [--force]
                          file

Run a workflow from a YAML definition file.

positional arguments:
  file                  Path to workflow YAML file

options:
  -h, --help            show this help message and exit
  --at TIME             Schedule start time (HH:MM, 24h format)
                        Example: --at "02:00" for 2am
  --in DURATION         Schedule start delay
                        Example: --in "4h" for 4 hours from now
  --name NAME           Override workflow name from YAML
  --force               Overwrite existing workflow with same name

Workflow YAML Format:
  A workflow defines sequential stages that execute one after another.
  Each stage is either a 'worker' (single run) or 'ralph' (loop).

  Required Fields:
    name: my-workflow           # Unique identifier

  Optional Global Settings:
    description: "..."          # Human description
    schedule: "02:00"           # Default start time (HH:MM)
    delay: "4h"                 # Alternative: start after delay
    heartbeat: 4h               # Rate limit recovery interval
    heartbeat-expire: 24h       # Stop heartbeat after duration
    heartbeat-message: "..."    # Custom nudge message
    worktree: true              # Git worktree isolation
    cwd: ./path                 # Working directory

  Stages (required, list):
    stages:
      - name: stage-name        # Required: stage identifier
        type: worker            # Required: worker | ralph

        # Prompt (exactly one required):
        prompt: |               # Inline prompt
          Your instructions...
        prompt-file: ./file.md  # OR file path

        # Completion (optional):
        done-pattern: "/done"   # Regex to detect completion
        timeout: 2h             # Max time before moving on

        # Failure handling (optional):
        on-failure: stop        # stop | retry | skip (default: stop)
        max-retries: 3          # Attempts if on-failure: retry

        # Ralph-specific (type: ralph only):
        max-iterations: 50      # Required for ralph
        inactivity-timeout: 60  # Seconds (default: 60)
        check-done-continuous: true

        # Stage overrides (optional):
        heartbeat: 2h           # Override global
        worktree: false         # Override global
        env:
          KEY: "value"
        tags:
          - my-tag

        # Flow control (optional):
        on-complete: next       # next | stop | goto:<stage>

Minimal Example:
  name: simple-task
  stages:
    - name: work
      type: worker
      prompt: |
        Complete the task in TASK.md.
        Say /done when finished.
      done-pattern: "/done"
      timeout: 1h

Full Example:
  name: feature-build
  description: Plan, build, and validate a feature
  heartbeat: 4h
  heartbeat-expire: 24h
  worktree: true

  stages:
    - name: plan
      type: worker
      prompt: |
        Read TASK.md. Create implementation plan in PLAN.md.
        Say /done when the plan is complete.
      done-pattern: "/done"
      timeout: 1h
      on-complete: next

    - name: build
      type: ralph
      prompt-file: ./prompts/build.md
      max-iterations: 50
      check-done-continuous: true
      done-pattern: "ALL TASKS COMPLETE"
      on-failure: retry
      max-retries: 2
      on-complete: next

    - name: validate
      type: ralph
      prompt: |
        Review implementation against PLAN.md.
        Run tests: python -m pytest
        Fix any failures. Say /done when all tests pass.
      max-iterations: 20
      done-pattern: "/done"
      on-complete: stop

Stage Type Reference:

  worker (single-run agent):
    - Spawns agent once
    - Waits for done-pattern or timeout
    - Good for: planning, review, one-shot tasks

  ralph (looping agent):
    - Spawns agent repeatedly (ralph loop)
    - Continues until max-iterations or done-pattern
    - Good for: implementation, multi-step tasks

Failure Handling:

  on-failure: stop    - Stop entire workflow (default)
  on-failure: retry   - Retry stage up to max-retries times
  on-failure: skip    - Skip stage, continue to next

Flow Control:

  on-complete: next       - Continue to next stage (default)
  on-complete: stop       - End workflow successfully
  on-complete: goto:name  - Jump to named stage (future)

Duration Format:
  Accepts: "4h", "30m", "90s", "1h30m", or seconds as integer

Tips:
  - Keep prompts SHORT (<20 lines) to maximize context for work
  - Use prompt-file for complex prompts with multiple instructions
  - Set heartbeat for overnight/unattended workflows
  - Always set timeout or max-iterations to prevent infinite runs
  - Use done-pattern for reliable stage completion detection

Debugging:
  swarm workflow validate file.yaml   # Check syntax without running
  swarm workflow status <name>        # Check progress
  swarm workflow logs <name>          # View all logs
  swarm attach <workflow>-<stage>     # Attach to running stage

Director Pattern (Agent-in-the-Loop):
  For workflows that need monitoring/intervention, spawn a separate
  "director" agent instead of building orchestration into the workflow:

    # Start workflow
    swarm workflow run build.yaml &

    # Spawn director agent to monitor and intervene
    swarm spawn --name director --tmux -- claude
    swarm send director "Monitor workflow 'my-workflow'. Check status
      every 10 min. Intervene with 'swarm send <worker> msg' if stuck."

  The director uses existing commands (workflow status, send, attach,
  pause, resume) to monitor and control the workflow. This keeps the
  workflow system simple while enabling sophisticated orchestration
  through agent prompts.

  Director can be a ralph loop for long-running monitoring:
    swarm ralph spawn --name director --prompt-file director.md \
      --max-iterations 100 -- claude
```

## Scenarios

### Scenario: Run simple workflow immediately
- **Given**: A valid workflow.yaml with 2 stages
- **When**: `swarm workflow run workflow.yaml`
- **Then**:
  - Workflow state created
  - First stage worker spawned
  - Output: "Workflow 'my-workflow' started (stage 1/2: plan)"

### Scenario: Schedule workflow for later
- **Given**: A valid workflow.yaml
- **When**: `swarm workflow run workflow.yaml --at "02:00"`
- **Then**:
  - Workflow state created with status "scheduled"
  - scheduled_for set to next 02:00
  - Output: "Workflow 'my-workflow' scheduled for 02:00"

### Scenario: Stage completes, next stage starts
- **Given**: Workflow "build" running, stage "plan" active
- **When**: Worker outputs "/done" (matches done-pattern)
- **Then**:
  - Stage "plan" marked completed
  - Stage "build" worker spawned
  - Log: "Stage 'plan' completed, starting 'build'"

### Scenario: Stage fails with on-failure: retry
- **Given**: Workflow running, stage with on-failure: retry, max-retries: 3
- **When**: Stage worker exits non-zero (attempt 1)
- **Then**:
  - Attempt count incremented
  - Stage restarted
  - Log: "Stage 'build' failed, retrying (attempt 2/3)"

### Scenario: Stage exhausts retries
- **Given**: Stage with max-retries: 3, currently on attempt 3
- **When**: Stage fails again
- **Then**:
  - Stage marked "failed"
  - Workflow marked "failed"
  - Log: "Stage 'build' failed after 3 attempts, workflow stopped"

### Scenario: Stage fails with on-failure: skip
- **Given**: Workflow running, stage with on-failure: skip
- **When**: Stage times out
- **Then**:
  - Stage marked "skipped"
  - Next stage started
  - Log: "Stage 'plan' timed out, skipping to 'build'"

### Scenario: Heartbeat active during workflow
- **Given**: Workflow with heartbeat: 4h
- **When**: Stage worker running for 4+ hours
- **Then**:
  - Heartbeat message sent to worker
  - If rate limited, agent resumes
  - Log: "Heartbeat sent to 'build' (beat 1)"

### Scenario: Cancel running workflow
- **Given**: Workflow "feature" running
- **When**: `swarm workflow cancel feature`
- **Then**:
  - Current stage worker killed
  - Heartbeat stopped
  - Status set to "cancelled"
  - Output: "Workflow 'feature' cancelled"

### Scenario: Resume failed workflow
- **Given**: Workflow "feature" failed at stage "validate"
- **When**: `swarm workflow resume feature`
- **Then**:
  - Workflow status set to "running"
  - Stage "validate" restarted
  - Output: "Workflow 'feature' resumed from stage 'validate'"

### Scenario: Inline prompt vs prompt-file
- **Given**: Stage with `prompt: |` inline text
- **When**: Stage starts
- **Then**:
  - Temporary prompt file created
  - Prompt injected to agent
  - Temp file cleaned up after stage

## Edge Cases

- **Empty stages list**: Rejected with "workflow must have at least one stage"
- **Duplicate stage names**: Rejected with "duplicate stage name: '<name>'"
- **Both prompt and prompt-file**: Rejected with "stage '<name>' has both prompt and prompt-file"
- **Neither prompt nor prompt-file**: Rejected with "stage '<name>' requires prompt or prompt-file"
- **ralph type without max-iterations**: Rejected with "ralph stage '<name>' requires max-iterations"
- **Invalid on-complete target**: Rejected with "unknown stage in goto: '<name>'"
- **Circular goto references**: Rejected with "circular stage reference detected"
- **Schedule time in past**: Schedules for next occurrence (tomorrow if time passed today)
- **Worker name collision**: Stage workers named `<workflow>-<stage>` to avoid collisions
- **Workflow file modified during run**: Warning logged, original definition used
- **System restart during workflow**: State persisted, can resume with `workflow resume`

## Recovery Procedures

### Workflow stuck on stage
```bash
swarm workflow status <name>           # Check which stage
swarm attach <workflow>-<stage>        # See what agent is doing
swarm send <workflow>-<stage> "..."    # Intervene if needed
```

### Resume after failure
```bash
swarm workflow status <name>           # See failure details
swarm workflow logs <name> --stage <s> # Check stage logs
swarm workflow resume <name>           # Restart from failed stage
swarm workflow resume <name> --from <s> # Or restart from specific stage
```

### Clean up abandoned workflow
```bash
swarm workflow cancel <name>           # Stop and mark cancelled
swarm workflow list                    # Verify stopped
```

## Director Pattern (Agent-in-the-Loop)

Workflows run autonomously by default, but you may want an agent (or human) to monitor progress and intervene when needed. Rather than building orchestration into the workflow system, use the **Director Pattern**: spawn a separate agent that monitors and controls workflows using existing swarm primitives.

### Concept

```
┌─────────────────────────────────────────────────────────┐
│                   Director Worker                        │
│  (Agent monitoring workflow, can intervene)              │
├─────────────────────────────────────────────────────────┤
│  Uses existing commands:                                 │
│  - swarm workflow status <name>    # Check progress      │
│  - swarm workflow list             # See all workflows   │
│  - swarm send <worker> "msg"       # Intervene in stage  │
│  - swarm attach <worker>           # Watch stage live    │
│  - swarm workflow pause <name>     # Pause workflow      │
│  - swarm workflow resume <name>    # Resume workflow     │
│  - swarm workflow cancel <name>    # Abort workflow      │
└─────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
    ┌─────────┐         ┌─────────┐         ┌─────────┐
    │  Plan   │   ───►  │  Build  │   ───►  │Validate │
    │  Stage  │         │  Stage  │         │  Stage  │
    └─────────┘         └─────────┘         └─────────┘
```

### Why This Approach

1. **Unix philosophy**: Keep primitives simple, compose for complex behavior
2. **No new features needed**: Director uses existing `swarm workflow`, `swarm send`, `swarm attach`
3. **Flexible**: Director logic lives in the prompt, not the tool
4. **Works for humans too**: Same commands work for manual intervention

### Director Setup

```bash
# 1. Start the workflow (runs autonomously)
swarm workflow run build.yaml &

# 2. Spawn a director agent to monitor
swarm spawn --name director --tmux -- claude

# 3. Give director its instructions
swarm send director "Monitor workflow 'feature-build'. Check status every 10 min.
Intervene if a stage is stuck or failing. Use 'swarm send <worker> msg' to guide."
```

### Example Director Prompt

```markdown
# Director Agent

You are orchestrating a multi-stage build workflow.

## Your Job
1. Monitor workflow progress: `swarm workflow status feature-build`
2. Check status periodically (every 10-15 minutes)
3. Watch for failures, stuck stages, or unexpected output
4. Intervene when needed: `swarm send feature-build-<stage> "guidance..."`
5. Report final status when workflow completes

## Available Commands
- `swarm workflow status <name>` - Check workflow progress
- `swarm workflow list` - See all workflows
- `swarm send <workflow>-<stage> "message"` - Send guidance to a stage worker
- `swarm attach <workflow>-<stage>` - Watch stage output live (Ctrl-B D to detach)
- `swarm workflow pause <name>` - Pause workflow between stages
- `swarm workflow resume <name>` - Resume paused workflow
- `swarm workflow cancel <name>` - Abort workflow entirely
- `swarm logs <workflow>-<stage>` - View stage output history

## Stage Worker Names
Workers are named `<workflow>-<stage>`:
- feature-build-plan
- feature-build-build
- feature-build-validate

## When to Intervene
- Stage running >1 hour without progress
- Error patterns in output (check with `swarm logs`)
- Stage completed but output looks incomplete
- Rate limit or API errors

## Intervention Examples
```bash
# Guide a stuck planning stage
swarm send feature-build-plan "Focus on the authentication module first"

# Help with a failing build
swarm send feature-build-build "Try using the existing UserService instead"

# Check what's happening in a stage
swarm attach feature-build-validate
# (Ctrl-B D to detach)
```

## Success Criteria
Workflow completes with all stages successful. Report summary when done.
```

### Director as Ralph Loop

For long-running workflows, run the director as a ralph loop so it survives context limits:

```bash
# director-prompt.md contains the director instructions above
swarm ralph spawn --name director \
  --prompt-file ./director-prompt.md \
  --max-iterations 100 \
  --inactivity-timeout 300 \
  -- claude
```

The director will periodically check workflow status and intervene as needed, restarting with fresh context when the inactivity timeout triggers.

### Human as Director

The same commands work for manual human intervention:

```bash
# Check workflow progress
swarm workflow status feature-build

# Watch a stage live
swarm attach feature-build-build

# Send guidance to struggling stage
swarm send feature-build-build "skip the optimization, just get tests passing"

# Pause while you investigate
swarm workflow pause feature-build

# Resume when ready
swarm workflow resume feature-build
```

### Scenarios

#### Scenario: Director monitors and intervenes
- **Given**: Workflow "feature-build" running, director agent spawned
- **When**: Director runs `swarm workflow status feature-build` and sees stage "build" stuck
- **Then**: Director runs `swarm send feature-build-build "try a different approach"`

#### Scenario: Director pauses for human review
- **Given**: Workflow running, director detects unusual output
- **When**: Director runs `swarm workflow pause feature-build`
- **Then**: Workflow pauses after current stage completes, director alerts human

#### Scenario: Human takes over from director
- **Given**: Director agent running, human wants to intervene directly
- **When**: Human runs `swarm kill director` and `swarm attach feature-build-build`
- **Then**: Human can directly observe and guide the stage

## Implementation Notes

- Workflow monitor runs as foreground process (use `&` or nohup for background)
- Stage workers named `<workflow>-<stage>` for uniqueness
- Inline prompts written to temp files, cleaned up after stage
- Workflow YAML copied to state directory for reproducibility
- Hash of original YAML stored to detect modifications
- Repo-local `.swarm/workflows/` searched before global `~/.swarm/workflows/`
- All times stored as UTC ISO8601 for consistency
- Director pattern requires no workflow changes - uses existing primitives
