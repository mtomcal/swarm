# Spawn Command

## Overview

The `spawn` command creates new workers that execute commands either as background processes or within tmux windows. It supports git worktree isolation for parallel development, environment variable injection, tagging for organization, and optional ready-wait functionality for orchestration scripts. This is the primary entry point for starting managed processes in Swarm.

## Dependencies

- **External**:
  - tmux (required for `--tmux` mode)
  - git (required for `--worktree` mode)
  - Filesystem access for logs and state
- **Internal**:
  - `state-management.md` (worker registry persistence)
  - `worktree-isolation.md` (git worktree creation)
  - `ready-detection.md` (agent readiness detection)
  - `tmux-integration.md` (tmux window management)

## Behavior

### Command Parsing

**Description**: Parse and validate the command to execute.

**Inputs**:
- `cmd` (list[str], required): Command arguments after `--`

**Behavior**:
1. If first element is `"--"`, strip it
2. Validate command is not empty

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Empty command after parsing | Exit 1 with "swarm: error: no command provided (use -- command...)" |

### Transactional Spawn

**Description**: Ensure spawn operations are atomic - either fully complete or leave no orphaned state.

**Problem**: Spawn involves multiple steps (worktree creation, tmux window creation, state update) that can fail at any point. Without transaction handling, failures leave orphaned resources (worktrees, tmux windows, state entries) that block subsequent spawns.

**Behavior**:
1. Spawn operations proceed in order: validate → worktree → tmux/process → state
2. If any step fails after previous steps completed, perform rollback
3. Rollback removes resources in reverse order of creation
4. After successful rollback, report the original error

**Rollback Actions**:
| Failed Step | Rollback Action |
|-------------|-----------------|
| Worktree creation | (none - nothing created yet) |
| Tmux window creation | Remove worktree if created |
| Process spawn | Remove worktree if created |
| State update | Kill process/window, remove worktree |

**Error Conditions with Rollback**:
| Condition | Behavior |
|-----------|----------|
| Worktree creation fails | Exit 1 with original error, no cleanup needed |
| Tmux window fails after worktree | Remove worktree, exit 1 with original error |
| Process spawn fails after worktree | Remove worktree, exit 1 with original error |
| State update fails | Kill worker, remove worktree, exit 1 with original error |

**Rollback Output**:
When rollback occurs, swarm prints a warning before the error:
```
swarm: warning: spawn failed, cleaning up partial state
swarm: error: <original error message>
```

### Name Uniqueness Validation

**Description**: Ensure worker name is unique in the registry.

**Behavior**:
1. Load current state
2. Check if worker with same name exists

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Worker name already exists | Exit 1 with "swarm: error: worker '<name>' already exists" |

### Working Directory Resolution

**Description**: Determine the working directory for the worker.

**Inputs**:
- `--worktree` (flag, optional): Create git worktree
- `--worktree-dir` (str, optional): Custom worktree parent directory
- `--branch` (str, optional): Branch name for worktree (default: same as `--name`)
- `--cwd` (str, optional): Explicit working directory

**Priority Order**:
1. If `--worktree`: create worktree and use its path
2. Else if `--cwd`: use specified path
3. Else: use current working directory

### Environment Variable Parsing

**Description**: Parse KEY=VAL formatted environment variables.

**Inputs**:
- `--env` (str, repeatable): Environment variable in KEY=VAL format

**Behavior**:
1. For each `--env` value, split on first `=`
2. Build env dict with key-value pairs

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Missing `=` in env string | Exit 1 with "swarm: error: invalid env format '<value>' (expected KEY=VAL)" |

### Environment Propagation Chain

**Description**: How `--env KEY=VAL` propagates through the full execution chain.

When `--env KEY=VAL` is specified, the value propagates through:

```
swarm spawn --env KEY=VAL
  -> tmux new-window with env set via shell wrapper
    -> command receives KEY=VAL in its environment
      -> (if command is sandbox.sh) docker run -e KEY passes it into container
```

