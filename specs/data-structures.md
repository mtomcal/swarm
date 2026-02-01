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

## Implementation Notes

- **Dataclass immutability**: Worker dataclasses are mutable by default. State management functions modify workers in-place before saving.
- **No validation**: Dataclasses do not validate field values on construction. Invalid status strings or paths are accepted without error.
- **Timestamp format**: Uses `datetime.now().isoformat()` which produces ISO 8601 format with microseconds.
- **Dictionary spread**: `from_dict` uses `d.get()` for optional fields to provide defaults if missing.
