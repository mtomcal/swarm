#!/usr/bin/env python3
"""Integration test for swarm kill command"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

SWARM_CMD = "./swarm.py"


def run_swarm(*args, check=True):
    """Run swarm command and return result."""
    cmd = [SWARM_CMD] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        print(f"Command failed: {' '.join(cmd)}", file=sys.stderr)
        print(f"stdout: {result.stdout}", file=sys.stderr)
        print(f"stderr: {result.stderr}", file=sys.stderr)
        raise RuntimeError(f"Command failed with code {result.returncode}")
    return result


def get_state():
    """Load current swarm state."""
    state_file = Path.home() / ".swarm" / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return {"workers": []}


def cleanup_worker(name):
    """Clean up a test worker."""
    run_swarm("kill", name, check=False)
    run_swarm("clean", name, "--rm-worktree", check=False)


def test_kill_basic_worker():
    """Test killing a basic worker."""
    print("Test: kill basic worker...")

    # Clean up any existing test worker
    cleanup_worker("test-kill-basic")

    # Spawn a simple process
    result = run_swarm("spawn", "--name", "test-kill-basic", "--", "sleep", "1000")
    assert result.returncode == 0, "spawn should succeed"

    # Verify it's running
    state = get_state()
    worker = next((w for w in state["workers"] if w["name"] == "test-kill-basic"), None)
    assert worker is not None, "worker should exist"
    assert worker["status"] == "running", "worker should be running"
    pid = worker["pid"]
    assert pid is not None, "worker should have a PID"

    # Kill the worker
    result = run_swarm("kill", "test-kill-basic")
    assert result.returncode == 0, "kill should succeed"
    assert "killed test-kill-basic" in result.stdout, "should print confirmation"

    # Verify it's stopped
    state = get_state()
    worker = next((w for w in state["workers"] if w["name"] == "test-kill-basic"), None)
    assert worker is not None, "worker should still be in state"
    assert worker["status"] == "stopped", "worker should be stopped"

    # Verify process is actually dead
    time.sleep(0.5)  # Give it time to die
    try:
        os.kill(pid, 0)
        # If we get here, process is still alive
        assert False, "Process should be dead"
    except ProcessLookupError:
        # Process is dead, this is expected
        pass

    # Clean up
    cleanup_worker("test-kill-basic")
    print("  PASS")


def test_kill_nonexistent_worker():
    """Test killing a worker that doesn't exist."""
    print("Test: kill nonexistent worker...")

    result = run_swarm("kill", "nonexistent-worker-xyz", check=False)
    assert result.returncode != 0, "should fail for nonexistent worker"
    assert "not found" in result.stderr.lower(), "should indicate worker not found"

    print("  PASS")


def test_kill_without_name_or_all():
    """Test kill without specifying name or --all."""
    print("Test: kill without name or --all...")

    result = run_swarm("kill", check=False)
    assert result.returncode != 0, "should fail without name or --all"
    assert "must specify" in result.stderr.lower() or "required" in result.stderr.lower(), \
        "should indicate name is required"

    print("  PASS")


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("Running swarm kill integration tests")
    print("=" * 60)

    tests = [
        test_kill_basic_worker,
        test_kill_nonexistent_worker,
        test_kill_without_name_or_all,
    ]

    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"  FAIL: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    print("=" * 60)
    print("All integration tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
