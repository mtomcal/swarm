#!/usr/bin/env python3
"""Memory-safe test runner with safeguards against memory exhaustion.

This module provides test infrastructure to prevent memory exhaustion during
test runs by:
1. Monitoring memory usage and issuing warnings when thresholds are exceeded
2. Forcing garbage collection between test classes to prevent accumulation
3. Providing isolation mechanisms for memory-heavy tests

Usage:
    # Run tests with memory monitoring
    python3 memory_safe_runner.py [--memory-limit MB] [--gc-between-classes] [test_pattern ...]

    # Or use as a module
    python3 -m memory_safe_runner --memory-limit 500 test_cmd_workflow

    # In code
    from memory_safe_runner import MemorySafeTestRunner, GCBetweenClassesSuite
    runner = MemorySafeTestRunner(memory_limit_mb=500)
    suite = GCBetweenClassesSuite(tests)
    runner.run(suite)
"""

import argparse
import gc
import os
import resource
import sys
import time
import tracemalloc
import unittest
import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Set


# Default memory limit in MB (500 MB is reasonable for most test suites)
DEFAULT_MEMORY_LIMIT_MB = 500

# Warning threshold as percentage of limit (warn at 80%)
WARNING_THRESHOLD_PERCENT = 80


def get_memory_usage_mb() -> float:
    """Get current memory usage in MB using resource module.

    Returns:
        Current memory usage in megabytes.

    Note:
        Uses maxrss (maximum resident set size) which on Linux is in KB.
    """
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # maxrss is in KB on Linux
    return usage.ru_maxrss / 1024


def force_gc() -> int:
    """Force garbage collection and return number of objects freed.

    This function runs multiple GC passes to ensure circular references
    are cleaned up.

    Returns:
        Total number of objects collected across all generations.
    """
    total_collected = 0
    # Run GC multiple times to catch circular references
    for _ in range(3):
        collected = gc.collect()
        total_collected += collected
        if collected == 0:
            break
    return total_collected


@dataclass
class MemorySnapshot:
    """A snapshot of memory state at a point in time."""
    timestamp: datetime
    memory_mb: float
    context: str = ""

    def __str__(self) -> str:
        return f"[{self.timestamp.strftime('%H:%M:%S')}] {self.memory_mb:.1f} MB - {self.context}"


@dataclass
class MemoryStats:
    """Statistics about memory usage during test execution."""
    start_memory_mb: float = 0.0
    peak_memory_mb: float = 0.0
    end_memory_mb: float = 0.0
    warnings_issued: int = 0
    gc_collections: int = 0
    objects_collected: int = 0
    snapshots: List[MemorySnapshot] = field(default_factory=list)

    @property
    def total_growth_mb(self) -> float:
        """Total memory growth from start to end."""
        return self.end_memory_mb - self.start_memory_mb

    def add_snapshot(self, context: str = "") -> MemorySnapshot:
        """Take a memory snapshot and add it to the list."""
        snapshot = MemorySnapshot(
            timestamp=datetime.now(),
            memory_mb=get_memory_usage_mb(),
            context=context
        )
        self.snapshots.append(snapshot)
        if snapshot.memory_mb > self.peak_memory_mb:
            self.peak_memory_mb = snapshot.memory_mb
        return snapshot


class MemoryWarning(UserWarning):
    """Warning issued when memory usage exceeds threshold."""
    pass


class MemoryLimitExceeded(Exception):
    """Exception raised when memory limit is exceeded and enforcement is strict."""
    pass


