# State Management

## Overview

Swarm maintains a persistent registry of all workers in a JSON file located at `~/.swarm/state.json`. This registry tracks worker metadata (name, status, command, timestamps) and enables commands like `ls`, `status`, and `kill` to operate on workers across CLI invocations. The state file uses fcntl-based exclusive locking to prevent race conditions during concurrent access.

## Dependencies

- **External**:
  - fcntl (Unix file locking - not available on Windows)
  - Filesystem access to `~/.swarm/` directory
- **Internal**: None (foundational spec)

## Behavior

### State File Location and Structure

**Description**: The state file is stored at `~/.swarm/state.json` with an accompanying lock file at `~/.swarm/state.lock`.

**JSON Schema**:
```json
{
  "workers": [
    {
      "name": "string (required, unique)",
      "status": "string (running|stopped)",
      "cmd": ["array", "of", "strings"],
      "started": "ISO 8601 timestamp",
      "cwd": "absolute path string",
      "env": {"KEY": "VALUE"},
      "tags": ["tag1", "tag2"],
      "tmux": {
        "session": "string",
        "window": "string",
        "socket": "string|null"
      } | null,
      "worktree": {
        "path": "string",
        "branch": "string",
        "base_repo": "string"
      } | null,
      "pid": "integer|null"
    }
  ]
}
```

### Directory Initialization

**Description**: Creates required directories if they don't exist.

**Behavior**:
- Creates `~/.swarm/` directory with parents
- Creates `~/.swarm/logs/` directory with parents
- Uses `exist_ok=True` to be idempotent

**Side Effects**:
- Creates directories on filesystem

### Exclusive File Locking

**Description**: All state file operations use fcntl exclusive locking to prevent race conditions.

**Mechanism**:
- Lock file: `~/.swarm/state.lock`
- Lock type: `fcntl.LOCK_EX` (exclusive, blocking)
- Lock release: `fcntl.LOCK_UN` in finally block

**Inputs**:
- None (uses hardcoded lock file path)

**Outputs**:
- Context manager yields lock file handle
- Lock is released when context exits

**Side Effects**:
- Creates lock file if it doesn't exist
- Blocks other processes attempting to acquire the lock

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Lock file directory doesn't exist | Creates via `ensure_dirs()` |
| Another process holds lock | Blocks until lock released |
| Exception during critical section | Lock still released via finally |

### Load State

**Description**: Reads worker registry from disk into memory.

**Behavior**:
1. Acquire exclusive lock
2. If state file exists, read and parse JSON
3. If state file doesn't exist, initialize empty workers list
4. Deserialize each worker dict into Worker dataclass

**Outputs**:
- `workers`: List of Worker objects

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| State file doesn't exist | Initialize with empty workers list |
| Invalid JSON | Raises JSONDecodeError |
| Missing required fields | Raises KeyError |

### Save State

**Description**: Persists worker registry from memory to disk.

**Behavior**:
1. Acquire exclusive lock
2. Serialize workers to dict format
3. Write JSON with indent=2 formatting
4. Release lock

**Important**: Save does NOT reload state before saving. The caller must ensure they have current state.

**Side Effects**:
- Overwrites `~/.swarm/state.json`

### Add Worker (Atomic)

**Description**: Atomically adds a worker to the registry.

**Behavior**:
1. Acquire exclusive lock
2. Reload state from disk (get latest)
3. Append new worker
4. Save immediately
5. Release lock

**Inputs**:
- `worker` (Worker): Worker object to add

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Worker name already exists | Not checked here - caller responsibility |

### Remove Worker (Atomic)

**Description**: Atomically removes a worker from the registry by name.

**Behavior**:
1. Acquire exclusive lock
2. Reload state from disk
3. Filter out worker with matching name
4. Save immediately
5. Release lock

**Inputs**:
- `name` (str): Worker name to remove

**Side Effects**:
- Worker removed from state file

### Update Worker (Atomic)

**Description**: Atomically updates a worker's fields.

**Behavior**:
1. Acquire exclusive lock
2. Reload state from disk
3. Find worker by name
4. Update specified fields via setattr
5. Save immediately
6. Release lock

**Inputs**:
- `name` (str): Worker name
- `**kwargs`: Fields to update (e.g., `status="stopped"`)

### Get Worker

**Description**: Retrieves a worker by name from current in-memory state.

**Inputs**:
- `name` (str): Worker name to find

**Outputs**:
- `Worker | None`: Worker object if found, None otherwise

**Note**: This reads from in-memory state, not disk. For atomic read, create a new State() instance.

## Scenarios

### Scenario: Basic state persistence
- **Given**: No existing state file
- **When**: `State()` is instantiated
- **Then**:
  - `~/.swarm/` directory is created
  - `workers` list is empty
  - No state.json file created until save() called

### Scenario: Load existing state
- **Given**: state.json exists with 2 workers
- **When**: `State()` is instantiated
- **Then**:
  - Both workers loaded into `workers` list
  - Worker objects have all fields populated

### Scenario: Concurrent spawn operations preserve all workers
- **Given**: 5 processes simultaneously call `state.add_worker()`
- **When**: All operations complete
- **Then**:
  - state.json contains all 5 workers
  - No workers lost due to race conditions

### Scenario: Lock released after exception
- **Given**: Process A holds exclusive lock
- **When**: Exception raised during critical section
- **Then**:
  - Lock is released via finally block
  - Process B can acquire lock immediately

### Scenario: Blocking behavior during contention
- **Given**: Process A holds exclusive lock
- **When**: Process B attempts to acquire lock
- **Then**:
  - Process B blocks (waits)
  - Process B proceeds only after A releases lock

## Edge Cases

- Empty workers list serializes as `{"workers": []}`
- Worker with all optional fields null/empty still serializes correctly
- Tags can be empty list
- Env can be empty dict
- tmux and worktree can be null
- pid can be null (for tmux workers)
- Timestamp format: ISO 8601 (e.g., `2024-01-15T10:30:00.123456`)

## Recovery Procedures

### Corrupted state.json

If state.json contains invalid JSON:
```bash
# Backup corrupted file
mv ~/.swarm/state.json ~/.swarm/state.json.corrupted

# Reinitialize (will create empty state on next swarm command)
swarm ls
```

### Orphaned lock file

Lock files are safe to delete if no swarm process is running:
```bash
rm ~/.swarm/state.lock
```

### State out of sync with reality

If state.json shows workers that don't exist:
```bash
# Refresh all statuses and clean stopped workers
swarm ls  # This refreshes status
swarm clean --all
```

## Implementation Notes

- **Locking granularity**: Lock is held for entire load-modify-save cycle, not just individual operations. This ensures atomicity but may reduce concurrency under heavy load.
- **No write-ahead log**: Updates are not crash-safe. A crash during write could corrupt state.json. Consider backup before operations in production.
- **Memory model**: State() loads entire registry into memory. For very large registries (1000+ workers), consider pagination.
