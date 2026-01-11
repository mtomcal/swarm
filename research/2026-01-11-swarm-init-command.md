---
date: 2026-01-11T10:00:00-08:00
researcher: Claude
topic: "Adding swarm init command for CLAUDE.md/AGENTS.md instructions"
tags: [research, codebase, cli, initialization, agent-instructions]
status: complete
---

# Research: Adding swarm init Command for CLAUDE.md/AGENTS.md Instructions

**Date**: 2026-01-11
**Researcher**: Claude

## Research Question
How can we add a `swarm init` command to add instructions to CLAUDE.md or AGENTS.md, similar to how beads works?

## Summary

The beads project provides an excellent reference implementation for adding agent instruction files. The approach involves:
1. An `onboard` command that displays instructions to manually add
2. An `init` command that automatically creates/updates AGENTS.md
3. A separation between minimal static instructions (in AGENTS.md) and dynamic context (via `bd prime`)

For swarm, we can implement a simpler `swarm init` command that:
- Creates or updates CLAUDE.md/AGENTS.md with swarm-specific instructions
- Is idempotent (safe to run multiple times)
- Follows the beads pattern of keeping instructions lean

## Detailed Findings

### How Beads Implements This

#### 1. Two-Command Architecture

Beads uses two related commands:

**`bd onboard`** (`/home/mtomcal/code/beads/cmd/bd/onboard.go:106-130`)
- Display-only command showing what to add to AGENTS.md
- Does NOT modify any files
- Provides copy-paste content with clear markers

**`bd init`** (calls `init_agent.go`)
- Actually creates/updates files automatically
- Called as part of the overall initialization flow

#### 2. Content Generation Pattern (`init_agent.go:56-114`)

The `updateAgentFile()` function handles both creation and updates:

```go
// If file doesn't exist - create with full template
if os.IsNotExist(err) {
    newContent := fmt.Sprintf(`# Agent Instructions...`, landingThePlaneSection)
    os.WriteFile(filename, []byte(newContent), 0644)
    return nil
}

// If file exists - check if section already present (idempotent)
if strings.Contains(string(content), "Landing the Plane") {
    return nil  // Already has it, skip
}

// Append section to existing file
newContent := string(content) + landingThePlaneSection
os.WriteFile(filename, []byte(newContent), 0644)
```

#### 3. Content Structure

Beads generates a minimal AGENTS.md (`/home/mtomcal/code/beads/cmd/bd/AGENTS.md`):
- Header: "Agent Instructions"
- Pointer to onboarding: `Run 'bd onboard' to get started`
- Quick reference: 5 essential commands
- Landing the Plane section: Session completion workflow

### Current Swarm CLI Structure

**Entry Point**: `/home/mtomcal/code/swarm/swarm.py:560-685`

**Command Registration Pattern**:
```python
# In main():
subparsers = parser.add_subparsers(dest="command", required=True)

# Add new command
init_p = subparsers.add_parser("init", help="Initialize swarm in a project")
init_p.add_argument("--force", action="store_true", help="Overwrite existing")

# Dispatch
if args.command == "init":
    cmd_init(args)
```

**Existing Commands**: spawn, ls, status, send, interrupt, eof, attach, logs, kill, wait, clean, respawn

### Proposed Swarm Instructions Content

Based on swarm's functionality, the AGENTS.md/CLAUDE.md content should include:

```markdown
## Process Management

This project uses **swarm** for agent process management.

**Quick Reference:**
```bash
swarm spawn --name <id> --tmux -- <command>  # Start worker
swarm ls                                       # List workers
swarm status <name>                           # Check status
swarm send <name> "text"                      # Send input
swarm logs <name>                             # View output
swarm kill <name>                             # Stop worker
swarm attach <name>                           # Connect to tmux
```

**Worktree Isolation:**
```bash
swarm spawn --name task1 --worktree --tmux -- claude
```
Creates isolated git worktree for parallel work.

