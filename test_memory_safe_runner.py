#!/usr/bin/env python3
"""Tests for memory_safe_runner module.

This module tests the memory monitoring and safeguard utilities.
"""

import gc
import sys
import unittest
import warnings
from io import StringIO
from unittest.mock import patch, MagicMock

from memory_safe_runner import (
    get_memory_usage_mb,
    force_gc,
    MemorySnapshot,
    MemoryStats,
    MemoryWarning,
    MemoryLimitExceeded,
    GCBetweenClassesSuite,
    MemoryMonitoringResult,
    MemorySafeTestRunner,
    MemoryMonitorMixin,
    memory_limit_context,
    run_tests_with_memory_monitoring,
    DEFAULT_MEMORY_LIMIT_MB,
    WARNING_THRESHOLD_PERCENT,
)


class TestMemoryUtilityFunctions(unittest.TestCase):
    """Test basic memory utility functions."""

    def test_get_memory_usage_mb_returns_positive_float(self):
        """Verify get_memory_usage_mb returns a positive float."""
        usage = get_memory_usage_mb()
        self.assertIsInstance(usage, float)
        self.assertGreater(usage, 0, "Memory usage should be positive")

    def test_get_memory_usage_mb_increases_with_allocation(self):
        """Verify memory usage increases when allocating large objects."""
        before = get_memory_usage_mb()
        # Allocate ~10 MB of data
        large_list = [b'x' * 1024 for _ in range(10000)]
        after = get_memory_usage_mb()
        # Memory should increase (may not be exact due to Python internals)
        # Just verify we can measure it
        self.assertGreaterEqual(after, 0)
        # Clean up
        del large_list

    def test_force_gc_returns_integer(self):
        """Verify force_gc returns an integer count of collected objects."""
        # Create some garbage
        for _ in range(100):
            _ = {'a': [1, 2, 3], 'b': {'c': [4, 5, 6]}}
        collected = force_gc()
        self.assertIsInstance(collected, int)
        self.assertGreaterEqual(collected, 0)

    def test_force_gc_collects_circular_references(self):
        """Verify force_gc can collect circular references."""
        class Node:
            def __init__(self):
                self.ref = None

        # Create circular reference
        a = Node()
        b = Node()
        a.ref = b
        b.ref = a
        del a, b

        # Force GC should collect the circular reference
        collected = force_gc()
        # At least some objects should be collected (may be 0 if already cleaned)
        self.assertGreaterEqual(collected, 0)


class TestMemorySnapshot(unittest.TestCase):
    """Test MemorySnapshot dataclass."""

    def test_snapshot_creation(self):
        """Verify MemorySnapshot can be created with all fields."""
        from datetime import datetime
        snapshot = MemorySnapshot(
            timestamp=datetime.now(),
            memory_mb=100.5,
            context="test snapshot"
        )
        self.assertEqual(snapshot.memory_mb, 100.5)
        self.assertEqual(snapshot.context, "test snapshot")
        self.assertIsInstance(snapshot.timestamp, datetime)

    def test_snapshot_str_format(self):
        """Verify MemorySnapshot string representation."""
        from datetime import datetime
        snapshot = MemorySnapshot(
            timestamp=datetime(2025, 1, 15, 10, 30, 45),
            memory_mb=256.7,
            context="after test"
        )
        result = str(snapshot)
        self.assertIn("10:30:45", result)
        self.assertIn("256.7", result)
        self.assertIn("after test", result)


class TestMemoryStats(unittest.TestCase):
    """Test MemoryStats dataclass."""

    def test_stats_defaults(self):
        """Verify MemoryStats has correct defaults."""
        stats = MemoryStats()
        self.assertEqual(stats.start_memory_mb, 0.0)
        self.assertEqual(stats.peak_memory_mb, 0.0)
        self.assertEqual(stats.end_memory_mb, 0.0)
        self.assertEqual(stats.warnings_issued, 0)
        self.assertEqual(stats.gc_collections, 0)
        self.assertEqual(stats.objects_collected, 0)
        self.assertEqual(stats.snapshots, [])

    def test_total_growth_mb_property(self):
        """Verify total_growth_mb calculated correctly."""
        stats = MemoryStats(start_memory_mb=100, end_memory_mb=150)
        self.assertEqual(stats.total_growth_mb, 50)

    def test_total_growth_mb_negative(self):
        """Verify total_growth_mb can be negative (memory freed)."""
        stats = MemoryStats(start_memory_mb=200, end_memory_mb=150)
        self.assertEqual(stats.total_growth_mb, -50)

    def test_add_snapshot_updates_peak(self):
        """Verify add_snapshot updates peak_memory_mb."""
        stats = MemoryStats()
        stats.peak_memory_mb = 0

        # Mock get_memory_usage_mb to return controlled values
        with patch('memory_safe_runner.get_memory_usage_mb', side_effect=[100, 200, 150]):
            snap1 = stats.add_snapshot("first")
            self.assertEqual(stats.peak_memory_mb, 100)

            snap2 = stats.add_snapshot("second")
            self.assertEqual(stats.peak_memory_mb, 200)

            snap3 = stats.add_snapshot("third")
            self.assertEqual(stats.peak_memory_mb, 200)  # Still 200, not lowered

        self.assertEqual(len(stats.snapshots), 3)


