# Sandboxed Director Guide

How to run a sandboxed Claude director that manages sandboxed workers — defense in depth where both layers are isolated.

## The Problem

In the standard swarm workflow, the **director** (the Claude session running ORCHESTRATOR.md) runs on the bare host with full privileges. It can read any file, run any command, and access any network resource. The workers it manages may be sandboxed in Docker containers, but the director itself is not.

This creates an asymmetric trust model: a prompt injection or misbehaving director has a larger blast radius than any individual worker.

## The Solution

Use Claude Code's **native sandbox** (bubblewrap on Linux) for the director, while workers continue to run in **Docker containers**. This gives you two independent isolation layers:

```
┌───────────────────────────────────────────────────────┐
│ Host OS                                                │
│                                                        │
│  ┌─────────────────────────────────────────────────┐  │
│  │ Native Sandbox (bubblewrap)                     │  │
│  │                                                 │  │
│  │  Director (Claude in ralph + heartbeat)         │  │
│  │  ├── ralph: context refresh every iteration     │  │
│  │  ├── heartbeat: rate limit recovery (4h nudge)  │  │
│  │  ├── reads ORCHESTRATOR.md, IMPLEMENTATION_PLAN │  │
│  │  ├── runs: swarm, git, grep                     │  │
│  │  ├── runs: docker (excluded from bwrap)         │  │
│  │  ├── runs: tmux (excluded from bwrap)           │  │
│  │  ├── writes: ~/.swarm/ (state)                  │  │
│  │  └── writes: repo dir (plans, prompts)          │  │
│  │                                                 │  │
│  │  CANNOT: read ~/.ssh, ~/.aws, /etc              │  │
│  │  CANNOT: reach arbitrary network hosts          │  │
│  └─────────────────────────────────────────────────┘  │
│                                                        │
│  ┌──────────────────┐  ┌──────────────────┐           │
│  │ Docker           │  │ Docker           │           │
│  │ Worker 1 (ralph) │  │ Worker 2 (ralph) │           │
│  │ (sandbox.sh)     │  │ (sandbox.sh)     │           │
│  │ 8g mem cap       │  │ 8g mem cap       │           │
│  │ net allowlist    │  │ net allowlist    │           │
│  │ heartbeat: 4h    │  │ heartbeat: 4h    │           │
│  └──────────────────┘  └──────────────────┘           │
└───────────────────────────────────────────────────────┘
```

### Why two layers instead of one?

| Threat | Docker-only workers | + Sandboxed director |
|--------|-------------------|---------------------|
| Worker prompt injection | Contained by Docker | Contained by Docker |
| Director prompt injection | **Full host access** | **Limited to repo + swarm state** |
| Credential theft via director | **Can read ~/.ssh, ~/.aws** | **Blocked by bwrap** |
| Data exfiltration via director | **Unrestricted network** | **Domain allowlist** |
| Director modifies system files | **Can write anywhere** | **CWD-only writes** |
| Worker OOM crashes host | Contained by cgroup | Contained by cgroup |

## Prerequisites

### Linux / WSL2

```bash
# Install bubblewrap and socat (required for native sandbox)
sudo apt-get install bubblewrap socat    # Ubuntu/Debian
sudo dnf install bubblewrap socat        # Fedora

# Verify installation
bwrap --version
socat -V | head -1
```

### Docker (for workers)

Workers use the same Docker sandbox from the [Autonomous Loop Guide](autonomous-loop-guide.md). If you haven't set that up:

```bash
# Build the sandbox image
docker build --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) \
    -t sandbox-loop -f Dockerfile.sandbox .

# Set up network lockdown
sudo ./setup-sandbox-network.sh

# Set up git auth
gh auth login
```

## Step-by-Step Setup

### Step 1: Configure the native sandbox

Create or update `~/.claude/settings.json` with sandbox settings tuned for the director role:

