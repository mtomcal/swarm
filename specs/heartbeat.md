# Heartbeat

## Overview

Heartbeat provides periodic nudges to workers to help them recover from rate limits or other blocking states. Instead of detecting rate limits directly, heartbeat sends configurable messages on a schedule, allowing stuck agents to resume work when limits renew.

## Dependencies

- External: tmux (for sending messages to workers)
- Internal: `send.md`, `state-management.md`, `spawn.md`

## Concepts

### Rate Limit Recovery Pattern

When AI agents hit API rate limits, they typically pause and wait. Rate limits often renew on fixed intervals (e.g., every 4 hours). Rather than detecting the rate limit state, heartbeat blindly sends nudges on a schedule:

- If the agent is stuck on a rate limit, the nudge prompts it to retry
- If the agent is working normally, the nudge is harmless (agent ignores it or acknowledges)
- If the agent has exited, the nudge has no effect

### Expiration Safety

Heartbeats automatically expire after a configurable duration to prevent:
- Infinite nudging of dead/stuck workers
- Resource waste on abandoned workflows
- Unexpected behavior days after starting a heartbeat

## Data Structures

### HeartbeatState

Stored in `~/.swarm/heartbeats/<worker-name>.json`:

```json
{
  "worker_name": "builder",
  "interval_seconds": 14400,
  "expire_at": "2026-02-05T02:00:00Z",
  "message": "continue",
  "created_at": "2026-02-04T02:00:00Z",
  "last_beat_at": "2026-02-04T06:00:00Z",
  "beat_count": 1,
  "status": "active"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `worker_name` | string | Target worker name |
| `interval_seconds` | int | Seconds between heartbeats |
| `expire_at` | ISO8601 | When heartbeat stops (null = never) |
| `message` | string | Message to send on each beat |
| `created_at` | ISO8601 | When heartbeat was created |
| `last_beat_at` | ISO8601 | Last successful beat (null if none) |
| `beat_count` | int | Number of beats sent |
| `status` | enum | `active`, `paused`, `expired`, `stopped` |

## Behavior

### Start Heartbeat

**Description**: Begin periodic nudges to a worker.

**Inputs**:
- `worker_name` (string, required): Target worker
- `interval` (duration, required): Time between beats (e.g., "4h", "30m", "3600")
- `expire` (duration, optional): Stop after this duration (e.g., "24h")
- `message` (string, optional): Message to send (default: "continue")

**Outputs**:
- Success: "Heartbeat started for <worker> (every <interval>, expires <time>)"
- Failure: Error message with exit code 1

**Side Effects**:
- Creates `~/.swarm/heartbeats/<worker>.json`
- Spawns background heartbeat monitor process

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Worker doesn't exist | "Error: worker '<name>' not found" (exit 1) |
| Worker not tmux | "Error: heartbeat requires tmux worker" (exit 1) |
| Heartbeat already exists | "Error: heartbeat already active for '<name>' (use --force to replace)" (exit 1) |
| Invalid interval | "Error: invalid interval '<value>'" (exit 1) |

### Stop Heartbeat

**Description**: Stop heartbeat for a worker.

**Inputs**:
- `worker_name` (string, required): Target worker

**Outputs**:
- Success: "Heartbeat stopped for <worker>"
- Not found: "No active heartbeat for <worker>"

**Side Effects**:
- Sets status to `stopped` in state file
- Terminates background monitor process

### List Heartbeats

**Description**: Show all heartbeats and their status.

**Inputs**: None

**Outputs**:
- Table showing: worker, interval, next beat, expires, status, beat count

### Heartbeat Status

**Description**: Show detailed status for one heartbeat.

**Inputs**:
- `worker_name` (string, required): Target worker

**Outputs**:
- Detailed status including last beat time, next beat time, beats sent

## CLI Interface

```
swarm heartbeat start <worker> --interval <duration> [--expire <duration>] [--message <text>] [--force]
swarm heartbeat stop <worker>
swarm heartbeat list
swarm heartbeat status <worker>
swarm heartbeat pause <worker>
swarm heartbeat resume <worker>
```

### Help Text

```
usage: swarm heartbeat [-h] {start,stop,list,status,pause,resume} ...

Periodic nudges to help workers recover from rate limits.

Heartbeat sends messages to workers on a schedule. This helps agents
recover from API rate limits that renew on fixed intervals (e.g., every
4 hours). Instead of detecting rate limits, heartbeat blindly nudges -
if the agent is stuck, it retries; if working, it ignores the nudge.

positional arguments:
  {start,stop,list,status,pause,resume}
    start               Start heartbeat for a worker
    stop                Stop heartbeat for a worker
    list                List all heartbeats
    status              Show heartbeat status
    pause               Pause heartbeat temporarily
    resume              Resume paused heartbeat

options:
  -h, --help            show this help message and exit

Quick Reference:
  swarm heartbeat start builder --interval 4h --expire 24h
  swarm heartbeat list
  swarm heartbeat stop builder