class GCBetweenClassesSuite(unittest.TestSuite):
    """Test suite that forces garbage collection between test classes.

    This suite wrapper runs gc.collect() after each test class completes,
    preventing memory accumulation from cross-class object references.

    Example:
        loader = unittest.TestLoader()
        suite = loader.discover('.')
        gc_suite = GCBetweenClassesSuite(suite)
        unittest.TextTestRunner().run(gc_suite)
    """

    def __init__(self, tests=(), verbose: bool = False):
        """Initialize the suite.

        Args:
            tests: Test cases or suites to include
            verbose: If True, print GC statistics after each class
        """
        super().__init__(tests)
        self.verbose = verbose
        self._last_class = None
        self._gc_stats = MemoryStats()

    def run(self, result, debug=False):
        """Run tests with GC between classes."""
        self._gc_stats.start_memory_mb = get_memory_usage_mb()

        for index, test in enumerate(self):
            if result.shouldStop:
                break

            # Detect class change
            current_class = test.__class__ if hasattr(test, '__class__') else None
            if current_class != self._last_class and self._last_class is not None:
                self._run_gc_between_classes()
            self._last_class = current_class

            # Run the test
            if hasattr(test, '__call__'):
                test(result)
            elif hasattr(test, 'run'):
                test.run(result, debug)
            else:
                test.debug() if debug else test(result)

        # Final GC after all tests
        self._run_gc_between_classes()
        self._gc_stats.end_memory_mb = get_memory_usage_mb()

        return result

    def _run_gc_between_classes(self):
        """Run garbage collection and optionally report stats."""
        mem_before = get_memory_usage_mb()
        collected = force_gc()
        mem_after = get_memory_usage_mb()

        self._gc_stats.gc_collections += 1
        self._gc_stats.objects_collected += collected

        if self.verbose:
            freed = mem_before - mem_after
            print(f"\n  [GC] Collected {collected} objects, "
                  f"freed {freed:.1f} MB "
                  f"(before: {mem_before:.1f} MB, after: {mem_after:.1f} MB)")

    @property
    def gc_stats(self) -> MemoryStats:
        """Get garbage collection statistics."""
        return self._gc_stats


class MemoryMonitoringResult(unittest.TestResult):
    """Test result that monitors memory usage during test execution.

    This result class tracks memory before and after each test, issues
    warnings when thresholds are exceeded, and can optionally fail tests
    that exceed memory limits.

    Attributes:
        memory_stats: MemoryStats object with usage statistics
        memory_limit_mb: Maximum allowed memory usage
        strict: If True, fail tests that exceed memory limit
    """

    def __init__(
        self,
        stream=None,
        descriptions=True,
        verbosity=1,
        memory_limit_mb: float = DEFAULT_MEMORY_LIMIT_MB,
        strict: bool = False,
        warn_threshold_percent: float = WARNING_THRESHOLD_PERCENT,
    ):
        super().__init__(stream, descriptions, verbosity)
        self.memory_limit_mb = memory_limit_mb
        self.strict = strict
        self.warn_threshold_percent = warn_threshold_percent
        self.memory_stats = MemoryStats()
        self._warned_tests: Set[str] = set()

    @property
    def warning_threshold_mb(self) -> float:
        """Memory threshold at which to issue warnings."""
        return self.memory_limit_mb * (self.warn_threshold_percent / 100)

    def startTestRun(self):
        """Called once before any tests are executed."""
        super().startTestRun()
        self.memory_stats.start_memory_mb = get_memory_usage_mb()
        self.memory_stats.peak_memory_mb = self.memory_stats.start_memory_mb
        self.memory_stats.add_snapshot("test run started")

    def stopTestRun(self):
        """Called once after all tests are executed."""
        super().stopTestRun()
        self.memory_stats.end_memory_mb = get_memory_usage_mb()
        self.memory_stats.add_snapshot("test run completed")

    def startTest(self, test):
        """Called before each test."""
        super().startTest(test)
        self._check_memory(f"before {test}")

    def stopTest(self, test):
        """Called after each test."""
        super().stopTest(test)
        self._check_memory(f"after {test}")

    def _check_memory(self, context: str):
        """Check memory usage and issue warnings/errors if needed."""
        current_mb = get_memory_usage_mb()
        self.memory_stats.add_snapshot(context)

        # Update peak
        if current_mb > self.memory_stats.peak_memory_mb:
            self.memory_stats.peak_memory_mb = current_mb

        # Check if we should warn
        if current_mb >= self.warning_threshold_mb:
            # Only warn once per unique context to avoid spam
            warn_key = f"{context[:50]}_{int(current_mb)}"
            if warn_key not in self._warned_tests:
                self._warned_tests.add(warn_key)
                self.memory_stats.warnings_issued += 1

                msg = (
                    f"Memory usage ({current_mb:.1f} MB) exceeds "
                    f"{self.warn_threshold_percent}% of limit "
                    f"({self.memory_limit_mb:.0f} MB) - {context}"
                )
                warnings.warn(msg, MemoryWarning, stacklevel=4)

        # Check if we should fail (strict mode)
        if self.strict and current_mb >= self.memory_limit_mb:
            raise MemoryLimitExceeded(
                f"Memory usage ({current_mb:.1f} MB) exceeds limit "
                f"({self.memory_limit_mb:.0f} MB) - {context}"
            )