**Tips:**
- Use `--ready-wait` to wait for agent prompt before sending
- Use `--tag` for filtering workers by purpose
- Use `swarm clean --all` to remove stopped workers
```

### Implementation Plan

#### Option A: Simple `init` Command (Recommended)

Add a new `cmd_init()` function that:
1. Checks if CLAUDE.md or AGENTS.md exists
2. Creates new file or appends section if not present
3. Uses idempotent marker to avoid duplicates

**Pros**: Simple, one command, follows beads pattern
**Cons**: Less flexible

#### Option B: Separate `init` and `onboard` Commands

Like beads, provide:
- `swarm init` - automatically adds to file
- `swarm onboard` - displays content for manual copy

**Pros**: More flexible, matches beads exactly
**Cons**: More code, users might be confused about which to use

#### Option C: Unified Setup with `--dry-run`

Single `swarm init` command with:
- Default: modifies files
- `--dry-run`: shows what would be added
- `--force`: overwrites existing section

**Pros**: Single command, flexible
**Cons**: More complex argument parsing

## Code References

### Beads Reference Implementation
- `/home/mtomcal/code/beads/cmd/bd/onboard.go:106-130` - onboard command definition
- `/home/mtomcal/code/beads/cmd/bd/onboard.go:26-37` - agentsContent template
- `/home/mtomcal/code/beads/cmd/bd/init_agent.go:15-41` - landingThePlaneSection constant
- `/home/mtomcal/code/beads/cmd/bd/init_agent.go:56-114` - updateAgentFile() implementation
- `/home/mtomcal/code/beads/cmd/bd/AGENTS.md:1-40` - Example output template

### Swarm Integration Points
- `/home/mtomcal/code/swarm/swarm.py:560-567` - Argument parser setup
- `/home/mtomcal/code/swarm/swarm.py:568-657` - Subparser definitions
- `/home/mtomcal/code/swarm/swarm.py:660-684` - Command dispatch
- `/home/mtomcal/code/swarm/CLAUDE.md` - Current file (has beads content)

## Architecture Insights

### Key Design Patterns from Beads

1. **Idempotent Operations**: Always check if content exists before adding
2. **Marker-Based Detection**: Use unique strings ("swarm init" or similar) to detect existing sections
3. **Minimal Static Content**: Keep AGENTS.md lean, point to commands for dynamic info
4. **Graceful Handling**: Non-fatal errors for file operations

### Recommended File Priority

Based on web research and current standards:
1. Check for AGENTS.md first (emerging standard)
2. Fall back to CLAUDE.md (Claude-specific)
3. Create AGENTS.md by default (vendor-neutral)

### Content Philosophy

Per [AGENTS.md best practices](https://agents.md/):
- Keep instructions minimal and focused
- Don't duplicate what linters/formatters do
- Point to other files rather than embedding everything
- Update iteratively based on effectiveness

## Open Questions

1. **Which file should be primary?** AGENTS.md (vendor-neutral standard) or CLAUDE.md (Claude-specific)?
   - Recommendation: Support both, default to AGENTS.md

2. **Should we integrate with beads?** The current CLAUDE.md already has beads instructions
   - Recommendation: Add swarm section alongside, not replacing beads

3. **Should we support `--stealth` mode like beads?** (Uses .git/info/exclude instead of .gitignore)
   - Recommendation: Not needed for v1, swarm doesn't create many files

4. **What about `.claude/settings.local.json`?** Beads uses this for auto-injection
   - Recommendation: Consider for v2, not essential for basic init

## Implementation Skeleton

```python
# Constants
SWARM_INSTRUCTIONS = '''
## Process Management (swarm)

This project uses **swarm** for agent process management.

**Quick Reference:**
```bash
swarm spawn --name <id> --tmux -- <command>  # Start worker
swarm ls                                       # List workers
swarm status <name>                           # Check status
swarm send <name> "text"                      # Send input
swarm logs <name>                             # View output
swarm kill <name>                             # Stop worker
```

For worktree isolation: `swarm spawn --name task1 --worktree --tmux -- claude`
'''

def cmd_init(args) -> None:
    """Initialize swarm instructions in project."""
    # Try AGENTS.md first, then CLAUDE.md
    for filename in ["AGENTS.md", "CLAUDE.md"]:
        path = Path(filename)
        if path.exists():
            content = path.read_text()
            if "Process Management (swarm)" in content:
                print(f"swarm: {filename} already has swarm instructions")
                return
            # Append section
            if not content.endswith("\n"):
                content += "\n"
            content += SWARM_INSTRUCTIONS
            path.write_text(content)
            print(f"swarm: added instructions to {filename}")
            return

    # No existing file, create AGENTS.md
    Path("AGENTS.md").write_text(f"# Agent Instructions\n{SWARM_INSTRUCTIONS}")
    print("swarm: created AGENTS.md with swarm instructions")
```

## Sources

- [AGENTS.md - A simple, open format for guiding coding agents](https://agents.md/)
- [Writing a good CLAUDE.md | HumanLayer Blog](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
- [Claude Code: Best practices for agentic coding](https://www.anthropic.com/engineering/claude-code-best-practices)
- [GitHub - agentsmd/agents.md](https://github.com/agentsmd/agents.md)
- [Improve your AI code output with AGENTS.md](https://www.builder.io/blog/agents-md)