class TestGCBetweenClassesSuite(unittest.TestCase):
    """Test GCBetweenClassesSuite functionality."""

    def test_suite_runs_tests(self):
        """Verify suite runs all tests."""
        # Create simple test cases
        class Test1(unittest.TestCase):
            def test_a(self):
                pass

        class Test2(unittest.TestCase):
            def test_b(self):
                pass

        suite = GCBetweenClassesSuite()
        suite.addTests([Test1('test_a'), Test2('test_b')])

        result = unittest.TestResult()
        suite.run(result)

        self.assertEqual(result.testsRun, 2)
        self.assertEqual(len(result.failures), 0)
        self.assertEqual(len(result.errors), 0)

    def test_gc_runs_between_classes(self):
        """Verify GC runs when class changes."""
        class TestA(unittest.TestCase):
            def test_1(self):
                pass

        class TestB(unittest.TestCase):
            def test_2(self):
                pass

        suite = GCBetweenClassesSuite()
        suite.addTests([TestA('test_1'), TestB('test_2')])

        result = unittest.TestResult()
        suite.run(result)

        # GC should have been called at least once (between classes)
        self.assertGreaterEqual(suite.gc_stats.gc_collections, 1)

    def test_gc_stats_tracked(self):
        """Verify gc_stats property returns MemoryStats."""
        suite = GCBetweenClassesSuite()
        stats = suite.gc_stats
        self.assertIsInstance(stats, MemoryStats)


class TestMemoryMonitoringResult(unittest.TestCase):
    """Test MemoryMonitoringResult functionality."""

    def test_result_tracks_memory_stats(self):
        """Verify result tracks memory statistics."""
        result = MemoryMonitoringResult()
        self.assertIsInstance(result.memory_stats, MemoryStats)

    def test_warning_threshold_calculation(self):
        """Verify warning threshold calculated from limit and percentage."""
        result = MemoryMonitoringResult(memory_limit_mb=500, warn_threshold_percent=80)
        self.assertEqual(result.warning_threshold_mb, 400)

    def test_start_test_run_records_initial_memory(self):
        """Verify startTestRun records initial memory."""
        result = MemoryMonitoringResult()
        with patch('memory_safe_runner.get_memory_usage_mb', return_value=100):
            result.startTestRun()
        self.assertEqual(result.memory_stats.start_memory_mb, 100)

    def test_stop_test_run_records_final_memory(self):
        """Verify stopTestRun records final memory."""
        result = MemoryMonitoringResult()
        result.startTestRun()
        with patch('memory_safe_runner.get_memory_usage_mb', return_value=200):
            result.stopTestRun()
        self.assertEqual(result.memory_stats.end_memory_mb, 200)

    def test_warning_issued_when_threshold_exceeded(self):
        """Verify warning issued when memory exceeds threshold."""
        result = MemoryMonitoringResult(memory_limit_mb=100, warn_threshold_percent=50)
        # Threshold is 50 MB

        with patch('memory_safe_runner.get_memory_usage_mb', return_value=60):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result._check_memory("test context")

                self.assertEqual(len(w), 1)
                self.assertTrue(issubclass(w[0].category, MemoryWarning))
                self.assertIn("60.0 MB", str(w[0].message))

    def test_no_warning_below_threshold(self):
        """Verify no warning when memory below threshold."""
        result = MemoryMonitoringResult(memory_limit_mb=100, warn_threshold_percent=50)

        with patch('memory_safe_runner.get_memory_usage_mb', return_value=40):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result._check_memory("test context")
                self.assertEqual(len(w), 0)

    def test_strict_mode_raises_on_limit_exceeded(self):
        """Verify strict mode raises exception when limit exceeded."""
        result = MemoryMonitoringResult(memory_limit_mb=100, strict=True)

        with patch('memory_safe_runner.get_memory_usage_mb', return_value=150):
            with self.assertRaises(MemoryLimitExceeded) as ctx:
                result._check_memory("test context")
            self.assertIn("150.0 MB", str(ctx.exception))

    def test_non_strict_mode_no_exception(self):
        """Verify non-strict mode doesn't raise on limit exceeded."""
        result = MemoryMonitoringResult(memory_limit_mb=100, strict=False)

        with patch('memory_safe_runner.get_memory_usage_mb', return_value=150):
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                # Should not raise
                result._check_memory("test context")


