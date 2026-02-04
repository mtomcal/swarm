# Implementation Plan: Heartbeat, Workflow, and CLI Help Improvements

**Created**: 2026-02-04
**Status**: Not Started
**Goal**: Add heartbeat system for rate limit recovery, workflow orchestration for multi-stage pipelines, and comprehensive CLI help across all commands

---

## Problem Statement

1. **Rate limits interrupt work**: When agents hit API rate limits during overnight/unattended work, they sit idle until manually restarted
2. **No multi-stage orchestration**: Complex tasks (plan → build → validate) require manual handoffs between stages
3. **Inconsistent CLI help**: Most commands have minimal help text; agents struggle to learn swarm from `-h` alone
4. **No scheduling**: Can't queue work to start when rate limits renew (e.g., at 2am)

---

## Solution Overview

| Feature | Description | Spec |
|---------|-------------|------|
| **Heartbeat** | Periodic nudges to workers on configurable interval with expiration | `specs/heartbeat.md` |
| **Workflow** | Multi-stage pipelines defined in YAML with scheduling and failure handling | `specs/workflow.md` |
| **CLI Help** | Comprehensive help text with examples for all commands | `specs/cli-help-standards.md` |

---

## Tasks

### Phase 1: CLI Help Improvements (Existing Commands)

Improve help text for all existing commands to match the quality of `ralph spawn --help`.

- [x] **1.1 Enhance `swarm --help` (root command)**
  - Add overview of swarm purpose
  - Add quick start example
  - Group commands by category

- [x] **1.2 Enhance `swarm spawn --help`**
  - Add description paragraph explaining worker types
  - Add 4+ examples (basic, worktree, env vars, ready-wait)
  - Add "Common Patterns" section
  - Document all flag defaults explicitly

- [x] **1.3 Enhance `swarm ls --help`**
  - Add description explaining output formats
  - Add examples for each format (table, json, names)
  - Add filter examples (--status, --tag)

- [ ] **1.4 Enhance `swarm status --help`**
  - Add description of status output fields
  - Add examples showing different worker states

- [ ] **1.5 Enhance `swarm send --help`**
  - Add description explaining tmux requirement
  - Add examples: single worker, broadcast, no-enter
  - Add "Intervention Patterns" section

- [ ] **1.6 Enhance `swarm kill --help`**
  - Add description with safety warnings
  - Add examples: basic, with worktree, force-dirty
  - Add "Warnings" section about data loss
  - Add recovery commands for mistakes

- [ ] **1.7 Enhance `swarm logs --help`**
  - Add description of log storage
  - Add examples: basic, follow, tail

- [ ] **1.8 Enhance `swarm wait --help`**
  - Add description of exit code propagation
  - Add examples: basic, with timeout, exit code check

- [ ] **1.9 Enhance `swarm clean --help`**
  - Add description of what gets cleaned
  - Add "Warnings" section
  - Add examples with filters

- [ ] **1.10 Enhance `swarm respawn --help`**
  - Add description of what's preserved
  - Add examples showing different scenarios

- [ ] **1.11 Enhance `swarm interrupt --help`**
  - Add description of Ctrl-C behavior
  - Add examples and use cases

- [ ] **1.12 Enhance `swarm eof --help`**
  - Add description of Ctrl-D behavior
  - Add examples and use cases

- [ ] **1.13 Enhance `swarm attach --help`**
  - Add description of tmux attachment
  - Add detach instructions
  - Add examples

- [ ] **1.14 Enhance `swarm init --help`**
  - Add description of what gets initialized
  - Add examples

### Phase 2: Heartbeat Implementation

- [ ] **2.1 Add HeartbeatState dataclass**
  - Fields: worker_name, interval_seconds, expire_at, message, created_at, last_beat_at, beat_count, status
  - Add to data-structures section of swarm.py

- [ ] **2.2 Add heartbeat state persistence**
  - Storage: `~/.swarm/heartbeats/<worker>.json`
  - Load/save functions with file locking
  - Status enum: active, paused, expired, stopped

- [ ] **2.3 Implement `swarm heartbeat start`**
  - Parse --interval (duration string)
  - Parse --expire (duration string, optional)
  - Parse --message (string, default "continue")
  - Parse --force (replace existing)
  - Validate worker exists and is tmux
  - Create heartbeat state
  - Start background monitor thread

