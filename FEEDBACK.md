# Swarm Ralph Feedback — 2026-02-13 Session

Field notes from running `swarm ralph` on a real project (stick-rumble) with beads task tracking.

## 1. Ralph doesn't detect compaction (HIGH PRIORITY)

**Problem**: When Claude Code compacts its context, the iteration is effectively dead — the agent loses working memory and produces low-quality output for the rest of the iteration. But ralph has no idea this happened. The inactivity timer doesn't fire because the agent is still technically producing output (just bad output).

**Proposed fix**: Watch the tmux pane for `"Compacting conversation"` text. When detected:
1. Immediately kill the agent process
2. Log `"compaction detected — killing iteration"` to ralph logs
3. Start the next iteration with fresh context

This could be a new flag like `--kill-on-compaction` (default: true), or built into the default behavior since compaction is never desirable in autonomous ralph mode.

## 2. `/done` output doesn't terminate the agent (HIGH PRIORITY)

**Problem**: The agent outputs `/done` as text but doesn't actually exit. Ralph's done-pattern check only runs after the agent process exits. So ralph sits waiting for the process to terminate while the agent idles at the prompt. Eventually the inactivity timeout fires (180s wasted).

**Proposed fix**: Add `--check-done-continuous` to the default ralph behavior, or make it opt-out. When the done pattern is matched in the tmux output, ralph should:
1. Send `/exit` + Enter to the tmux pane
2. Wait 10s for clean exit
3. Force-kill if still alive
4. Check the done pattern and stop the loop

Alternatively, a `--done-action kill` flag that sends a kill signal when the done pattern is matched, rather than just noting it for post-exit checking.

## 3. `swarm send` doesn't reliably deliver `/exit` (MEDIUM)

**Problem**: Sending `/exit` via `swarm send` often gets eaten by Claude Code's autocomplete dropdown. The `/exit` text appears in the input, autocomplete shows a menu, and the Enter keypress selects from the menu rather than submitting. Multiple attempts needed.

**Observed sequence**:
```
swarm send dev "/exit"   # types /exit into prompt
                         # autocomplete menu appears: /exit, /extra-usage, /context...
                         # Enter selects from menu but may not submit
```

**Proposed fix**: `swarm send` should:
1. Send `Escape` first to dismiss any autocomplete
2. Clear the input line (`Ctrl-U`)
3. Type the text
4. Send `Enter`

Or provide a `swarm interrupt dev` command that sends Ctrl-C + `/exit` + Enter as a reliable kill sequence for Claude Code specifically.

## 4. Ralph monitor gets stuck when worker dies (MEDIUM)

**Problem**: After the agent process exits (via `/exit`), `swarm ralph status` still shows `Status: running, Iteration: 1/10` indefinitely. The monitor doesn't detect that the worker process is gone. `swarm peek dev` returns `worker 'dev' is not running` but ralph doesn't know.

**Proposed fix**: The ralph monitor loop should check if the worker process is alive. If the tmux window/pane is gone, ralph should:
1. Mark the iteration as complete
2. Check for done pattern in the last captured output
3. Either start the next iteration or stop the loop

## 5. `Last screen change: (none)` always (LOW)

**Problem**: `swarm ralph status` always shows `Last screen change: (none)` even when the agent is actively producing output. This makes it impossible to tell from status alone whether the agent is working or stuck.

**Proposed fix**: The screen-change tracking should capture timestamps when the tmux pane content differs from the previous poll.

## 6. Feature request: `--max-context` flag (NICE TO HAVE)

**Problem**: Even with PROMPT.md instructions telling the agent to self-monitor context and exit at 60%, agents don't always follow instructions. A belt-and-suspenders approach would have ralph enforce this.

**Proposed behavior**: `--max-context 60` would:
1. Poll the tmux pane for the context percentage (regex on the status bar, e.g., `(\d+)%`)
2. At the threshold, send a nudge: `"You're at {n}% context. Commit WIP and /exit NOW."`
3. At threshold + 15%, force-kill the iteration

This removes reliance on the agent following its own instructions.

## Summary — Priority Order

| # | Issue | Impact | Effort |
|---|-------|--------|--------|
| 1 | Detect compaction, kill iteration | Prevents wasted iterations | Medium |
| 2 | Done pattern should kill agent | Prevents 180s idle waste | Low |
| 3 | `swarm send` vs autocomplete | Unreliable manual intervention | Low |
| 4 | Monitor stuck after worker death | Ralph loop hangs | Medium |
| 5 | Screen change tracking broken | Status is useless | Low |
| 6 | `--max-context` enforcement | Belt-and-suspenders | High |