```json
{
  "sandbox": {
    "enabled": true,
    "autoAllowBashIfSandboxed": true,
    "excludedCommands": ["docker", "docker-compose", "tmux"],
    "allowUnsandboxedCommands": false,
    "network": {
      "allowedDomains": [
        "api.anthropic.com",
        "statsig.anthropic.com",
        "statsig.com",
        "sentry.io",
        "github.com",
        "api.github.com"
      ]
    }
  }
}
```

**Key settings explained:**

| Setting | Value | Why |
|---------|-------|-----|
| `enabled: true` | Activates bubblewrap sandbox | All bash commands run inside bwrap by default |
| `autoAllowBashIfSandboxed` | `true` | Sandboxed commands don't prompt for permission — enables autonomous operation |
| `excludedCommands` | `docker`, `tmux` | These are incompatible with bwrap (they need host namespaces). They bypass the sandbox but still go through Claude's normal permission flow |
| `allowUnsandboxedCommands` | `false` | **Critical**: disables the `dangerouslyDisableSandbox` escape hatch. Commands either run sandboxed or must be in `excludedCommands`. No backdoor |
| `allowedDomains` | API + git hosts | Director only needs Claude API and GitHub. Everything else is blocked at the network proxy level |

#### What the director CAN do (sandboxed)

- Read/write files in the repo directory (CWD)
- Read/write `~/.swarm/` (state management)
- Read `~/.claude/` (credentials, settings)
- Run `swarm` commands (`swarm ls`, `swarm ralph status`, `swarm kill`, etc.)
- Run `git` commands (`git log`, `git status`, `git diff`)
- Run `grep`, `pgrep`, `ps`, and other monitoring tools
- Reach `api.anthropic.com` (Claude API) and `github.com` (git operations)

#### What the director CANNOT do (blocked)

- Read `~/.ssh/`, `~/.aws/`, `~/.gnupg/`, or other credential directories
- Write to any directory outside the repo
- Modify system files (`/etc/`, `/usr/`, `~/.bashrc`, etc.)
- Reach arbitrary network hosts (data exfiltration blocked)
- Run unsandboxed commands except `docker` and `tmux` (no escape hatch)

#### What runs outside the sandbox (excluded commands)

`docker` and `tmux` are excluded because they need host-level access:
- `docker` needs the Docker socket to manage worker containers
- `tmux` needs the host tmux server to manage sessions

These commands go through Claude's standard permission flow. If you use `--dangerously-skip-permissions`, they run without prompting. This is the one intentional trust boundary: the director can manage Docker containers and tmux sessions on the host.

### Step 2: Verify the sandbox works

Start Claude interactively and test the boundaries:

```bash
claude
```

Then try these commands inside Claude:

```bash
# Should work (inside sandbox, CWD access)
ls
git log --oneline -5
swarm ls

# Should work (excluded from sandbox, runs on host)
docker ps
tmux ls

# Should be BLOCKED (outside CWD)
cat ~/.ssh/id_rsa
cat /etc/passwd

# Should be BLOCKED (network not in allowlist)
curl https://example.com
```

If filesystem/network blocks are working correctly, proceed to step 3.

### Step 3: Write the director's ORCHESTRATOR.md

The director reads ORCHESTRATOR.md to know what to do. Write it for your specific epic. Here's a template tuned for sandboxed operation:

```markdown
# [Epic Name] — Sandboxed Director Runbook

You are a **sandboxed director**. You manage workers but do not write code yourself.

## Your Constraints
- You run inside Claude's native sandbox (bubblewrap)
- Filesystem: you can only write to this repo directory and ~/.swarm/
- Network: you can only reach api.anthropic.com and github.com
- docker and tmux commands run outside the sandbox (normal permission flow)

## Start Workers
\`\`\`bash
swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 \
    -- ./sandbox.sh --dangerously-skip-permissions
\`\`\`

## Monitor (every 5-15 minutes)
\`\`\`bash
swarm ralph status dev
git log --oneline -5
grep -cE '^\s*-\s*\[x\]' IMPLEMENTATION_PLAN.md
grep -cE '^\s*-\s*\[ \]' IMPLEMENTATION_PLAN.md
\`\`\`

## Intervene When Stuck
- If a worker loops on the same task for 2+ iterations, update PROMPT.md
- If OOM (exit 137), bump memory: MEMORY_LIMIT=12g
- If rate limited, add heartbeat: swarm heartbeat start dev --interval 4h

## Done
When all tasks are [x] in IMPLEMENTATION_PLAN.md, verify and report to user.
```