- [ ] **2.4 Implement heartbeat monitor thread**
  - Check interval using monotonic time
  - Send message via `tmux send-keys`
  - Update last_beat_at and beat_count
  - Check expiration
  - Detect worker death and auto-stop

- [ ] **2.5 Implement `swarm heartbeat stop`**
  - Set status to stopped
  - Terminate monitor thread

- [ ] **2.6 Implement `swarm heartbeat list`**
  - Table output: worker, interval, next beat, expires, status, beats
  - JSON output option

- [ ] **2.7 Implement `swarm heartbeat status`**
  - Detailed output for single heartbeat

- [ ] **2.8 Implement `swarm heartbeat pause/resume`**
  - Set status to paused/active

- [ ] **2.9 Add --heartbeat flag to spawn**
  - Parse --heartbeat (duration)
  - Parse --heartbeat-expire (duration)
  - Parse --heartbeat-message (string)
  - Auto-start heartbeat after spawn

- [ ] **2.10 Add heartbeat cleanup on kill**
  - When worker killed, stop associated heartbeat

- [ ] **2.11 Add comprehensive heartbeat help text**
  - Follow cli-help-standards.md
  - Include duration format docs
  - Include rate limit recovery explanation

- [ ] **2.12 Add heartbeat unit tests**
  - Test state persistence
  - Test interval calculation
  - Test expiration
  - Test worker death detection

### Phase 3: Workflow Implementation

- [ ] **3.1 Add WorkflowState and StageState dataclasses**
  - WorkflowState: name, status, current_stage, stages dict, timestamps
  - StageState: status, worker_name, attempts, timestamps, exit_reason

- [ ] **3.2 Implement YAML parser for workflow definitions**
  - Parse all fields from workflow.md spec
  - Validate required fields
  - Validate stage types
  - Validate on-failure values
  - Handle both prompt and prompt-file

- [ ] **3.3 Add workflow state persistence**
  - Storage: `~/.swarm/workflows/<name>/state.json`
  - Copy workflow YAML to state directory
  - Store workflow hash for change detection

- [ ] **3.4 Implement `swarm workflow validate`**
  - Parse and validate YAML
  - Check prompt files exist
  - Report all errors

- [ ] **3.5 Implement `swarm workflow run`**
  - Parse --at (time)
  - Parse --in (duration)
  - Parse --name (override)
  - Parse --force (overwrite)
  - If scheduled, set status and return
  - Otherwise, start first stage

- [ ] **3.6 Implement stage spawning logic**
  - For worker type: spawn with done-pattern detection
  - For ralph type: ralph spawn with configured options
  - Apply global settings (heartbeat, worktree, cwd, env)
  - Apply stage overrides

- [ ] **3.7 Implement stage completion detection**
  - Monitor worker output for done-pattern
  - Handle timeout
  - Detect worker exit

- [ ] **3.8 Implement stage transition logic**
  - Mark stage completed/failed/skipped
  - Handle on-failure: stop/retry/skip
  - Handle on-complete: next/stop
  - Start next stage or complete workflow

- [ ] **3.9 Implement workflow monitor loop**
  - Background process managing workflow execution
  - Handle scheduled start times
  - Manage stage transitions
  - Handle heartbeats

- [ ] **3.10 Implement `swarm workflow status`**
  - Show overall workflow status
  - Show each stage status
  - Show current stage details
  - Show timing information

- [ ] **3.11 Implement `swarm workflow list`**
  - Table: name, status, current stage, started, source
  - JSON output option

- [ ] **3.12 Implement `swarm workflow cancel`**
  - Kill current stage worker
  - Stop heartbeats
  - Set status to cancelled

- [ ] **3.13 Implement `swarm workflow resume`**
  - Parse --from (stage name)
  - Restart from failed/specified stage
  - Reset attempt counts if needed

- [ ] **3.14 Implement `swarm workflow logs`**
  - Parse --stage (filter)
  - Show aggregated logs
  - Per-stage log viewing

- [ ] **3.15 Add comprehensive workflow help text**
  - Follow cli-help-standards.md
  - Include full YAML schema in `run --help`
  - Include examples for all common patterns

- [ ] **3.16 Add workflow unit tests**
  - Test YAML parsing
  - Test validation
  - Test state persistence
  - Test stage transitions

- [ ] **3.17 Add workflow integration tests**
  - Test simple 2-stage workflow
  - Test retry behavior
  - Test skip behavior
  - Test scheduling

### Phase 4: Integration and Polish

