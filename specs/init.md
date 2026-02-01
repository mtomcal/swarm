# Init

## Overview

The `init` command initializes a project for use with swarm by adding agent instructions to a documentation file. It supports auto-discovery of existing files (AGENTS.md or CLAUDE.md) and is idempotent (won't duplicate instructions).

## Dependencies

- **External**: filesystem
- **Internal**: None

## Behavior

### Initialize Project

**Description**: Add swarm instructions to a project's agent documentation file.

**Inputs**:
- `--dry-run` (flag, optional): Show what would be done without making changes
- `--file` (string, optional): Target file, choices: "AGENTS.md" or "CLAUDE.md" (default: auto-detect)
- `--force` (flag, optional): Replace existing swarm section if present

**Outputs**:
- Success (new file): `Created <filename>`
- Success (append): `Added swarm instructions to <filename>`
- Success (force update): `Updated swarm instructions in <filename>`
- Idempotent (already exists): `swarm: <filename> already contains swarm instructions`
- Dry run: `Would create <filename>` or `Would append swarm instructions to <filename>`

**Side Effects**:
- Creates or modifies AGENTS.md or CLAUDE.md in current directory
- File content includes SWARM_INSTRUCTIONS constant with marker

**Error Conditions**:

| Condition | Behavior |
|-----------|----------|
| Invalid --file choice | argparse error: `invalid choice` |

## File Discovery Algorithm

When `--file` is not specified:

1. Check if `AGENTS.md` exists → use it
2. Else check if `CLAUDE.md` exists → use it
3. Else create `AGENTS.md` (default)

When `--file` is specified:
- Use the specified file regardless of what exists

## Idempotency Marker

The marker string `"Process Management (swarm)"` is used to detect existing instructions:

- If marker found in target file → report already exists, don't modify
- If marker found in other file during auto-discovery → report already exists
- With `--force` → replace existing section with new instructions

## Content Added

The `SWARM_INSTRUCTIONS` constant is added, which includes:
- Section header: `## Process Management (swarm)`
- Quick reference commands (spawn, ls, status, send, logs, kill)
- Worktree isolation explanation
- Power user tips

## Scenarios

### Scenario: Init creates AGENTS.md by default
- **Given**: Current directory has no AGENTS.md or CLAUDE.md
- **When**: `swarm init` is executed
- **Then**:
  - AGENTS.md created with swarm instructions
  - Output: `Created AGENTS.md`
  - File contains marker `Process Management (swarm)`

### Scenario: Init appends to existing AGENTS.md
- **Given**: AGENTS.md exists with content `# My Project\n\nSome content`
- **When**: `swarm init` is executed
- **Then**:
  - Swarm instructions appended to AGENTS.md
  - Original content preserved
  - Output: `Added swarm instructions to AGENTS.md`
  - Blank line separates original from new content

### Scenario: Init uses CLAUDE.md when AGENTS.md doesn't exist
- **Given**: Only CLAUDE.md exists (no AGENTS.md)
- **When**: `swarm init` is executed
- **Then**:
  - Swarm instructions appended to CLAUDE.md
  - AGENTS.md not created
  - Output: `Added swarm instructions to CLAUDE.md`

### Scenario: Init prefers AGENTS.md when both exist
- **Given**: Both AGENTS.md and CLAUDE.md exist (neither has marker)
- **When**: `swarm init` is executed
- **Then**:
  - Swarm instructions appended to AGENTS.md only
  - CLAUDE.md unchanged

### Scenario: Init --file overrides auto-discovery
- **Given**: AGENTS.md exists
- **When**: `swarm init --file CLAUDE.md` is executed
- **Then**:
  - CLAUDE.md created (or modified) with swarm instructions
  - AGENTS.md unchanged

### Scenario: Init detects existing instructions (idempotent)
- **Given**: AGENTS.md contains `## Process Management (swarm)` marker
- **When**: `swarm init` is executed
- **Then**:
  - File not modified
  - Output: `swarm: AGENTS.md already contains swarm instructions`
  - Exit code is 0

### Scenario: Init detects marker in CLAUDE.md during auto-discovery
- **Given**: AGENTS.md exists without marker, CLAUDE.md has marker
- **When**: `swarm init` is executed
- **Then**:
  - Neither file modified
  - Output: `swarm: CLAUDE.md already contains swarm instructions`

### Scenario: Init --force replaces existing section
- **Given**: AGENTS.md contains old swarm instructions with marker
- **When**: `swarm init --file AGENTS.md --force` is executed
- **Then**:
  - Existing swarm section replaced with new instructions
  - Other content preserved
  - Output: `Updated swarm instructions in AGENTS.md`

### Scenario: Init --dry-run shows what would happen
- **Given**: No AGENTS.md or CLAUDE.md exists
- **When**: `swarm init --dry-run` is executed
- **Then**:
  - No file created
  - Output: `Would create AGENTS.md with swarm agent instructions`
  - Exit code is 0

### Scenario: Init --dry-run with existing file
- **Given**: AGENTS.md exists without marker
- **When**: `swarm init --dry-run` is executed
- **Then**:
  - File not modified
  - Output: `Would append swarm instructions to AGENTS.md`

### Scenario: Init handles trailing newlines correctly
- **Given**: AGENTS.md exists without trailing newline: `# Project\nContent`
- **When**: `swarm init` is executed
- **Then**:
  - Proper blank line separator added
  - Result has normalized newlines (not triple newlines)

### Scenario: Init normalizes multiple trailing newlines
- **Given**: AGENTS.md exists with multiple trailing newlines: `# Project\n\n\n\n`
- **When**: `swarm init` is executed
- **Then**:
  - Trailing newlines normalized
  - Single blank line before swarm instructions

## Edge Cases

- **Empty existing file**: Swarm instructions added (empty + instructions)
- **File permissions**: Standard Python file operations; may fail if no write permission
- **Very large file**: Entire file read into memory for marker detection
- **Binary file**: Not handled; may corrupt file or detect false marker
- **Marker substring**: Partial matches could cause false positives (e.g., `Process Management (swarm-like)`)

## Recovery Procedures

### Accidentally overwrote content with --force
```bash
# If using git
git checkout -- AGENTS.md

# Otherwise, manually restore from backup
```

### Duplicate swarm sections
If somehow multiple sections exist:
1. Edit file manually to remove duplicates
2. Keep one `## Process Management (swarm)` section

### Wrong file modified
```bash
# Remove from wrong file
# Edit to remove swarm section

# Add to correct file
swarm init --file CLAUDE.md
```

## SWARM_INSTRUCTIONS Content

The instructions include:

```markdown
## Process Management (swarm)

Swarm manages parallel agent workers in isolated git worktrees via tmux.

### Quick Reference
- swarm spawn --name <id> --tmux --worktree -- <command>
- swarm ls
- swarm status <name>
- swarm send <name> "prompt"
- swarm logs <name>
- swarm kill <name> --rm-worktree

### Worktree Isolation
Each --worktree worker gets isolated git branch and directory.

### Power User Tips
- --ready-wait: Block until agent ready
- --tag <tag>: Tag workers for filtering
- --env KEY=VAL: Pass environment variables
- swarm send --all "msg": Broadcast to all workers
- swarm wait --all: Wait for all workers to complete

State stored in ~/.swarm/state.json. Logs in ~/.swarm/logs/.
```

## Implementation Notes

- `--force` uses regex to find and replace existing section: `r'(## Process Management \(swarm\).*?)(?=\n## |\Z)'`
- Newline normalization: `content.rstrip('\n') + "\n\n" + SWARM_INSTRUCTIONS + "\n"`
- File discovery checks both files during auto-discovery even if first file selected
- The marker check is a simple string `in` operation, not regex
