# Data Structures

## Overview

Swarm uses Python dataclasses to define the core data models that represent workers and their associated metadata. These structures are serialized to JSON for persistence in `~/.swarm/state.json` and deserialized when loading state. The three primary dataclasses are `Worker`, `TmuxInfo`, and `WorktreeInfo`.

## Dependencies

- **External**:
  - Python 3.10+ (dataclasses, type hints)
  - JSON serialization via `dataclasses.asdict()`
- **Internal**: None (foundational spec)

## Behavior

### TmuxInfo Dataclass

**Description**: Stores tmux session and window information for workers running in tmux mode.

**Schema**:
```python
@dataclass
class TmuxInfo:
    session: str      # Tmux session name
    window: str       # Tmux window name (matches worker name)
    socket: Optional[str] = None  # Custom socket path (for testing/isolation)
```

**JSON Representation**:
```json
{
  "session": "string",
  "window": "string",
  "socket": "string|null"
}
```

**Field Constraints**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session` | string | Yes | Tmux session name (hash-based by default) |
| `window` | string | Yes | Window name, same as worker name |
| `socket` | string | No | Custom socket for isolation (default: null) |

**Session Naming Convention**:
- Default session name: `swarm-<hash>` where hash is derived from `$USER` and repo path
- Custom session via `--session` flag overrides default
- Socket path enables complete tmux isolation for testing

### WorktreeInfo Dataclass

**Description**: Stores git worktree information for workers running in worktree isolation mode.

**Schema**:
```python
@dataclass
class WorktreeInfo:
    path: str       # Absolute path to worktree directory
    branch: str     # Git branch name
    base_repo: str  # Absolute path to base repository
```

**JSON Representation**:
```json
{
  "path": "string",
  "branch": "string",
  "base_repo": "string"
}
```

**Field Constraints**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | Yes | Absolute path to worktree directory |
| `branch` | string | Yes | Branch name (default: same as worker name) |
| `base_repo` | string | Yes | Absolute path to base git repository |

**Path Conventions**:
- Default worktree location: `<repo>-worktrees/<worker-name>/`
- Custom location via `--worktree-dir` flag
- Branch name default: worker name
- Custom branch via `--branch` flag

### Worker Dataclass

**Description**: The primary data structure representing a tracked worker process with all its metadata.

**Schema**:
```python
@dataclass
class Worker:
    name: str                           # Unique identifier
    status: str                         # "running" or "stopped"
    cmd: list[str]                      # Command and arguments
    started: str                        # ISO 8601 timestamp
    cwd: str                            # Working directory
    env: dict[str, str] = field(default_factory=dict)      # Environment variables
    tags: list[str] = field(default_factory=list)          # Tags for filtering
    tmux: Optional[TmuxInfo] = None     # Tmux info (if tmux mode)
    worktree: Optional[WorktreeInfo] = None  # Worktree info (if worktree mode)
    pid: Optional[int] = None           # Process ID (if non-tmux mode)
```

**JSON Representation**:
```json
{
  "name": "string",
  "status": "running|stopped",
  "cmd": ["array", "of", "strings"],
  "started": "2024-01-15T10:30:00.123456",
  "cwd": "/absolute/path",
  "env": {"KEY": "VALUE"},
  "tags": ["tag1", "tag2"],
  "tmux": {"session": "...", "window": "...", "socket": null} | null,
  "worktree": {"path": "...", "branch": "...", "base_repo": "..."} | null,
  "pid": 12345 | null
}
```

**Field Constraints**:
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | - | Unique worker identifier |
| `status` | string | Yes | - | "running" or "stopped" |
| `cmd` | list[str] | Yes | - | Command with arguments |
| `started` | string | Yes | - | ISO 8601 timestamp |
| `cwd` | string | Yes | - | Absolute working directory path |
| `env` | dict | No | `{}` | Environment variables |
| `tags` | list[str] | No | `[]` | Filter tags |
| `tmux` | TmuxInfo | No | `null` | Tmux metadata (mutually exclusive with pid) |
| `worktree` | WorktreeInfo | No | `null` | Git worktree metadata |
| `pid` | int | No | `null` | Process ID (non-tmux workers only) |

### Serialization Methods

**Description**: Worker provides bidirectional conversion between dataclass and dictionary for JSON persistence.

#### to_dict()

**Description**: Converts a Worker instance to a dictionary suitable for JSON serialization.

**Inputs**: None (uses instance fields)

**Outputs**:
- Dictionary with all Worker fields
- Nested TmuxInfo/WorktreeInfo converted via `dataclasses.asdict()`
- None values preserved for optional fields

**Behavior**:
```python
def to_dict(self) -> dict:
    d = {
        "name": self.name,
        "status": self.status,
        "cmd": self.cmd,
        "started": self.started,
        "cwd": self.cwd,
        "env": self.env,
        "tags": self.tags,
        "tmux": asdict(self.tmux) if self.tmux else None,
        "worktree": asdict(self.worktree) if self.worktree else None,
        "pid": self.pid,
    }
    return d