### Step 4: Launch the sandboxed director

**Option A: Interactive director** (you watch, it reports back)

```bash
claude --dangerously-skip-permissions
# Then tell it:
# "Read ORCHESTRATOR.md and begin managing the epic. Monitor every 5 minutes."
```

**Option B: Fully autonomous director** (ralph + heartbeat, self-healing)

The director runs as its own ralph loop with a heartbeat for rate limit recovery. This is the full autonomous stack — the director loops and self-heals, managing workers that also loop and self-heal.

```bash
swarm ralph spawn --name director \
    --prompt-file DIRECTOR_PROMPT.md \
    --max-iterations 200 \
    --inactivity-timeout 14400 \
    --heartbeat 30m \
    --heartbeat-expire 48h \
    -- claude --dangerously-skip-permissions
```

| Flag | Value | Why |
|------|-------|-----|
| `--max-iterations 200` | High ceiling | Director iterations are cheap (monitoring, not coding) |
| `--inactivity-timeout 14400` | 4 hours | Matches Claude's rate limit window. Prevents ralph from burning iterations restarting into the same rate limit. See [Rate limits and iteration burn](#rate-limits-and-iteration-burn) |
| `--heartbeat 30m` | 30 minutes | Rate limits can hit anywhere in the 4h window (often at ~2h). Frequent nudges mean you're at most 30 min from a retry after the limit lifts. Nudges to a busy worker are harmlessly ignored |
| `--heartbeat-expire 48h` | 2 days | Stop nudging after the epic should be done |

Each iteration the director:
1. Reads DIRECTOR_PROMPT.md (fresh context window)
2. Checks if workers are already running (`swarm ls`, `swarm ralph list`)
3. Spawns workers if none exist, monitors them if they do
4. Intervenes if workers are stuck (edits PROMPT.md, bumps memory, etc.)
5. Updates ORCHESTRATOR.md with progress notes
6. Commits and exits — ralph restarts it with a clean context

If Claude hits a rate limit, the heartbeat nudges it every 4 hours. If the context window fills up from verbose monitoring output, ralph restarts it fresh. The director is self-healing.

#### DIRECTOR_PROMPT.md

The critical detail: **each ralph iteration starts with no memory of the previous one**. The prompt must tell the director to check for existing workers before spawning duplicates.

```markdown
Read ORCHESTRATOR.md. You are the director.

FIRST: run `swarm ralph list` and `swarm ls` to see what's already running.
- If workers exist and are running, monitor them. Do NOT spawn duplicates.
- If no workers exist, spawn them per ORCHESTRATOR.md.
- If a worker is stuck (same task for 2+ iterations in ralph logs), intervene
  by editing PROMPT.md or IMPLEMENTATION_PLAN.md to unblock it.
- If all tasks in IMPLEMENTATION_PLAN.md are marked [x], verify and output /done.

Before exiting, commit progress notes to ORCHESTRATOR.md.
```

**Key rules for DIRECTOR_PROMPT.md:**
- **Always check before spawning** — `swarm ls` first, spawn only if no workers exist
- **Keep it short** — less prompt = more context for monitoring output
- **Commit progress** — ORCHESTRATOR.md is the director's persistent memory across iterations
- **Output `/done`** — ralph watches for this to terminate the loop

### Step 5: Monitor the director

The director is itself a swarm worker, so you monitor it the same way you'd monitor any worker:

