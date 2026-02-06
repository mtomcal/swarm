# Loop Orchestrator Guide

## Quick Status Check
```bash
# Is the loop running?
ps aux | grep "claude -p" | grep -v grep

# Is a sandbox container running?
docker ps --filter "name=sandbox-loop"

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

### Sandbox Mode (recommended)

One-time setup:
```bash
# Build the sandbox image
docker build --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) \
    -t sandbox-loop -f Dockerfile.sandbox .
```

**Reminder**: Run `setup-sandbox-network.sh` manually before first use to set up network lockdown. See [Network Lockdown](#network-lockdown).

Run the loop:
```bash
# Foreground
SANDBOX=1 ./loop.sh 30

# Background with nohup
mkdir -p .loop-logs && rm -f .loop-logs/iteration-*.log* 2>/dev/null
SANDBOX=1 nohup ./loop.sh 30 > .loop-logs/loop-main.log 2>&1 &
echo "Loop PID: $!"
```

Resource overrides:
```bash
SANDBOX=1 MEMORY_LIMIT=12g CPU_LIMIT=6 PIDS_LIMIT=1024 ./loop.sh 30
```

### Bare-Metal Mode (no Docker)
```bash
# Foreground
./loop.sh 30

# Background with nohup
mkdir -p .loop-logs && rm -f .loop-logs/iteration-*.log* 2>/dev/null
nohup ./loop.sh 30 > .loop-logs/loop-main.log 2>&1 &
echo "Loop PID: $!"
```

**Note**: Bare-metal has no memory protection. Use sandbox mode for unattended runs.

## Monitor (every 5 mins with memory tracking)

### Sandbox Mode
```bash
# Container resource usage (live)
docker stats --filter "name=sandbox-loop" --no-stream

# Watch container memory over time
while true; do
  echo "=== $(date) ==="
  docker stats --filter "name=sandbox-loop" --no-stream --format \
    "{{.Name}}: MEM={{.MemUsage}} CPU={{.CPUPerc}} PIDs={{.PIDs}}" 2>/dev/null || echo "No container running"
  echo "Tasks remaining: $(grep -cE '^\s*-\s*\[ \]' IMPLEMENTATION_PLAN.md)"
  echo "Tasks completed: $(grep -cE '^\s*-\s*\[x\]' IMPLEMENTATION_PLAN.md)"
  sleep 30
done
```

### Bare-Metal Mode
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

## Stop the Loop

### Sandbox Mode
```bash
# Stop the loop script and kill any running container
pkill -f "loop.sh"
docker kill $(docker ps -q --filter "name=sandbox-loop") 2>/dev/null
```

### Bare-Metal Mode
```bash
pkill -f "loop.sh"; pkill -f "claude -p"
```

## Restart After Stop/Failure
```bash
# Stop everything
pkill -f "loop.sh" 2>/dev/null; pkill -f "claude -p" 2>/dev/null
docker kill $(docker ps -q --filter "name=sandbox-loop") 2>/dev/null
sleep 2

# Clear logs and restart
rm -f .loop-logs/iteration-*.log*
SANDBOX=1 ./loop.sh 30
```

## Check for Rate Limit
Look for this in output:
```
You've hit your limit · resets 10am (UTC)
```
If hit, wait until reset time and restart.

## Network Lockdown

**These scripts require elevated privileges. Remind the user to run them manually in their terminal.**

`setup-sandbox-network.sh` creates a `sandbox-net` Docker network (172.30.0.0/24) with iptables rules allowing only:
- api.anthropic.com:443 (Claude API)
- statsig.anthropic.com:443 + statsig.com:443 (feature flags)
- sentry.io:443 (error reporting)
- github.com:22+443 (git push, API)
- DNS (udp+tcp/53)

Everything else is REJECTED.

### Verify
```bash
# Should fail (Connection refused)
docker run --rm --network=sandbox-net sandbox-loop curl -v --max-time 5 https://example.com

# Should connect
docker run --rm --network=sandbox-net sandbox-loop curl -v --max-time 5 https://api.anthropic.com
```

### Refresh IPs
Domain IPs can rotate. Re-run `teardown-sandbox-network.sh` then `setup-sandbox-network.sh` manually to refresh.

### Notes
- iptables rules don't survive reboot. Re-run `setup-sandbox-network.sh` after restart.
- Run `teardown-sandbox-network.sh` to remove all rules and the Docker network.

## OOM Handling

### Sandbox Mode (automatic recovery)
When a container hits the memory limit, the kernel cgroup OOM-killer fires:
- Container is killed with exit code **137**
- Host is unaffected (cgroup kills the container, not the host)
- `loop.sh` logs the OOM, waits 5s, and starts the next iteration
- Committed work is preserved (bind-mounted repo)
- Uncommitted work in that iteration is lost (loop retries)

### OOM Forensics

After an OOM (exit 137), investigate what consumed the memory:

**1. Check which iteration OOM'd**
```bash
# Look for OOM warnings in the main loop output
grep -n "OOM-killed" .loop-logs/loop-main.log