class MemorySafeTestRunner(unittest.TextTestRunner):
    """Test runner with memory monitoring and safeguards.

    This runner extends TextTestRunner with:
    - Memory usage monitoring with configurable limits
    - Warnings when memory threshold is exceeded
    - Optional strict mode to fail tests exceeding limits
    - Automatic garbage collection between test classes
    - Summary statistics at the end of the run

    Example:
        runner = MemorySafeTestRunner(
            memory_limit_mb=500,
            gc_between_classes=True,
            verbosity=2
        )
        suite = unittest.TestLoader().discover('.')
        result = runner.run(suite)
    """

    def __init__(
        self,
        stream=None,
        descriptions=True,
        verbosity=1,
        failfast=False,
        buffer=False,
        resultclass=None,
        warnings=None,
        tb_locals=False,
        memory_limit_mb: float = DEFAULT_MEMORY_LIMIT_MB,
        gc_between_classes: bool = True,
        strict_memory: bool = False,
        warn_threshold_percent: float = WARNING_THRESHOLD_PERCENT,
    ):
        super().__init__(
            stream=stream,
            descriptions=descriptions,
            verbosity=verbosity,
            failfast=failfast,
            buffer=buffer,
            resultclass=resultclass,
            warnings=warnings,
            tb_locals=tb_locals,
        )
        self.memory_limit_mb = memory_limit_mb
        self.gc_between_classes = gc_between_classes
        self.strict_memory = strict_memory
        self.warn_threshold_percent = warn_threshold_percent

    def _makeResult(self):
        """Create a memory-monitoring result object."""
        return MemoryMonitoringResult(
            stream=self.stream,
            descriptions=self.descriptions,
            verbosity=self.verbosity,
            memory_limit_mb=self.memory_limit_mb,
            strict=self.strict_memory,
            warn_threshold_percent=self.warn_threshold_percent,
        )

    def run(self, test):
        """Run the test suite with memory monitoring."""
        # Wrap suite with GC between classes if enabled
        if self.gc_between_classes and not isinstance(test, GCBetweenClassesSuite):
            test = GCBetweenClassesSuite(test, verbose=self.verbosity >= 2)

        # Run tests
        result = super().run(test)

        # Print memory summary
        self._print_memory_summary(result, test)

        return result

    def _print_memory_summary(self, result, suite):
        """Print memory usage summary after test run."""
        stats = result.memory_stats

        self.stream.writeln("\n" + "=" * 70)
        self.stream.writeln("MEMORY USAGE SUMMARY")
        self.stream.writeln("=" * 70)
        self.stream.writeln(f"  Start memory:    {stats.start_memory_mb:.1f} MB")
        self.stream.writeln(f"  End memory:      {stats.end_memory_mb:.1f} MB")
        self.stream.writeln(f"  Peak memory:     {stats.peak_memory_mb:.1f} MB")
        self.stream.writeln(f"  Memory growth:   {stats.total_growth_mb:.1f} MB")
        self.stream.writeln(f"  Memory limit:    {self.memory_limit_mb:.0f} MB")
        self.stream.writeln(f"  Warnings issued: {stats.warnings_issued}")

        if isinstance(suite, GCBetweenClassesSuite):
            gc_stats = suite.gc_stats
            self.stream.writeln(f"  GC collections:  {gc_stats.gc_collections}")
            self.stream.writeln(f"  Objects freed:   {gc_stats.objects_collected}")

        # Status indicator
        if stats.peak_memory_mb >= self.memory_limit_mb:
            self.stream.writeln("\n  STATUS: EXCEEDED MEMORY LIMIT")
        elif stats.peak_memory_mb >= self.memory_limit_mb * 0.8:
            self.stream.writeln("\n  STATUS: WARNING - High memory usage")
        else:
            self.stream.writeln("\n  STATUS: OK - Memory usage within limits")

        self.stream.writeln("=" * 70)