**Guarantee**: Any `--env` value set at spawn time is available in the worker process environment. For Docker sandbox workers, `sandbox.sh` must explicitly forward the env var via `docker run -e KEY`.

**Implementation**: tmux windows inherit the tmux server's environment at creation time. `swarm spawn` sets environment variables by wrapping the command in `env KEY=VAL <command>` to ensure reliable propagation regardless of tmux server state.

### Tmux Mode Spawn

**Description**: Create worker running in a tmux window.

**Inputs**:
- `--tmux` (flag, required): Enable tmux mode
- `--session` (str, optional): Tmux session name (default: hash-based)
- `--tmux-socket` (str, optional): Tmux socket name for isolation

**Behavior**:
1. Determine session name (specified or auto-generated hash)
2. Ensure tmux session exists (create if needed)
3. Create new window in session with worker name
4. Run command in window with specified cwd

**Side Effects**:
- Creates tmux session if it doesn't exist
- Creates tmux window named after worker
- Command runs in window

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| tmux not available | Exit 1 with "swarm: error: failed to create tmux window: <error>" |
| Window creation fails | Exit 1 with "swarm: error: failed to create tmux window: <error>" |

### Process Mode Spawn

**Description**: Create worker running as background process.

**Behavior**:
1. Merge provided env with current environment
2. Open stdout/stderr log files at `~/.swarm/logs/<name>.stdout.log` and `<name>.stderr.log`
3. Spawn process with `start_new_session=True` (detached)
4. Record PID

**Side Effects**:
- Creates log files in `~/.swarm/logs/`
- Process runs detached from terminal

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Process spawn fails | Exit 1 with "swarm: error: failed to spawn process: <error>" |

### Worker Record Creation

**Description**: Create Worker object and persist to state.

**Behavior**:
1. Create Worker with all collected information
2. Atomically add to state registry

**Worker Fields Set**:
- `name`: From `--name` argument
- `status`: Always "running"
- `cmd`: Parsed command list
- `started`: Current ISO 8601 timestamp
- `cwd`: Resolved working directory path
- `env`: Parsed environment variables dict
- `tags`: From `--tag` arguments (list)
- `tmux`: TmuxInfo if tmux mode, else null
- `worktree`: WorktreeInfo if worktree mode, else null
- `pid`: Process PID if process mode, else null

### Ready Wait Integration

**Description**: Optionally wait for agent CLI to be ready.

**Inputs**:
- `--ready-wait` (flag, optional): Enable ready detection
- `--ready-timeout` (int, optional): Timeout in seconds (default: 120)

**Behavior**:
1. If `--ready-wait` and worker is tmux mode:
2. Call ready detection with configured timeout
3. If timeout expires, print warning (worker still created)

**Outputs**:
- Warning to stderr if timeout: "swarm: warning: agent '<name>' did not become ready within <N>s"

**Note**: Ready detection only works with tmux mode (needs pane capture).

### Success Output

**Description**: Print confirmation message on successful spawn.

**Tmux Mode Output**:
```
spawned <name> (tmux: <session>:<window>)
```

**Process Mode Output**:
```
spawned <name> (pid: <pid>)
```

## CLI Arguments

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `--name` | str | Yes | - | Unique worker identifier |
| `--tmux` | flag | No | false | Run in tmux window |
| `--session` | str | No | hash-based | Tmux session name |
| `--tmux-socket` | str | No | null | Tmux socket for isolation |
| `--worktree` | flag | No | false | Create git worktree |
| `--branch` | str | No | same as name | Branch name for worktree |
| `--worktree-dir` | str | No | `<repo>-worktrees` | Custom worktree parent |
| `--tag` | str | No | [] | Tag (repeatable) |
| `--env` | str | No | [] | Env var KEY=VAL (repeatable) |
| `--cwd` | str | No | current dir | Working directory |
| `--ready-wait` | flag | No | false | Wait for agent ready |
| `--ready-timeout` | int | No | 120 | Ready wait timeout |
| `-- command...` | list | Yes | - | Command to execute |

## Scenarios

