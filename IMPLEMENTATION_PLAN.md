# Implementation Plan: Remove Workflow Subcommand

**Created**: 2026-02-07
**Status**: IN PROGRESS
**Goal**: Remove `swarm workflow` subcommand entirely. Orchestration belongs in ORCHESTRATOR.md (a markdown file), not in code.

---

## Rationale

The `swarm workflow` subcommand reimplements sequential pipeline orchestration in ~2000 lines of Python + 8500 lines of tests. This duplicates what a simple markdown file (ORCHESTRATOR.md) already does better:

- ORCHESTRATOR.md composes existing primitives (`ralph`, `spawn`, `send`, `heartbeat`)
- No YAML schema to learn, no stage state machines to debug
- A human or director agent adapts in real-time instead of following rigid YAML
- Unix philosophy: keep primitives simple, compose via documents

---

## Tasks

### Phase 1: Remove Workflow Code from swarm.py

- [x] **1.1 Remove workflow data classes**
  - Delete: `StageState` (line ~2660), `WorkflowState` (~2698), `StageDefinition` (~2754), `WorkflowDefinition` (~2835), `WorkflowValidationError` (~2891)
  - Delete: `StageCompletionResult` (~8514), `StageTransitionResult` (~8764)
  - File: `swarm.py`

- [x] **1.2 Remove workflow helper functions**
  - Delete all functions between the data classes and `cmd_workflow` that are workflow-specific
  - This includes: `load_workflow_state`, `save_workflow_state`, `run_workflow_monitor`, `parse_workflow_yaml`, `validate_workflow_definition`, and any other workflow-only helpers
  - File: `swarm.py`

- [x] **1.3 Remove workflow command handlers**
  - Delete: `cmd_workflow`, `cmd_workflow_validate`, `cmd_workflow_status`, `cmd_workflow_list`, `cmd_workflow_cancel`, `cmd_workflow_resume`, `cmd_workflow_resume_all`, `cmd_workflow_logs`, `cmd_workflow_run`
  - File: `swarm.py`

- [x] **1.4 Remove workflow argparse subparsers**
  - Remove the `workflow` subparser from `main()` argparse setup
  - Remove any workflow-related help text constants (e.g. `WORKFLOW_HELP_*`)
  - File: `swarm.py`

- [x] **1.5 Remove WORKFLOWS_DIR constant and any workflow imports**
  - Delete `WORKFLOWS_DIR = SWARM_DIR / "workflows"` near top of file
  - Remove any `import yaml` or yaml-related imports that are only used by workflow
  - Check if `yaml` is used elsewhere (ralph uses it too?) -- only remove if workflow-only
  - File: `swarm.py`

### Phase 2: Remove Workflow Tests

- [x] **2.1 Delete workflow unit tests**
  - Delete file: `test_cmd_workflow.py`

- [x] **2.2 Delete workflow integration tests**
  - Delete file: `tests/test_integration_workflow.py`

### Phase 3: Remove Workflow Spec

- [x] **3.1 Delete workflow spec**
  - Delete file: `specs/workflow.md`

- [x] **3.2 Update specs/README.md**
  - Remove `workflow.md` from the P1 table
  - Update any cross-references

### Phase 4: Update Documentation

- [ ] **4.1 Update README.md**
  - Remove workflow section and all `swarm workflow` examples
  - Add/promote ORCHESTRATOR.md pattern in its place (link to `docs/autonomous-loop-guide.md`)
  - Keep it brief: the guide doc has the details

- [ ] **4.2 Update CLAUDE.md**
  - Remove workflow references from Quick Reference, Architecture Notes, Testing Guidelines
  - Remove WorkflowState/StageState from Key Data Classes
  - Remove `test_cmd_workflow.py` and `tests/test_integration_workflow.py` from Test Files

- [ ] **4.3 Update specs that cross-reference workflow**
  - `specs/cli-help-standards.md` - remove workflow help text examples (16 references)
  - `specs/heartbeat.md` - update cross-reference (~1 reference)
  - `specs/ralph-loop.md` - update cross-reference (~2 references)
  - `specs/security-permissions.md` - update if needed (~1 reference)

### Phase 5: Update Remaining References

- [ ] **5.1 Clean up SWARM_INSTRUCTIONS constant**
  - The `SWARM_INSTRUCTIONS` template (injected by `swarm init`) likely mentions workflow
  - Remove workflow section from it
  - File: `swarm.py`

- [ ] **5.2 Update cli-help-standards spec**
  - Remove workflow-specific help text examples
  - File: `specs/cli-help-standards.md`

### Phase 6: Verify

- [ ] **6.1 Run tests to verify nothing is broken**
  - Run: `python3 -m unittest test_cmd_ralph -v`
  - Run: `python3 -m unittest test_cmd_spawn -v`
  - Run: `python3 -m unittest test_cmd_kill -v`
  - Run: `python3 -m unittest test_cmd_init -v`
  - Run: `python3 -m unittest test_cmd_heartbeat -v`
  - Run any other non-workflow test files
  - Verify no import errors or missing references

- [ ] **6.2 Verify clean CLI**
  - Run: `python3 swarm.py --help` -- workflow should not appear
  - Run: `python3 swarm.py workflow` -- should error cleanly (unknown command)

- [ ] **6.3 Grep for stale references**
  - `grep -rn 'workflow' swarm.py` -- should only find incidental uses (e.g. "workflow" in generic help text about agent workflows), not `cmd_workflow` or `WorkflowState`
  - `grep -rn 'cmd_workflow\|WorkflowState\|StageState\|WorkflowDefinition' swarm.py` -- should return 0 results

---

## Files Modified

| File | Change |
|------|--------|
| `swarm.py` | Remove ~2000 lines of workflow code |
| `test_cmd_workflow.py` | DELETE entire file |
| `tests/test_integration_workflow.py` | DELETE entire file |
| `specs/workflow.md` | DELETE entire file |
| `specs/README.md` | Remove workflow from P1 table |
| `specs/cli-help-standards.md` | Remove workflow examples |
| `specs/heartbeat.md` | Update cross-reference |
| `specs/ralph-loop.md` | Update cross-reference |
| `specs/security-permissions.md` | Update cross-reference |
| `README.md` | Remove workflow section, add ORCHESTRATOR.md mention |
| `CLAUDE.md` | Remove workflow references |

---

## What We Keep

All other swarm primitives are untouched:
- `spawn` / `kill` / `ls` / `status` / `logs` / `wait` / `clean` / `respawn`
- `send` / `attach` / `interrupt` / `eof`
- `ralph` (autonomous looping)
- `heartbeat` (rate limit recovery)
- `init` (project scaffolding)

Orchestration is done via ORCHESTRATOR.md + existing primitives.