```bash
# Director's own ralph status (iteration count, ETA)
swarm ralph status director
swarm logs director

# Workers managed by the director
swarm ralph status dev
swarm logs dev

# Heartbeat status (is the director recovering from rate limits?)
swarm heartbeat status director

# Attach to the director's tmux pane for live inspection
swarm attach director
```

The human's role with a fully autonomous director is minimal: check in occasionally, review commits, and intervene only if the director itself gets stuck (which ralph + heartbeat should prevent in most cases).

## Security Model

### Trust boundaries

```
Human (minimal oversight)
 │
 │  trusts
 ▼
Director (native sandbox + ralph + heartbeat)
 │  isolation: bubblewrap (filesystem + network)
 │  filesystem: repo + ~/.swarm/ only
 │  network: API + github only
 │  excluded: docker, tmux (host access)
 │  self-healing: ralph restarts on context fill / crash
 │  rate-limit recovery: heartbeat nudges every 4h
 │
 │  manages (via swarm commands)
 ▼
Workers (Docker containers + ralph + heartbeat)
   isolation: Docker (container boundary)
   filesystem: /workspace bind mount only
   network: iptables allowlist only
   memory: cgroup capped (8g default)
   CPU: cgroup capped (4 cores default)
   PIDs: cgroup capped (512 default)
   self-healing: ralph restarts on context fill / crash
   rate-limit recovery: heartbeat nudges every 4h
```

The entire stack is self-healing. If a worker hits a rate limit, its heartbeat recovers it. If a worker's context fills up, ralph restarts it. If the director hits a rate limit, its heartbeat recovers it. If the director's context fills up, ralph restarts it. The human only needs to intervene if something is fundamentally broken (wrong plan, missing prerequisites, etc.).

### What each layer prevents

**Native sandbox (director):**
- Prevents reading credentials outside the repo
- Prevents writing to system directories
- Prevents network exfiltration to unauthorized hosts
- Prevents modifying shell configs or PATH

**Docker sandbox (workers):**
- Prevents escaping the container filesystem
- Prevents host OOM (cgroup memory limit)
- Prevents fork bombs (PID limit)
- Prevents network access outside the iptables allowlist
- Container is disposable — killed on OOM, restarted cleanly

### Known limitations

1. **`docker` and `tmux` are excluded from the sandbox**. A compromised director can run arbitrary Docker commands (including mounting host paths). This is an intentional tradeoff — the director's job is to manage containers. Mitigation: if this is unacceptable, switch to Approach C (swarm daemon API) described below.

2. **No OOM protection for the director**. The director runs as a host process. Since directors are lightweight (monitoring commands, no test suites), OOM risk is near zero in practice.

3. **`--dangerously-skip-permissions` still applies to excluded commands**. Docker and tmux commands are auto-approved. If you want them prompted, don't use `--dangerously-skip-permissions` — but then the director needs interactive approval for every swarm/docker/tmux command.

4. **Network domain allowlist is DNS-based**. Domain fronting on allowed domains (e.g., exfiltrating data through `github.com`) is theoretically possible. Keep the allowlist minimal.

5. **bubblewrap does not restrict CPU/memory**. Unlike Docker's cgroups, bwrap only provides namespace isolation. The director can use unlimited CPU and memory. This is fine for monitoring workloads.

6. **Rate limits can burn ralph iterations**. This is an important interaction between ralph and heartbeat that needs careful tuning. See the section below.

### Rate limits and iteration burn

When Claude hits a rate limit, the screen freezes (rate limit message displayed, no further output). Ralph's inactivity detector sees a stable screen and, after `inactivity_timeout` seconds, kills and restarts the worker. The new worker immediately hits the same rate limit. This cycle repeats, burning iterations without doing useful work, until `max_iterations` is exhausted.