class MemoryMonitorMixin:
    """Mixin for test classes that need memory monitoring.

    This mixin provides methods for tracking memory usage within individual
    tests or test classes.

    Example:
        class MyTest(MemoryMonitorMixin, unittest.TestCase):
            def test_memory_intensive(self):
                self.start_memory_tracking()
                # ... do memory-intensive work ...
                growth = self.get_memory_growth()
                self.assertLess(growth, 100, "Memory growth exceeded 100 MB")
    """

    _memory_tracking_start: Optional[float] = None
    _memory_snapshots: List[MemorySnapshot] = []

    def start_memory_tracking(self):
        """Start tracking memory for this test."""
        force_gc()  # Clean slate
        self._memory_tracking_start = get_memory_usage_mb()
        self._memory_snapshots = [
            MemorySnapshot(datetime.now(), self._memory_tracking_start, "tracking started")
        ]

    def take_memory_snapshot(self, context: str = "") -> MemorySnapshot:
        """Take a memory snapshot and return it."""
        snapshot = MemorySnapshot(datetime.now(), get_memory_usage_mb(), context)
        self._memory_snapshots.append(snapshot)
        return snapshot

    def get_memory_growth(self) -> float:
        """Get memory growth since tracking started.

        Returns:
            Memory growth in MB since start_memory_tracking() was called.

        Raises:
            RuntimeError: If start_memory_tracking() was not called.
        """
        if self._memory_tracking_start is None:
            raise RuntimeError("start_memory_tracking() must be called first")
        force_gc()  # Ensure accurate measurement
        current = get_memory_usage_mb()
        return current - self._memory_tracking_start

    def get_memory_snapshots(self) -> List[MemorySnapshot]:
        """Get all memory snapshots taken during this test."""
        return self._memory_snapshots.copy()

    def assertMemoryGrowthLessThan(self, max_growth_mb: float, msg: str = None):
        """Assert that memory growth is less than specified amount.

        Args:
            max_growth_mb: Maximum allowed memory growth in MB
            msg: Optional message to include in assertion error
        """
        growth = self.get_memory_growth()
        if msg is None:
            msg = f"Memory growth ({growth:.1f} MB) exceeds limit ({max_growth_mb:.1f} MB)"
        self.assertLess(growth, max_growth_mb, msg)


@contextmanager
def memory_limit_context(limit_mb: float, strict: bool = False):
    """Context manager that monitors memory usage and warns/fails if exceeded.

    Args:
        limit_mb: Memory limit in MB
        strict: If True, raise MemoryLimitExceeded if limit is exceeded

    Example:
        with memory_limit_context(100) as monitor:
            # Do memory-intensive work
            large_list = [i for i in range(1000000)]
        print(f"Peak memory: {monitor.peak_memory_mb} MB")
    """
    force_gc()
    stats = MemoryStats()
    stats.start_memory_mb = get_memory_usage_mb()
    stats.peak_memory_mb = stats.start_memory_mb

    try:
        yield stats
    finally:
        force_gc()
        stats.end_memory_mb = get_memory_usage_mb()

        # Check final memory
        if stats.peak_memory_mb >= limit_mb:
            msg = f"Memory usage ({stats.peak_memory_mb:.1f} MB) exceeded limit ({limit_mb:.0f} MB)"
            if strict:
                raise MemoryLimitExceeded(msg)
            else:
                warnings.warn(msg, MemoryWarning)