```

#### from_dict()

**Description**: Class method that creates a Worker instance from a dictionary.

**Inputs**:
- `d` (dict): Dictionary with worker data

**Outputs**:
- Worker instance with all fields populated

**Behavior**:
```python
@classmethod
def from_dict(cls, d: dict) -> "Worker":
    tmux = TmuxInfo(**d["tmux"]) if d.get("tmux") else None
    worktree = WorktreeInfo(**d["worktree"]) if d.get("worktree") else None
    return cls(
        name=d["name"],
        status=d["status"],
        cmd=d["cmd"],
        started=d["started"],
        cwd=d["cwd"],
        env=d.get("env", {}),
        tags=d.get("tags", []),
        tmux=tmux,
        worktree=worktree,
        pid=d.get("pid"),
    )
```

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Missing required field | Raises KeyError |
| Invalid nested structure | Raises TypeError |
| Extra fields in dict | Ignored (not passed to constructor) |

## Scenarios

### Scenario: Create worker with all fields
- **Given**: All worker attributes are provided
- **When**: Worker instance is created
- **Then**:
  - All fields populated correctly
  - `to_dict()` produces valid JSON-serializable dict
  - `from_dict(worker.to_dict())` produces equivalent Worker

### Scenario: Create worker with defaults
- **Given**: Only required fields provided
- **When**: Worker instance is created
- **Then**:
  - `env` defaults to empty dict `{}`
  - `tags` defaults to empty list `[]`
  - `tmux` defaults to `None`
  - `worktree` defaults to `None`
  - `pid` defaults to `None`

### Scenario: Serialize tmux worker
- **Given**: Worker has tmux=TmuxInfo(...) and pid=None
- **When**: `to_dict()` is called
- **Then**:
  - `tmux` field contains nested dict with session/window/socket
  - `pid` field is `null`

### Scenario: Serialize non-tmux worker
- **Given**: Worker has tmux=None and pid=12345
- **When**: `to_dict()` is called
- **Then**:
  - `tmux` field is `null`
  - `pid` field is 12345

### Scenario: Serialize worktree worker
- **Given**: Worker has worktree=WorktreeInfo(...)
- **When**: `to_dict()` is called
- **Then**:
  - `worktree` field contains nested dict with path/branch/base_repo

### Scenario: Deserialize with missing optional fields
- **Given**: JSON dict without `env`, `tags`, `tmux`, `worktree`, `pid` fields
- **When**: `Worker.from_dict()` is called
- **Then**:
  - Worker created successfully
  - Missing optional fields use defaults
  - No KeyError raised

### Scenario: Deserialize legacy state file
- **Given**: State file from older version missing `tags` field
- **When**: `Worker.from_dict()` is called
- **Then**:
  - Worker created with `tags=[]`
  - Backward compatibility maintained

## Edge Cases

- **Empty command**: `cmd=[]` is valid but will fail on spawn execution
- **Empty tags**: `tags=[]` is the default, filter `--tag` matches nothing
- **Empty env**: `env={}` is the default, no additional environment variables
- **Unicode in names**: Worker names can contain unicode but may cause issues with tmux
- **Long names**: No explicit length limit but filesystem path limits apply for worktrees
- **Special characters in names**: Forward slashes `/` will cause issues with tmux windows and branches
- **Timestamp precision**: Python datetime includes microseconds
- **Timezone**: Timestamps are local time, no timezone info stored

## Recovery Procedures

### Worker with corrupted nested structure

If TmuxInfo or WorktreeInfo has invalid structure:
```bash
# Edit state.json directly to fix or remove corrupted worker
vim ~/.swarm/state.json

# Or remove the worker entry and re-create
swarm clean <worker-name>
```

### Missing required fields in state

If state.json has workers missing required fields:
```bash
# Backup and reset
mv ~/.swarm/state.json ~/.swarm/state.json.backup
swarm ls  # Creates fresh empty state
```

### RalphState Dataclass

**Description**: Stores ralph loop state for autonomous agent iteration tracking. Persisted separately from worker state in `~/.swarm/ralph/<worker-name>/state.json`.

**Schema**:
```python
@dataclass
class RalphState:
    worker_name: str                      # Associated worker name
    prompt_file: str                      # Path to prompt file
    max_iterations: int                   # Maximum iteration count
    current_iteration: int = 0            # Current iteration number
    status: str = "running"               # running, paused, stopped, failed
    started: str = ""                     # ISO 8601 timestamp (loop start)
    last_iteration_started: str = ""      # ISO 8601 timestamp
    last_iteration_ended: str = ""        # ISO 8601 timestamp
    iteration_durations: list[int] = field(default_factory=list)  # Durations in seconds
    consecutive_failures: int = 0         # Consecutive failure count
    total_failures: int = 0               # Total failure count
    done_pattern: Optional[str] = None    # Regex to stop loop
    inactivity_timeout: int = 180         # Seconds before restart
    check_done_continuous: bool = False   # Check pattern during monitoring
    exit_reason: Optional[str] = None     # Why loop stopped
    prompt_baseline_content: str = ""     # Pane content after prompt injection (done-pattern self-match prevention)