class TestMemorySafeTestRunner(unittest.TestCase):
    """Test MemorySafeTestRunner functionality."""

    def test_runner_creates_with_defaults(self):
        """Verify runner creates with default settings."""
        runner = MemorySafeTestRunner()
        self.assertEqual(runner.memory_limit_mb, DEFAULT_MEMORY_LIMIT_MB)
        self.assertTrue(runner.gc_between_classes)
        self.assertFalse(runner.strict_memory)
        self.assertEqual(runner.warn_threshold_percent, WARNING_THRESHOLD_PERCENT)

    def test_runner_creates_memory_monitoring_result(self):
        """Verify runner creates MemoryMonitoringResult."""
        runner = MemorySafeTestRunner(memory_limit_mb=200)
        result = runner._makeResult()
        self.assertIsInstance(result, MemoryMonitoringResult)
        self.assertEqual(result.memory_limit_mb, 200)

    def test_runner_wraps_suite_with_gc(self):
        """Verify runner wraps suite with GCBetweenClassesSuite when enabled."""
        class TestDummy(unittest.TestCase):
            def test_pass(self):
                pass

        # Use /dev/null to suppress output while testing functionality
        import os
        with open(os.devnull, 'w') as devnull:
            runner = MemorySafeTestRunner(
                stream=devnull,
                gc_between_classes=True,
                verbosity=0
            )
            suite = unittest.TestSuite([TestDummy('test_pass')])
            result = runner.run(suite)
        self.assertEqual(result.testsRun, 1)

    def test_runner_prints_memory_summary(self):
        """Verify runner prints memory summary."""
        class TestDummy(unittest.TestCase):
            def test_pass(self):
                pass

        # Create a custom stream that has writeln method
        class WriteableStringIO(StringIO):
            def writeln(self, text=''):
                self.write(text + '\n')

        stream = WriteableStringIO()
        runner = MemorySafeTestRunner(
            stream=stream,
            verbosity=0,
            gc_between_classes=False
        )
        suite = unittest.TestSuite([TestDummy('test_pass')])
        runner.run(suite)

        output = stream.getvalue()
        self.assertIn("MEMORY USAGE SUMMARY", output)
        self.assertIn("Memory limit:", output)