# Or check raw logs for short-lived iterations
ls -la .loop-logs/iteration-*.log.raw | awk '{print $5, $9}' | sort -n
# Small files = iterations that died early (possibly OOM)
```

**2. Read the last assistant message before the OOM**
```bash
# Replace N with the OOM'd iteration number
jq -r 'select(.type == "assistant") | .message.content[]? | select(.type == "text") | .text' \
  .loop-logs/iteration-N.log.raw | tail -30
```
This shows what Claude was doing when memory spiked — usually running tests or spawning processes.

**3. Check what tool was being used**
```bash
# Look for the last tool_use before the crash
jq -r 'select(.type == "assistant") | .message.content[]? | select(.type == "tool_use") | .name' \
  .loop-logs/iteration-N.log.raw | tail -5
```
If the last tool was `Bash`, check the command:
```bash
jq -r 'select(.type == "assistant") | .message.content[]? | select(.type == "tool_use") | select(.name == "Bash") | .input.command' \
  .loop-logs/iteration-N.log.raw | tail -3
```

**4. Check host dmesg for cgroup OOM details**
```bash
# Shows which process inside the container was killed and memory stats
dmesg | grep -A 5 "oom-kill" | tail -20

# More detail: cgroup memory stats at time of kill
dmesg | grep -B 2 -A 10 "Memory cgroup out of memory" | tail -30
```
This tells you exactly which process (node, python3, tmux) triggered the OOM and the cgroup's memory breakdown.

**5. Check if it's a pattern**
```bash
# Did multiple iterations OOM?
grep -c "OOM-killed" .loop-logs/loop-main.log

# What were the common commands across OOM'd iterations?
for f in .loop-logs/iteration-*.log.raw; do
  size=$(stat -c%s "$f" 2>/dev/null || echo 0)
  if [ "$size" -lt 5000 ]; then
    echo "=== $f (likely OOM) ==="
    jq -r 'select(.type == "assistant") | .message.content[]? | select(.type == "tool_use") | select(.name == "Bash") | .input.command' "$f" 2>/dev/null | tail -3
  fi
done
```

**6. Raise the memory limit if needed**
```bash
# Default is 8g. If OOMs are frequent, bump it:
SANDBOX=1 MEMORY_LIMIT=12g ./loop.sh 30
```

### Bare-Metal OOM
If not using sandbox mode, OOM kills the host process directly:
```bash
# Check kernel OOM killer activity
dmesg | grep -i oom

# Review which tests were running when crash occurred
# Run memory profiling on suspect tests
python3 -m memory_profiler -m unittest test_cmd_ralph -v
```

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

**Total: 28 tasks (COMPLETE)**

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

### Tests failing in pre-commit
The worker will retry or skip pre-commit with `--no-verify` if needed.

### Loop not advancing
Check if claude process is alive:
```bash
# Sandbox
docker ps --filter "name=sandbox-loop"

# Bare-metal
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
- If tests crash the loop, restart with `SANDBOX=1 ./loop.sh 30`

## Prompt Optimization

If you notice bad patterns in loop behavior — iterations wasting tokens on irrelevant context, repeating mistakes, reading files they don't need, or failing to complete tasks within a single iteration — you are free to edit `PROMPT.md` to correct the behavior. The goal is to keep each iteration focused, low-context, and on-task.

Examples of when to edit `PROMPT.md`:
- Iterations keep reading the same large files unnecessarily — add "Do not read X unless needed"
- Claude keeps running `make test` instead of specific test files — strengthen the warning
- Iterations are doing multiple tasks instead of one — make the "ONE task" rule more prominent
- Claude is spending tokens on explanation instead of working — add "minimize commentary"
- OOM patterns suggest certain commands are problematic — add restrictions to PROMPT.md

## Key Files
- `PROMPT.md` - Instructions for each iteration
- `IMPLEMENTATION_PLAN.md` - Task list with checkboxes
- `FEEDBACK.md` - User feedback being addressed
- `.loop-logs/` - Iteration logs
- `loop.sh` - The loop script
- `Dockerfile.sandbox` - Sandbox container image
- `setup-sandbox-network.sh` - Network lockdown setup (run manually)
- `teardown-sandbox-network.sh` - Network lockdown teardown (run manually)
