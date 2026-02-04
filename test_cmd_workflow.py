#!/usr/bin/env python3
"""Tests for swarm workflow command - TDD tests for workflow dataclasses and commands."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import swarm


class TestStageStateDataclass(unittest.TestCase):
    """Test StageState dataclass creation and serialization."""

    def test_create_with_defaults(self):
        """Test creating StageState with default values."""
        stage = swarm.StageState()
        self.assertEqual(stage.status, "pending")
        self.assertIsNone(stage.started_at)
        self.assertIsNone(stage.completed_at)
        self.assertIsNone(stage.worker_name)
        self.assertEqual(stage.attempts, 0)
        self.assertIsNone(stage.exit_reason)

    def test_create_with_all_fields(self):
        """Test creating StageState with all fields populated."""
        stage = swarm.StageState(
            status="running",
            started_at="2026-02-04T10:00:00Z",
            completed_at="2026-02-04T11:00:00Z",
            worker_name="my-workflow-plan",
            attempts=2,
            exit_reason="done_pattern",
        )
        self.assertEqual(stage.status, "running")
        self.assertEqual(stage.started_at, "2026-02-04T10:00:00Z")
        self.assertEqual(stage.completed_at, "2026-02-04T11:00:00Z")
        self.assertEqual(stage.worker_name, "my-workflow-plan")
        self.assertEqual(stage.attempts, 2)
        self.assertEqual(stage.exit_reason, "done_pattern")

    def test_to_dict(self):
        """Test converting StageState to dictionary."""
        stage = swarm.StageState(
            status="completed",
            started_at="2026-02-04T10:00:00Z",
            completed_at="2026-02-04T11:00:00Z",
            worker_name="my-workflow-plan",
            attempts=1,
            exit_reason="done_pattern",
        )
        d = stage.to_dict()
        self.assertEqual(d["status"], "completed")
        self.assertEqual(d["started_at"], "2026-02-04T10:00:00Z")
        self.assertEqual(d["completed_at"], "2026-02-04T11:00:00Z")
        self.assertEqual(d["worker_name"], "my-workflow-plan")
        self.assertEqual(d["attempts"], 1)
        self.assertEqual(d["exit_reason"], "done_pattern")

    def test_to_dict_with_defaults(self):
        """Test converting StageState with defaults to dictionary."""
        stage = swarm.StageState()
        d = stage.to_dict()
        self.assertEqual(d["status"], "pending")
        self.assertIsNone(d["started_at"])
        self.assertIsNone(d["completed_at"])
        self.assertIsNone(d["worker_name"])
        self.assertEqual(d["attempts"], 0)
        self.assertIsNone(d["exit_reason"])

    def test_from_dict(self):
        """Test creating StageState from dictionary."""
        d = {
            "status": "failed",
            "started_at": "2026-02-04T10:00:00Z",
            "completed_at": "2026-02-04T10:30:00Z",
            "worker_name": "my-workflow-build",
            "attempts": 3,
            "exit_reason": "timeout",
        }
        stage = swarm.StageState.from_dict(d)
        self.assertEqual(stage.status, "failed")
        self.assertEqual(stage.started_at, "2026-02-04T10:00:00Z")
        self.assertEqual(stage.completed_at, "2026-02-04T10:30:00Z")
        self.assertEqual(stage.worker_name, "my-workflow-build")
        self.assertEqual(stage.attempts, 3)
        self.assertEqual(stage.exit_reason, "timeout")

    def test_from_dict_with_minimal_data(self):
        """Test creating StageState from dictionary with minimal fields."""
        d = {}
        stage = swarm.StageState.from_dict(d)
        self.assertEqual(stage.status, "pending")
        self.assertIsNone(stage.started_at)
        self.assertIsNone(stage.completed_at)
        self.assertIsNone(stage.worker_name)
        self.assertEqual(stage.attempts, 0)
        self.assertIsNone(stage.exit_reason)

    def test_from_dict_partial_data(self):
        """Test creating StageState from dictionary with partial fields."""
        d = {"status": "running", "attempts": 1}
        stage = swarm.StageState.from_dict(d)
        self.assertEqual(stage.status, "running")
        self.assertIsNone(stage.started_at)
        self.assertEqual(stage.attempts, 1)

    def test_roundtrip_serialization(self):
        """Test that to_dict/from_dict round-trip preserves data."""
        original = swarm.StageState(
            status="skipped",
            started_at="2026-02-04T10:00:00Z",
            completed_at=None,
            worker_name="test-worker",
            attempts=0,
            exit_reason="skipped",
        )
        d = original.to_dict()
        restored = swarm.StageState.from_dict(d)
        self.assertEqual(original.status, restored.status)
        self.assertEqual(original.started_at, restored.started_at)
        self.assertEqual(original.completed_at, restored.completed_at)
        self.assertEqual(original.worker_name, restored.worker_name)
        self.assertEqual(original.attempts, restored.attempts)
        self.assertEqual(original.exit_reason, restored.exit_reason)

    def test_all_status_values(self):
        """Test all valid status values can be set."""
        statuses = ["pending", "running", "completed", "failed", "skipped"]
        for status in statuses:
            stage = swarm.StageState(status=status)
            self.assertEqual(stage.status, status)

    def test_all_exit_reason_values(self):
        """Test all valid exit_reason values can be set."""
        reasons = ["done_pattern", "timeout", "error", "skipped", None]
        for reason in reasons:
            stage = swarm.StageState(exit_reason=reason)
            self.assertEqual(stage.exit_reason, reason)


class TestWorkflowStateDataclass(unittest.TestCase):
    """Test WorkflowState dataclass creation and serialization."""

    def test_create_with_minimal_fields(self):
        """Test creating WorkflowState with minimal required fields."""
        workflow = swarm.WorkflowState(name="my-workflow")
        self.assertEqual(workflow.name, "my-workflow")
        self.assertEqual(workflow.status, "created")
        self.assertIsNone(workflow.current_stage)
        self.assertEqual(workflow.current_stage_index, 0)
        self.assertEqual(workflow.created_at, "")
        self.assertIsNone(workflow.started_at)
        self.assertIsNone(workflow.scheduled_for)
        self.assertIsNone(workflow.completed_at)
        self.assertEqual(workflow.stages, {})
        self.assertEqual(workflow.workflow_file, "")
        self.assertEqual(workflow.workflow_hash, "")

    def test_create_with_all_fields(self):
        """Test creating WorkflowState with all fields populated."""
        stages = {
            "plan": swarm.StageState(status="completed"),
            "build": swarm.StageState(status="running"),
        }
        workflow = swarm.WorkflowState(
            name="feature-build",
            status="running",
            current_stage="build",
            current_stage_index=1,
            created_at="2026-02-04T02:00:00Z",
            started_at="2026-02-04T02:00:00Z",
            scheduled_for=None,
            completed_at=None,
            stages=stages,
            workflow_file="/home/user/workflow.yaml",
            workflow_hash="abc123",
        )
        self.assertEqual(workflow.name, "feature-build")
        self.assertEqual(workflow.status, "running")
        self.assertEqual(workflow.current_stage, "build")
        self.assertEqual(workflow.current_stage_index, 1)
        self.assertEqual(workflow.created_at, "2026-02-04T02:00:00Z")
        self.assertEqual(workflow.started_at, "2026-02-04T02:00:00Z")
        self.assertIsNone(workflow.scheduled_for)
        self.assertIsNone(workflow.completed_at)
        self.assertEqual(len(workflow.stages), 2)
        self.assertEqual(workflow.stages["plan"].status, "completed")
        self.assertEqual(workflow.stages["build"].status, "running")
        self.assertEqual(workflow.workflow_file, "/home/user/workflow.yaml")
        self.assertEqual(workflow.workflow_hash, "abc123")

    def test_to_dict(self):
        """Test converting WorkflowState to dictionary."""
        stages = {
            "plan": swarm.StageState(status="completed", attempts=1),
            "build": swarm.StageState(status="pending"),
        }
        workflow = swarm.WorkflowState(
            name="test-workflow",
            status="running",
            current_stage="plan",
            current_stage_index=0,
            created_at="2026-02-04T10:00:00Z",
            started_at="2026-02-04T10:00:00Z",
            stages=stages,
            workflow_file="/path/to/workflow.yaml",
            workflow_hash="hash123",
        )
        d = workflow.to_dict()
        self.assertEqual(d["name"], "test-workflow")
        self.assertEqual(d["status"], "running")
        self.assertEqual(d["current_stage"], "plan")
        self.assertEqual(d["current_stage_index"], 0)
        self.assertEqual(d["created_at"], "2026-02-04T10:00:00Z")
        self.assertEqual(d["started_at"], "2026-02-04T10:00:00Z")
        self.assertIsNone(d["scheduled_for"])
        self.assertIsNone(d["completed_at"])
        self.assertIn("plan", d["stages"])
        self.assertIn("build", d["stages"])
        self.assertEqual(d["stages"]["plan"]["status"], "completed")
        self.assertEqual(d["stages"]["plan"]["attempts"], 1)
        self.assertEqual(d["stages"]["build"]["status"], "pending")
        self.assertEqual(d["workflow_file"], "/path/to/workflow.yaml")
        self.assertEqual(d["workflow_hash"], "hash123")

    def test_to_dict_empty_stages(self):
        """Test converting WorkflowState with no stages to dictionary."""
        workflow = swarm.WorkflowState(name="empty-workflow")
        d = workflow.to_dict()
        self.assertEqual(d["stages"], {})

    def test_from_dict(self):
        """Test creating WorkflowState from dictionary."""
        d = {
            "name": "restored-workflow",
            "status": "completed",
            "current_stage": None,
            "current_stage_index": 2,
            "created_at": "2026-02-04T10:00:00Z",
            "started_at": "2026-02-04T10:00:00Z",
            "scheduled_for": None,
            "completed_at": "2026-02-04T12:00:00Z",
            "stages": {
                "plan": {"status": "completed", "attempts": 1, "exit_reason": "done_pattern"},
                "build": {"status": "completed", "attempts": 2, "exit_reason": "done_pattern"},
            },
            "workflow_file": "/path/to/workflow.yaml",
            "workflow_hash": "abc123",
        }
        workflow = swarm.WorkflowState.from_dict(d)
        self.assertEqual(workflow.name, "restored-workflow")
        self.assertEqual(workflow.status, "completed")
        self.assertIsNone(workflow.current_stage)
        self.assertEqual(workflow.current_stage_index, 2)
        self.assertEqual(workflow.created_at, "2026-02-04T10:00:00Z")
        self.assertEqual(workflow.started_at, "2026-02-04T10:00:00Z")
        self.assertIsNone(workflow.scheduled_for)
        self.assertEqual(workflow.completed_at, "2026-02-04T12:00:00Z")
        self.assertEqual(len(workflow.stages), 2)
        self.assertIsInstance(workflow.stages["plan"], swarm.StageState)
        self.assertEqual(workflow.stages["plan"].status, "completed")
        self.assertEqual(workflow.stages["plan"].attempts, 1)
        self.assertEqual(workflow.stages["build"].status, "completed")
        self.assertEqual(workflow.stages["build"].attempts, 2)
        self.assertEqual(workflow.workflow_file, "/path/to/workflow.yaml")
        self.assertEqual(workflow.workflow_hash, "abc123")

    def test_from_dict_minimal_data(self):
        """Test creating WorkflowState from dictionary with minimal fields."""
        d = {"name": "minimal-workflow"}
        workflow = swarm.WorkflowState.from_dict(d)
        self.assertEqual(workflow.name, "minimal-workflow")
        self.assertEqual(workflow.status, "created")
        self.assertIsNone(workflow.current_stage)
        self.assertEqual(workflow.current_stage_index, 0)
        self.assertEqual(workflow.created_at, "")
        self.assertEqual(workflow.stages, {})
        self.assertEqual(workflow.workflow_file, "")
        self.assertEqual(workflow.workflow_hash, "")

    def test_from_dict_missing_stages(self):
        """Test creating WorkflowState when stages key is missing."""
        d = {"name": "no-stages-workflow", "status": "created"}
        workflow = swarm.WorkflowState.from_dict(d)
        self.assertEqual(workflow.name, "no-stages-workflow")
        self.assertEqual(workflow.stages, {})

    def test_roundtrip_serialization(self):
        """Test that to_dict/from_dict round-trip preserves data."""
        original = swarm.WorkflowState(
            name="roundtrip-workflow",
            status="scheduled",
            current_stage=None,
            current_stage_index=0,
            created_at="2026-02-04T10:00:00Z",
            started_at=None,
            scheduled_for="2026-02-05T02:00:00Z",
            completed_at=None,
            stages={
                "stage1": swarm.StageState(status="pending"),
                "stage2": swarm.StageState(status="pending"),
            },
            workflow_file="/path/workflow.yaml",
            workflow_hash="xyz789",
        )
        d = original.to_dict()
        restored = swarm.WorkflowState.from_dict(d)
        self.assertEqual(original.name, restored.name)
        self.assertEqual(original.status, restored.status)
        self.assertEqual(original.current_stage, restored.current_stage)
        self.assertEqual(original.current_stage_index, restored.current_stage_index)
        self.assertEqual(original.created_at, restored.created_at)
        self.assertEqual(original.started_at, restored.started_at)
        self.assertEqual(original.scheduled_for, restored.scheduled_for)
        self.assertEqual(original.completed_at, restored.completed_at)
        self.assertEqual(len(original.stages), len(restored.stages))
        for name in original.stages:
            self.assertEqual(original.stages[name].status, restored.stages[name].status)
        self.assertEqual(original.workflow_file, restored.workflow_file)
        self.assertEqual(original.workflow_hash, restored.workflow_hash)

    def test_all_status_values(self):
        """Test all valid workflow status values can be set."""
        statuses = ["created", "scheduled", "running", "completed", "failed", "cancelled"]
        for status in statuses:
            workflow = swarm.WorkflowState(name="test", status=status)
            self.assertEqual(workflow.status, status)

    def test_json_serialization(self):
        """Test that to_dict produces JSON-serializable output."""
        workflow = swarm.WorkflowState(
            name="json-test",
            status="running",
            stages={
                "s1": swarm.StageState(status="completed"),
            },
        )
        d = workflow.to_dict()
        # Should not raise
        json_str = json.dumps(d)
        # Should be valid JSON
        parsed = json.loads(json_str)
        self.assertEqual(parsed["name"], "json-test")

    def test_stages_are_independent(self):
        """Test that stage states are independent objects."""
        stage1 = swarm.StageState(status="pending")
        stage2 = swarm.StageState(status="running")
        workflow = swarm.WorkflowState(
            name="test",
            stages={"s1": stage1, "s2": stage2},
        )
        # Modify original stage
        stage1.status = "completed"
        # Workflow stage should also be modified (they share the same object)
        self.assertEqual(workflow.stages["s1"].status, "completed")


class TestWorkflowStateEdgeCases(unittest.TestCase):
    """Test edge cases for workflow state handling."""

    def test_workflow_with_many_stages(self):
        """Test workflow with many stages."""
        stages = {}
        for i in range(20):
            stages[f"stage{i}"] = swarm.StageState(status="pending")
        workflow = swarm.WorkflowState(name="many-stages", stages=stages)
        d = workflow.to_dict()
        restored = swarm.WorkflowState.from_dict(d)
        self.assertEqual(len(restored.stages), 20)

    def test_stage_with_unicode_names(self):
        """Test stage with unicode characters in names."""
        stages = {
            "étape-1": swarm.StageState(status="completed"),
            "步骤-2": swarm.StageState(status="pending"),
        }
        workflow = swarm.WorkflowState(name="unicode-test", stages=stages)
        d = workflow.to_dict()
        restored = swarm.WorkflowState.from_dict(d)
        self.assertIn("étape-1", restored.stages)
        self.assertIn("步骤-2", restored.stages)

    def test_workflow_name_with_special_chars(self):
        """Test workflow name with special characters."""
        workflow = swarm.WorkflowState(name="test-workflow_v2.1")
        d = workflow.to_dict()
        restored = swarm.WorkflowState.from_dict(d)
        self.assertEqual(restored.name, "test-workflow_v2.1")

    def test_empty_workflow_hash(self):
        """Test workflow with empty hash is handled correctly."""
        workflow = swarm.WorkflowState(name="test", workflow_hash="")
        d = workflow.to_dict()
        self.assertEqual(d["workflow_hash"], "")
        restored = swarm.WorkflowState.from_dict(d)
        self.assertEqual(restored.workflow_hash, "")


if __name__ == "__main__":
    unittest.main()