**Why heartbeat alone doesn't fix this**: Heartbeat sends a nudge to the worker inside the current ralph iteration. If the heartbeat fires while the worker is rate-limited, the nudge may prompt Claude to retry the API call. But if `inactivity_timeout` (e.g., 180s) is much shorter than the heartbeat interval (e.g., 4h), ralph will have already killed and restarted the worker many times before the first heartbeat fires.

**Why consecutive_failures doesn't help**: Ralph's failure counter only increments on spawn failures (exceptions during worker creation), not on rate-limit-induced inactivity timeouts. Inactivity restarts are treated as normal iteration boundaries.

```
Rate limit hit
  └── Screen freezes
       └── 180s passes (inactivity_timeout)
            └── Ralph kills worker, starts iteration N+1
                 └── New worker hits same rate limit
                      └── 180s passes
                           └── Ralph kills worker, starts iteration N+2
                                └── ... burns through max_iterations
```

**Mitigations (pick one or combine):**

1. **Match inactivity timeout to rate limit window**: Set `--inactivity-timeout 14400` (4 hours) so ralph waits long enough for the rate limit to expire. Downside: ralph can't detect legitimately stuck workers quickly.

2. **Use heartbeat with a shorter interval than the rate limit window**: Set `--heartbeat 30m` so the nudge arrives while the worker is still alive and rate-limited, prompting a retry. Combined with a longer inactivity timeout (e.g., 3600s), this gives heartbeat time to work before ralph restarts.

3. **Set a high max_iterations ceiling**: If iterations are cheap (director monitoring loops), burning a few on rate limits is acceptable. Set `--max-iterations 500` and accept that some will be wasted.

4. **Director monitors for rate limit burn**: If the director is autonomous, DIRECTOR_PROMPT.md can instruct it to check `swarm ralph logs dev` for rapid TIMEOUT entries and pause the worker (`swarm ralph pause dev`) until the rate limit window passes.

**Recommended configuration for Claude rate limits (4-hour window):**

Claude's rate limits reset on a 4-hour window, but you can exhaust your token budget anywhere within that window — sometimes as early as 2 hours in. The inactivity timeout must cover the full window, and heartbeat should nudge frequently so recovery happens promptly whenever the limit lifts.

```bash
# Director: wait out the full 4h rate limit window, nudge every 30m
swarm ralph spawn --name director \
    --prompt-file DIRECTOR_PROMPT.md \
    --max-iterations 200 \
    --inactivity-timeout 14400 \
    --heartbeat 30m \
    --heartbeat-expire 48h \
    -- claude --dangerously-skip-permissions

# Workers: same pattern
swarm ralph spawn --name dev \
    --prompt-file PROMPT.md \
    --max-iterations 100 \
    --inactivity-timeout 14400 \
    --heartbeat 30m \
    --heartbeat-expire 24h \
    -- ./sandbox.sh --dangerously-skip-permissions
```

| Setting | Value | Why |
|---------|-------|-----|
| `--inactivity-timeout 14400` | 4 hours | Matches the rate limit window. Ralph won't kill a rate-limited worker prematurely |
| `--heartbeat 30m` | 30 minutes | Token budget can be exhausted at any point in the 4h window. Frequent nudges mean at most 30 min of dead time after the limit lifts. Nudges to a working agent are ignored |
| `--heartbeat-expire 48h` | 2 days | Director runs for the duration of an epic |

**Tradeoff**: With a 4-hour inactivity timeout, ralph can't detect a legitimately stuck worker (infinite loop, hung process) for 4 hours either. This is acceptable for most workloads — a stuck worker just wastes one rate-limit-window of time before ralph restarts it. If faster stuck detection matters, use mitigation #4 above (director monitors ralph logs for rapid timeouts).

## Comparison of Sandboxing Approaches