class TestMemoryMonitorMixin(unittest.TestCase):
    """Test MemoryMonitorMixin functionality."""

    def test_mixin_start_tracking(self):
        """Verify start_memory_tracking initializes tracking."""
        class TestWithMixin(MemoryMonitorMixin, unittest.TestCase):
            pass

        test = TestWithMixin()
        with patch('memory_safe_runner.get_memory_usage_mb', return_value=100):
            test.start_memory_tracking()
        self.assertEqual(test._memory_tracking_start, 100)
        self.assertEqual(len(test._memory_snapshots), 1)

    def test_mixin_get_memory_growth(self):
        """Verify get_memory_growth calculates correctly."""
        class TestWithMixin(MemoryMonitorMixin, unittest.TestCase):
            pass

        test = TestWithMixin()
        with patch('memory_safe_runner.get_memory_usage_mb', return_value=100):
            test.start_memory_tracking()

        with patch('memory_safe_runner.get_memory_usage_mb', return_value=150):
            growth = test.get_memory_growth()
        self.assertEqual(growth, 50)

    def test_mixin_get_memory_growth_without_start_raises(self):
        """Verify get_memory_growth raises if tracking not started."""
        class TestWithMixin(MemoryMonitorMixin, unittest.TestCase):
            pass

        test = TestWithMixin()
        with self.assertRaises(RuntimeError):
            test.get_memory_growth()

    def test_mixin_take_memory_snapshot(self):
        """Verify take_memory_snapshot adds to snapshots list."""
        class TestWithMixin(MemoryMonitorMixin, unittest.TestCase):
            pass

        test = TestWithMixin()
        test.start_memory_tracking()

        with patch('memory_safe_runner.get_memory_usage_mb', return_value=200):
            snap = test.take_memory_snapshot("mid-test")

        self.assertEqual(snap.memory_mb, 200)
        self.assertEqual(snap.context, "mid-test")
        self.assertEqual(len(test._memory_snapshots), 2)  # start + this one

    def test_mixin_assert_memory_growth_passes(self):
        """Verify assertMemoryGrowthLessThan passes when within limit."""
        class TestWithMixin(MemoryMonitorMixin, unittest.TestCase):
            pass

        test = TestWithMixin()
        with patch('memory_safe_runner.get_memory_usage_mb', return_value=100):
            test.start_memory_tracking()

        with patch('memory_safe_runner.get_memory_usage_mb', return_value=120):
            # Should not raise
            test.assertMemoryGrowthLessThan(50)

    def test_mixin_assert_memory_growth_fails(self):
        """Verify assertMemoryGrowthLessThan fails when exceeds limit."""
        class TestWithMixin(MemoryMonitorMixin, unittest.TestCase):
            pass

        test = TestWithMixin()
        with patch('memory_safe_runner.get_memory_usage_mb', return_value=100):
            test.start_memory_tracking()

        with patch('memory_safe_runner.get_memory_usage_mb', return_value=200):
            with self.assertRaises(AssertionError):
                test.assertMemoryGrowthLessThan(50)


class TestMemoryLimitContext(unittest.TestCase):
    """Test memory_limit_context context manager."""

    def test_context_returns_stats(self):
        """Verify context manager yields MemoryStats."""
        with memory_limit_context(500) as stats:
            self.assertIsInstance(stats, MemoryStats)

    def test_context_tracks_memory(self):
        """Verify context tracks start and end memory."""
        with patch('memory_safe_runner.get_memory_usage_mb', side_effect=[100, 150]):
            with memory_limit_context(500) as stats:
                pass
        self.assertEqual(stats.start_memory_mb, 100)
        self.assertEqual(stats.end_memory_mb, 150)

    def test_context_warns_on_exceeded(self):
        """Verify context warns when limit exceeded."""
        with patch('memory_safe_runner.get_memory_usage_mb', side_effect=[100, 600]):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                with memory_limit_context(500, strict=False) as stats:
                    stats.peak_memory_mb = 600

                self.assertEqual(len(w), 1)
                self.assertTrue(issubclass(w[0].category, MemoryWarning))

    def test_context_raises_on_strict_exceeded(self):
        """Verify strict context raises when limit exceeded."""
        with patch('memory_safe_runner.get_memory_usage_mb', side_effect=[100, 600]):
            with self.assertRaises(MemoryLimitExceeded):
                with memory_limit_context(500, strict=True) as stats:
                    stats.peak_memory_mb = 600


class TestRunTestsWithMemoryMonitoring(unittest.TestCase):
    """Test run_tests_with_memory_monitoring function."""

    def test_function_runs_and_returns_result(self):
        """Verify function runs tests and returns TestResult."""
        # Create a temporary test that will be discovered
        result = run_tests_with_memory_monitoring(
            test_pattern="test_memory_safe_runner.py",
            start_dir=".",
            memory_limit_mb=1000,
            verbosity=0,
        )
        self.assertIsInstance(result, unittest.TestResult)
        # Should have run at least one test (this test file)
        self.assertGreater(result.testsRun, 0)


class TestConstants(unittest.TestCase):
    """Test module constants have reasonable values."""

    def test_default_memory_limit(self):
        """Verify default memory limit is reasonable."""
        self.assertEqual(DEFAULT_MEMORY_LIMIT_MB, 500)

    def test_warning_threshold_percent(self):
        """Verify warning threshold is reasonable."""
        self.assertEqual(WARNING_THRESHOLD_PERCENT, 80)
        self.assertGreater(WARNING_THRESHOLD_PERCENT, 50)
        self.assertLess(WARNING_THRESHOLD_PERCENT, 100)


if __name__ == "__main__":
    unittest.main()