- [ ] **4.1 Add heartbeat support to ralph spawn**
  - Same --heartbeat flags as regular spawn
  - Heartbeat during ralph loop

- [ ] **4.2 Add repo-local workflow discovery**
  - Check `.swarm/workflows/` before global
  - Document in help text

- [ ] **4.3 Resume heartbeats on swarm startup**
  - Check for active heartbeats
  - Restart monitor threads

- [ ] **4.4 Resume workflows on swarm startup**
  - Check for running workflows
  - Provide `swarm workflow resume-all` command

- [ ] **4.5 Update CLAUDE.md**
  - Add heartbeat section
  - Add workflow section
  - Update examples

- [ ] **4.6 Final help text review**
  - Verify all commands meet cli-help-standards.md
  - Ensure consistency

### Phase 5: Verification

- [ ] **5.1 Run all unit tests**
  ```bash
  python3 -m unittest discover -v
  ```

- [ ] **5.2 Run integration tests**
  ```bash
  timeout 300 python3 -m unittest tests.test_integration_ralph -v
  ```

- [ ] **5.3 Manual verification - heartbeat**
  ```bash
  swarm spawn --name test --tmux -- bash -c 'while true; do sleep 10; done'
  swarm heartbeat start test --interval 30s --expire 5m --message "ping"
  swarm heartbeat status test
  swarm heartbeat list
  # Wait and observe beats
  swarm heartbeat stop test
  swarm kill test
  ```

- [ ] **5.4 Manual verification - workflow**
  ```bash
  cat > /tmp/test-workflow.yaml << 'EOF'
  name: test-workflow
  stages:
    - name: stage1
      type: worker
      prompt: |
        echo "Stage 1 complete"
        echo "/done"
      done-pattern: "/done"
      timeout: 1m
    - name: stage2
      type: worker
      prompt: |
        echo "Stage 2 complete"
        echo "/done"
      done-pattern: "/done"
      timeout: 1m
  EOF
  swarm workflow validate /tmp/test-workflow.yaml
  swarm workflow run /tmp/test-workflow.yaml
  swarm workflow status test-workflow
  swarm workflow list
  ```

- [ ] **5.5 Manual verification - help text**
  ```bash
  swarm --help
  swarm spawn --help
  swarm kill --help
  swarm heartbeat --help
  swarm heartbeat start --help
  swarm workflow --help
  swarm workflow run --help
  ```

---

## Files to Create

| File | Description |
|------|-------------|
| `specs/heartbeat.md` | Heartbeat behavioral spec (DONE) |
| `specs/workflow.md` | Workflow behavioral spec (DONE) |
| `specs/cli-help-standards.md` | CLI help standards spec (DONE) |
| `test_cmd_heartbeat.py` | Heartbeat unit tests |
| `test_cmd_workflow.py` | Workflow unit tests |
| `tests/test_integration_workflow.py` | Workflow integration tests |

## Files to Modify

| File | Changes |
|------|---------|
| `swarm.py` | Add heartbeat, workflow commands; enhance all help text |
| `CLAUDE.md` | Add heartbeat, workflow documentation |
| `specs/README.md` | Add new specs to TOC (DONE) |

---

## Design Decisions

1. **Heartbeat as blind nudge**: Simpler than rate limit detection, handles many blocking scenarios
2. **Expiration for safety**: Prevents infinite nudging of abandoned workers
3. **YAML workflows**: Familiar format, supports inline prompts to reduce file litter
4. **Help text as documentation**: Agents primarily learn from `-h`, so it must be comprehensive
5. **Linear stages first**: DAG support deferred to avoid complexity
6. **Stage workers named `<workflow>-<stage>`**: Prevents naming conflicts

---

## Rollback Plan

All features are additive:
1. Heartbeat commands are new - can be removed without breaking existing functionality
2. Workflow commands are new - can be removed without breaking existing functionality
3. Help text improvements are backwards compatible

---

## Estimated Scope

| Phase | Tasks | Complexity |
|-------|-------|------------|
| Phase 1: CLI Help | 14 tasks | Low (text changes only) |
| Phase 2: Heartbeat | 12 tasks | Medium (new subsystem) |
| Phase 3: Workflow | 17 tasks | High (orchestration logic) |
| Phase 4: Integration | 6 tasks | Medium (cross-cutting) |
| Phase 5: Verification | 5 tasks | Low (testing) |

Total: 54 tasks