### Scenario: Spawn basic process
- **Given**: No existing workers
- **When**: `swarm spawn --name worker1 -- echo hello`
- **Then**:
  - Process spawned with PID
  - Output: "spawned worker1 (pid: <pid>)"
  - Worker added to state with status "running"
  - Logs created at `~/.swarm/logs/worker1.stdout.log`

### Scenario: Spawn in tmux
- **Given**: tmux available, no existing workers
- **When**: `swarm spawn --name agent1 --tmux -- claude`
- **Then**:
  - Tmux session created (if needed)
  - Window "agent1" created in session
  - Command "claude" runs in window
  - Output: "spawned agent1 (tmux: swarm:agent1)"
  - Worker stored with TmuxInfo

### Scenario: Spawn with worktree
- **Given**: In git repository `/home/user/myproject`
- **When**: `swarm spawn --name feature-x --tmux --worktree -- claude`
- **Then**:
  - Worktree created at `/home/user/myproject-worktrees/feature-x/`
  - Branch "feature-x" created
  - Command runs in worktree directory
  - Worker stored with WorktreeInfo

### Scenario: Spawn with custom branch
- **Given**: In git repository
- **When**: `swarm spawn --name w1 --worktree --branch my-feature --tmux -- claude`
- **Then**:
  - Worktree directory named "w1"
  - Branch named "my-feature" (not "w1")

### Scenario: Spawn with environment variables
- **Given**: No existing workers
- **When**: `swarm spawn --name env-test --env FOO=bar --env BAZ=qux -- printenv`
- **Then**:
  - Worker env contains {"FOO": "bar", "BAZ": "qux"}
  - Process environment includes these variables

### Scenario: Spawn with tags
- **Given**: No existing workers
- **When**: `swarm spawn --name tagged --tag important --tag test -- echo hi`
- **Then**:
  - Worker tags list is ["important", "test"]
  - Worker can be filtered with `swarm ls --tag important`

### Scenario: Spawn with ready-wait succeeds
- **Given**: No existing workers, tmux available
- **When**: `swarm spawn --name agent --tmux --ready-wait -- claude`
- **Then** (if agent becomes ready):
  - Spawn blocks until ready pattern detected
  - Returns after detecting ready indicator
  - No warning printed

### Scenario: Spawn with ready-wait timeout
- **Given**: No existing workers
- **When**: `swarm spawn --name slow --tmux --ready-wait --ready-timeout 2 -- sleep 300`
- **Then**:
  - Waits 2 seconds for ready pattern
  - Worker created regardless
  - Warning: "swarm: warning: agent 'slow' did not become ready within 2s"

### Scenario: Duplicate name rejected
- **Given**: Worker "dupe" already exists
- **When**: `swarm spawn --name dupe -- echo hi`
- **Then**:
  - Exit code 1
  - Error: "swarm: error: worker 'dupe' already exists"
  - No new worker created

### Scenario: Empty command rejected
- **Given**: No arguments after `--`
- **When**: `swarm spawn --name empty --`
- **Then**:
  - Exit code 1
  - Error: "swarm: error: no command provided (use -- command...)"

### Scenario: Invalid env format rejected
- **Given**: Malformed environment variable
- **When**: `swarm spawn --name bad --env INVALID -- echo hi`
- **Then**:
  - Exit code 1
  - Error: "swarm: error: invalid env format 'INVALID' (expected KEY=VAL)"

### Scenario: Not in git repo with worktree
- **Given**: Current directory is not a git repository
- **When**: `swarm spawn --name wt --worktree -- echo hi`
- **Then**:
  - Exit code 1
  - Error: "swarm: error: not in a git repository (required for --worktree)"

### Scenario: Rollback on tmux failure after worktree creation
- **Given**: In git repository, tmux unavailable or fails
- **When**: `swarm spawn --name worker --tmux --worktree -- echo hi`
- **Then**:
  - Worktree created at `/repo-worktrees/worker`
  - Tmux window creation fails
  - Rollback: worktree removed via `git worktree remove`
  - Warning: "swarm: warning: spawn failed, cleaning up partial state"
  - Exit code 1
  - Error: "swarm: error: failed to create tmux window: <original error>"
  - No worker entry in state

