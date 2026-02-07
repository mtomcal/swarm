# Remove Workflow Subcommand - Orchestrator

## Quick Status
```bash
git log --oneline -5
grep -cE '^\s*-\s*\[x\]' IMPLEMENTATION_PLAN.md  # Tasks done
grep -cE '^\s*-\s*\[ \]' IMPLEMENTATION_PLAN.md   # Tasks remaining
```

## Start
```bash
SANDBOX=1 ./loop.sh 20
```

## Monitor
```bash
# Container resource usage
docker stats --filter "name=sandbox-loop" --no-stream

# Recent commits
git log --oneline -5

# Progress
grep -cE '^\s*-\s*\[x\]' IMPLEMENTATION_PLAN.md
grep -cE '^\s*-\s*\[ \]' IMPLEMENTATION_PLAN.md
```

## Stop / Restart
```bash
pkill -f "loop.sh"; docker kill $(docker ps -q --filter "name=sandbox-loop") 2>/dev/null
sleep 2
SANDBOX=1 ./loop.sh 20
```

## OOM Recovery
Exit 137 = container hit memory limit. Loop auto-continues.
```bash
SANDBOX=1 MEMORY_LIMIT=12g ./loop.sh 20
```

## Progress

| Phase | Description | Tasks |
|-------|-------------|-------|
| Phase 1 | Remove workflow code from swarm.py | 5 tasks |
| Phase 2 | Delete workflow test files | 2 tasks |
| Phase 3 | Delete workflow spec, update spec README | 2 tasks |
| Phase 4 | Update README.md, CLAUDE.md, cross-ref specs | 3 tasks |
| Phase 5 | Clean up remaining references | 2 tasks |
| Phase 6 | Verify tests pass, CLI clean, no stale refs | 3 tasks |

**Total: 17 tasks**