Common Patterns:
  # Nudge every 4 hours for overnight work (24h expiry)
  swarm heartbeat start agent --interval 4h --expire 24h

  # Custom message for specific recovery
  swarm heartbeat start agent --interval 4h --message "please continue where you left off"

  # Attach heartbeat at spawn time (see: swarm spawn --heartbeat)
  swarm spawn --name agent --tmux --heartbeat 4h --heartbeat-expire 24h -- claude
```

### Start Help Text

```
usage: swarm heartbeat start [-h] --interval INTERVAL [--expire EXPIRE]
                              [--message MESSAGE] [--force]
                              worker

Start periodic heartbeat nudges for a worker.

positional arguments:
  worker                Worker name to send heartbeats to

options:
  -h, --help            show this help message and exit
  --interval INTERVAL   Time between heartbeats (e.g., "4h", "30m", "3600s")
  --expire EXPIRE       Stop heartbeat after this duration (e.g., "24h")
                        Default: no expiration (runs until stopped)
  --message MESSAGE     Message to send on each beat
                        Default: "continue"
  --force               Replace existing heartbeat if one exists

Duration Format:
  Accepts: "4h", "30m", "90s", "3600" (seconds), or combinations "1h30m"

Examples:
  # Basic 4-hour heartbeat with 24-hour expiry
  swarm heartbeat start builder --interval 4h --expire 24h

  # Custom recovery message
  swarm heartbeat start builder --interval 4h \
    --message "If you hit a rate limit, please continue now"

  # Short interval for testing
  swarm heartbeat start builder --interval 5m --expire 1h

  # No expiration (manual stop required)
  swarm heartbeat start builder --interval 4h

Rate Limit Recovery:
  API rate limits often renew on fixed intervals. Set --interval to match
  your rate limit renewal period. The heartbeat will nudge the agent at
  each interval, prompting it to retry if it was blocked.

  Example: Claude API limits renew every 4 hours
    swarm heartbeat start agent --interval 4h --expire 24h

Safety:
  Always set --expire for unattended work to prevent infinite nudging.
  Heartbeats automatically stop when:
    - Expiration time is reached
    - Worker is killed
    - Manual stop via: swarm heartbeat stop <worker>
```

## Scenarios

### Scenario: Start heartbeat for running worker
- **Given**: A tmux worker "builder" is running
- **When**: `swarm heartbeat start builder --interval 4h --expire 24h`
- **Then**:
  - Heartbeat state created at `~/.swarm/heartbeats/builder.json`
  - Status shows "active"
  - First beat scheduled for 4 hours from now
  - Output: "Heartbeat started for builder (every 4h, expires in 24h)"

### Scenario: Heartbeat sends nudge at interval
- **Given**: Heartbeat active for "builder" with interval 4h
- **When**: 4 hours elapse
- **Then**:
  - Message sent to worker via `swarm send builder "continue"`
  - `last_beat_at` updated in state
  - `beat_count` incremented

### Scenario: Heartbeat expires
- **Given**: Heartbeat for "builder" with expire 24h, created 24h ago
- **When**: Next beat check occurs
- **Then**:
  - Status set to "expired"
  - No more beats sent
  - State file preserved for inspection

### Scenario: Worker killed while heartbeat active
- **Given**: Heartbeat active for "builder"
- **When**: `swarm kill builder`
- **Then**:
  - Heartbeat automatically stops
  - Status set to "stopped"
  - Output: "Heartbeat stopped (worker killed)"

### Scenario: Start heartbeat for non-tmux worker
- **Given**: A non-tmux worker "bg-job" is running
- **When**: `swarm heartbeat start bg-job --interval 4h`
- **Then**:
  - Error: "heartbeat requires tmux worker"
  - Exit code 1

## Edge Cases

- **Worker exits between beats**: Heartbeat detects worker not running, sets status to "stopped"
- **Multiple heartbeats for same worker**: Rejected unless `--force` used
- **Very short interval**: Allowed but warned (< 1 minute shows warning)
- **Zero or negative interval**: Rejected with error
- **Heartbeat for non-existent worker**: Rejected with error
- **System clock change**: Heartbeat uses monotonic time internally to avoid issues

## Recovery Procedures

### Heartbeat stuck/not sending
```bash
swarm heartbeat status <worker>    # Check status
swarm heartbeat stop <worker>      # Stop current
swarm heartbeat start <worker> ... # Restart
```

### Orphaned heartbeat (worker gone)
```bash
swarm heartbeat list               # Shows orphaned heartbeats
swarm heartbeat stop <worker>      # Clean up
```

## Implementation Notes

- Heartbeat monitor runs as a background thread/process
- Uses monotonic time to avoid clock drift issues
- State file locked during updates (same pattern as worker state)
- Heartbeat check happens every 30 seconds, but only sends at interval
- On startup, swarm checks for active heartbeats and resumes monitoring
