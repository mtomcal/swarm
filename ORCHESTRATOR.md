# Loop Orchestrator Guide

## Quick Status Check
```bash
# Is the loop running?
ps aux | grep "claude -p" | grep -v grep

# Current progress
git log --oneline -5

# Tasks remaining
grep -E "^\s*-\s*\[ \]" IMPLEMENTATION_PLAN.md | wc -l

# Tasks completed
grep -E "^\s*-\s*\[x\]" IMPLEMENTATION_PLAN.md | wc -l

# Recent output (if loop running)
cat .loop-logs/iteration-*.log.raw 2>/dev/null | jq -r 'select(.type == "assistant") | .message.content[]? | select(.type == "text") | .text' 2>/dev/null | tail -20
```

## Start the Loop
```bash
rm -f .loop-logs/iteration-*.log* && ./loop.sh 30
```

## Monitor (every 5 mins with memory tracking)
```bash
sleep 300 && echo "=== $(date) ===" && \
echo "=== MEMORY ===" && free -h | head -2 && \
CLAUDE_PID=$(pgrep -f "claude -p.*stream-json" | head -1) && \
if [ -n "$CLAUDE_PID" ]; then \
  ps -p $CLAUDE_PID -o pid,rss,vsz,%mem --no-headers | \
  awk '{printf "Claude: RSS=%dMB VSZ=%dMB %%MEM=%s\n", $2/1024, $3/1024, $4}'; \
else echo "Claude not running"; fi && \
echo "" && \
cat .loop-logs/iteration-*.log.raw 2>/dev/null | jq -r 'select(.type == "assistant") | .message.content[]? | select(.type == "text") | .text' 2>/dev/null | tail -20 && \
echo "" && echo "=== COMMITS ===" && git log --oneline -5 && \
echo "" && echo "Tasks remaining: $(grep -cE '^\s*-\s*\[ \]' IMPLEMENTATION_PLAN.md)" && \
echo "Tasks completed: $(grep -cE '^\s*-\s*\[x\]' IMPLEMENTATION_PLAN.md)"
```

## Memory Monitoring

### Warning Signs
- **RSS > 2GB**: Claude process using too much memory
- **System free < 2GB**: Risk of OOM killer
- **VSZ growing rapidly**: Potential memory leak

### Real-time Memory Watch
```bash
# Watch memory every 30 seconds
while true; do
  echo "=== $(date) ==="
  free -h | head -2
  CLAUDE_PID=$(pgrep -f "claude -p.*stream-json" | head -1)
  if [ -n "$CLAUDE_PID" ]; then
    ps -p $CLAUDE_PID -o pid,rss,vsz,%mem --no-headers | \
    awk '{printf "Claude: RSS=%dMB VSZ=%dMB %%MEM=%s\n", $2/1024, $3/1024, $4}'
  fi
  sleep 30
done
```

### If Memory Gets High
1. **Check for runaway tests**: Tests spawning many subprocesses
2. **Kill and restart**: `pkill -f "claude -p" && sleep 5 && ./loop.sh 30`
3. **Check for zombie processes**: `ps aux | grep defunct`
4. **Check tmux sessions**: `tmux list-sessions` (orphaned sessions waste memory)

### Memory-Safe Test Running
```bash
# Run tests with memory limit (2GB)
systemd-run --user --scope -p MemoryMax=2G python3 -m unittest discover -v
```

## Stop the Loop
```bash
pkill -f "loop.sh"; pkill -f "claude -p"
```

## Restart After Stop/Failure
```bash
pkill -f "loop.sh" 2>/dev/null; pkill -f "claude -p" 2>/dev/null
sleep 2
rm -f .loop-logs/iteration-*.log*
./loop.sh 30
```

## Check for Rate Limit
Look for this in output:
```
You've hit your limit · resets 10am (UTC)
```
If hit, wait until reset time and restart.

## Progress Summary

### Current Project: Ralph Bug Fixes and Improvements

**Goal**: Fix ralph bugs from user feedback and add quality-of-life features

| Phase | Description | Tasks |
|-------|-------------|-------|
| Phase 1 | Spec Updates | 7 tasks |
| Phase 2 | Bug Fixes | 7 tasks |
| Phase 3 | New Features | 5 tasks |
| Phase 4 | Testing | 4 tasks |
| Phase 5 | Documentation | 3 tasks |
| Phase 6 | Verification | 2 tasks |

**Total: 28 tasks**

### Bug Fixes (B1-B7)
- B1: Ralph state cleanup on `kill --rm-worktree`
- B2: Transactional ralph spawn (rollback on failure)
- B3: Worktree error handling (`core.bare` prevention)
- B4: Status/reason accuracy (exit_reason tracking)
- B5: Monitor disconnect handling
- B6: `--tmux` flag as no-op for ralph spawn
- B7: Increase default inactivity timeout to 180s

### New Features (F1, F2, F3, F5, F7)
- F1: `--replace` flag for ralph spawn
- F2: `swarm ralph logs` command
- F3: ETA display in ralph status
- F5: `--clean-state` flag for ralph spawn
- F7: Document test artifact prevention

## Troubleshooting

### Loop stops unexpectedly
1. Check for rate limit message
2. Check if `/done` was found: `grep "/done" .loop-logs/iteration-*.log`
3. Check for errors: `tail -50 .loop-logs/iteration-*.log.raw`

### Memory exhaustion crash
1. Check `dmesg | grep -i oom` for OOM killer activity
2. Review which tests were running when crash occurred
3. Run memory profiling on suspect tests:
   ```bash
   python3 -m memory_profiler -m unittest test_cmd_ralph -v
   ```

### Tests failing in pre-commit
The worker will retry or skip pre-commit with `--no-verify` if needed.

### Loop not advancing
Check if claude process is alive:
```bash
ps aux | grep "claude -p" | grep -v grep
```

Check log freshness:
```bash
stat .loop-logs/iteration-*.log.raw | grep Modify
```

### WARNING: Running `make test` crashes swarm workers

When working on the swarm repo itself, `make test` will spawn child workers that clobber `~/.swarm/state.json`. This causes parent workers to lose state and crash.

**Mitigation for loop.sh**:
- Run specific test files instead of full suite when possible
- The loop uses `loop.sh` (not swarm ralph) to avoid this issue
- If tests crash the loop, restart with `./loop.sh 30`

## Key Files
- `PROMPT.md` - Instructions for each iteration
- `IMPLEMENTATION_PLAN.md` - Task list with checkboxes
- `FEEDBACK.md` - User feedback being addressed
- `.loop-logs/` - Iteration logs
- `loop.sh` - The loop script