```

**JSON Representation**:
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
  "inactivity_timeout": 180,
  "check_done_continuous": false,
  "exit_reason": "done_pattern|max_iterations|killed|failed|monitor_disconnected|null",
  "prompt_baseline_content": ""
}
```

**Field Constraints**:
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `worker_name` | string | Yes | - | Associated worker name |
| `prompt_file` | string | Yes | - | Absolute path to prompt file |
| `max_iterations` | int | Yes | - | Maximum number of iterations |
| `current_iteration` | int | No | 0 | Current iteration (0 = not started) |
| `status` | string | No | "running" | Loop status |
| `started` | string | No | "" | ISO 8601 timestamp when loop started |
| `last_iteration_started` | string | No | "" | When current iteration began |
| `last_iteration_ended` | string | No | "" | When last iteration completed |
| `iteration_durations` | list[int] | No | `[]` | Duration of each completed iteration in seconds |
| `consecutive_failures` | int | No | 0 | Failures without success |
| `total_failures` | int | No | 0 | Total failures across all iterations |
| `done_pattern` | string | No | null | Regex to match for loop completion |
| `inactivity_timeout` | int | No | 180 | Seconds of screen stability before restart |
| `check_done_continuous` | bool | No | false | Check done pattern during monitoring |
| `exit_reason` | string | No | null | Why the loop stopped |
| `prompt_baseline_content` | string | No | "" | Pane content after prompt injection (done-pattern self-match prevention) |

**Status Values**:
| Status | Description |
|--------|-------------|
| `running` | Loop is actively monitoring/iterating |
| `paused` | Loop paused via `swarm ralph pause` |
| `stopped` | Loop completed normally |
| `failed` | Loop stopped due to errors |

**Exit Reason Values**:
| Reason | Description |
|--------|-------------|
| `done_pattern` | Done pattern matched in agent output |
| `max_iterations` | Reached maximum iteration count |
| `killed` | Stopped via `swarm kill` command |
| `failed` | 5 consecutive failures |
| `monitor_disconnected` | Monitor process lost connection |
| `null` | Still running (no exit yet) |

**Iteration Duration Tracking**:
The `iteration_durations` field stores the duration of each completed iteration in seconds. This enables:
- ETA calculation: `avg_duration * remaining_iterations`
- Performance analysis: identify slow iterations
- Status display: "avg 5m12s/iter, ~48m remaining"

Duration is calculated as `last_iteration_ended - last_iteration_started` and appended after each successful iteration.

**State File Location**: `~/.swarm/ralph/<worker-name>/state.json`

**Iteration Log File**: `~/.swarm/ralph/<worker-name>/iterations.log`

Log format:
```
2024-01-15T10:30:00 [START] iteration 1/100
2024-01-15T10:35:42 [END] iteration 1 exit=0 duration=5m42s
2024-01-15T12:00:00 [DONE] loop complete after 47 iterations reason=done_pattern
```

### Scenario: Create ralph state with all fields
- **Given**: Ralph loop starting with full configuration
- **When**: RalphState instance is created
- **Then**:
  - All fields populated correctly
  - `to_dict()` produces valid JSON-serializable dict
  - `from_dict(state.to_dict())` produces equivalent RalphState

### Scenario: Track iteration durations for ETA
- **Given**: Ralph loop has completed 5 iterations
- **When**: Status is displayed
- **Then**:
  - `iteration_durations` contains 5 duration values
  - Average can be calculated: `sum(durations) / len(durations)`
  - ETA: `avg * (max_iterations - current_iteration)`

### Scenario: Record exit reason on loop completion
- **Given**: Ralph loop running, done pattern matched
- **When**: Loop stops
- **Then**:
  - `status` set to "stopped"
  - `exit_reason` set to "done_pattern"
  - `last_iteration_ended` set to current timestamp

### Scenario: Exit reason on kill command
- **Given**: Ralph loop running
- **When**: `swarm kill <name>` executed
- **Then**:
  - `status` set to "stopped"
  - `exit_reason` set to "killed"
  - Distinct from natural completion

### Scenario: Monitor disconnect exit reason
- **Given**: Ralph monitor process crashes while worker runs
- **When**: Monitor stops unexpectedly
- **Then**:
  - `exit_reason` set to "monitor_disconnected"
  - Worker may still be running in tmux
  - Status reflects actual state

## Implementation Notes

- **Dataclass immutability**: Worker dataclasses are mutable by default. State management functions modify workers in-place before saving.
- **No validation**: Dataclasses do not validate field values on construction. Invalid status strings or paths are accepted without error.
- **Timestamp format**: Uses `datetime.now().isoformat()` which produces ISO 8601 format with microseconds.
- **Dictionary spread**: `from_dict` uses `d.get()` for optional fields to provide defaults if missing.
- **Ralph state isolation**: RalphState is stored separately from Worker state to allow independent lifecycle management and avoid coupling.
- **Duration tracking**: Iteration durations are stored as integers (seconds) for simplicity and easy averaging.
