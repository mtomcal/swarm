# Worktree Isolation

## Overview

Swarm provides git worktree integration via `--worktree` flag, enabling each worker to operate in an isolated copy of the repository with its own branch. This prevents workers from conflicting when making concurrent changes to the same codebase. The feature includes protection against accidental data loss by refusing to remove worktrees with uncommitted changes.

## Dependencies

- **External**:
  - git (for worktree operations)
  - Filesystem access
- **Internal**:
  - `state-management.md` (stores WorktreeInfo in worker record)

## Behavior

### Get Git Root

**Description**: Determines the root directory of the current git repository.

**Inputs**: None (uses current working directory context)

**Outputs**:
- `Path`: Absolute path to git repository root

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Not in git repository | Raises `subprocess.CalledProcessError` |

### Create Worktree

**Description**: Creates a new git worktree at the specified path with the given branch name.

**Inputs**:
- `path` (Path, required): Target directory for worktree
- `branch` (str, required): Branch name for the worktree

**Behavior**:
1. Create parent directory if needed
2. Try `git worktree add -b <branch> <path>` (create new branch)
3. If fails (branch exists), try `git worktree add <path> <branch>` (use existing branch)

**Outputs**:
- Success: Worktree created at path
- Failure: Raises `subprocess.CalledProcessError`

**Side Effects**:
- Creates new directory at `<path>`
- Creates or checks out branch `<branch>`
- Adds worktree to git's worktree registry

### Worktree Location Convention

**Description**: Default worktree location is a sibling directory to the git repository.

**Algorithm**:
1. If `--worktree-dir` specified: use that path
2. Otherwise: `<repo-parent>/<repo-name>-worktrees/<worker-name>/`

**Example**:
```
/home/user/code/myproject/           # Original repo
/home/user/code/myproject-worktrees/ # Worktrees container
/home/user/code/myproject-worktrees/feature-auth/   # Worker worktree
```

### Check Worktree Dirty

**Description**: Determines if a worktree has uncommitted changes.

**Inputs**:
- `path` (Path, required): Path to worktree directory

**Outputs**:
- `True`: Worktree has uncommitted changes
- `False`: Worktree is clean

**Detection Criteria** (any triggers dirty):
- Staged changes (files in index)
- Unstaged changes (modified tracked files)
- Untracked files

**Implementation**:
```bash
git -C <path> status --porcelain
# Any output = dirty
```

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Path doesn't exist | Returns `False` |
| git command fails | Returns `True` (fail-safe) |

### Remove Worktree

**Description**: Removes a git worktree with protection against data loss.

**Inputs**:
- `path` (Path, required): Path to worktree
- `force` (bool, optional): If True, remove even with uncommitted changes (default: False)

**Outputs**:
- `(True, "")`: Success
- `(False, message)`: Failure with description

**Behavior**:
1. If path doesn't exist: return success
2. If not force and worktree is dirty: return failure with change count
3. Run `git worktree remove --force <path>`
4. Return success

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Path doesn't exist | Success (idempotent) |
| Dirty without force | `(False, "worktree has N uncommitted change(s)")` |
| git remove fails | Raises `subprocess.CalledProcessError` |

### Spawn with Worktree

**Description**: Creates worker with isolated git worktree.

**Inputs**:
- `--worktree` (flag): Enable worktree isolation
- `--branch` (str, optional): Branch name (default: same as worker name)
- `--worktree-dir` (str, optional): Custom worktree parent directory

**Behavior**:
1. Get git root of current repository
2. Compute worktree path (default or custom)
3. Create worktree with branch
4. Set worker's cwd to worktree path
5. Store WorktreeInfo in worker record

**WorktreeInfo Schema**:
```json
{
  "path": "/absolute/path/to/worktree",
  "branch": "branch-name",
  "base_repo": "/absolute/path/to/original/repo"
}
```

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Not in git repository | Exit 1 with error message |
| Worktree creation fails | Exit 1 with error message |

### Kill with Worktree Removal

**Description**: The `--rm-worktree` flag attempts to remove the worktree after killing worker.

**Inputs**:
- `--rm-worktree` (flag): Remove worktree after kill
- `--force-dirty` (flag): Force removal even with uncommitted changes

**Behavior**:
1. Kill the worker process
2. If `--rm-worktree` and worker has worktree:
   a. Call `remove_worktree(path, force=force_dirty)`
   b. If fails: print warning, preserve worktree
3. Update worker status to "stopped"

**Output Messages**:
- Success: `"killed <name>"`
- Dirty worktree preserved: `"swarm: warning: cannot remove worktree for '<name>': <msg>"`

### Clean with Worktree Removal

**Description**: Clean command removes worktrees for stopped workers.

