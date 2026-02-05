#!/usr/bin/env python3
"""
Memory profiling script for swarm test suite.

This script runs each test file individually and measures:
- Peak memory usage (via resource module)
- Memory allocation patterns (via tracemalloc)
- Memory growth during test execution

Usage:
    python3 profile_test_memory.py [--verbose] [--top N] [test_file ...]

If no test files are specified, all test files are profiled.
"""

import argparse
import gc
import os
import resource
import subprocess
import sys
import tracemalloc
import unittest
from pathlib import Path
from datetime import datetime
import json


def get_test_files():
    """Get all test files in the project."""
    root = Path(__file__).parent
    test_files = []

    # Root level test files
    for f in root.glob("test_*.py"):
        test_files.append(f)

    # Tests in tests/ directory
    tests_dir = root / "tests"
    if tests_dir.exists():
        for f in tests_dir.glob("test_*.py"):
            test_files.append(f)

    return sorted(test_files)


def get_memory_usage_mb():
    """Get current memory usage in MB using resource module."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # maxrss is in KB on Linux
    return usage.ru_maxrss / 1024


def run_test_file_in_subprocess(test_file: Path, timeout: int = 120) -> dict:
    """Run a single test file in a subprocess and capture memory stats."""
    result = {
        "file": str(test_file.relative_to(test_file.parent.parent) if test_file.parent.name == "tests" else test_file.name),
        "success": False,
        "peak_memory_mb": 0,
        "duration_seconds": 0,
        "error": None,
        "num_tests": 0,
    }

    # Create a small script to run tests with memory tracking
    script = f'''
import gc
import resource
import sys
import tracemalloc
import unittest
import time

# Start memory tracking
tracemalloc.start()
start_time = time.time()
start_mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

# Load and run tests
loader = unittest.TestLoader()
try:
    suite = loader.discover("{test_file.parent}", pattern="{test_file.name}")
    num_tests = suite.countTestCases()
except Exception as e:
    print(f"LOAD_ERROR: {{e}}", file=sys.stderr)
    sys.exit(1)

# Run tests silently
runner = unittest.TextTestRunner(verbosity=0, stream=open("/dev/null", "w"))
result = runner.run(suite)

# Collect memory stats
gc.collect()
end_time = time.time()
current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
end_mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

# Report stats
stats = {{
    "success": result.wasSuccessful(),
    "num_tests": num_tests,
    "failures": len(result.failures),
    "errors": len(result.errors),
    "duration_seconds": round(end_time - start_time, 2),
    "tracemalloc_peak_mb": round(peak / (1024 * 1024), 2),
    "resource_peak_mb": round(end_mem, 2),
    "memory_growth_mb": round(end_mem - start_mem, 2),
}}
print("STATS:" + str(stats))
'''

    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=test_file.parent.parent if test_file.parent.name == "tests" else test_file.parent,
            env={**os.environ, "SWARM_DIR": "/tmp/swarm-test-profile"}
        )

        # Parse output
        for line in proc.stdout.split("\n") + proc.stderr.split("\n"):
            if line.startswith("STATS:"):
                stats = eval(line[6:])
                result.update(stats)
                result["peak_memory_mb"] = stats["resource_peak_mb"]
                break

        if proc.returncode != 0 and not result.get("success"):
            result["error"] = proc.stderr[:500] if proc.stderr else f"Exit code {proc.returncode}"

    except subprocess.TimeoutExpired:
        result["error"] = f"Timeout after {timeout}s"
    except Exception as e:
        result["error"] = str(e)

    return result


def run_all_tests_with_tracking() -> dict:
    """Run all tests together and track memory growth over time."""
    print("\n=== Running All Tests Together ===\n")

    tracemalloc.start()
    gc.collect()

    snapshots = []
    start_mem = get_memory_usage_mb()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Load all test files
    for test_file in get_test_files():
        try:
            if test_file.parent.name == "tests":
                tests = loader.discover(str(test_file.parent), pattern=test_file.name)
            else:
                tests = loader.discover(str(test_file.parent), pattern=test_file.name)
            suite.addTests(tests)
        except Exception as e:
            print(f"  Error loading {test_file.name}: {e}")

    total_tests = suite.countTestCases()
    print(f"Loaded {total_tests} tests")

    # Custom test result to track memory per test
    class MemoryTrackingResult(unittest.TestResult):
        def __init__(self):
            super().__init__()
            self.test_memories = []

        def startTest(self, test):
            super().startTest(test)
            gc.collect()
            self._start_mem = get_memory_usage_mb()

        def stopTest(self, test):
            super().stopTest(test)
            gc.collect()
            end_mem = get_memory_usage_mb()
            self.test_memories.append({
                "test": str(test),
                "memory_mb": end_mem,
                "growth_mb": end_mem - self._start_mem
            })

    result = MemoryTrackingResult()

    # Run tests
    suite.run(result)

    gc.collect()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    end_mem = get_memory_usage_mb()

    # Find tests with highest memory growth
    tests_by_growth = sorted(result.test_memories, key=lambda x: x["growth_mb"], reverse=True)

    return {
        "total_tests": total_tests,
        "passed": total_tests - len(result.failures) - len(result.errors),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "start_memory_mb": round(start_mem, 2),
        "end_memory_mb": round(end_mem, 2),
        "total_growth_mb": round(end_mem - start_mem, 2),
        "tracemalloc_peak_mb": round(peak / (1024 * 1024), 2),
        "top_memory_tests": tests_by_growth[:20],
    }


def main():
    parser = argparse.ArgumentParser(description="Profile memory usage of test suite")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--top", type=int, default=10, help="Show top N memory consumers")
    parser.add_argument("--all-together", action="store_true", help="Run all tests together to track memory accumulation")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per test file in seconds")
    parser.add_argument("test_files", nargs="*", help="Specific test files to profile")
    args = parser.parse_args()

    print("=" * 60)
    print("Swarm Test Suite Memory Profiler")
    print(f"Date: {datetime.now().isoformat()}")
    print("=" * 60)

    if args.all_together:
        results = run_all_tests_with_tracking()
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"\nTotal tests: {results['total_tests']}")
            print(f"Passed: {results['passed']}, Failures: {results['failures']}, Errors: {results['errors']}")
            print(f"\nMemory Usage:")
            print(f"  Start:  {results['start_memory_mb']:.2f} MB")
            print(f"  End:    {results['end_memory_mb']:.2f} MB")
            print(f"  Growth: {results['total_growth_mb']:.2f} MB")
            print(f"  Peak (tracemalloc): {results['tracemalloc_peak_mb']:.2f} MB")

            print(f"\nTop {args.top} Tests by Memory Growth:")
            for i, test in enumerate(results["top_memory_tests"][:args.top], 1):
                print(f"  {i}. {test['test'][:60]}")
                print(f"     Growth: {test['growth_mb']:.2f} MB, Total: {test['memory_mb']:.2f} MB")
        return

    # Profile individual test files
    if args.test_files:
        test_files = [Path(f) for f in args.test_files]
    else:
        test_files = get_test_files()

    print(f"\nProfiling {len(test_files)} test files...\n")

    results = []
    for test_file in test_files:
        print(f"  Running {test_file.name}...", end=" ", flush=True)
        result = run_test_file_in_subprocess(test_file, timeout=args.timeout)
        results.append(result)

        status = "OK" if result["success"] else "FAIL"
        print(f"{status} - {result['peak_memory_mb']:.1f} MB, {result['duration_seconds']:.1f}s, {result['num_tests']} tests")

        if args.verbose and result.get("error"):
            print(f"    Error: {result['error'][:100]}")

    # Sort by peak memory usage
    results_by_memory = sorted(results, key=lambda x: x["peak_memory_mb"], reverse=True)

    print("\n" + "=" * 60)
    print(f"Top {args.top} Test Files by Peak Memory Usage:")
    print("=" * 60)

    for i, result in enumerate(results_by_memory[:args.top], 1):
        print(f"\n{i}. {result['file']}")
        print(f"   Peak Memory: {result['peak_memory_mb']:.2f} MB")
        print(f"   Duration: {result['duration_seconds']:.2f}s")
        print(f"   Tests: {result['num_tests']}")
        if result.get("memory_growth_mb"):
            print(f"   Memory Growth: {result['memory_growth_mb']:.2f} MB")
        if result.get("error"):
            print(f"   Error: {result['error'][:80]}")

    # Summary statistics
    total_memory = sum(r["peak_memory_mb"] for r in results)
    avg_memory = total_memory / len(results) if results else 0
    max_memory = max(r["peak_memory_mb"] for r in results) if results else 0

    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    print(f"  Total test files: {len(results)}")
    print(f"  Average peak memory: {avg_memory:.2f} MB")
    print(f"  Maximum peak memory: {max_memory:.2f} MB")
    print(f"  Files with errors: {sum(1 for r in results if r.get('error'))}")

    if args.json:
        print("\n" + "=" * 60)
        print("JSON Output:")
        print("=" * 60)
        print(json.dumps({
            "summary": {
                "total_files": len(results),
                "avg_peak_memory_mb": round(avg_memory, 2),
                "max_peak_memory_mb": round(max_memory, 2),
                "files_with_errors": sum(1 for r in results if r.get("error")),
            },
            "results": results,
        }, indent=2))


if __name__ == "__main__":
    main()