### Scenario: Rollback on state update failure
- **Given**: In git repository, state file locked or corrupted
- **When**: `swarm spawn --name worker --tmux --worktree -- echo hi`
- **Then**:
  - Worktree created
  - Tmux window created
  - State update fails
  - Rollback: tmux window killed, worktree removed
  - Warning: "swarm: warning: spawn failed, cleaning up partial state"
  - Exit code 1
  - Error: "swarm: error: failed to save state: <original error>"

### Scenario: Clean state after failed spawn attempt
- **Given**: Previous spawn failed mid-operation leaving no orphaned state (due to rollback)
- **When**: `swarm spawn --name worker --tmux --worktree -- echo hi`
- **Then**:
  - Spawn succeeds normally
  - No "worker already exists" error
  - Worker created fresh

### Scenario: Command with leading --
- **Given**: Command arguments include "--"
- **When**: `swarm spawn --name dash -- -- echo hello`
- **Then**:
  - Leading "--" stripped from command
  - Actual command is ["echo", "hello"]

## Edge Cases

- Worker name can contain alphanumeric, dash, underscore characters
- Tags are stored as list, can be empty
- Env dict can be empty
- Multiple `--env` flags accumulate into single dict
- Multiple `--tag` flags accumulate into list
- Session name defaults to hash-based unique value if not specified
- Tmux socket null by default (uses default server)
- Process mode stores PID, tmux mode stores null PID
- Tmux mode stores null for pid field
- `--cwd` is ignored when `--worktree` is specified
- `--ready-wait` has no effect in process mode (only tmux)
- Rollback removes resources in reverse order of creation to avoid dangling references
- Rollback is best-effort: if worktree removal fails during rollback, a warning is printed but the original error is still reported
- Transactional behavior applies to all spawn modes (tmux and process)
- If process spawn fails, only worktree rollback is needed (no tmux window to clean)

## Recovery Procedures

### Spawn fails mid-operation

Spawn uses transactional semantics with automatic rollback, so most failures clean up automatically. However, if rollback itself fails (e.g., due to permissions), manual cleanup may be needed:

```bash
# Check what was created
swarm ls --status all

# If worker exists but process/window doesn't
swarm clean <name>

# If worktree created but worker spawn failed (rollback failed)
git worktree remove /path/to/worktree
# Or force if needed
git worktree remove --force /path/to/worktree

# If state entry exists but no actual worker
swarm clean <name>
```

### Rollback failure leaves orphaned resources

If spawn fails and rollback also fails, you may see:
```
swarm: warning: spawn failed, cleaning up partial state
swarm: warning: rollback failed: could not remove worktree
swarm: error: <original error>
```

In this case:
```bash
# List orphaned worktrees
git worktree list

# Manually remove
git worktree remove --force /path/to/worktree

# Clean any state entry
swarm clean <name>
```

### Tmux session accumulates dead windows

```bash
# List windows in session
tmux list-windows -t swarm

# Kill specific window
tmux kill-window -t swarm:<window>
```

### Process orphaned (worker removed but process running)

```bash
# Find process by command
ps aux | grep <command>

# Kill by PID
kill <pid>
```

## Implementation Notes

- **Atomic name check**: Name uniqueness check and worker add should be atomic, but current implementation has small race window
- **Hash-based session**: Default session name uses hash to avoid conflicts between concurrent users
- **Detached processes**: Process mode uses `start_new_session=True` to fully detach from terminal
- **Log file handling**: Log files are opened before spawn, file handles passed to subprocess
- **Environment merge**: Worker env is merged with parent process env (worker env takes precedence)
- **Timestamp precision**: `started` uses full ISO 8601 with microseconds
- **Transactional spawn**: Spawn uses try/except with explicit rollback to ensure no orphaned state on failure
- **Rollback order**: Resources are cleaned in reverse creation order (state → process/window → worktree)
- **Rollback errors**: Rollback failures are logged as warnings but don't override the original error
- **No partial workers**: Worker is only added to state after all resources are successfully created