| | No sandbox | Native sandbox (this guide) | Docker for director too | Swarm daemon API |
|---|---|---|---|---|
| Director isolation | None | Filesystem + network | Full container | Minimal privilege API |
| Worker isolation | Docker | Docker | Docker | Docker |
| Director can read ~/.ssh | Yes | **No** | **No** | **No** |
| Director can exfiltrate data | Yes | **Domain-limited** | **Allowlisted** | **No network** |
| OOM protection (director) | No | No | **Yes** | N/A |
| Docker socket needed | No | Yes (excluded cmd) | Yes (mounted) | No (daemon manages) |
| Setup complexity | Low | **Low** | Medium | High (requires daemon) |
| Works today | Yes | **Yes** | Yes | Needs new architecture |

## Troubleshooting

### "bwrap: command not found"

Install bubblewrap:
```bash
sudo apt-get install bubblewrap socat   # Ubuntu/Debian
sudo dnf install bubblewrap socat       # Fedora
```

### Sandbox blocks a command the director needs

Two options:

1. **Add to `excludedCommands`** — the command runs outside the sandbox with normal permissions:
   ```json
   { "sandbox": { "excludedCommands": ["docker", "tmux", "your-command"] } }
   ```

2. **Add the domain to `allowedDomains`** — if it's a network issue:
   ```json
   { "sandbox": { "network": { "allowedDomains": ["new-domain.com"] } } }
   ```

### Director can't manage workers (swarm commands fail)

Ensure `~/.swarm/` is readable/writable. The native sandbox allows read/write to CWD and its config directories by default. If `~/.swarm/` is outside CWD, you may need to verify that Claude's sandbox allows access to it. The sandbox permits read access to most of the filesystem by default and write access to CWD — `~/.swarm/` may need explicit allowance depending on your configuration.

Check by running inside the director session:
```bash
ls -la ~/.swarm/
swarm ls
```

If blocked, run `/sandbox` in Claude to review and adjust path permissions.

### Workers fail to spawn (docker excluded command not working)

Verify `docker` is in `excludedCommands`:
```bash
cat ~/.claude/settings.json | jq '.sandbox.excludedCommands'
# Should show: ["docker", "docker-compose", "tmux"]
```

If `allowUnsandboxedCommands` is `false` and `docker` is not in `excludedCommands`, docker commands will be blocked entirely.

### Network blocked for git operations

Ensure `github.com` and `api.github.com` are in `allowedDomains`. If using a self-hosted git server, add that domain too.

## Future: Swarm Daemon API (Approach C)

The native sandbox approach has one structural weakness: `docker` and `tmux` must be excluded from the sandbox, giving the director host-level access to those subsystems.

The principled long-term solution is a **swarm daemon**: a small privileged process on the host that exposes a Unix socket API. The director talks to the daemon instead of running docker/tmux directly:

```
Director (fully sandboxed, no exclusions)
    │
    │  Unix socket: /tmp/swarm.sock
    ▼
Swarm Daemon (privileged, host process)
    ├── manages tmux sessions
    ├── manages Docker containers
    ├── manages ~/.swarm/ state
    └── enforces policy (max workers, resource limits)
```

This eliminates the need for `excludedCommands` entirely. The director would only need:
- Filesystem: repo directory (rw)
- Network: `api.anthropic.com` only
- Unix socket: `/tmp/swarm.sock` (to talk to the daemon)

The daemon validates every request and enforces limits. A compromised director cannot spawn unlimited containers, mount host paths, or bypass resource caps.

This requires significant architectural changes to swarm (from CLI tool to client-server) and is not yet implemented. The native sandbox approach in this guide is the practical solution available today.

## References

- [Sandboxing — Claude Code Docs](https://code.claude.com/docs/en/sandboxing)
- [Claude Code Sandboxing — Anthropic Engineering](https://www.anthropic.com/engineering/claude-code-sandboxing)
- [Bubblewrap — GitHub](https://github.com/containers/bubblewrap)
- [Autonomous Loop Guide](autonomous-loop-guide.md) — Docker sandbox setup for workers
- [Sandbox Loop Spec](sandbox-loop-spec.md) — Detailed Docker sandbox architecture