def run_tests_with_memory_monitoring(
    test_pattern: str = "test_*.py",
    start_dir: str = ".",
    memory_limit_mb: float = DEFAULT_MEMORY_LIMIT_MB,
    gc_between_classes: bool = True,
    strict: bool = False,
    verbosity: int = 2,
) -> unittest.TestResult:
    """Convenience function to run tests with memory monitoring.

    Args:
        test_pattern: Pattern to match test files
        start_dir: Directory to start test discovery
        memory_limit_mb: Memory limit in MB
        gc_between_classes: Run GC between test classes
        strict: Fail if memory limit exceeded
        verbosity: Output verbosity level

    Returns:
        TestResult object with test outcomes and memory stats
    """
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir, pattern=test_pattern)

    runner = MemorySafeTestRunner(
        memory_limit_mb=memory_limit_mb,
        gc_between_classes=gc_between_classes,
        strict_memory=strict,
        verbosity=verbosity,
    )

    return runner.run(suite)


def main():
    """Command-line interface for memory-safe test runner."""
    parser = argparse.ArgumentParser(
        description="Run tests with memory monitoring and safeguards",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run all tests with default memory limit (500 MB)
    python3 memory_safe_runner.py

    # Run specific test file with 200 MB limit
    python3 memory_safe_runner.py --memory-limit 200 test_cmd_workflow

    # Run with strict mode (fail if limit exceeded)
    python3 memory_safe_runner.py --strict --memory-limit 300

    # Disable GC between classes
    python3 memory_safe_runner.py --no-gc-between-classes

    # Run with verbose output
    python3 memory_safe_runner.py -v
"""
    )
    parser.add_argument(
        "tests",
        nargs="*",
        default=[],
        help="Test modules, classes, or methods to run (default: discover all)"
    )
    parser.add_argument(
        "--memory-limit", "-m",
        type=float,
        default=DEFAULT_MEMORY_LIMIT_MB,
        metavar="MB",
        help=f"Memory limit in MB (default: {DEFAULT_MEMORY_LIMIT_MB})"
    )
    parser.add_argument(
        "--warn-threshold", "-w",
        type=float,
        default=WARNING_THRESHOLD_PERCENT,
        metavar="PERCENT",
        help=f"Warning threshold as %% of limit (default: {WARNING_THRESHOLD_PERCENT})"
    )
    parser.add_argument(
        "--strict", "-s",
        action="store_true",
        help="Fail tests that exceed memory limit"
    )
    parser.add_argument(
        "--no-gc-between-classes",
        action="store_true",
        help="Disable garbage collection between test classes"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="count",
        default=1,
        help="Increase output verbosity"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Quiet output (only show errors)"
    )
    parser.add_argument(
        "--pattern", "-p",
        default="test_*.py",
        help="Pattern to match test files (default: test_*.py)"
    )
    parser.add_argument(
        "--start-dir", "-d",
        default=".",
        help="Directory to start test discovery (default: .)"
    )

    args = parser.parse_args()

    # Determine verbosity
    verbosity = 0 if args.quiet else args.verbose

    print(f"Memory Safe Test Runner")
    print(f"  Memory limit: {args.memory_limit:.0f} MB")
    print(f"  Warning threshold: {args.warn_threshold:.0f}%")
    print(f"  Strict mode: {'Yes' if args.strict else 'No'}")
    print(f"  GC between classes: {'No' if args.no_gc_between_classes else 'Yes'}")
    print()

    # Create runner
    runner = MemorySafeTestRunner(
        memory_limit_mb=args.memory_limit,
        gc_between_classes=not args.no_gc_between_classes,
        strict_memory=args.strict,
        warn_threshold_percent=args.warn_threshold,
        verbosity=verbosity,
    )

    # Load tests
    loader = unittest.TestLoader()
    if args.tests:
        # Load specific tests
        suite = unittest.TestSuite()
        for test_spec in args.tests:
            try:
                # Try loading as module first
                tests = loader.loadTestsFromName(test_spec)
                suite.addTests(tests)
            except (ImportError, AttributeError):
                # Try loading as file pattern
                tests = loader.discover(args.start_dir, pattern=test_spec)
                suite.addTests(tests)
    else:
        # Discover all tests
        suite = loader.discover(args.start_dir, pattern=args.pattern)

    # Run tests
    result = runner.run(suite)

    # Exit code
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