**Inputs**:
- `--rm-worktree` (flag, default: True): Remove worktree during clean
- `--force-dirty` (flag): Force removal even with uncommitted changes

**Behavior**:
1. Verify worker is stopped (refuse to clean running)
2. If worktree exists and `--rm-worktree`:
   a. Call `remove_worktree(path, force=force_dirty)`
   b. If fails: print warning, preserve worktree, continue cleanup
3. Remove log files
4. Remove worker from state

## Scenarios

### Scenario: Spawn creates worktree and branch
- **Given**: User is in git repository `/home/user/myproject`
- **When**: `swarm spawn --name feature-auth --worktree --tmux -- claude`
- **Then**:
  - Worktree created at `/home/user/myproject-worktrees/feature-auth/`
  - Branch `feature-auth` created (or checked out if exists)
  - Worker's cwd set to worktree path
  - Worker record contains WorktreeInfo

### Scenario: Spawn with custom branch name
- **Given**: User wants branch name different from worker name
- **When**: `swarm spawn --name worker1 --worktree --branch my-feature -- claude`
- **Then**:
  - Worktree created at `.../worker1/`
  - Branch name is `my-feature`

### Scenario: Kill refuses dirty worktree
- **Given**: Worker with worktree containing uncommitted changes
- **When**: `swarm kill worker1 --rm-worktree`
- **Then**:
  - Worker process killed
  - Exit code 0
  - Warning printed: "cannot remove worktree... uncommitted change(s)"
  - Worktree directory preserved
  - Worker removed from state (but worktree remains)

### Scenario: Kill with force-dirty removes worktree
- **Given**: Worker with worktree containing uncommitted changes
- **When**: `swarm kill worker1 --rm-worktree --force-dirty`
- **Then**:
  - Worker process killed
  - Worktree removed despite uncommitted changes
  - All changes in worktree are lost

### Scenario: Clean preserves dirty worktree
- **Given**: Stopped worker with dirty worktree
- **When**: `swarm clean worker1`
- **Then**:
  - Warning printed about preserving worktree
  - Worker removed from state
  - Log files removed
  - Worktree directory preserved with all changes

### Scenario: Worktree detection - unstaged changes
- **Given**: Worktree with modified tracked file
- **When**: `worktree_is_dirty(path)` called
- **Then**: Returns `True`

### Scenario: Worktree detection - staged changes
- **Given**: Worktree with staged file (git add run)
- **When**: `worktree_is_dirty(path)` called
- **Then**: Returns `True`

### Scenario: Worktree detection - untracked files
- **Given**: Worktree with new untracked file
- **When**: `worktree_is_dirty(path)` called
- **Then**: Returns `True`

### Scenario: Worktree detection - clean state
- **Given**: Worktree with all changes committed
- **When**: `worktree_is_dirty(path)` called
- **Then**: Returns `False`

### Scenario: Remove nonexistent worktree
- **Given**: Path that doesn't exist
- **When**: `remove_worktree(nonexistent_path)`
- **Then**: Returns `(True, "")` - success (idempotent)

## Edge Cases

- Worker name with special characters may cause branch name issues
- Branch name must be valid git ref (no spaces, certain special chars)
- Worktree path must be outside the main repository
- If branch already exists, worktree uses it rather than creating new
- Worktree with no commits (brand new branch) is considered clean
- Empty untracked directories don't trigger dirty detection
- `.gitignore`d files don't trigger dirty detection

## Recovery Procedures

### Orphaned worktree (worker deleted, worktree remains)
```bash
# List git worktrees
git worktree list

# Remove manually
git worktree remove /path/to/worktree
# Or if dirty:
git worktree remove --force /path/to/worktree
```

### Worktree with valuable uncommitted changes
```bash
# Navigate to worktree
cd /path/to/myproject-worktrees/worker-name

# Commit changes
git add .
git commit -m "WIP: description"
git push origin branch-name

# Now safe to remove
swarm clean worker-name
```

### Corrupted worktree state
```bash
# Prune stale worktree entries
git worktree prune

# Re-check list
git worktree list
```

### Worktree on missing branch
If the branch was deleted remotely:
```bash
# Inside worktree
git checkout -b new-branch-name

# Push to recreate
git push origin new-branch-name
```

## Implementation Notes

- **Worktree vs Clone**: Worktrees share object database with main repo, making them faster and smaller than full clones
- **Branch requirement**: Each worktree must have its own branch (git constraint)
- **Atomic cleanup**: Worktree removal happens after kill, so interrupted cleanup leaves worktree intact
- **Fail-safe dirty detection**: If `git status` fails, assume dirty to prevent accidental data loss
- **Relative paths**: WorktreeInfo stores absolute paths to avoid ambiguity
