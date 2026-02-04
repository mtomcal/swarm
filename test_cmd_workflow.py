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


class TestStageDefinitionDataclass(unittest.TestCase):
    """Test StageDefinition dataclass creation and serialization."""

    def test_create_with_minimal_fields(self):
        """Test creating StageDefinition with minimal required fields."""
        stage = swarm.StageDefinition(name="plan", type="worker", prompt="Do the task")
        self.assertEqual(stage.name, "plan")
        self.assertEqual(stage.type, "worker")
        self.assertEqual(stage.prompt, "Do the task")
        self.assertIsNone(stage.prompt_file)
        self.assertIsNone(stage.done_pattern)
        self.assertIsNone(stage.timeout)
        self.assertEqual(stage.on_failure, "stop")
        self.assertEqual(stage.max_retries, 3)
        self.assertEqual(stage.on_complete, "next")
        self.assertIsNone(stage.max_iterations)
        self.assertEqual(stage.inactivity_timeout, 60)
        self.assertFalse(stage.check_done_continuous)
        self.assertIsNone(stage.heartbeat)
        self.assertIsNone(stage.worktree)
        self.assertEqual(stage.env, {})
        self.assertEqual(stage.tags, [])

    def test_create_worker_stage_with_all_fields(self):
        """Test creating worker StageDefinition with all fields."""
        stage = swarm.StageDefinition(
            name="plan",
            type="worker",
            prompt="Create the plan",
            prompt_file=None,
            done_pattern="/done",
            timeout="2h",
            on_failure="retry",
            max_retries=5,
            on_complete="next",
            heartbeat="1h",
            heartbeat_expire="8h",
            heartbeat_message="ping",
            worktree=True,
            cwd="/path/to/work",
            env={"DEBUG": "true"},
            tags=["planning", "phase1"],
        )
        self.assertEqual(stage.name, "plan")
        self.assertEqual(stage.type, "worker")
        self.assertEqual(stage.prompt, "Create the plan")
        self.assertEqual(stage.done_pattern, "/done")
        self.assertEqual(stage.timeout, "2h")
        self.assertEqual(stage.on_failure, "retry")
        self.assertEqual(stage.max_retries, 5)
        self.assertEqual(stage.on_complete, "next")
        self.assertEqual(stage.heartbeat, "1h")
        self.assertEqual(stage.heartbeat_expire, "8h")
        self.assertEqual(stage.heartbeat_message, "ping")
        self.assertTrue(stage.worktree)
        self.assertEqual(stage.cwd, "/path/to/work")
        self.assertEqual(stage.env, {"DEBUG": "true"})
        self.assertEqual(stage.tags, ["planning", "phase1"])

    def test_create_ralph_stage(self):
        """Test creating ralph StageDefinition with ralph-specific fields."""
        stage = swarm.StageDefinition(
            name="build",
            type="ralph",
            prompt_file="./prompts/build.md",
            max_iterations=50,
            inactivity_timeout=120,
            check_done_continuous=True,
            done_pattern="COMPLETE",
        )
        self.assertEqual(stage.name, "build")
        self.assertEqual(stage.type, "ralph")
        self.assertEqual(stage.prompt_file, "./prompts/build.md")
        self.assertEqual(stage.max_iterations, 50)
        self.assertEqual(stage.inactivity_timeout, 120)
        self.assertTrue(stage.check_done_continuous)
        self.assertEqual(stage.done_pattern, "COMPLETE")

    def test_to_dict(self):
        """Test converting StageDefinition to dictionary."""
        stage = swarm.StageDefinition(
            name="test",
            type="worker",
            prompt="Do something",
            done_pattern="/done",
            env={"KEY": "value"},
            tags=["tag1"],
        )
        d = stage.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertEqual(d["type"], "worker")
        self.assertEqual(d["prompt"], "Do something")
        self.assertEqual(d["done_pattern"], "/done")
        self.assertEqual(d["env"], {"KEY": "value"})
        self.assertEqual(d["tags"], ["tag1"])

    def test_from_dict_with_hyphens(self):
        """Test creating StageDefinition from dictionary with hyphenated keys."""
        d = {
            "name": "build",
            "type": "ralph",
            "prompt-file": "./prompts/build.md",
            "max-iterations": 50,
            "inactivity-timeout": 90,
            "check-done-continuous": True,
            "done-pattern": "/done",
            "on-failure": "retry",
            "max-retries": 2,
            "on-complete": "stop",
            "heartbeat-expire": "24h",
            "heartbeat-message": "continue working",
        }
        stage = swarm.StageDefinition.from_dict(d)
        self.assertEqual(stage.name, "build")
        self.assertEqual(stage.type, "ralph")
        self.assertEqual(stage.prompt_file, "./prompts/build.md")
        self.assertEqual(stage.max_iterations, 50)
        self.assertEqual(stage.inactivity_timeout, 90)
        self.assertTrue(stage.check_done_continuous)
        self.assertEqual(stage.done_pattern, "/done")
        self.assertEqual(stage.on_failure, "retry")
        self.assertEqual(stage.max_retries, 2)
        self.assertEqual(stage.on_complete, "stop")
        self.assertEqual(stage.heartbeat_expire, "24h")
        self.assertEqual(stage.heartbeat_message, "continue working")

    def test_from_dict_with_underscores(self):
        """Test creating StageDefinition from dictionary with underscore keys."""
        d = {
            "name": "test",
            "type": "worker",
            "prompt": "Do task",
            "prompt_file": None,
            "done_pattern": "/done",
            "on_failure": "skip",
            "max_retries": 1,
            "on_complete": "next",
        }
        stage = swarm.StageDefinition.from_dict(d)
        self.assertEqual(stage.done_pattern, "/done")
        self.assertEqual(stage.on_failure, "skip")
        self.assertEqual(stage.max_retries, 1)
        self.assertEqual(stage.on_complete, "next")

    def test_roundtrip_serialization(self):
        """Test that to_dict/from_dict round-trip preserves data."""
        original = swarm.StageDefinition(
            name="roundtrip",
            type="ralph",
            prompt_file="./prompt.md",
            max_iterations=25,
            inactivity_timeout=45,
            check_done_continuous=True,
            done_pattern="DONE",
            timeout="3h",
            on_failure="retry",
            max_retries=2,
            on_complete="stop",
            heartbeat="2h",
            heartbeat_expire="12h",
            heartbeat_message="keep going",
            worktree=True,
            cwd="/work",
            env={"A": "1", "B": "2"},
            tags=["x", "y"],
        )
        d = original.to_dict()
        restored = swarm.StageDefinition.from_dict(d)
        self.assertEqual(original.name, restored.name)
        self.assertEqual(original.type, restored.type)
        self.assertEqual(original.prompt_file, restored.prompt_file)
        self.assertEqual(original.max_iterations, restored.max_iterations)
        self.assertEqual(original.inactivity_timeout, restored.inactivity_timeout)
        self.assertEqual(original.check_done_continuous, restored.check_done_continuous)
        self.assertEqual(original.done_pattern, restored.done_pattern)
        self.assertEqual(original.timeout, restored.timeout)
        self.assertEqual(original.on_failure, restored.on_failure)
        self.assertEqual(original.max_retries, restored.max_retries)
        self.assertEqual(original.on_complete, restored.on_complete)
        self.assertEqual(original.heartbeat, restored.heartbeat)
        self.assertEqual(original.heartbeat_expire, restored.heartbeat_expire)
        self.assertEqual(original.heartbeat_message, restored.heartbeat_message)
        self.assertEqual(original.worktree, restored.worktree)
        self.assertEqual(original.cwd, restored.cwd)
        self.assertEqual(original.env, restored.env)
        self.assertEqual(original.tags, restored.tags)


class TestWorkflowDefinitionDataclass(unittest.TestCase):
    """Test WorkflowDefinition dataclass creation and serialization."""

    def test_create_with_minimal_fields(self):
        """Test creating WorkflowDefinition with minimal required fields."""
        workflow = swarm.WorkflowDefinition(name="my-workflow")
        self.assertEqual(workflow.name, "my-workflow")
        self.assertIsNone(workflow.description)
        self.assertIsNone(workflow.schedule)
        self.assertIsNone(workflow.delay)
        self.assertIsNone(workflow.heartbeat)
        self.assertIsNone(workflow.heartbeat_expire)
        self.assertEqual(workflow.heartbeat_message, "continue")
        self.assertFalse(workflow.worktree)
        self.assertIsNone(workflow.cwd)
        self.assertEqual(workflow.stages, [])

    def test_create_with_all_fields(self):
        """Test creating WorkflowDefinition with all fields."""
        stages = [
            swarm.StageDefinition(name="plan", type="worker", prompt="Do planning"),
            swarm.StageDefinition(name="build", type="ralph", prompt_file="./build.md", max_iterations=50),
        ]
        workflow = swarm.WorkflowDefinition(
            name="feature-build",
            description="Build and validate feature",
            schedule="02:00",
            delay=None,
            heartbeat="4h",
            heartbeat_expire="24h",
            heartbeat_message="continue working",
            worktree=True,
            cwd="./project",
            stages=stages,
        )
        self.assertEqual(workflow.name, "feature-build")
        self.assertEqual(workflow.description, "Build and validate feature")
        self.assertEqual(workflow.schedule, "02:00")
        self.assertIsNone(workflow.delay)
        self.assertEqual(workflow.heartbeat, "4h")
        self.assertEqual(workflow.heartbeat_expire, "24h")
        self.assertEqual(workflow.heartbeat_message, "continue working")
        self.assertTrue(workflow.worktree)
        self.assertEqual(workflow.cwd, "./project")
        self.assertEqual(len(workflow.stages), 2)
        self.assertEqual(workflow.stages[0].name, "plan")
        self.assertEqual(workflow.stages[1].name, "build")

    def test_to_dict(self):
        """Test converting WorkflowDefinition to dictionary."""
        stages = [swarm.StageDefinition(name="s1", type="worker", prompt="Do task")]
        workflow = swarm.WorkflowDefinition(
            name="test",
            description="Test workflow",
            heartbeat="2h",
            worktree=True,
            stages=stages,
        )
        d = workflow.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertEqual(d["description"], "Test workflow")
        self.assertEqual(d["heartbeat"], "2h")
        self.assertTrue(d["worktree"])
        self.assertEqual(len(d["stages"]), 1)
        self.assertEqual(d["stages"][0]["name"], "s1")

    def test_from_dict_with_hyphens(self):
        """Test creating WorkflowDefinition from dictionary with hyphenated keys."""
        d = {
            "name": "test-workflow",
            "heartbeat-expire": "12h",
            "heartbeat-message": "nudge",
            "stages": [
                {"name": "s1", "type": "worker", "prompt": "Task"}
            ],
        }
        workflow = swarm.WorkflowDefinition.from_dict(d)
        self.assertEqual(workflow.name, "test-workflow")
        self.assertEqual(workflow.heartbeat_expire, "12h")
        self.assertEqual(workflow.heartbeat_message, "nudge")
        self.assertEqual(len(workflow.stages), 1)

    def test_roundtrip_serialization(self):
        """Test that to_dict/from_dict round-trip preserves data."""
        original = swarm.WorkflowDefinition(
            name="roundtrip-test",
            description="Roundtrip testing",
            schedule="03:00",
            heartbeat="1h",
            heartbeat_expire="6h",
            heartbeat_message="ping",
            worktree=True,
            cwd="/code",
            stages=[
                swarm.StageDefinition(name="s1", type="worker", prompt="Task 1"),
                swarm.StageDefinition(name="s2", type="ralph", prompt_file="./s2.md", max_iterations=10),
            ],
        )
        d = original.to_dict()
        restored = swarm.WorkflowDefinition.from_dict(d)
        self.assertEqual(original.name, restored.name)
        self.assertEqual(original.description, restored.description)
        self.assertEqual(original.schedule, restored.schedule)
        self.assertEqual(original.heartbeat, restored.heartbeat)
        self.assertEqual(original.heartbeat_expire, restored.heartbeat_expire)
        self.assertEqual(original.heartbeat_message, restored.heartbeat_message)
        self.assertEqual(original.worktree, restored.worktree)
        self.assertEqual(original.cwd, restored.cwd)
        self.assertEqual(len(original.stages), len(restored.stages))
        for i in range(len(original.stages)):
            self.assertEqual(original.stages[i].name, restored.stages[i].name)
            self.assertEqual(original.stages[i].type, restored.stages[i].type)


class TestParseWorkflowYaml(unittest.TestCase):
    """Test parse_workflow_yaml function."""

    def setUp(self):
        """Set up temporary directory for test files."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def write_yaml(self, filename: str, content: str) -> str:
        """Write YAML content to a file and return the path."""
        path = os.path.join(self.temp_dir, filename)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def test_parse_minimal_workflow(self):
        """Test parsing a minimal valid workflow."""
        yaml_content = """
name: simple-task
stages:
  - name: work
    type: worker
    prompt: |
      Complete the task.
"""
        path = self.write_yaml("minimal.yaml", yaml_content)
        workflow = swarm.parse_workflow_yaml(path)
        self.assertEqual(workflow.name, "simple-task")
        self.assertEqual(len(workflow.stages), 1)
        self.assertEqual(workflow.stages[0].name, "work")
        self.assertEqual(workflow.stages[0].type, "worker")
        self.assertIn("Complete the task", workflow.stages[0].prompt)

    def test_parse_full_workflow(self):
        """Test parsing a workflow with all fields."""
        yaml_content = """
name: feature-build
description: Build and validate feature
heartbeat: 4h
heartbeat-expire: 24h
heartbeat-message: continue working
worktree: true
cwd: ./project

stages:
  - name: plan
    type: worker
    prompt: Create the plan
    done-pattern: "/done"
    timeout: 2h
    on-failure: stop
    on-complete: next

  - name: build
    type: ralph
    prompt-file: ./prompts/build.md
    max-iterations: 50
    inactivity-timeout: 90
    check-done-continuous: true
    on-failure: retry
    max-retries: 2
    env:
      DEBUG: "true"
    tags:
      - building
"""
        path = self.write_yaml("full.yaml", yaml_content)
        workflow = swarm.parse_workflow_yaml(path)
        self.assertEqual(workflow.name, "feature-build")
        self.assertEqual(workflow.description, "Build and validate feature")
        self.assertEqual(workflow.heartbeat, "4h")
        self.assertEqual(workflow.heartbeat_expire, "24h")
        self.assertEqual(workflow.heartbeat_message, "continue working")
        self.assertTrue(workflow.worktree)
        self.assertEqual(workflow.cwd, "./project")
        self.assertEqual(len(workflow.stages), 2)

        plan_stage = workflow.stages[0]
        self.assertEqual(plan_stage.name, "plan")
        self.assertEqual(plan_stage.type, "worker")
        self.assertEqual(plan_stage.prompt, "Create the plan")
        self.assertEqual(plan_stage.done_pattern, "/done")
        self.assertEqual(plan_stage.timeout, "2h")
        self.assertEqual(plan_stage.on_failure, "stop")
        self.assertEqual(plan_stage.on_complete, "next")

        build_stage = workflow.stages[1]
        self.assertEqual(build_stage.name, "build")
        self.assertEqual(build_stage.type, "ralph")
        self.assertEqual(build_stage.prompt_file, "./prompts/build.md")
        self.assertEqual(build_stage.max_iterations, 50)
        self.assertEqual(build_stage.inactivity_timeout, 90)
        self.assertTrue(build_stage.check_done_continuous)
        self.assertEqual(build_stage.on_failure, "retry")
        self.assertEqual(build_stage.max_retries, 2)
        self.assertEqual(build_stage.env, {"DEBUG": "true"})
        self.assertEqual(build_stage.tags, ["building"])

    def test_parse_workflow_with_schedule(self):
        """Test parsing workflow with schedule time."""
        yaml_content = """
name: scheduled-work
schedule: "02:00"
stages:
  - name: task
    type: worker
    prompt: Do work
"""
        path = self.write_yaml("scheduled.yaml", yaml_content)
        workflow = swarm.parse_workflow_yaml(path)
        self.assertEqual(workflow.schedule, "02:00")

    def test_parse_workflow_with_delay(self):
        """Test parsing workflow with delay."""
        yaml_content = """
name: delayed-work
delay: "4h"
stages:
  - name: task
    type: worker
    prompt: Do work
"""
        path = self.write_yaml("delayed.yaml", yaml_content)
        workflow = swarm.parse_workflow_yaml(path)
        self.assertEqual(workflow.delay, "4h")

    def test_error_file_not_found(self):
        """Test error when workflow file doesn't exist."""
        with self.assertRaises(FileNotFoundError) as ctx:
            swarm.parse_workflow_yaml("/nonexistent/path/workflow.yaml")
        self.assertIn("workflow file not found", str(ctx.exception))

    def test_error_invalid_yaml(self):
        """Test error when YAML is malformed."""
        yaml_content = """
name: bad-yaml
stages:
  - name: [invalid yaml here
"""
        path = self.write_yaml("invalid.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("invalid workflow YAML", str(ctx.exception))

    def test_error_empty_file(self):
        """Test error when YAML file is empty."""
        path = self.write_yaml("empty.yaml", "")
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("workflow file is empty", str(ctx.exception))

    def test_error_not_a_mapping(self):
        """Test error when YAML is not a mapping."""
        yaml_content = "- item1\n- item2"
        path = self.write_yaml("list.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("workflow must be a YAML mapping", str(ctx.exception))

    def test_error_missing_name(self):
        """Test error when workflow name is missing."""
        yaml_content = """
stages:
  - name: task
    type: worker
    prompt: Do work
"""
        path = self.write_yaml("no_name.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("missing required field 'name'", str(ctx.exception))

    def test_error_missing_stages(self):
        """Test error when stages is missing."""
        yaml_content = """
name: no-stages
"""
        path = self.write_yaml("no_stages.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("missing required field 'stages'", str(ctx.exception))

    def test_error_stages_not_list(self):
        """Test error when stages is not a list."""
        yaml_content = """
name: bad-stages
stages:
  plan: worker
"""
        path = self.write_yaml("stages_dict.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("'stages' must be a list", str(ctx.exception))

    def test_error_empty_stages(self):
        """Test error when stages list is empty."""
        yaml_content = """
name: empty-stages
stages: []
"""
        path = self.write_yaml("empty_stages.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("workflow must have at least one stage", str(ctx.exception))

    def test_error_stage_not_mapping(self):
        """Test error when stage is not a mapping."""
        yaml_content = """
name: bad-stage
stages:
  - just a string
"""
        path = self.write_yaml("stage_string.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("stage 1 must be a YAML mapping", str(ctx.exception))

    def test_error_stage_missing_name(self):
        """Test error when stage name is missing."""
        yaml_content = """
name: missing-stage-name
stages:
  - type: worker
    prompt: Do work
"""
        path = self.write_yaml("stage_no_name.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("stage 1 missing required field 'name'", str(ctx.exception))

    def test_error_stage_missing_type(self):
        """Test error when stage type is missing."""
        yaml_content = """
name: missing-type
stages:
  - name: plan
    prompt: Do work
"""
        path = self.write_yaml("stage_no_type.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("stage 'plan' missing required field 'type'", str(ctx.exception))

    def test_error_invalid_stage_type(self):
        """Test error when stage type is invalid."""
        yaml_content = """
name: bad-type
stages:
  - name: task
    type: invalid
    prompt: Do work
"""
        path = self.write_yaml("bad_type.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("invalid type 'invalid'", str(ctx.exception))
        self.assertIn("must be 'worker' or 'ralph'", str(ctx.exception))

    def test_error_duplicate_stage_names(self):
        """Test error when stage names are duplicated."""
        yaml_content = """
name: duplicate-names
stages:
  - name: task
    type: worker
    prompt: First task
  - name: task
    type: worker
    prompt: Second task
"""
        path = self.write_yaml("duplicate.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("duplicate stage name: 'task'", str(ctx.exception))

    def test_error_both_prompt_and_prompt_file(self):
        """Test error when stage has both prompt and prompt-file."""
        yaml_content = """
name: both-prompts
stages:
  - name: task
    type: worker
    prompt: Inline prompt
    prompt-file: ./prompt.md
"""
        path = self.write_yaml("both_prompts.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("stage 'task' has both prompt and prompt-file", str(ctx.exception))

    def test_error_neither_prompt_nor_prompt_file(self):
        """Test error when stage has neither prompt nor prompt-file."""
        yaml_content = """
name: no-prompt
stages:
  - name: task
    type: worker
"""
        path = self.write_yaml("no_prompt.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("stage 'task' requires prompt or prompt-file", str(ctx.exception))

    def test_error_ralph_without_max_iterations(self):
        """Test error when ralph stage is missing max-iterations."""
        yaml_content = """
name: ralph-no-iterations
stages:
  - name: build
    type: ralph
    prompt: Build it
"""
        path = self.write_yaml("ralph_no_iter.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("ralph stage 'build' requires max-iterations", str(ctx.exception))

    def test_error_ralph_invalid_max_iterations(self):
        """Test error when ralph max-iterations is invalid."""
        yaml_content = """
name: ralph-bad-iterations
stages:
  - name: build
    type: ralph
    prompt: Build it
    max-iterations: 0
"""
        path = self.write_yaml("ralph_zero_iter.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("max-iterations must be a positive integer", str(ctx.exception))

    def test_error_invalid_on_failure(self):
        """Test error when on-failure value is invalid."""
        yaml_content = """
name: bad-on-failure
stages:
  - name: task
    type: worker
    prompt: Do work
    on-failure: explode
"""
        path = self.write_yaml("bad_onfailure.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("invalid on-failure 'explode'", str(ctx.exception))
        self.assertIn("must be 'stop', 'retry', or 'skip'", str(ctx.exception))

    def test_error_invalid_max_retries(self):
        """Test error when max-retries is invalid."""
        yaml_content = """
name: bad-retries
stages:
  - name: task
    type: worker
    prompt: Do work
    on-failure: retry
    max-retries: -1
"""
        path = self.write_yaml("bad_retries.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("max-retries must be a positive integer", str(ctx.exception))

    def test_error_invalid_on_complete(self):
        """Test error when on-complete value is invalid."""
        yaml_content = """
name: bad-on-complete
stages:
  - name: task
    type: worker
    prompt: Do work
    on-complete: crash
"""
        path = self.write_yaml("bad_oncomplete.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("invalid on-complete 'crash'", str(ctx.exception))
        self.assertIn("must be 'next', 'stop', or 'goto:<stage>'", str(ctx.exception))

    def test_error_unknown_goto_target(self):
        """Test error when goto target doesn't exist."""
        yaml_content = """
name: bad-goto
stages:
  - name: task
    type: worker
    prompt: Do work
    on-complete: goto:nonexistent
"""
        path = self.write_yaml("bad_goto.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("unknown stage in goto: 'nonexistent'", str(ctx.exception))

    def test_error_circular_goto(self):
        """Test error when goto creates a cycle."""
        yaml_content = """
name: circular-goto
stages:
  - name: a
    type: worker
    prompt: Do A
    on-complete: goto:b
  - name: b
    type: worker
    prompt: Do B
    on-complete: goto:a
"""
        path = self.write_yaml("circular.yaml", yaml_content)
        with self.assertRaises(swarm.WorkflowValidationError) as ctx:
            swarm.parse_workflow_yaml(path)
        self.assertIn("circular stage reference detected", str(ctx.exception))

    def test_valid_goto_no_cycle(self):
        """Test that valid goto (no cycle) is accepted."""
        yaml_content = """
name: valid-goto
stages:
  - name: a
    type: worker
    prompt: Do A
    on-complete: goto:c
  - name: b
    type: worker
    prompt: Do B
    on-complete: next
  - name: c
    type: worker
    prompt: Do C
    on-complete: stop
"""
        path = self.write_yaml("valid_goto.yaml", yaml_content)
        workflow = swarm.parse_workflow_yaml(path)
        self.assertEqual(workflow.stages[0].on_complete, "goto:c")

    def test_on_failure_values(self):
        """Test all valid on-failure values."""
        for value in ["stop", "retry", "skip"]:
            yaml_content = f"""
name: test-{value}
stages:
  - name: task
    type: worker
    prompt: Do work
    on-failure: {value}
"""
            path = self.write_yaml(f"onfailure_{value}.yaml", yaml_content)
            workflow = swarm.parse_workflow_yaml(path)
            self.assertEqual(workflow.stages[0].on_failure, value)

    def test_on_complete_values(self):
        """Test valid on-complete values."""
        for value in ["next", "stop"]:
            yaml_content = f"""
name: test-{value}
stages:
  - name: task
    type: worker
    prompt: Do work
    on-complete: {value}
"""
            path = self.write_yaml(f"oncomplete_{value}.yaml", yaml_content)
            workflow = swarm.parse_workflow_yaml(path)
            self.assertEqual(workflow.stages[0].on_complete, value)

    def test_multiline_prompt(self):
        """Test parsing multiline inline prompt."""
        yaml_content = """
name: multiline
stages:
  - name: task
    type: worker
    prompt: |
      Line 1
      Line 2
      Line 3
"""
        path = self.write_yaml("multiline.yaml", yaml_content)
        workflow = swarm.parse_workflow_yaml(path)
        self.assertIn("Line 1", workflow.stages[0].prompt)
        self.assertIn("Line 2", workflow.stages[0].prompt)
        self.assertIn("Line 3", workflow.stages[0].prompt)

    def test_multiple_stages(self):
        """Test parsing workflow with multiple stages."""
        yaml_content = """
name: multi-stage
stages:
  - name: plan
    type: worker
    prompt: Plan
  - name: build
    type: ralph
    prompt: Build
    max-iterations: 10
  - name: validate
    type: worker
    prompt: Validate
"""
        path = self.write_yaml("multi.yaml", yaml_content)
        workflow = swarm.parse_workflow_yaml(path)
        self.assertEqual(len(workflow.stages), 3)
        self.assertEqual(workflow.stages[0].name, "plan")
        self.assertEqual(workflow.stages[1].name, "build")
        self.assertEqual(workflow.stages[2].name, "validate")


class TestValidateWorkflowPromptFiles(unittest.TestCase):
    """Test validate_workflow_prompt_files function."""

    def setUp(self):
        """Set up temporary directory for test files."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_no_prompt_files(self):
        """Test workflow with only inline prompts."""
        workflow = swarm.WorkflowDefinition(
            name="test",
            stages=[
                swarm.StageDefinition(name="s1", type="worker", prompt="Do task"),
            ],
        )
        errors = swarm.validate_workflow_prompt_files(workflow)
        self.assertEqual(errors, [])

    def test_existing_prompt_file(self):
        """Test validation passes when prompt file exists."""
        prompt_path = os.path.join(self.temp_dir, "prompt.md")
        with open(prompt_path, 'w') as f:
            f.write("Do the task")

        workflow = swarm.WorkflowDefinition(
            name="test",
            stages=[
                swarm.StageDefinition(name="s1", type="worker", prompt_file="prompt.md"),
            ],
        )
        errors = swarm.validate_workflow_prompt_files(workflow, Path(self.temp_dir))
        self.assertEqual(errors, [])

    def test_missing_prompt_file(self):
        """Test validation fails when prompt file doesn't exist."""
        workflow = swarm.WorkflowDefinition(
            name="test",
            stages=[
                swarm.StageDefinition(name="s1", type="worker", prompt_file="nonexistent.md"),
            ],
        )
        errors = swarm.validate_workflow_prompt_files(workflow, Path(self.temp_dir))
        self.assertEqual(len(errors), 1)
        self.assertIn("prompt file not found: nonexistent.md", errors[0])

    def test_multiple_missing_files(self):
        """Test validation reports all missing files."""
        workflow = swarm.WorkflowDefinition(
            name="test",
            stages=[
                swarm.StageDefinition(name="s1", type="worker", prompt_file="missing1.md"),
                swarm.StageDefinition(name="s2", type="worker", prompt="Inline is fine"),
                swarm.StageDefinition(name="s3", type="ralph", prompt_file="missing2.md", max_iterations=10),
            ],
        )
        errors = swarm.validate_workflow_prompt_files(workflow, Path(self.temp_dir))
        self.assertEqual(len(errors), 2)
        self.assertIn("missing1.md", errors[0])
        self.assertIn("missing2.md", errors[1])

    def test_absolute_path_prompt_file(self):
        """Test validation with absolute path prompt file."""
        prompt_path = os.path.join(self.temp_dir, "prompt.md")
        with open(prompt_path, 'w') as f:
            f.write("Do the task")

        workflow = swarm.WorkflowDefinition(
            name="test",
            stages=[
                swarm.StageDefinition(name="s1", type="worker", prompt_file=prompt_path),
            ],
        )
        errors = swarm.validate_workflow_prompt_files(workflow)
        self.assertEqual(errors, [])

    def test_relative_path_with_subdirectory(self):
        """Test validation with relative path in subdirectory."""
        subdir = os.path.join(self.temp_dir, "prompts")
        os.makedirs(subdir)
        prompt_path = os.path.join(subdir, "prompt.md")
        with open(prompt_path, 'w') as f:
            f.write("Do the task")

        workflow = swarm.WorkflowDefinition(
            name="test",
            stages=[
                swarm.StageDefinition(name="s1", type="worker", prompt_file="prompts/prompt.md"),
            ],
        )
        errors = swarm.validate_workflow_prompt_files(workflow, Path(self.temp_dir))
        self.assertEqual(errors, [])


class TestWorkflowStatePersistence(unittest.TestCase):
    """Test workflow state persistence functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_workflows_dir = swarm.WORKFLOWS_DIR
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.WORKFLOWS_DIR = swarm.SWARM_DIR / "workflows"
        swarm.WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.WORKFLOWS_DIR = self.original_workflows_dir
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_workflow_state_dir(self):
        """Test get_workflow_state_dir returns correct path."""
        state_dir = swarm.get_workflow_state_dir("my-workflow")
        self.assertEqual(state_dir, swarm.WORKFLOWS_DIR / "my-workflow")

    def test_get_workflow_state_path(self):
        """Test get_workflow_state_path returns correct path."""
        state_path = swarm.get_workflow_state_path("my-workflow")
        self.assertEqual(state_path, swarm.WORKFLOWS_DIR / "my-workflow" / "state.json")

    def test_get_workflow_yaml_copy_path(self):
        """Test get_workflow_yaml_copy_path returns correct path."""
        yaml_path = swarm.get_workflow_yaml_copy_path("my-workflow")
        self.assertEqual(yaml_path, swarm.WORKFLOWS_DIR / "my-workflow" / "workflow.yaml")

    def test_get_workflow_logs_dir(self):
        """Test get_workflow_logs_dir returns correct path."""
        logs_dir = swarm.get_workflow_logs_dir("my-workflow")
        self.assertEqual(logs_dir, swarm.WORKFLOWS_DIR / "my-workflow" / "logs")

    def test_compute_workflow_hash(self):
        """Test compute_workflow_hash produces consistent hash."""
        content = "name: test\nstages:\n  - name: s1\n    type: worker\n    prompt: Do it"
        hash1 = swarm.compute_workflow_hash(content)
        hash2 = swarm.compute_workflow_hash(content)
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 16)  # First 16 chars of SHA-256 hex

    def test_compute_workflow_hash_different_content(self):
        """Test compute_workflow_hash produces different hash for different content."""
        content1 = "name: test1"
        content2 = "name: test2"
        hash1 = swarm.compute_workflow_hash(content1)
        hash2 = swarm.compute_workflow_hash(content2)
        self.assertNotEqual(hash1, hash2)

    def test_save_and_load_workflow_state(self):
        """Test saving and loading workflow state."""
        stages = {
            "plan": swarm.StageState(status="completed", attempts=1),
            "build": swarm.StageState(status="running"),
        }
        state = swarm.WorkflowState(
            name="test-workflow",
            status="running",
            current_stage="build",
            current_stage_index=1,
            created_at="2026-02-04T10:00:00Z",
            started_at="2026-02-04T10:00:00Z",
            stages=stages,
            workflow_file="/path/to/workflow.yaml",
            workflow_hash="abc123",
        )
        swarm.save_workflow_state(state)

        loaded = swarm.load_workflow_state("test-workflow")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "test-workflow")
        self.assertEqual(loaded.status, "running")
        self.assertEqual(loaded.current_stage, "build")
        self.assertEqual(loaded.current_stage_index, 1)
        self.assertEqual(loaded.created_at, "2026-02-04T10:00:00Z")
        self.assertEqual(loaded.started_at, "2026-02-04T10:00:00Z")
        self.assertEqual(len(loaded.stages), 2)
        self.assertEqual(loaded.stages["plan"].status, "completed")
        self.assertEqual(loaded.stages["plan"].attempts, 1)
        self.assertEqual(loaded.stages["build"].status, "running")
        self.assertEqual(loaded.workflow_file, "/path/to/workflow.yaml")
        self.assertEqual(loaded.workflow_hash, "abc123")

    def test_save_workflow_state_creates_directory(self):
        """Test save_workflow_state creates state directory if needed."""
        state = swarm.WorkflowState(
            name="new-workflow",
            status="created",
            created_at="2026-02-04T10:00:00Z",
        )
        state_dir = swarm.get_workflow_state_dir("new-workflow")
        self.assertFalse(state_dir.exists())

        swarm.save_workflow_state(state)
        self.assertTrue(state_dir.exists())

    def test_load_nonexistent_returns_none(self):
        """Test loading non-existent workflow returns None."""
        loaded = swarm.load_workflow_state("nonexistent")
        self.assertIsNone(loaded)

    def test_delete_workflow_state(self):
        """Test deleting workflow state removes directory."""
        state = swarm.WorkflowState(
            name="to-delete",
            status="created",
            created_at="2026-02-04T10:00:00Z",
        )
        swarm.save_workflow_state(state)

        state_dir = swarm.get_workflow_state_dir("to-delete")
        self.assertTrue(state_dir.exists())

        result = swarm.delete_workflow_state("to-delete")
        self.assertTrue(result)
        self.assertFalse(state_dir.exists())

    def test_delete_nonexistent_returns_false(self):
        """Test deleting non-existent workflow returns False."""
        result = swarm.delete_workflow_state("nonexistent")
        self.assertFalse(result)

    def test_list_workflow_states_empty(self):
        """Test listing workflow states when none exist."""
        states = swarm.list_workflow_states()
        self.assertEqual(states, [])

    def test_list_workflow_states(self):
        """Test listing workflow states."""
        state1 = swarm.WorkflowState(name="workflow-a", status="running", created_at="2026-02-04T10:00:00Z")
        state2 = swarm.WorkflowState(name="workflow-b", status="completed", created_at="2026-02-04T11:00:00Z")
        swarm.save_workflow_state(state1)
        swarm.save_workflow_state(state2)

        states = swarm.list_workflow_states()
        self.assertEqual(len(states), 2)
        # Should be sorted by name
        self.assertEqual(states[0].name, "workflow-a")
        self.assertEqual(states[1].name, "workflow-b")

    def test_list_workflow_states_skips_invalid(self):
        """Test list_workflow_states skips invalid state files."""
        # Create a valid state
        state = swarm.WorkflowState(name="valid", status="running", created_at="2026-02-04T10:00:00Z")
        swarm.save_workflow_state(state)

        # Create an invalid state file
        invalid_dir = swarm.WORKFLOWS_DIR / "invalid"
        invalid_dir.mkdir(parents=True, exist_ok=True)
        with open(invalid_dir / "state.json", "w") as f:
            f.write("not valid json")

        states = swarm.list_workflow_states()
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].name, "valid")

    def test_workflow_exists(self):
        """Test workflow_exists check."""
        self.assertFalse(swarm.workflow_exists("test-workflow"))

        state = swarm.WorkflowState(name="test-workflow", status="created", created_at="2026-02-04T10:00:00Z")
        swarm.save_workflow_state(state)

        self.assertTrue(swarm.workflow_exists("test-workflow"))

    def test_state_survives_status_transitions(self):
        """Test state persists correctly through status transitions."""
        state = swarm.WorkflowState(
            name="transition-test",
            status="created",
            created_at="2026-02-04T10:00:00Z",
        )
        swarm.save_workflow_state(state)

        # Transition to scheduled
        loaded = swarm.load_workflow_state("transition-test")
        loaded.status = "scheduled"
        loaded.scheduled_for = "2026-02-05T02:00:00Z"
        swarm.save_workflow_state(loaded)

        reloaded = swarm.load_workflow_state("transition-test")
        self.assertEqual(reloaded.status, "scheduled")
        self.assertEqual(reloaded.scheduled_for, "2026-02-05T02:00:00Z")

        # Transition to running
        reloaded.status = "running"
        reloaded.started_at = "2026-02-05T02:00:00Z"
        swarm.save_workflow_state(reloaded)

        final = swarm.load_workflow_state("transition-test")
        self.assertEqual(final.status, "running")
        self.assertEqual(final.started_at, "2026-02-05T02:00:00Z")


class TestCreateWorkflowState(unittest.TestCase):
    """Test create_workflow_state function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_workflows_dir = swarm.WORKFLOWS_DIR
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.WORKFLOWS_DIR = swarm.SWARM_DIR / "workflows"
        swarm.WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.WORKFLOWS_DIR = self.original_workflows_dir
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_creates_workflow_state(self):
        """Test create_workflow_state creates WorkflowState with correct fields."""
        definition = swarm.WorkflowDefinition(
            name="test-workflow",
            description="Test workflow",
            stages=[
                swarm.StageDefinition(name="plan", type="worker", prompt="Plan it"),
                swarm.StageDefinition(name="build", type="ralph", prompt="Build it", max_iterations=10),
            ],
        )
        yaml_content = "name: test-workflow\nstages:\n  - name: plan\n    type: worker\n    prompt: Plan it"
        yaml_path = os.path.join(self.temp_dir, "workflow.yaml")

        state = swarm.create_workflow_state(definition, yaml_path, yaml_content)

        self.assertEqual(state.name, "test-workflow")
        self.assertEqual(state.status, "created")
        self.assertIsNone(state.current_stage)
        self.assertEqual(state.current_stage_index, 0)
        self.assertIsNotNone(state.created_at)
        self.assertIsNone(state.started_at)
        self.assertIsNone(state.scheduled_for)
        self.assertIsNone(state.completed_at)
        self.assertEqual(len(state.stages), 2)
        self.assertEqual(state.stages["plan"].status, "pending")
        self.assertEqual(state.stages["build"].status, "pending")
        self.assertEqual(state.workflow_file, str(Path(yaml_path).resolve()))
        self.assertEqual(len(state.workflow_hash), 16)

    def test_creates_state_directory(self):
        """Test create_workflow_state creates state directory."""
        definition = swarm.WorkflowDefinition(
            name="dir-test",
            stages=[swarm.StageDefinition(name="s1", type="worker", prompt="Do it")],
        )
        yaml_content = "name: dir-test"
        yaml_path = os.path.join(self.temp_dir, "workflow.yaml")

        swarm.create_workflow_state(definition, yaml_path, yaml_content)

        state_dir = swarm.get_workflow_state_dir("dir-test")
        self.assertTrue(state_dir.exists())

    def test_creates_logs_directory(self):
        """Test create_workflow_state creates logs directory."""
        definition = swarm.WorkflowDefinition(
            name="logs-test",
            stages=[swarm.StageDefinition(name="s1", type="worker", prompt="Do it")],
        )
        yaml_content = "name: logs-test"
        yaml_path = os.path.join(self.temp_dir, "workflow.yaml")

        swarm.create_workflow_state(definition, yaml_path, yaml_content)

        logs_dir = swarm.get_workflow_logs_dir("logs-test")
        self.assertTrue(logs_dir.exists())

    def test_copies_yaml_file(self):
        """Test create_workflow_state copies YAML to state directory."""
        definition = swarm.WorkflowDefinition(
            name="yaml-copy-test",
            stages=[swarm.StageDefinition(name="s1", type="worker", prompt="Do it")],
        )
        yaml_content = "name: yaml-copy-test\nstages:\n  - name: s1\n    type: worker\n    prompt: Do it"
        yaml_path = os.path.join(self.temp_dir, "workflow.yaml")

        swarm.create_workflow_state(definition, yaml_path, yaml_content)

        yaml_copy_path = swarm.get_workflow_yaml_copy_path("yaml-copy-test")
        self.assertTrue(yaml_copy_path.exists())
        with open(yaml_copy_path) as f:
            copied_content = f.read()
        self.assertEqual(copied_content, yaml_content)

    def test_saves_state_file(self):
        """Test create_workflow_state saves state.json."""
        definition = swarm.WorkflowDefinition(
            name="state-file-test",
            stages=[swarm.StageDefinition(name="s1", type="worker", prompt="Do it")],
        )
        yaml_content = "name: state-file-test"
        yaml_path = os.path.join(self.temp_dir, "workflow.yaml")

        swarm.create_workflow_state(definition, yaml_path, yaml_content)

        state_path = swarm.get_workflow_state_path("state-file-test")
        self.assertTrue(state_path.exists())

        # Verify it can be loaded
        loaded = swarm.load_workflow_state("state-file-test")
        self.assertEqual(loaded.name, "state-file-test")

    def test_computes_hash_from_yaml_content(self):
        """Test create_workflow_state computes hash from YAML content."""
        definition = swarm.WorkflowDefinition(
            name="hash-test",
            stages=[swarm.StageDefinition(name="s1", type="worker", prompt="Do it")],
        )
        yaml_content = "name: hash-test\nstages:\n  - name: s1"
        yaml_path = os.path.join(self.temp_dir, "workflow.yaml")

        state = swarm.create_workflow_state(definition, yaml_path, yaml_content)

        expected_hash = swarm.compute_workflow_hash(yaml_content)
        self.assertEqual(state.workflow_hash, expected_hash)

    def test_initializes_all_stages_as_pending(self):
        """Test create_workflow_state initializes all stages as pending."""
        definition = swarm.WorkflowDefinition(
            name="stages-test",
            stages=[
                swarm.StageDefinition(name="plan", type="worker", prompt="Plan"),
                swarm.StageDefinition(name="build", type="ralph", prompt="Build", max_iterations=10),
                swarm.StageDefinition(name="validate", type="worker", prompt="Validate"),
            ],
        )
        yaml_content = "name: stages-test"
        yaml_path = os.path.join(self.temp_dir, "workflow.yaml")

        state = swarm.create_workflow_state(definition, yaml_path, yaml_content)

        self.assertEqual(len(state.stages), 3)
        for stage_name, stage_state in state.stages.items():
            self.assertEqual(stage_state.status, "pending")
            self.assertIsNone(stage_state.started_at)
            self.assertIsNone(stage_state.completed_at)
            self.assertIsNone(stage_state.worker_name)
            self.assertEqual(stage_state.attempts, 0)
            self.assertIsNone(stage_state.exit_reason)


# ==============================================================================
# CLI Command Tests
# ==============================================================================


class TestWorkflowSubparser(unittest.TestCase):
    """Test that workflow subparser is correctly configured."""

    def test_workflow_subparser_exists(self):
        """Test that 'workflow' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('workflow', result.stdout.lower())

    def test_workflow_validate_subcommand_exists(self):
        """Test that 'workflow validate' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('validate', result.stdout.lower())

    def test_workflow_help_description(self):
        """Test that workflow help contains description."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('Multi-stage agent pipelines', result.stdout)
        self.assertIn('scheduling', result.stdout.lower())

    def test_workflow_validate_help_has_examples(self):
        """Test that workflow validate help has examples."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('Examples:', result.stdout)


class TestWorkflowValidateCommand(unittest.TestCase):
    """Test workflow validate command functionality."""

    def setUp(self):
        """Create a temporary directory for test files."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_yaml(self, filename, content):
        """Write YAML content to a file in the temp directory."""
        path = Path(self.temp_dir) / filename
        path.write_text(content)
        return str(path)

    def test_validate_valid_workflow(self):
        """Test validating a valid workflow file."""
        yaml_path = self._write_yaml('valid.yaml', '''
name: test-workflow
description: A test workflow

stages:
  - name: plan
    type: worker
    prompt: Create a plan
    done-pattern: "/done"

  - name: build
    type: ralph
    prompt: Build it
    max-iterations: 50
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', yaml_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Workflow 'test-workflow' is valid", result.stdout)
        self.assertIn('2 stages', result.stdout)

    def test_validate_single_stage(self):
        """Test validating a workflow with a single stage."""
        yaml_path = self._write_yaml('single.yaml', '''
name: single-stage
stages:
  - name: work
    type: worker
    prompt: Do the work
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', yaml_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('1 stage', result.stdout)

    def test_validate_missing_file(self):
        """Test that missing file shows error."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', '/nonexistent/path.yaml'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('workflow file not found', result.stderr.lower())

    def test_validate_missing_name(self):
        """Test that missing name field shows error."""
        yaml_path = self._write_yaml('missing-name.yaml', '''
stages:
  - name: plan
    type: worker
    prompt: test
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', yaml_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing required field 'name'", result.stderr)

    def test_validate_missing_stages(self):
        """Test that missing stages field shows error."""
        yaml_path = self._write_yaml('missing-stages.yaml', '''
name: test
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', yaml_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing required field 'stages'", result.stderr)

    def test_validate_empty_stages(self):
        """Test that empty stages list shows error."""
        yaml_path = self._write_yaml('empty-stages.yaml', '''
name: test
stages: []
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', yaml_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('must have at least one stage', result.stderr)

    def test_validate_invalid_stage_type(self):
        """Test that invalid stage type shows error."""
        yaml_path = self._write_yaml('invalid-type.yaml', '''
name: test
stages:
  - name: plan
    type: invalid
    prompt: test
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', yaml_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid type 'invalid'", result.stderr)

    def test_validate_ralph_missing_max_iterations(self):
        """Test that ralph stage without max-iterations shows error."""
        yaml_path = self._write_yaml('ralph-no-max.yaml', '''
name: test
stages:
  - name: plan
    type: ralph
    prompt: test
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', yaml_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('ralph stage', result.stderr)
        self.assertIn('requires max-iterations', result.stderr)

    def test_validate_invalid_on_failure(self):
        """Test that invalid on-failure value shows error."""
        yaml_path = self._write_yaml('invalid-on-failure.yaml', '''
name: test
stages:
  - name: plan
    type: worker
    prompt: test
    on-failure: invalid
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', yaml_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid on-failure 'invalid'", result.stderr)

    def test_validate_duplicate_stage_names(self):
        """Test that duplicate stage names show error."""
        yaml_path = self._write_yaml('duplicate-names.yaml', '''
name: test
stages:
  - name: plan
    type: worker
    prompt: test1
  - name: plan
    type: worker
    prompt: test2
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', yaml_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate stage name: 'plan'", result.stderr)

    def test_validate_unknown_goto_target(self):
        """Test that unknown goto target shows error."""
        yaml_path = self._write_yaml('unknown-goto.yaml', '''
name: test
stages:
  - name: plan
    type: worker
    prompt: test
    on-complete: goto:nonexistent
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', yaml_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown stage in goto: 'nonexistent'", result.stderr)

    def test_validate_circular_goto(self):
        """Test that circular goto reference shows error."""
        yaml_path = self._write_yaml('circular-goto.yaml', '''
name: test
stages:
  - name: a
    type: worker
    prompt: test
    on-complete: goto:b
  - name: b
    type: worker
    prompt: test
    on-complete: goto:a
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', yaml_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('circular stage reference', result.stderr)

    def test_validate_missing_prompt_file(self):
        """Test that missing prompt file shows error."""
        yaml_path = self._write_yaml('missing-prompt-file.yaml', '''
name: test
stages:
  - name: plan
    type: worker
    prompt-file: ./nonexistent-prompt.md
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', yaml_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('prompt file not found', result.stderr)

    def test_validate_existing_prompt_file(self):
        """Test that existing prompt file is validated successfully."""
        # Create prompt file
        prompt_path = Path(self.temp_dir) / 'prompt.md'
        prompt_path.write_text('This is the prompt')

        yaml_path = self._write_yaml('with-prompt-file.yaml', '''
name: test
stages:
  - name: plan
    type: worker
    prompt-file: ./prompt.md
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', yaml_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_validate_empty_file(self):
        """Test that empty file shows error."""
        yaml_path = self._write_yaml('empty.yaml', '')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'validate', yaml_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('empty', result.stderr.lower())


# ==============================================================================
# Workflow Run Command Tests
# ==============================================================================


class TestCmdWorkflowRunDirect(unittest.TestCase):
    """Test cmd_workflow_run function directly (for coverage)."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_workflows_dir = swarm.WORKFLOWS_DIR
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.WORKFLOWS_DIR = swarm.SWARM_DIR / "workflows"
        swarm.WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.WORKFLOWS_DIR = self.original_workflows_dir
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_yaml(self, filename, content):
        """Write YAML content to a file in the temp directory."""
        path = Path(self.temp_dir) / filename
        path.write_text(content)
        return str(path)

    @patch('swarm.spawn_workflow_stage')
    def test_run_immediate_direct(self, mock_spawn):
        """Test running workflow immediately via direct call."""
        # Mock spawn to return a mock worker
        mock_worker = MagicMock()
        mock_worker.name = 'direct-workflow-work'
        mock_worker.tmux = MagicMock()
        mock_worker.tmux.session = 'test-session'
        mock_worker.tmux.window = 'direct-workflow-work'
        mock_spawn.return_value = mock_worker

        yaml_path = self._write_yaml('direct.yaml', '''
name: direct-workflow
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        args = Namespace(
            file=yaml_path,
            at_time=None,
            in_delay=None,
            name=None,
            force=False
        )
        # Capture stdout
        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_run(args)

        output = captured.getvalue()
        self.assertIn("started", output.lower())

        # Verify state
        state = swarm.load_workflow_state("direct-workflow")
        self.assertIsNotNone(state)
        self.assertEqual(state.status, "running")

    @patch('swarm.spawn_workflow_stage')
    def test_run_with_name_override_direct(self, mock_spawn):
        """Test running with --name override via direct call."""
        # Mock spawn to return a mock worker
        mock_worker = MagicMock()
        mock_worker.name = 'custom-name-work'
        mock_worker.tmux = MagicMock()
        mock_worker.tmux.session = 'test-session'
        mock_worker.tmux.window = 'custom-name-work'
        mock_spawn.return_value = mock_worker

        yaml_path = self._write_yaml('name-override.yaml', '''
name: original
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        args = Namespace(
            file=yaml_path,
            at_time=None,
            in_delay=None,
            name="custom-name",
            force=False
        )
        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_run(args)

        state = swarm.load_workflow_state("custom-name")
        self.assertIsNotNone(state)
        self.assertEqual(state.name, "custom-name")

    def test_run_scheduled_with_at_direct(self):
        """Test running scheduled workflow with --at via direct call."""
        yaml_path = self._write_yaml('at-schedule.yaml', '''
name: at-scheduled
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        args = Namespace(
            file=yaml_path,
            at_time="02:00",
            in_delay=None,
            name=None,
            force=False
        )
        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_run(args)

        state = swarm.load_workflow_state("at-scheduled")
        self.assertEqual(state.status, "scheduled")
        self.assertIsNotNone(state.scheduled_for)

    def test_run_scheduled_with_in_direct(self):
        """Test running scheduled workflow with --in via direct call."""
        yaml_path = self._write_yaml('in-schedule.yaml', '''
name: in-scheduled
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        args = Namespace(
            file=yaml_path,
            at_time=None,
            in_delay="4h",
            name=None,
            force=False
        )
        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_run(args)

        state = swarm.load_workflow_state("in-scheduled")
        self.assertEqual(state.status, "scheduled")

    def test_run_file_not_found_direct(self):
        """Test file not found error via direct call."""
        args = Namespace(
            file="/nonexistent/path.yaml",
            at_time=None,
            in_delay=None,
            name=None,
            force=False
        )
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_run(args)
        self.assertEqual(ctx.exception.code, 1)

    @patch('swarm.spawn_workflow_stage')
    def test_run_duplicate_error_direct(self, mock_spawn):
        """Test duplicate workflow error via direct call."""
        # Mock spawn to return a mock worker
        mock_worker = MagicMock()
        mock_worker.name = 'duplicate-work'
        mock_worker.tmux = MagicMock()
        mock_worker.tmux.session = 'test-session'
        mock_worker.tmux.window = 'duplicate-work'
        mock_spawn.return_value = mock_worker

        yaml_path = self._write_yaml('dup.yaml', '''
name: duplicate
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        # First run
        args = Namespace(file=yaml_path, at_time=None, in_delay=None, name=None, force=False)
        import io
        with patch('sys.stdout', io.StringIO()):
            swarm.cmd_workflow_run(args)

        # Second run should fail (workflow already exists error, not spawn error)
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_run(args)
        self.assertEqual(ctx.exception.code, 1)

    @patch('swarm.spawn_workflow_stage')
    def test_run_force_overwrite_direct(self, mock_spawn):
        """Test --force overwrites via direct call."""
        # Mock spawn to return a mock worker
        mock_worker = MagicMock()
        mock_worker.name = 'force-test-work'
        mock_worker.tmux = MagicMock()
        mock_worker.tmux.session = 'test-session'
        mock_worker.tmux.window = 'force-test-work'
        mock_spawn.return_value = mock_worker

        yaml_path = self._write_yaml('force.yaml', '''
name: force-test
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        args = Namespace(file=yaml_path, at_time=None, in_delay=None, name=None, force=False)
        import io
        with patch('sys.stdout', io.StringIO()):
            swarm.cmd_workflow_run(args)

        # Second run with force
        args.force = True
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_run(args)
        self.assertIn("started", captured.getvalue().lower())

    def test_run_at_in_mutually_exclusive_direct(self):
        """Test --at and --in mutually exclusive via direct call."""
        yaml_path = self._write_yaml('both.yaml', '''
name: both-test
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        args = Namespace(
            file=yaml_path,
            at_time="02:00",
            in_delay="4h",
            name=None,
            force=False
        )
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_run(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_run_invalid_at_direct(self):
        """Test invalid --at time via direct call."""
        yaml_path = self._write_yaml('bad-at.yaml', '''
name: bad-at-test
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        args = Namespace(
            file=yaml_path,
            at_time="invalid",
            in_delay=None,
            name=None,
            force=False
        )
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_run(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_run_invalid_in_direct(self):
        """Test invalid --in duration via direct call."""
        yaml_path = self._write_yaml('bad-in.yaml', '''
name: bad-in-test
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        args = Namespace(
            file=yaml_path,
            at_time=None,
            in_delay="invalid",
            name=None,
            force=False
        )
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_run(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_run_yaml_schedule_direct(self):
        """Test workflow with schedule in YAML via direct call."""
        yaml_path = self._write_yaml('yaml-sched.yaml', '''
name: yaml-sched-test
schedule: "03:00"
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        args = Namespace(file=yaml_path, at_time=None, in_delay=None, name=None, force=False)
        import io
        with patch('sys.stdout', io.StringIO()):
            swarm.cmd_workflow_run(args)

        state = swarm.load_workflow_state("yaml-sched-test")
        self.assertEqual(state.status, "scheduled")

    def test_run_yaml_delay_direct(self):
        """Test workflow with delay in YAML via direct call."""
        yaml_path = self._write_yaml('yaml-delay.yaml', '''
name: yaml-delay-test
delay: "2h"
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        args = Namespace(file=yaml_path, at_time=None, in_delay=None, name=None, force=False)
        import io
        with patch('sys.stdout', io.StringIO()):
            swarm.cmd_workflow_run(args)

        state = swarm.load_workflow_state("yaml-delay-test")
        self.assertEqual(state.status, "scheduled")

    def test_run_invalid_yaml_schedule_direct(self):
        """Test workflow with invalid schedule in YAML via direct call."""
        yaml_path = self._write_yaml('bad-yaml-sched.yaml', '''
name: bad-yaml-sched-test
schedule: "invalid"
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        args = Namespace(file=yaml_path, at_time=None, in_delay=None, name=None, force=False)
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_run(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_run_invalid_yaml_delay_direct(self):
        """Test workflow with invalid delay in YAML via direct call."""
        yaml_path = self._write_yaml('bad-yaml-delay.yaml', '''
name: bad-yaml-delay-test
delay: "invalid"
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        args = Namespace(file=yaml_path, at_time=None, in_delay=None, name=None, force=False)
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_run(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_run_validation_errors_direct(self):
        """Test prompt file validation errors via direct call."""
        yaml_path = self._write_yaml('prompt-errors.yaml', '''
name: prompt-errors-test
stages:
  - name: work
    type: worker
    prompt-file: ./nonexistent.md
''')
        args = Namespace(file=yaml_path, at_time=None, in_delay=None, name=None, force=False)
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_run(args)
        self.assertEqual(ctx.exception.code, 1)

    @patch('swarm.spawn_workflow_stage')
    def test_run_multi_stage_direct(self, mock_spawn):
        """Test multi-stage workflow via direct call."""
        # Mock spawn to return a mock worker
        mock_worker = MagicMock()
        mock_worker.name = 'multi-test-plan'
        mock_worker.tmux = MagicMock()
        mock_worker.tmux.session = 'test-session'
        mock_worker.tmux.window = 'multi-test-plan'
        mock_spawn.return_value = mock_worker

        yaml_path = self._write_yaml('multi.yaml', '''
name: multi-test
stages:
  - name: plan
    type: worker
    prompt: Plan
  - name: build
    type: ralph
    prompt: Build
    max-iterations: 10
  - name: test
    type: worker
    prompt: Test
''')
        args = Namespace(file=yaml_path, at_time=None, in_delay=None, name=None, force=False)
        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_run(args)

        self.assertIn("stage 1/3", captured.getvalue())
        state = swarm.load_workflow_state("multi-test")
        self.assertEqual(len(state.stages), 3)
        self.assertEqual(state.stages["plan"].status, "running")
        self.assertEqual(state.stages["build"].status, "pending")
        self.assertEqual(state.stages["test"].status, "pending")


class TestParseScheduleTime(unittest.TestCase):
    """Test parse_schedule_time function."""

    def test_parse_valid_time(self):
        """Test parsing valid HH:MM time."""
        # We can't test exact datetime, but we can test format validation
        result = swarm.parse_schedule_time("02:00")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.hour, 2)
        self.assertEqual(result.minute, 0)

    def test_parse_afternoon_time(self):
        """Test parsing afternoon time."""
        result = swarm.parse_schedule_time("14:30")
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)

    def test_parse_midnight(self):
        """Test parsing midnight."""
        result = swarm.parse_schedule_time("00:00")
        self.assertEqual(result.hour, 0)
        self.assertEqual(result.minute, 0)

    def test_parse_end_of_day(self):
        """Test parsing end of day time."""
        result = swarm.parse_schedule_time("23:59")
        self.assertEqual(result.hour, 23)
        self.assertEqual(result.minute, 59)

    def test_parse_single_digit_hour(self):
        """Test parsing time with single digit hour."""
        result = swarm.parse_schedule_time("2:00")
        self.assertEqual(result.hour, 2)
        self.assertEqual(result.minute, 0)

    def test_error_invalid_format(self):
        """Test error on invalid format."""
        with self.assertRaises(ValueError) as ctx:
            swarm.parse_schedule_time("2:00pm")
        self.assertIn("invalid time format", str(ctx.exception))

    def test_error_invalid_hour(self):
        """Test error on invalid hour."""
        with self.assertRaises(ValueError) as ctx:
            swarm.parse_schedule_time("25:00")
        self.assertIn("invalid hour", str(ctx.exception))

    def test_error_invalid_minute(self):
        """Test error on invalid minute."""
        with self.assertRaises(ValueError) as ctx:
            swarm.parse_schedule_time("12:60")
        self.assertIn("invalid minute", str(ctx.exception))

    def test_error_empty_string(self):
        """Test error on empty string."""
        with self.assertRaises(ValueError) as ctx:
            swarm.parse_schedule_time("")
        self.assertIn("empty time string", str(ctx.exception))

    def test_error_no_colon(self):
        """Test error on time without colon."""
        with self.assertRaises(ValueError) as ctx:
            swarm.parse_schedule_time("1400")
        self.assertIn("invalid time format", str(ctx.exception))

    def test_returns_future_time(self):
        """Test that returned time is always in the future."""
        result = swarm.parse_schedule_time("02:00")
        now = datetime.now(timezone.utc)
        self.assertGreater(result, now)


class TestWorkflowRunSubparser(unittest.TestCase):
    """Test that workflow run subparser is correctly configured."""

    def test_workflow_run_subcommand_exists(self):
        """Test that 'workflow run' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('run', result.stdout.lower())

    def test_workflow_run_help_has_description(self):
        """Test that workflow run help has description."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('Run a workflow', result.stdout)

    def test_workflow_run_help_has_scheduling_options(self):
        """Test that workflow run help shows scheduling options."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--at', result.stdout)
        self.assertIn('--in', result.stdout)
        self.assertIn('--name', result.stdout)
        self.assertIn('--force', result.stdout)

    def test_workflow_run_help_has_examples(self):
        """Test that workflow run help has examples."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('Examples:', result.stdout)


class TestWorkflowRunCommand(unittest.TestCase):
    """Test workflow run command functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_workflows_dir = swarm.WORKFLOWS_DIR
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.WORKFLOWS_DIR = swarm.SWARM_DIR / "workflows"
        swarm.WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.WORKFLOWS_DIR = self.original_workflows_dir
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_yaml(self, filename, content):
        """Write YAML content to a file in the temp directory."""
        path = Path(self.temp_dir) / filename
        path.write_text(content)
        return str(path)

    def test_run_valid_workflow_immediate(self):
        """Test running a valid workflow with scheduling (to avoid tmux dependency)."""
        yaml_path = self._write_yaml('valid.yaml', '''
name: test-workflow
stages:
  - name: plan
    type: worker
    prompt: Create a plan
''')
        # Use --at to schedule instead of running immediately (avoids tmux)
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path, '--at', '02:00'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("Workflow 'test-workflow' scheduled", result.stdout)

    def test_run_creates_workflow_state(self):
        """Test that running creates workflow state."""
        yaml_path = self._write_yaml('state-test.yaml', '''
name: state-test-workflow
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        # Use scheduling to avoid tmux dependency
        subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path, '--at', '02:00'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )

        # Verify state was created
        state = swarm.load_workflow_state("state-test-workflow")
        self.assertIsNotNone(state)
        self.assertEqual(state.name, "state-test-workflow")
        # Status is scheduled since we used --at
        self.assertEqual(state.status, "scheduled")
        # Current stage is not set until workflow actually starts
        self.assertIsNone(state.current_stage)
        self.assertEqual(state.current_stage_index, 0)

    def test_run_with_name_override(self):
        """Test running with --name override."""
        yaml_path = self._write_yaml('override.yaml', '''
name: original-name
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path, '--name', 'custom-name'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("Workflow 'custom-name' started", result.stdout)

        # Verify state uses custom name
        state = swarm.load_workflow_state("custom-name")
        self.assertIsNotNone(state)
        self.assertEqual(state.name, "custom-name")

    def test_run_duplicate_name_error(self):
        """Test error when workflow with same name exists."""
        yaml_path = self._write_yaml('dup.yaml', '''
name: duplicate-workflow
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        # First run
        subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )

        # Second run should fail
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("already exists", result.stderr)
        self.assertIn("--force", result.stderr)

    def test_run_with_force_overwrites(self):
        """Test --force overwrites existing workflow."""
        # Use --at scheduling to avoid tmux dependency in tests
        yaml_path = self._write_yaml('force.yaml', '''
name: force-workflow
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        # First run with scheduling (no tmux needed)
        subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path, '--at', '02:00'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )

        # Second run with --force should succeed
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path, '--force', '--at', '03:00'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("Workflow 'force-workflow' scheduled", result.stdout)

    def test_run_missing_file_error(self):
        """Test error when file doesn't exist."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', '/nonexistent/path.yaml'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('not found', result.stderr.lower())

    def test_run_validation_error(self):
        """Test error when YAML is invalid."""
        yaml_path = self._write_yaml('invalid.yaml', '''
name: invalid-workflow
stages: []
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('at least one stage', result.stderr)

    def test_run_with_at_schedule(self):
        """Test running with --at schedule."""
        yaml_path = self._write_yaml('scheduled.yaml', '''
name: scheduled-workflow
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path, '--at', '02:00'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("scheduled", result.stdout.lower())
        self.assertIn("02:00", result.stdout)

        # Verify state is scheduled
        state = swarm.load_workflow_state("scheduled-workflow")
        self.assertIsNotNone(state)
        self.assertEqual(state.status, "scheduled")
        self.assertIsNotNone(state.scheduled_for)

    def test_run_with_in_schedule(self):
        """Test running with --in delay."""
        yaml_path = self._write_yaml('delayed.yaml', '''
name: delayed-workflow
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path, '--in', '4h'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("scheduled", result.stdout.lower())
        self.assertIn("in 4h", result.stdout)

        # Verify state is scheduled
        state = swarm.load_workflow_state("delayed-workflow")
        self.assertIsNotNone(state)
        self.assertEqual(state.status, "scheduled")
        self.assertIsNotNone(state.scheduled_for)

    def test_run_at_and_in_mutually_exclusive(self):
        """Test that --at and --in are mutually exclusive."""
        yaml_path = self._write_yaml('both.yaml', '''
name: both-workflow
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path, '--at', '02:00', '--in', '4h'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('cannot use both', result.stderr)

    def test_run_invalid_at_time_error(self):
        """Test error on invalid --at time format."""
        yaml_path = self._write_yaml('bad-time.yaml', '''
name: bad-time-workflow
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path, '--at', 'invalid'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('invalid time format', result.stderr)

    def test_run_invalid_in_duration_error(self):
        """Test error on invalid --in duration."""
        yaml_path = self._write_yaml('bad-duration.yaml', '''
name: bad-duration-workflow
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path, '--in', 'invalid'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('invalid duration', result.stderr)

    def test_run_with_yaml_schedule(self):
        """Test running workflow that has schedule in YAML."""
        yaml_path = self._write_yaml('yaml-scheduled.yaml', '''
name: yaml-scheduled-workflow
schedule: "03:00"
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("scheduled", result.stdout.lower())

        # Verify state is scheduled
        state = swarm.load_workflow_state("yaml-scheduled-workflow")
        self.assertEqual(state.status, "scheduled")

    def test_run_with_yaml_delay(self):
        """Test running workflow that has delay in YAML."""
        yaml_path = self._write_yaml('yaml-delayed.yaml', '''
name: yaml-delayed-workflow
delay: "2h"
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("scheduled", result.stdout.lower())

        # Verify state is scheduled
        state = swarm.load_workflow_state("yaml-delayed-workflow")
        self.assertEqual(state.status, "scheduled")

    def test_run_cli_schedule_overrides_yaml(self):
        """Test that CLI --at overrides YAML schedule."""
        yaml_path = self._write_yaml('override-schedule.yaml', '''
name: override-schedule-workflow
schedule: "05:00"
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        # Run with --at should use CLI time
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path, '--at', '08:00'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("08:00", result.stdout)

    def test_run_multi_stage_workflow(self):
        """Test running workflow with multiple stages (scheduled to avoid tmux)."""
        yaml_path = self._write_yaml('multi-stage.yaml', '''
name: multi-stage-workflow
stages:
  - name: plan
    type: worker
    prompt: Create plan
  - name: build
    type: ralph
    prompt: Build it
    max-iterations: 10
  - name: validate
    type: worker
    prompt: Validate
''')
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path, '--at', '02:00'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("scheduled", result.stdout.lower())

        # Verify state has all stages initialized
        state = swarm.load_workflow_state("multi-stage-workflow")
        self.assertEqual(len(state.stages), 3)
        # All stages are pending since workflow is scheduled
        self.assertEqual(state.stages["plan"].status, "pending")
        self.assertEqual(state.stages["build"].status, "pending")
        self.assertEqual(state.stages["validate"].status, "pending")

    def test_run_sets_worker_name(self):
        """Test that workflow state has worker name placeholder (scheduled, no worker spawned yet)."""
        yaml_path = self._write_yaml('worker-name.yaml', '''
name: worker-name-test
stages:
  - name: my-stage
    type: worker
    prompt: Do work
''')
        # Use scheduling to avoid tmux - worker_name won't be set until stage starts
        subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path, '--at', '02:00'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )

        state = swarm.load_workflow_state("worker-name-test")
        # Worker name is not set until stage actually starts
        self.assertIsNone(state.stages["my-stage"].worker_name)

    def test_run_copies_yaml_file(self):
        """Test that running copies the YAML file."""
        yaml_path = self._write_yaml('copy-test.yaml', '''
name: copy-test-workflow
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        # Use scheduling to avoid tmux
        subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path, '--at', '02:00'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )

        # Verify YAML was copied
        yaml_copy_path = swarm.get_workflow_yaml_copy_path("copy-test-workflow")
        self.assertTrue(yaml_copy_path.exists())

    def test_run_creates_logs_directory(self):
        """Test that running creates logs directory."""
        yaml_path = self._write_yaml('logs-test.yaml', '''
name: logs-test-workflow
stages:
  - name: work
    type: worker
    prompt: Do work
''')
        # Use scheduling to avoid tmux
        subprocess.run(
            [sys.executable, 'swarm.py', 'workflow', 'run', yaml_path, '--at', '02:00'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )

        # Verify logs directory was created
        logs_dir = swarm.get_workflow_logs_dir("logs-test-workflow")
        self.assertTrue(logs_dir.exists())


class TestSpawnWorkflowStage(unittest.TestCase):
    """Test spawn_workflow_stage function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_workflows_dir = swarm.WORKFLOWS_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_logs_dir = swarm.LOGS_DIR
        self.original_heartbeats_dir = swarm.HEARTBEATS_DIR
        self.original_ralph_dir = swarm.RALPH_DIR

        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.WORKFLOWS_DIR = swarm.SWARM_DIR / "workflows"
        swarm.STATE_FILE = swarm.SWARM_DIR / "state.json"
        swarm.LOGS_DIR = swarm.SWARM_DIR / "logs"
        swarm.HEARTBEATS_DIR = swarm.SWARM_DIR / "heartbeats"
        swarm.RALPH_DIR = swarm.SWARM_DIR / "ralph"
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"

        swarm.SWARM_DIR.mkdir(parents=True, exist_ok=True)
        swarm.WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.HEARTBEATS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.RALPH_DIR.mkdir(parents=True, exist_ok=True)

        self.workflow_dir = Path(self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.WORKFLOWS_DIR = self.original_workflows_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.LOGS_DIR = self.original_logs_dir
        swarm.HEARTBEATS_DIR = self.original_heartbeats_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_workflow_def(self, **kwargs):
        """Create a basic workflow definition."""
        defaults = {
            'name': 'test-workflow',
            'description': None,
            'schedule': None,
            'delay': None,
            'heartbeat': None,
            'heartbeat_expire': None,
            'heartbeat_message': 'continue',
            'worktree': False,
            'cwd': None,
            'stages': [],
        }
        defaults.update(kwargs)
        return swarm.WorkflowDefinition(**defaults)

    def _make_stage_def(self, **kwargs):
        """Create a basic stage definition."""
        defaults = {
            'name': 'test-stage',
            'type': 'worker',
            'prompt': 'Test prompt',
            'prompt_file': None,
            'done_pattern': None,
            'timeout': None,
            'on_failure': 'stop',
            'max_retries': 3,
            'on_complete': 'next',
            'max_iterations': None,
            'inactivity_timeout': 60,
            'check_done_continuous': False,
            'heartbeat': None,
            'heartbeat_expire': None,
            'heartbeat_message': None,
            'worktree': None,
            'cwd': None,
            'env': {},
            'tags': [],
        }
        defaults.update(kwargs)
        return swarm.StageDefinition(**defaults)

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    def test_spawn_worker_stage_basic(self, mock_session, mock_send, mock_create_tmux):
        """Test spawning a basic worker stage."""
        mock_session.return_value = "test-session"

        workflow_def = self._make_workflow_def(name='my-workflow')
        stage_def = self._make_stage_def(name='plan', prompt='Create a plan')

        worker = swarm.spawn_workflow_stage(
            workflow_name='my-workflow',
            workflow_def=workflow_def,
            stage_def=stage_def,
            workflow_dir=self.workflow_dir,
        )

        # Verify worker was created correctly
        self.assertEqual(worker.name, 'my-workflow-plan')
        self.assertEqual(worker.status, 'running')
        self.assertIsNotNone(worker.tmux)
        self.assertEqual(worker.tmux.session, 'test-session')
        self.assertEqual(worker.tmux.window, 'my-workflow-plan')

        # Verify tmux window was created
        mock_create_tmux.assert_called_once()

        # Verify prompt was sent
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        self.assertEqual(call_args[0][1], 'Create a plan')

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    def test_spawn_worker_stage_with_prompt_file(self, mock_session, mock_send, mock_create_tmux):
        """Test spawning worker stage with prompt file."""
        mock_session.return_value = "test-session"

        # Create a prompt file
        prompt_file = self.workflow_dir / 'prompts' / 'plan.md'
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text('This is the plan prompt from file.')

        workflow_def = self._make_workflow_def(name='file-workflow')
        stage_def = self._make_stage_def(
            name='plan',
            prompt=None,
            prompt_file='prompts/plan.md'
        )

        worker = swarm.spawn_workflow_stage(
            workflow_name='file-workflow',
            workflow_def=workflow_def,
            stage_def=stage_def,
            workflow_dir=self.workflow_dir,
        )

        # Verify prompt was read from file and sent
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        self.assertEqual(call_args[0][1], 'This is the plan prompt from file.')

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    def test_spawn_worker_stage_with_env_vars(self, mock_session, mock_send, mock_create_tmux):
        """Test spawning worker stage with environment variables."""
        mock_session.return_value = "test-session"

        workflow_def = self._make_workflow_def(name='env-workflow')
        stage_def = self._make_stage_def(
            name='work',
            prompt='Do work',
            env={'DEBUG': 'true', 'API_KEY': 'secret'}
        )

        worker = swarm.spawn_workflow_stage(
            workflow_name='env-workflow',
            workflow_def=workflow_def,
            stage_def=stage_def,
            workflow_dir=self.workflow_dir,
        )

        self.assertEqual(worker.env, {'DEBUG': 'true', 'API_KEY': 'secret'})

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    def test_spawn_worker_stage_with_tags(self, mock_session, mock_send, mock_create_tmux):
        """Test spawning worker stage with tags."""
        mock_session.return_value = "test-session"

        workflow_def = self._make_workflow_def(name='tag-workflow')
        stage_def = self._make_stage_def(
            name='work',
            prompt='Do work',
            tags=['planning', 'important']
        )

        worker = swarm.spawn_workflow_stage(
            workflow_name='tag-workflow',
            workflow_def=workflow_def,
            stage_def=stage_def,
            workflow_dir=self.workflow_dir,
        )

        self.assertEqual(worker.tags, ['planning', 'important'])

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    @patch('swarm.save_ralph_state')
    @patch('swarm.log_ralph_iteration')
    def test_spawn_ralph_stage(self, mock_log, mock_save_ralph, mock_session, mock_send, mock_create_tmux):
        """Test spawning a ralph-type stage."""
        mock_session.return_value = "test-session"

        # Create workflow state directory (needed for inline prompt temp file)
        workflow_state_dir = swarm.get_workflow_state_dir('ralph-workflow')
        workflow_state_dir.mkdir(parents=True, exist_ok=True)

        workflow_def = self._make_workflow_def(name='ralph-workflow')
        stage_def = self._make_stage_def(
            name='build',
            type='ralph',
            prompt='Build the feature',
            max_iterations=50,
            inactivity_timeout=120,
            done_pattern='/done',
            check_done_continuous=True
        )

        worker = swarm.spawn_workflow_stage(
            workflow_name='ralph-workflow',
            workflow_def=workflow_def,
            stage_def=stage_def,
            workflow_dir=self.workflow_dir,
        )

        # Verify worker was created as ralph
        self.assertEqual(worker.name, 'ralph-workflow-build')
        self.assertTrue(worker.metadata.get('ralph'))
        self.assertEqual(worker.metadata.get('ralph_iteration'), 1)

        # Verify ralph state was saved
        mock_save_ralph.assert_called()
        call_args = mock_save_ralph.call_args[0][0]
        self.assertEqual(call_args.worker_name, 'ralph-workflow-build')
        self.assertEqual(call_args.max_iterations, 50)
        self.assertEqual(call_args.inactivity_timeout, 120)
        self.assertEqual(call_args.done_pattern, '/done')
        self.assertTrue(call_args.check_done_continuous)

        # Verify iteration was logged
        mock_log.assert_called()

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    def test_spawn_worker_added_to_state(self, mock_session, mock_send, mock_create_tmux):
        """Test that spawned worker is added to swarm state."""
        mock_session.return_value = "test-session"

        workflow_def = self._make_workflow_def(name='state-workflow')
        stage_def = self._make_stage_def(name='work', prompt='Do work')

        worker = swarm.spawn_workflow_stage(
            workflow_name='state-workflow',
            workflow_def=workflow_def,
            stage_def=stage_def,
            workflow_dir=self.workflow_dir,
        )

        # Verify worker is in state
        state = swarm.State()
        found = state.get_worker('state-workflow-work')
        self.assertIsNotNone(found)
        self.assertEqual(found.name, 'state-workflow-work')

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    def test_spawn_duplicate_worker_raises_error(self, mock_session, mock_send, mock_create_tmux):
        """Test that spawning duplicate worker raises RuntimeError."""
        mock_session.return_value = "test-session"

        workflow_def = self._make_workflow_def(name='dup-workflow')
        stage_def = self._make_stage_def(name='work', prompt='Do work')

        # Spawn first worker
        swarm.spawn_workflow_stage(
            workflow_name='dup-workflow',
            workflow_def=workflow_def,
            stage_def=stage_def,
            workflow_dir=self.workflow_dir,
        )

        # Try to spawn again - should fail
        with self.assertRaises(RuntimeError) as ctx:
            swarm.spawn_workflow_stage(
                workflow_name='dup-workflow',
                workflow_def=workflow_def,
                stage_def=stage_def,
                workflow_dir=self.workflow_dir,
            )
        self.assertIn("already exists", str(ctx.exception))

    def test_spawn_no_prompt_raises_error(self):
        """Test that spawning without prompt raises RuntimeError."""
        workflow_def = self._make_workflow_def(name='no-prompt-workflow')
        stage_def = self._make_stage_def(
            name='work',
            prompt=None,
            prompt_file=None
        )

        with self.assertRaises(RuntimeError) as ctx:
            swarm.spawn_workflow_stage(
                workflow_name='no-prompt-workflow',
                workflow_def=workflow_def,
                stage_def=stage_def,
                workflow_dir=self.workflow_dir,
            )
        self.assertIn("no prompt or prompt_file", str(ctx.exception))

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    @patch('swarm.save_heartbeat_state')
    @patch('swarm.start_heartbeat_monitor')
    def test_spawn_with_heartbeat(self, mock_start_hb, mock_save_hb, mock_session, mock_send, mock_create_tmux):
        """Test spawning stage with heartbeat configuration."""
        mock_session.return_value = "test-session"
        mock_start_hb.return_value = 12345

        workflow_def = self._make_workflow_def(
            name='hb-workflow',
            heartbeat='4h',
            heartbeat_expire='24h',
            heartbeat_message='keep going'
        )
        stage_def = self._make_stage_def(name='work', prompt='Do work')

        swarm.spawn_workflow_stage(
            workflow_name='hb-workflow',
            workflow_def=workflow_def,
            stage_def=stage_def,
            workflow_dir=self.workflow_dir,
        )

        # Verify heartbeat was set up
        mock_save_hb.assert_called()
        mock_start_hb.assert_called_with('hb-workflow-work')

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    @patch('swarm.save_heartbeat_state')
    @patch('swarm.start_heartbeat_monitor')
    def test_spawn_stage_heartbeat_overrides_global(self, mock_start_hb, mock_save_hb, mock_session, mock_send, mock_create_tmux):
        """Test that stage heartbeat settings override global settings."""
        mock_session.return_value = "test-session"
        mock_start_hb.return_value = 12345

        workflow_def = self._make_workflow_def(
            name='override-workflow',
            heartbeat='4h',
            heartbeat_message='global'
        )
        stage_def = self._make_stage_def(
            name='work',
            prompt='Do work',
            heartbeat='2h',
            heartbeat_message='stage'
        )

        swarm.spawn_workflow_stage(
            workflow_name='override-workflow',
            workflow_def=workflow_def,
            stage_def=stage_def,
            workflow_dir=self.workflow_dir,
        )

        # Verify stage heartbeat was used
        mock_save_hb.assert_called()
        call_args = mock_save_hb.call_args[0][0]
        # 2h = 7200 seconds
        self.assertEqual(call_args.interval_seconds, 7200)
        self.assertEqual(call_args.message, 'stage')

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    def test_spawn_with_cwd_setting(self, mock_session, mock_send, mock_create_tmux):
        """Test spawning stage with cwd setting."""
        mock_session.return_value = "test-session"

        # Create a cwd directory
        cwd_dir = self.workflow_dir / 'work-dir'
        cwd_dir.mkdir(parents=True, exist_ok=True)

        workflow_def = self._make_workflow_def(
            name='cwd-workflow',
            cwd='work-dir'
        )
        stage_def = self._make_stage_def(
            name='work',
            prompt='Do work'
        )

        worker = swarm.spawn_workflow_stage(
            workflow_name='cwd-workflow',
            workflow_def=workflow_def,
            stage_def=stage_def,
            workflow_dir=self.workflow_dir,
        )

        # Verify cwd was set (relative path resolved against workflow_dir)
        self.assertEqual(worker.cwd, str(self.workflow_dir / 'work-dir'))

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    def test_spawn_with_stage_cwd_overrides_global(self, mock_session, mock_send, mock_create_tmux):
        """Test that stage cwd overrides global cwd."""
        mock_session.return_value = "test-session"

        # Create cwd directories
        global_cwd = self.workflow_dir / 'global-dir'
        global_cwd.mkdir(parents=True, exist_ok=True)
        stage_cwd = self.workflow_dir / 'stage-dir'
        stage_cwd.mkdir(parents=True, exist_ok=True)

        workflow_def = self._make_workflow_def(
            name='cwd-override-workflow',
            cwd='global-dir'
        )
        stage_def = self._make_stage_def(
            name='work',
            prompt='Do work',
            cwd='stage-dir'
        )

        worker = swarm.spawn_workflow_stage(
            workflow_name='cwd-override-workflow',
            workflow_def=workflow_def,
            stage_def=stage_def,
            workflow_dir=self.workflow_dir,
        )

        # Verify stage cwd was used, not global
        self.assertEqual(worker.cwd, str(self.workflow_dir / 'stage-dir'))

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    @patch('swarm.create_worktree')
    @patch('swarm.get_git_root')
    def test_spawn_with_worktree(self, mock_git_root, mock_create_wt, mock_session, mock_send, mock_create_tmux):
        """Test spawning stage with worktree enabled."""
        mock_session.return_value = "test-session"
        mock_git_root.return_value = Path('/fake/repo')

        workflow_def = self._make_workflow_def(
            name='wt-workflow',
            worktree=True
        )
        stage_def = self._make_stage_def(
            name='build',
            prompt='Build it'
        )

        worker = swarm.spawn_workflow_stage(
            workflow_name='wt-workflow',
            workflow_def=workflow_def,
            stage_def=stage_def,
            workflow_dir=self.workflow_dir,
        )

        # Verify worktree was created
        mock_create_wt.assert_called_once()
        call_args = mock_create_wt.call_args[0]
        self.assertIn('wt-workflow-build', str(call_args[0]))

        # Verify worktree info was set
        self.assertIsNotNone(worker.worktree)
        self.assertEqual(worker.worktree.branch, 'wt-workflow-build')

    @patch('swarm.create_tmux_window')
    @patch('swarm.get_default_session_name')
    @patch('swarm.get_git_root')
    def test_spawn_worktree_not_in_git_repo(self, mock_git_root, mock_session, mock_create_tmux):
        """Test that worktree fails when not in git repo."""
        mock_session.return_value = "test-session"
        mock_git_root.side_effect = subprocess.CalledProcessError(1, 'git')

        workflow_def = self._make_workflow_def(
            name='no-git-workflow',
            worktree=True
        )
        stage_def = self._make_stage_def(
            name='work',
            prompt='Do work'
        )

        with self.assertRaises(RuntimeError) as ctx:
            swarm.spawn_workflow_stage(
                workflow_name='no-git-workflow',
                workflow_def=workflow_def,
                stage_def=stage_def,
                workflow_dir=self.workflow_dir,
            )
        self.assertIn("not in a git repository", str(ctx.exception))

    @patch('swarm.create_tmux_window')
    @patch('swarm.get_default_session_name')
    @patch('swarm.create_worktree')
    @patch('swarm.get_git_root')
    def test_spawn_worktree_creation_fails(self, mock_git_root, mock_create_wt, mock_session, mock_create_tmux):
        """Test handling when worktree creation fails."""
        mock_session.return_value = "test-session"
        mock_git_root.return_value = Path('/fake/repo')
        mock_create_wt.side_effect = subprocess.CalledProcessError(1, 'git worktree')

        workflow_def = self._make_workflow_def(
            name='wt-fail-workflow',
            worktree=True
        )
        stage_def = self._make_stage_def(
            name='work',
            prompt='Do work'
        )

        with self.assertRaises(RuntimeError) as ctx:
            swarm.spawn_workflow_stage(
                workflow_name='wt-fail-workflow',
                workflow_def=workflow_def,
                stage_def=stage_def,
                workflow_dir=self.workflow_dir,
            )
        self.assertIn("failed to create worktree", str(ctx.exception))

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    @patch('swarm.remove_worktree')
    @patch('swarm.create_worktree')
    @patch('swarm.get_git_root')
    def test_spawn_tmux_fails_cleans_up_worktree(self, mock_git_root, mock_create_wt, mock_remove_wt, mock_session, mock_send, mock_create_tmux):
        """Test that worktree is cleaned up when tmux fails."""
        mock_session.return_value = "test-session"
        mock_git_root.return_value = Path('/fake/repo')
        mock_create_tmux.side_effect = subprocess.CalledProcessError(1, 'tmux')

        workflow_def = self._make_workflow_def(
            name='cleanup-workflow',
            worktree=True
        )
        stage_def = self._make_stage_def(
            name='work',
            prompt='Do work'
        )

        with self.assertRaises(RuntimeError) as ctx:
            swarm.spawn_workflow_stage(
                workflow_name='cleanup-workflow',
                workflow_def=workflow_def,
                stage_def=stage_def,
                workflow_dir=self.workflow_dir,
            )
        self.assertIn("failed to create tmux window", str(ctx.exception))

        # Verify worktree cleanup was attempted
        mock_remove_wt.assert_called_once()

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    @patch('swarm.save_ralph_state')
    @patch('swarm.log_ralph_iteration')
    def test_spawn_ralph_stage_with_prompt_file(self, mock_log, mock_save_ralph, mock_session, mock_send, mock_create_tmux):
        """Test spawning a ralph-type stage with prompt file (not inline)."""
        mock_session.return_value = "test-session"

        # Create a prompt file
        prompt_file = self.workflow_dir / 'prompts' / 'build.md'
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text('Build the feature.')

        # Create workflow state directory (needed for ralph)
        workflow_state_dir = swarm.get_workflow_state_dir('ralph-file-workflow')
        workflow_state_dir.mkdir(parents=True, exist_ok=True)

        workflow_def = self._make_workflow_def(name='ralph-file-workflow')
        stage_def = self._make_stage_def(
            name='build',
            type='ralph',
            prompt=None,
            prompt_file='prompts/build.md',
            max_iterations=20
        )

        worker = swarm.spawn_workflow_stage(
            workflow_name='ralph-file-workflow',
            workflow_def=workflow_def,
            stage_def=stage_def,
            workflow_dir=self.workflow_dir,
        )

        # Verify ralph state was saved with the prompt file path
        mock_save_ralph.assert_called()
        call_args = mock_save_ralph.call_args[0][0]
        self.assertIn('build.md', call_args.prompt_file)

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    def test_spawn_with_invalid_heartbeat_interval(self, mock_session, mock_send, mock_create_tmux):
        """Test spawning with invalid heartbeat interval (logs warning but continues)."""
        mock_session.return_value = "test-session"

        workflow_def = self._make_workflow_def(
            name='bad-hb-workflow',
            heartbeat='invalid-duration'  # Invalid format
        )
        stage_def = self._make_stage_def(name='work', prompt='Do work')

        import io
        import sys
        captured = io.StringIO()
        with patch('sys.stderr', captured):
            worker = swarm.spawn_workflow_stage(
                workflow_name='bad-hb-workflow',
                workflow_def=workflow_def,
                stage_def=stage_def,
                workflow_dir=self.workflow_dir,
            )

        # Should still succeed (heartbeat failure is a warning, not error)
        self.assertIsNotNone(worker)
        self.assertEqual(worker.name, 'bad-hb-workflow-work')
        # Warning should be logged
        self.assertIn('invalid heartbeat interval', captured.getvalue())

    @patch('swarm.create_tmux_window')
    @patch('swarm.send_prompt_to_worker')
    @patch('swarm.get_default_session_name')
    @patch('swarm.save_heartbeat_state')
    @patch('swarm.start_heartbeat_monitor')
    def test_spawn_with_invalid_heartbeat_expire(self, mock_start_hb, mock_save_hb, mock_session, mock_send, mock_create_tmux):
        """Test spawning with invalid heartbeat expire (logs warning but continues)."""
        mock_session.return_value = "test-session"
        mock_start_hb.return_value = 12345

        workflow_def = self._make_workflow_def(
            name='bad-expire-workflow',
            heartbeat='1h',  # Valid interval
            heartbeat_expire='invalid-duration'  # Invalid expire
        )
        stage_def = self._make_stage_def(name='work', prompt='Do work')

        import io
        captured = io.StringIO()
        with patch('sys.stderr', captured):
            worker = swarm.spawn_workflow_stage(
                workflow_name='bad-expire-workflow',
                workflow_def=workflow_def,
                stage_def=stage_def,
                workflow_dir=self.workflow_dir,
            )

        # Should still succeed
        self.assertIsNotNone(worker)
        # Heartbeat should be set up (without expire)
        mock_save_hb.assert_called()
        # Warning should be logged
        self.assertIn('invalid heartbeat-expire', captured.getvalue())


class TestStageCompletionResultDataclass(unittest.TestCase):
    """Test StageCompletionResult dataclass creation and attributes."""

    def test_create_successful_done_pattern(self):
        """Test creating a successful done_pattern completion result."""
        result = swarm.StageCompletionResult(
            completed=True,
            success=True,
            reason="done_pattern",
            details="Done pattern matched in worker output",
        )
        self.assertTrue(result.completed)
        self.assertTrue(result.success)
        self.assertEqual(result.reason, "done_pattern")
        self.assertEqual(result.details, "Done pattern matched in worker output")

    def test_create_timeout_result(self):
        """Test creating a timeout completion result."""
        result = swarm.StageCompletionResult(
            completed=True,
            success=False,
            reason="timeout",
            details="Stage timed out after 1h 30m",
        )
        self.assertTrue(result.completed)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "timeout")
        self.assertIn("timed out", result.details)

    def test_create_worker_exit_result(self):
        """Test creating a worker exit completion result."""
        result = swarm.StageCompletionResult(
            completed=True,
            success=False,
            reason="worker_exit",
            details="Worker exited before done pattern matched",
        )
        self.assertTrue(result.completed)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "worker_exit")

    def test_create_ralph_complete_result(self):
        """Test creating a ralph completion result."""
        result = swarm.StageCompletionResult(
            completed=True,
            success=True,
            reason="ralph_complete",
            details="Ralph loop completed after 25 iterations",
        )
        self.assertTrue(result.completed)
        self.assertTrue(result.success)
        self.assertEqual(result.reason, "ralph_complete")

    def test_create_ralph_failed_result(self):
        """Test creating a ralph failed result."""
        result = swarm.StageCompletionResult(
            completed=True,
            success=False,
            reason="ralph_failed",
            details="Ralph loop failed after 5 total failures",
        )
        self.assertTrue(result.completed)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "ralph_failed")

    def test_create_error_result(self):
        """Test creating an error completion result."""
        result = swarm.StageCompletionResult(
            completed=True,
            success=False,
            reason="error",
            details="Ralph state not found - worker may have been killed",
        )
        self.assertTrue(result.completed)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "error")

    def test_create_without_details(self):
        """Test creating a completion result without details."""
        result = swarm.StageCompletionResult(
            completed=True,
            success=True,
            reason="done_pattern",
        )
        self.assertTrue(result.completed)
        self.assertTrue(result.success)
        self.assertEqual(result.reason, "done_pattern")
        self.assertIsNone(result.details)

    def test_all_valid_reasons(self):
        """Test all valid reason values can be set."""
        reasons = [
            "done_pattern",
            "timeout",
            "worker_exit",
            "ralph_complete",
            "ralph_failed",
            "error",
        ]
        for reason in reasons:
            result = swarm.StageCompletionResult(
                completed=True,
                success=reason in ("done_pattern", "ralph_complete"),
                reason=reason,
            )
            self.assertEqual(result.reason, reason)


class TestMonitorWorkerStageCompletion(unittest.TestCase):
    """Test _monitor_worker_stage_completion function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        # Create a mock worker
        self.mock_worker = swarm.Worker(
            name="test-workflow-work",
            status="running",
            cmd=["claude"],
            started=datetime.now().isoformat(),
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session="swarm", window="test-workflow-work", socket=None),
        )

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    def test_done_pattern_matched(self, mock_capture, mock_refresh):
        """Test completion when done pattern matches."""
        import re
        mock_refresh.return_value = "running"
        mock_capture.return_value = "Working...\n/done\nMore output"

        done_regex = re.compile(r"/done")
        result = swarm._monitor_worker_stage_completion(
            worker=self.mock_worker,
            done_regex=done_regex,
            timeout_seconds=None,
            start_time=0,
            poll_interval=0.01,
        )

        self.assertTrue(result.completed)
        self.assertTrue(result.success)
        self.assertEqual(result.reason, "done_pattern")

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    def test_worker_exited_without_pattern(self, mock_capture, mock_refresh):
        """Test completion when worker exits without done pattern."""
        import re
        mock_refresh.return_value = "stopped"
        mock_capture.return_value = "Working...\nFinished but no pattern"

        done_regex = re.compile(r"/done")
        result = swarm._monitor_worker_stage_completion(
            worker=self.mock_worker,
            done_regex=done_regex,
            timeout_seconds=None,
            start_time=0,
            poll_interval=0.01,
        )

        self.assertTrue(result.completed)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "worker_exit")

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    def test_worker_exited_with_pattern_before_exit(self, mock_capture, mock_refresh):
        """Test completion when worker exits after done pattern matched."""
        import re
        mock_refresh.return_value = "stopped"
        mock_capture.return_value = "Working...\n/done\nExiting"

        done_regex = re.compile(r"/done")
        result = swarm._monitor_worker_stage_completion(
            worker=self.mock_worker,
            done_regex=done_regex,
            timeout_seconds=None,
            start_time=0,
            poll_interval=0.01,
        )

        self.assertTrue(result.completed)
        self.assertTrue(result.success)
        self.assertEqual(result.reason, "done_pattern")

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    @patch('time.time')
    def test_timeout_reached(self, mock_time, mock_capture, mock_refresh):
        """Test completion when timeout is reached."""
        import re
        mock_refresh.return_value = "running"
        mock_capture.return_value = "Still working..."
        # Simulate time passing beyond timeout
        mock_time.side_effect = [100, 200]  # start=100, now=200, elapsed=100 > 60

        done_regex = re.compile(r"/done")
        result = swarm._monitor_worker_stage_completion(
            worker=self.mock_worker,
            done_regex=done_regex,
            timeout_seconds=60,  # 60 second timeout
            start_time=100,  # start time from mock
            poll_interval=0.01,
        )

        self.assertTrue(result.completed)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "timeout")
        self.assertIn("timed out", result.details)

    @patch('swarm.refresh_worker_status')
    def test_worker_exited_no_tmux(self, mock_refresh):
        """Test completion when worker exits without tmux."""
        mock_refresh.return_value = "stopped"

        # Worker without tmux info
        worker_no_tmux = swarm.Worker(
            name="test-worker",
            status="running",
            cmd=["claude"],
            started=datetime.now().isoformat(),
            cwd=self.temp_dir,
            tmux=None,
        )

        result = swarm._monitor_worker_stage_completion(
            worker=worker_no_tmux,
            done_regex=None,
            timeout_seconds=None,
            start_time=0,
            poll_interval=0.01,
        )

        self.assertTrue(result.completed)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "worker_exit")

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    def test_tmux_capture_error(self, mock_capture, mock_refresh):
        """Test handling of tmux capture errors."""
        import subprocess
        mock_refresh.side_effect = ["running", "stopped"]
        mock_capture.side_effect = subprocess.CalledProcessError(1, "tmux")

        result = swarm._monitor_worker_stage_completion(
            worker=self.mock_worker,
            done_regex=None,
            timeout_seconds=None,
            start_time=0,
            poll_interval=0.01,
        )

        # Should detect worker exit (window closed)
        self.assertTrue(result.completed)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "worker_exit")


class TestMonitorRalphStageCompletion(unittest.TestCase):
    """Test _monitor_ralph_stage_completion function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('swarm.load_ralph_state')
    def test_ralph_completed_normally(self, mock_load):
        """Test completion when ralph loop finishes normally."""
        mock_load.return_value = swarm.RalphState(
            worker_name="test-workflow-build",
            prompt_file="/path/to/prompt.md",
            max_iterations=50,
            current_iteration=50,
            status="stopped",
        )

        result = swarm._monitor_ralph_stage_completion(
            worker_name="test-workflow-build",
            timeout_seconds=None,
            start_time=0,
            poll_interval=0.01,
        )

        self.assertTrue(result.completed)
        self.assertTrue(result.success)
        self.assertEqual(result.reason, "ralph_complete")
        self.assertIn("50 iterations", result.details)

    @patch('swarm.load_ralph_state')
    def test_ralph_failed(self, mock_load):
        """Test completion when ralph loop fails."""
        mock_load.return_value = swarm.RalphState(
            worker_name="test-workflow-build",
            prompt_file="/path/to/prompt.md",
            max_iterations=50,
            current_iteration=5,
            status="failed",
            total_failures=5,
        )

        result = swarm._monitor_ralph_stage_completion(
            worker_name="test-workflow-build",
            timeout_seconds=None,
            start_time=0,
            poll_interval=0.01,
        )

        self.assertTrue(result.completed)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "ralph_failed")
        self.assertIn("5 total failures", result.details)

    @patch('swarm.load_ralph_state')
    def test_ralph_state_not_found(self, mock_load):
        """Test completion when ralph state is not found."""
        mock_load.return_value = None

        result = swarm._monitor_ralph_stage_completion(
            worker_name="nonexistent-worker",
            timeout_seconds=None,
            start_time=0,
            poll_interval=0.01,
        )

        self.assertTrue(result.completed)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "error")
        self.assertIn("not found", result.details)

    @patch('swarm.load_ralph_state')
    @patch('time.time')
    def test_ralph_timeout(self, mock_time, mock_load):
        """Test completion when ralph stage times out."""
        mock_load.return_value = swarm.RalphState(
            worker_name="test-workflow-build",
            prompt_file="/path/to/prompt.md",
            max_iterations=50,
            current_iteration=10,
            status="running",
        )
        # Simulate time passing beyond timeout
        mock_time.side_effect = [100, 200]  # start=100, now=200, elapsed=100 > 60

        result = swarm._monitor_ralph_stage_completion(
            worker_name="test-workflow-build",
            timeout_seconds=60,  # 60 second timeout
            start_time=100,  # start time from mock
            poll_interval=0.01,
        )

        self.assertTrue(result.completed)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "timeout")


class TestMonitorStageCompletion(unittest.TestCase):
    """Test monitor_stage_completion function (high-level)."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        # Create a mock worker
        self.mock_worker = swarm.Worker(
            name="test-workflow-work",
            status="running",
            cmd=["claude"],
            started=datetime.now().isoformat(),
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session="swarm", window="test-workflow-work", socket=None),
        )

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('swarm._monitor_worker_stage_completion')
    def test_dispatches_to_worker_monitor_for_worker_type(self, mock_worker_monitor):
        """Test that worker type stages use worker monitor."""
        mock_worker_monitor.return_value = swarm.StageCompletionResult(
            completed=True,
            success=True,
            reason="done_pattern",
        )

        stage_def = swarm.StageDefinition(
            name="work",
            type="worker",
            prompt="Do some work",
            done_pattern="/done",
        )

        result = swarm.monitor_stage_completion(
            workflow_name="test-workflow",
            stage_def=stage_def,
            worker=self.mock_worker,
            poll_interval=0.01,
        )

        self.assertTrue(mock_worker_monitor.called)
        self.assertEqual(result.reason, "done_pattern")

    @patch('swarm._monitor_ralph_stage_completion')
    def test_dispatches_to_ralph_monitor_for_ralph_type(self, mock_ralph_monitor):
        """Test that ralph type stages use ralph monitor."""
        mock_ralph_monitor.return_value = swarm.StageCompletionResult(
            completed=True,
            success=True,
            reason="ralph_complete",
        )

        stage_def = swarm.StageDefinition(
            name="build",
            type="ralph",
            prompt="Build something",
            max_iterations=50,
        )

        result = swarm.monitor_stage_completion(
            workflow_name="test-workflow",
            stage_def=stage_def,
            worker=self.mock_worker,
            poll_interval=0.01,
        )

        self.assertTrue(mock_ralph_monitor.called)
        self.assertEqual(result.reason, "ralph_complete")

    @patch('swarm._monitor_worker_stage_completion')
    def test_parses_timeout_duration(self, mock_worker_monitor):
        """Test that timeout duration string is parsed correctly."""
        mock_worker_monitor.return_value = swarm.StageCompletionResult(
            completed=True,
            success=False,
            reason="timeout",
        )

        stage_def = swarm.StageDefinition(
            name="work",
            type="worker",
            prompt="Do some work",
            timeout="2h30m",  # Duration string
        )

        swarm.monitor_stage_completion(
            workflow_name="test-workflow",
            stage_def=stage_def,
            worker=self.mock_worker,
            poll_interval=0.01,
        )

        # Check that timeout_seconds was passed correctly (2h30m = 9000s)
        call_args = mock_worker_monitor.call_args
        self.assertEqual(call_args.kwargs.get('timeout_seconds'), 9000)

    @patch('swarm._monitor_worker_stage_completion')
    def test_handles_invalid_done_pattern(self, mock_worker_monitor):
        """Test that invalid regex patterns are handled gracefully."""
        mock_worker_monitor.return_value = swarm.StageCompletionResult(
            completed=True,
            success=False,
            reason="worker_exit",
        )

        stage_def = swarm.StageDefinition(
            name="work",
            type="worker",
            prompt="Do some work",
            done_pattern="[invalid(regex",  # Invalid regex
        )

        # Should not raise an exception
        result = swarm.monitor_stage_completion(
            workflow_name="test-workflow",
            stage_def=stage_def,
            worker=self.mock_worker,
            poll_interval=0.01,
        )

        # Should proceed without pattern matching
        call_args = mock_worker_monitor.call_args
        self.assertIsNone(call_args.kwargs.get('done_regex'))

    @patch('swarm._monitor_worker_stage_completion')
    def test_handles_invalid_timeout(self, mock_worker_monitor):
        """Test that invalid timeout strings are handled gracefully."""
        mock_worker_monitor.return_value = swarm.StageCompletionResult(
            completed=True,
            success=False,
            reason="worker_exit",
        )

        stage_def = swarm.StageDefinition(
            name="work",
            type="worker",
            prompt="Do some work",
            timeout="not-a-duration",  # Invalid duration
        )

        # Should not raise an exception
        result = swarm.monitor_stage_completion(
            workflow_name="test-workflow",
            stage_def=stage_def,
            worker=self.mock_worker,
            poll_interval=0.01,
        )

        # Should proceed without timeout
        call_args = mock_worker_monitor.call_args
        self.assertIsNone(call_args.kwargs.get('timeout_seconds'))


class TestStageTransitionResultDataclass(unittest.TestCase):
    """Test StageTransitionResult dataclass creation and attributes."""

    def test_create_next_stage_result(self):
        """Test creating a next_stage transition result."""
        result = swarm.StageTransitionResult(
            action="next_stage",
            next_stage_name="build",
            next_stage_index=1,
            message="Stage 'plan' completed, starting 'build'",
        )
        self.assertEqual(result.action, "next_stage")
        self.assertEqual(result.next_stage_name, "build")
        self.assertEqual(result.next_stage_index, 1)
        self.assertEqual(result.message, "Stage 'plan' completed, starting 'build'")

    def test_create_complete_result(self):
        """Test creating a complete transition result."""
        result = swarm.StageTransitionResult(
            action="complete",
            message="All stages finished",
        )
        self.assertEqual(result.action, "complete")
        self.assertIsNone(result.next_stage_name)
        self.assertEqual(result.next_stage_index, -1)

    def test_create_retry_result(self):
        """Test creating a retry transition result."""
        result = swarm.StageTransitionResult(
            action="retry",
            next_stage_name="build",
            next_stage_index=1,
            message="Stage 'build' failed, retrying (attempt 2/3)",
        )
        self.assertEqual(result.action, "retry")
        self.assertEqual(result.next_stage_name, "build")
        self.assertEqual(result.next_stage_index, 1)

    def test_create_fail_result(self):
        """Test creating a fail transition result."""
        result = swarm.StageTransitionResult(
            action="fail",
            message="Stage 'build' failed after 3 attempts",
        )
        self.assertEqual(result.action, "fail")
        self.assertIsNone(result.next_stage_name)

    def test_create_skip_result(self):
        """Test creating a skip transition result."""
        result = swarm.StageTransitionResult(
            action="skip",
            next_stage_name="validate",
            next_stage_index=2,
            message="Stage 'build' skipped (timeout), starting 'validate'",
        )
        self.assertEqual(result.action, "skip")
        self.assertEqual(result.next_stage_name, "validate")
        self.assertEqual(result.next_stage_index, 2)


class TestHandleStageTransition(unittest.TestCase):
    """Test handle_stage_transition function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.workflow_dir = Path(self.temp_dir)

        # Patch WORKFLOWS_DIR to use temp directory
        self.workflows_dir_patcher = patch.object(swarm, 'WORKFLOWS_DIR', Path(self.temp_dir) / 'workflows')
        self.workflows_dir_patcher.start()

    def tearDown(self):
        """Clean up test fixtures."""
        self.workflows_dir_patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_workflow_def(self, stages):
        """Helper to create a WorkflowDefinition."""
        return swarm.WorkflowDefinition(
            name="test-workflow",
            stages=stages,
        )

    def _make_stage_def(self, name, on_complete="next", on_failure="stop", max_retries=3):
        """Helper to create a StageDefinition."""
        return swarm.StageDefinition(
            name=name,
            type="worker",
            prompt="Test prompt",
            on_complete=on_complete,
            on_failure=on_failure,
            max_retries=max_retries,
        )

    def _make_workflow_state(self, name, current_stage, current_stage_index, stages_status):
        """Helper to create a WorkflowState."""
        stages = {}
        for stage_name, status_dict in stages_status.items():
            stages[stage_name] = swarm.StageState(
                status=status_dict.get('status', 'pending'),
                attempts=status_dict.get('attempts', 0),
            )
        return swarm.WorkflowState(
            name=name,
            status="running",
            current_stage=current_stage,
            current_stage_index=current_stage_index,
            stages=stages,
        )

    # --- Success cases ---

    def test_success_on_complete_next_advances_to_next_stage(self):
        """Test successful completion with on-complete: next advances to next stage."""
        stage1 = self._make_stage_def("plan", on_complete="next")
        stage2 = self._make_stage_def("build", on_complete="next")
        workflow_def = self._make_workflow_def([stage1, stage2])

        workflow_state = self._make_workflow_state(
            name="test-workflow",
            current_stage="plan",
            current_stage_index=0,
            stages_status={"plan": {"status": "running", "attempts": 1}, "build": {"status": "pending"}},
        )

        completion = swarm.StageCompletionResult(
            completed=True, success=True, reason="done_pattern"
        )

        result = swarm.handle_stage_transition(
            workflow_state, workflow_def, completion, self.workflow_dir
        )

        self.assertEqual(result.action, "next_stage")
        self.assertEqual(result.next_stage_name, "build")
        self.assertEqual(result.next_stage_index, 1)
        self.assertEqual(workflow_state.stages["plan"].status, "completed")
        self.assertEqual(workflow_state.stages["plan"].exit_reason, "done_pattern")

    def test_success_on_complete_next_last_stage_completes_workflow(self):
        """Test successful completion of last stage completes workflow."""
        stage1 = self._make_stage_def("plan", on_complete="next")
        workflow_def = self._make_workflow_def([stage1])

        workflow_state = self._make_workflow_state(
            name="test-workflow",
            current_stage="plan",
            current_stage_index=0,
            stages_status={"plan": {"status": "running", "attempts": 1}},
        )

        completion = swarm.StageCompletionResult(
            completed=True, success=True, reason="done_pattern"
        )

        result = swarm.handle_stage_transition(
            workflow_state, workflow_def, completion, self.workflow_dir
        )

        self.assertEqual(result.action, "complete")
        self.assertEqual(workflow_state.status, "completed")
        self.assertIsNotNone(workflow_state.completed_at)

    def test_success_on_complete_stop_completes_workflow(self):
        """Test successful completion with on-complete: stop completes workflow."""
        stage1 = self._make_stage_def("plan", on_complete="stop")
        stage2 = self._make_stage_def("build", on_complete="next")  # Won't be reached
        workflow_def = self._make_workflow_def([stage1, stage2])

        workflow_state = self._make_workflow_state(
            name="test-workflow",
            current_stage="plan",
            current_stage_index=0,
            stages_status={"plan": {"status": "running", "attempts": 1}, "build": {"status": "pending"}},
        )

        completion = swarm.StageCompletionResult(
            completed=True, success=True, reason="done_pattern"
        )

        result = swarm.handle_stage_transition(
            workflow_state, workflow_def, completion, self.workflow_dir
        )

        self.assertEqual(result.action, "complete")
        self.assertEqual(workflow_state.status, "completed")
        # Build stage should still be pending
        self.assertEqual(workflow_state.stages["build"].status, "pending")

    def test_success_on_complete_goto_jumps_to_stage(self):
        """Test successful completion with on-complete: goto:<stage> jumps to stage."""
        stage1 = self._make_stage_def("plan", on_complete="goto:validate")
        stage2 = self._make_stage_def("build", on_complete="next")  # Will be skipped
        stage3 = self._make_stage_def("validate", on_complete="stop")
        workflow_def = self._make_workflow_def([stage1, stage2, stage3])

        workflow_state = self._make_workflow_state(
            name="test-workflow",
            current_stage="plan",
            current_stage_index=0,
            stages_status={"plan": {"status": "running", "attempts": 1}, "build": {"status": "pending"}, "validate": {"status": "pending"}},
        )

        completion = swarm.StageCompletionResult(
            completed=True, success=True, reason="done_pattern"
        )

        result = swarm.handle_stage_transition(
            workflow_state, workflow_def, completion, self.workflow_dir
        )

        self.assertEqual(result.action, "next_stage")
        self.assertEqual(result.next_stage_name, "validate")
        self.assertEqual(result.next_stage_index, 2)

    # --- Failure cases ---

    def test_failure_on_failure_stop_fails_workflow(self):
        """Test failure with on-failure: stop fails workflow."""
        stage1 = self._make_stage_def("build", on_failure="stop")
        workflow_def = self._make_workflow_def([stage1])

        workflow_state = self._make_workflow_state(
            name="test-workflow",
            current_stage="build",
            current_stage_index=0,
            stages_status={"build": {"status": "running", "attempts": 1}},
        )

        completion = swarm.StageCompletionResult(
            completed=True, success=False, reason="timeout"
        )

        result = swarm.handle_stage_transition(
            workflow_state, workflow_def, completion, self.workflow_dir
        )

        self.assertEqual(result.action, "fail")
        self.assertEqual(workflow_state.status, "failed")
        self.assertEqual(workflow_state.stages["build"].status, "failed")
        self.assertEqual(workflow_state.stages["build"].exit_reason, "timeout")

    def test_failure_on_failure_retry_retries_stage(self):
        """Test failure with on-failure: retry retries the stage."""
        stage1 = self._make_stage_def("build", on_failure="retry", max_retries=3)
        workflow_def = self._make_workflow_def([stage1])

        workflow_state = self._make_workflow_state(
            name="test-workflow",
            current_stage="build",
            current_stage_index=0,
            stages_status={"build": {"status": "running", "attempts": 1}},
        )

        completion = swarm.StageCompletionResult(
            completed=True, success=False, reason="worker_exit"
        )

        result = swarm.handle_stage_transition(
            workflow_state, workflow_def, completion, self.workflow_dir
        )

        self.assertEqual(result.action, "retry")
        self.assertEqual(result.next_stage_name, "build")
        self.assertEqual(result.next_stage_index, 0)
        # Workflow should still be running
        self.assertEqual(workflow_state.status, "running")

    def test_failure_on_failure_retry_exhausted_fails_workflow(self):
        """Test failure with on-failure: retry fails workflow when retries exhausted."""
        stage1 = self._make_stage_def("build", on_failure="retry", max_retries=3)
        workflow_def = self._make_workflow_def([stage1])

        workflow_state = self._make_workflow_state(
            name="test-workflow",
            current_stage="build",
            current_stage_index=0,
            stages_status={"build": {"status": "running", "attempts": 3}},  # Already at max
        )

        completion = swarm.StageCompletionResult(
            completed=True, success=False, reason="worker_exit"
        )

        result = swarm.handle_stage_transition(
            workflow_state, workflow_def, completion, self.workflow_dir
        )

        self.assertEqual(result.action, "fail")
        self.assertEqual(workflow_state.status, "failed")
        self.assertEqual(workflow_state.stages["build"].status, "failed")

    def test_failure_on_failure_skip_skips_to_next_stage(self):
        """Test failure with on-failure: skip skips to next stage."""
        stage1 = self._make_stage_def("build", on_failure="skip")
        stage2 = self._make_stage_def("validate", on_complete="stop")
        workflow_def = self._make_workflow_def([stage1, stage2])

        workflow_state = self._make_workflow_state(
            name="test-workflow",
            current_stage="build",
            current_stage_index=0,
            stages_status={"build": {"status": "running", "attempts": 1}, "validate": {"status": "pending"}},
        )

        completion = swarm.StageCompletionResult(
            completed=True, success=False, reason="timeout"
        )

        result = swarm.handle_stage_transition(
            workflow_state, workflow_def, completion, self.workflow_dir
        )

        self.assertEqual(result.action, "skip")
        self.assertEqual(result.next_stage_name, "validate")
        self.assertEqual(result.next_stage_index, 1)
        self.assertEqual(workflow_state.stages["build"].status, "skipped")
        self.assertEqual(workflow_state.stages["build"].exit_reason, "skipped")

    def test_failure_on_failure_skip_last_stage_completes_workflow(self):
        """Test failure with on-failure: skip on last stage completes workflow."""
        stage1 = self._make_stage_def("validate", on_failure="skip")
        workflow_def = self._make_workflow_def([stage1])

        workflow_state = self._make_workflow_state(
            name="test-workflow",
            current_stage="validate",
            current_stage_index=0,
            stages_status={"validate": {"status": "running", "attempts": 1}},
        )

        completion = swarm.StageCompletionResult(
            completed=True, success=False, reason="timeout"
        )

        result = swarm.handle_stage_transition(
            workflow_state, workflow_def, completion, self.workflow_dir
        )

        self.assertEqual(result.action, "complete")
        self.assertEqual(workflow_state.status, "completed")
        self.assertEqual(workflow_state.stages["validate"].status, "skipped")

    # --- Edge cases ---

    def test_no_current_stage_returns_fail(self):
        """Test that missing current stage returns fail."""
        stage1 = self._make_stage_def("plan")
        workflow_def = self._make_workflow_def([stage1])

        workflow_state = swarm.WorkflowState(
            name="test-workflow",
            status="running",
            current_stage=None,  # No current stage
            current_stage_index=-1,
        )

        completion = swarm.StageCompletionResult(
            completed=True, success=True, reason="done_pattern"
        )

        result = swarm.handle_stage_transition(
            workflow_state, workflow_def, completion, self.workflow_dir
        )

        self.assertEqual(result.action, "fail")
        self.assertIn("no current stage", result.message.lower())

    def test_stage_index_out_of_range_returns_fail(self):
        """Test that stage index out of range returns fail."""
        stage1 = self._make_stage_def("plan")
        workflow_def = self._make_workflow_def([stage1])

        workflow_state = swarm.WorkflowState(
            name="test-workflow",
            status="running",
            current_stage="plan",
            current_stage_index=5,  # Out of range
            stages={"plan": swarm.StageState(status="running", attempts=1)},
        )

        completion = swarm.StageCompletionResult(
            completed=True, success=True, reason="done_pattern"
        )

        result = swarm.handle_stage_transition(
            workflow_state, workflow_def, completion, self.workflow_dir
        )

        self.assertEqual(result.action, "fail")
        self.assertIn("out of range", result.message.lower())

    def test_success_preserves_exit_reason_in_stage_state(self):
        """Test that successful completion preserves the exit reason."""
        stage1 = self._make_stage_def("plan", on_complete="next")
        stage2 = self._make_stage_def("build", on_complete="stop")
        workflow_def = self._make_workflow_def([stage1, stage2])

        workflow_state = self._make_workflow_state(
            name="test-workflow",
            current_stage="plan",
            current_stage_index=0,
            stages_status={"plan": {"status": "running", "attempts": 1}, "build": {"status": "pending"}},
        )

        completion = swarm.StageCompletionResult(
            completed=True, success=True, reason="ralph_complete",
            details="Ralph loop completed after 25 iterations"
        )

        result = swarm.handle_stage_transition(
            workflow_state, workflow_def, completion, self.workflow_dir
        )

        self.assertEqual(workflow_state.stages["plan"].exit_reason, "ralph_complete")


class TestStartNextStage(unittest.TestCase):
    """Test start_next_stage function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.workflow_dir = Path(self.temp_dir)

        # Patch WORKFLOWS_DIR to use temp directory
        self.workflows_dir_patcher = patch.object(swarm, 'WORKFLOWS_DIR', Path(self.temp_dir) / 'workflows')
        self.workflows_dir_patcher.start()

        # Create workflows directory
        (Path(self.temp_dir) / 'workflows').mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        self.workflows_dir_patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_workflow_def(self, stages):
        """Helper to create a WorkflowDefinition."""
        return swarm.WorkflowDefinition(
            name="test-workflow",
            stages=stages,
        )

    def _make_stage_def(self, name, on_complete="next"):
        """Helper to create a StageDefinition."""
        return swarm.StageDefinition(
            name=name,
            type="worker",
            prompt="Test prompt",
            on_complete=on_complete,
        )

    @patch('swarm.spawn_workflow_stage')
    @patch('swarm.save_workflow_state')
    def test_start_next_stage_updates_workflow_state(self, mock_save, mock_spawn):
        """Test that start_next_stage updates workflow state correctly."""
        mock_spawn.return_value = swarm.Worker(
            name="test-workflow-build",
            status="running",
            cmd=["claude"],
            started=datetime.now().isoformat(),
            cwd="/tmp/test",
        )

        stage1 = self._make_stage_def("plan")
        stage2 = self._make_stage_def("build")
        workflow_def = self._make_workflow_def([stage1, stage2])

        workflow_state = swarm.WorkflowState(
            name="test-workflow",
            status="running",
            current_stage="plan",
            current_stage_index=0,
            stages={
                "plan": swarm.StageState(status="completed"),
                "build": swarm.StageState(status="pending"),
            },
        )

        transition = swarm.StageTransitionResult(
            action="next_stage",
            next_stage_name="build",
            next_stage_index=1,
            message="Moving to build",
        )

        result = swarm.start_next_stage(
            workflow_state, workflow_def, transition, self.workflow_dir
        )

        self.assertIsNotNone(result)
        self.assertEqual(workflow_state.current_stage, "build")
        self.assertEqual(workflow_state.current_stage_index, 1)
        self.assertEqual(workflow_state.stages["build"].status, "running")
        self.assertEqual(workflow_state.stages["build"].attempts, 1)
        self.assertEqual(workflow_state.stages["build"].worker_name, "test-workflow-build")
        mock_save.assert_called()

    @patch('swarm.spawn_workflow_stage')
    @patch('swarm.save_workflow_state')
    def test_start_next_stage_with_retry_increments_attempts(self, mock_save, mock_spawn):
        """Test that retry increments attempt count."""
        mock_spawn.return_value = swarm.Worker(
            name="test-workflow-build",
            status="running",
            cmd=["claude"],
            started=datetime.now().isoformat(),
            cwd="/tmp/test",
        )

        stage1 = self._make_stage_def("build")
        workflow_def = self._make_workflow_def([stage1])

        workflow_state = swarm.WorkflowState(
            name="test-workflow",
            status="running",
            current_stage="build",
            current_stage_index=0,
            stages={
                "build": swarm.StageState(status="running", attempts=1),
            },
        )

        transition = swarm.StageTransitionResult(
            action="retry",
            next_stage_name="build",
            next_stage_index=0,
            message="Retrying build",
        )

        result = swarm.start_next_stage(
            workflow_state, workflow_def, transition, self.workflow_dir, is_retry=True
        )

        self.assertIsNotNone(result)
        self.assertEqual(workflow_state.stages["build"].attempts, 2)

    def test_start_next_stage_with_no_next_stage_returns_none(self):
        """Test that no next stage returns None."""
        stage1 = self._make_stage_def("plan")
        workflow_def = self._make_workflow_def([stage1])

        workflow_state = swarm.WorkflowState(
            name="test-workflow",
            status="completed",
            current_stage="plan",
            current_stage_index=0,
            stages={"plan": swarm.StageState(status="completed")},
        )

        transition = swarm.StageTransitionResult(
            action="complete",
            next_stage_name=None,
            next_stage_index=-1,
            message="Workflow complete",
        )

        result = swarm.start_next_stage(
            workflow_state, workflow_def, transition, self.workflow_dir
        )

        self.assertIsNone(result)

    @patch('swarm.spawn_workflow_stage')
    @patch('swarm.save_workflow_state')
    def test_start_next_stage_creates_stage_state_if_missing(self, mock_save, mock_spawn):
        """Test that start_next_stage creates stage state if missing."""
        mock_spawn.return_value = swarm.Worker(
            name="test-workflow-build",
            status="running",
            cmd=["claude"],
            started=datetime.now().isoformat(),
            cwd="/tmp/test",
        )

        stage1 = self._make_stage_def("plan")
        stage2 = self._make_stage_def("build")
        workflow_def = self._make_workflow_def([stage1, stage2])

        # Workflow state missing the "build" stage state
        workflow_state = swarm.WorkflowState(
            name="test-workflow",
            status="running",
            current_stage="plan",
            current_stage_index=0,
            stages={
                "plan": swarm.StageState(status="completed"),
                # "build" is missing
            },
        )

        transition = swarm.StageTransitionResult(
            action="next_stage",
            next_stage_name="build",
            next_stage_index=1,
            message="Moving to build",
        )

        result = swarm.start_next_stage(
            workflow_state, workflow_def, transition, self.workflow_dir
        )

        self.assertIsNotNone(result)
        self.assertIn("build", workflow_state.stages)
        self.assertEqual(workflow_state.stages["build"].status, "running")


class TestRunWorkflowMonitor(unittest.TestCase):
    """Test run_workflow_monitor function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.workflow_dir = Path(self.temp_dir)

        # Patch WORKFLOWS_DIR to use temp directory
        self.workflows_dir_patcher = patch.object(swarm, 'WORKFLOWS_DIR', Path(self.temp_dir) / 'workflows')
        self.workflows_dir_patcher.start()

        # Create workflows directory
        (Path(self.temp_dir) / 'workflows').mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        self.workflows_dir_patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_workflow_def(self, stages):
        """Helper to create a WorkflowDefinition."""
        return swarm.WorkflowDefinition(
            name="test-workflow",
            stages=stages,
        )

    def _make_stage_def(self, name, stage_type="worker", on_complete="next", on_failure="stop"):
        """Helper to create a StageDefinition."""
        return swarm.StageDefinition(
            name=name,
            type=stage_type,
            prompt="Test prompt",
            done_pattern="/done",
            on_complete=on_complete,
            on_failure=on_failure,
        )

    def _setup_workflow_state(self, workflow_name, status, stages_dict):
        """Helper to set up workflow state on disk."""
        workflow_state = swarm.WorkflowState(
            name=workflow_name,
            status=status,
            stages=stages_dict,
        )
        # Create workflow state directory and save
        state_dir = Path(self.temp_dir) / 'workflows' / workflow_name
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / 'state.json'
        with open(state_path, 'w') as f:
            json.dump(workflow_state.to_dict(), f)
        return workflow_state

    @patch('swarm.load_workflow_state')
    def test_monitor_exits_when_workflow_not_found(self, mock_load):
        """Test monitor exits when workflow state is not found."""
        mock_load.return_value = None

        stage1 = self._make_stage_def("plan")
        workflow_def = self._make_workflow_def([stage1])

        # Should not raise, should exit gracefully
        swarm.run_workflow_monitor("missing-workflow", workflow_def, self.workflow_dir)

        mock_load.assert_called_once_with("missing-workflow")

    @patch('swarm.save_workflow_state')
    @patch('swarm.load_workflow_state')
    def test_monitor_exits_when_workflow_completed(self, mock_load, mock_save):
        """Test monitor exits when workflow is already completed."""
        mock_load.return_value = swarm.WorkflowState(
            name="test-workflow",
            status="completed",
            stages={},
        )

        stage1 = self._make_stage_def("plan")
        workflow_def = self._make_workflow_def([stage1])

        swarm.run_workflow_monitor("test-workflow", workflow_def, self.workflow_dir)

        # Only one call to load_workflow_state, then exit
        mock_load.assert_called_once()

    @patch('swarm.save_workflow_state')
    @patch('swarm.load_workflow_state')
    def test_monitor_exits_when_workflow_failed(self, mock_load, mock_save):
        """Test monitor exits when workflow is already failed."""
        mock_load.return_value = swarm.WorkflowState(
            name="test-workflow",
            status="failed",
            stages={},
        )

        stage1 = self._make_stage_def("plan")
        workflow_def = self._make_workflow_def([stage1])

        swarm.run_workflow_monitor("test-workflow", workflow_def, self.workflow_dir)

        mock_load.assert_called_once()

    @patch('swarm.save_workflow_state')
    @patch('swarm.load_workflow_state')
    def test_monitor_exits_when_workflow_cancelled(self, mock_load, mock_save):
        """Test monitor exits when workflow is cancelled."""
        mock_load.return_value = swarm.WorkflowState(
            name="test-workflow",
            status="cancelled",
            stages={},
        )

        stage1 = self._make_stage_def("plan")
        workflow_def = self._make_workflow_def([stage1])

        swarm.run_workflow_monitor("test-workflow", workflow_def, self.workflow_dir)

        mock_load.assert_called_once()

    @patch('swarm.spawn_workflow_stage')
    @patch('time.sleep')
    @patch('swarm.save_workflow_state')
    @patch('swarm.load_workflow_state')
    def test_monitor_waits_for_scheduled_time(self, mock_load, mock_save, mock_sleep, mock_spawn):
        """Test monitor waits until scheduled time before starting."""
        # First call returns scheduled state, second call returns running state
        future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        scheduled_state = swarm.WorkflowState(
            name="test-workflow",
            status="scheduled",
            scheduled_for=future_time,
            stages={"plan": swarm.StageState(status="pending")},
        )
        # After "sleeping", workflow becomes completed (simulating external completion)
        completed_state = swarm.WorkflowState(
            name="test-workflow",
            status="completed",
            stages={"plan": swarm.StageState(status="completed")},
        )
        mock_load.side_effect = [scheduled_state, completed_state]

        stage1 = self._make_stage_def("plan")
        workflow_def = self._make_workflow_def([stage1])

        swarm.run_workflow_monitor("test-workflow", workflow_def, self.workflow_dir)

        # Should have slept while waiting for scheduled time
        mock_sleep.assert_called()

    @patch('swarm.State')
    @patch('swarm.monitor_stage_completion')
    @patch('swarm.save_workflow_state')
    @patch('swarm.load_workflow_state')
    def test_monitor_handles_missing_worker(self, mock_load, mock_save, mock_monitor, mock_state_class):
        """Test monitor handles case where worker is missing."""
        # Workflow is running but worker is missing
        running_state = swarm.WorkflowState(
            name="test-workflow",
            status="running",
            current_stage="plan",
            current_stage_index=0,
            stages={
                "plan": swarm.StageState(
                    status="running",
                    worker_name="test-workflow-plan",
                )
            },
        )
        # After handling missing worker, workflow is failed
        failed_state = swarm.WorkflowState(
            name="test-workflow",
            status="failed",
            current_stage="plan",
            current_stage_index=0,
            stages={
                "plan": swarm.StageState(
                    status="failed",
                    worker_name="test-workflow-plan",
                )
            },
        )
        mock_load.side_effect = [running_state, running_state, failed_state]

        # Mock State().get_worker returns None (worker not found)
        mock_state_instance = MagicMock()
        mock_state_instance.get_worker.return_value = None
        mock_state_class.return_value = mock_state_instance

        stage1 = self._make_stage_def("plan")
        workflow_def = self._make_workflow_def([stage1])

        swarm.run_workflow_monitor("test-workflow", workflow_def, self.workflow_dir)

        # Worker was not found
        mock_state_instance.get_worker.assert_called_with("test-workflow-plan")

    @patch('swarm.start_next_stage')
    @patch('swarm.handle_stage_transition')
    @patch('swarm.State')
    @patch('swarm.monitor_stage_completion')
    @patch('swarm.save_workflow_state')
    @patch('swarm.load_workflow_state')
    def test_monitor_handles_stage_completion(self, mock_load, mock_save, mock_monitor,
                                               mock_state_class, mock_transition, mock_start_next):
        """Test monitor handles stage completion and transitions."""
        mock_worker = swarm.Worker(
            name="test-workflow-plan",
            status="running",
            cmd=["claude"],
            started=datetime.now().isoformat(),
            cwd="/tmp/test",
        )

        # First load: running workflow
        running_state = swarm.WorkflowState(
            name="test-workflow",
            status="running",
            current_stage="plan",
            current_stage_index=0,
            stages={
                "plan": swarm.StageState(
                    status="running",
                    worker_name="test-workflow-plan",
                ),
                "build": swarm.StageState(status="pending"),
            },
        )
        # After transition: completed
        completed_state = swarm.WorkflowState(
            name="test-workflow",
            status="completed",
            stages={
                "plan": swarm.StageState(status="completed"),
                "build": swarm.StageState(status="completed"),
            },
        )
        mock_load.side_effect = [running_state, running_state, completed_state]

        # Mock State().get_worker returns the worker
        mock_state_instance = MagicMock()
        mock_state_instance.get_worker.return_value = mock_worker
        mock_state_class.return_value = mock_state_instance

        # Stage completes successfully
        mock_monitor.return_value = swarm.StageCompletionResult(
            completed=True,
            success=True,
            reason="done_pattern",
        )

        # Transition to complete
        mock_transition.return_value = swarm.StageTransitionResult(
            action="complete",
            message="Workflow completed",
        )

        stage1 = self._make_stage_def("plan", on_complete="stop")
        workflow_def = self._make_workflow_def([stage1])

        swarm.run_workflow_monitor("test-workflow", workflow_def, self.workflow_dir)

        # monitor_stage_completion was called
        mock_monitor.assert_called_once()
        # handle_stage_transition was called
        mock_transition.assert_called_once()


class TestHandleWorkflowTransition(unittest.TestCase):
    """Test _handle_workflow_transition helper function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.workflow_dir = Path(self.temp_dir)

        # Patch WORKFLOWS_DIR to use temp directory
        self.workflows_dir_patcher = patch.object(swarm, 'WORKFLOWS_DIR', Path(self.temp_dir) / 'workflows')
        self.workflows_dir_patcher.start()

        # Create workflows directory
        (Path(self.temp_dir) / 'workflows').mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        self.workflows_dir_patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_stage_def(self, name):
        """Helper to create a StageDefinition."""
        return swarm.StageDefinition(
            name=name,
            type="worker",
            prompt="Test prompt",
        )

    @patch('swarm.start_next_stage')
    @patch('swarm.handle_stage_transition')
    @patch('swarm.save_workflow_state')
    @patch('swarm.load_workflow_state')
    def test_handle_transition_for_complete_action(self, mock_load, mock_save, mock_transition, mock_start_next):
        """Test _handle_workflow_transition with complete action."""
        workflow_state = swarm.WorkflowState(
            name="test-workflow",
            status="running",
            stages={"plan": swarm.StageState(status="running")},
        )
        mock_load.return_value = workflow_state

        mock_transition.return_value = swarm.StageTransitionResult(
            action="complete",
            message="Workflow completed",
        )

        stage1 = self._make_stage_def("plan")
        workflow_def = swarm.WorkflowDefinition(name="test-workflow", stages=[stage1])

        completion_result = swarm.StageCompletionResult(
            completed=True,
            success=True,
            reason="done_pattern",
        )

        swarm._handle_workflow_transition(
            workflow_name="test-workflow",
            workflow_state=workflow_state,
            workflow_def=workflow_def,
            stage_def=stage1,
            completion_result=completion_result,
            workflow_dir=self.workflow_dir,
        )

        mock_transition.assert_called_once()
        mock_save.assert_called()
        # start_next_stage should NOT be called for complete action
        mock_start_next.assert_not_called()

    @patch('swarm.start_next_stage')
    @patch('swarm.handle_stage_transition')
    @patch('swarm.save_workflow_state')
    @patch('swarm.load_workflow_state')
    def test_handle_transition_for_next_stage_action(self, mock_load, mock_save, mock_transition, mock_start_next):
        """Test _handle_workflow_transition with next_stage action."""
        workflow_state = swarm.WorkflowState(
            name="test-workflow",
            status="running",
            stages={
                "plan": swarm.StageState(status="running"),
                "build": swarm.StageState(status="pending"),
            },
        )
        mock_load.return_value = workflow_state

        mock_transition.return_value = swarm.StageTransitionResult(
            action="next_stage",
            next_stage_name="build",
            next_stage_index=1,
            message="Starting build stage",
        )

        mock_start_next.return_value = swarm.Worker(
            name="test-workflow-build",
            status="running",
            cmd=["claude"],
            started=datetime.now().isoformat(),
            cwd="/tmp/test",
        )

        stage1 = self._make_stage_def("plan")
        stage2 = self._make_stage_def("build")
        workflow_def = swarm.WorkflowDefinition(name="test-workflow", stages=[stage1, stage2])

        completion_result = swarm.StageCompletionResult(
            completed=True,
            success=True,
            reason="done_pattern",
        )

        swarm._handle_workflow_transition(
            workflow_name="test-workflow",
            workflow_state=workflow_state,
            workflow_def=workflow_def,
            stage_def=stage1,
            completion_result=completion_result,
            workflow_dir=self.workflow_dir,
        )

        mock_transition.assert_called_once()
        mock_start_next.assert_called_once()

    @patch('swarm.start_next_stage')
    @patch('swarm.handle_stage_transition')
    @patch('swarm.save_workflow_state')
    @patch('swarm.load_workflow_state')
    def test_handle_transition_for_retry_action(self, mock_load, mock_save, mock_transition, mock_start_next):
        """Test _handle_workflow_transition with retry action."""
        workflow_state = swarm.WorkflowState(
            name="test-workflow",
            status="running",
            stages={"plan": swarm.StageState(status="running", attempts=1)},
        )
        mock_load.return_value = workflow_state

        mock_transition.return_value = swarm.StageTransitionResult(
            action="retry",
            next_stage_name="plan",
            next_stage_index=0,
            message="Retrying plan stage",
        )

        mock_start_next.return_value = swarm.Worker(
            name="test-workflow-plan",
            status="running",
            cmd=["claude"],
            started=datetime.now().isoformat(),
            cwd="/tmp/test",
        )

        stage1 = self._make_stage_def("plan")
        workflow_def = swarm.WorkflowDefinition(name="test-workflow", stages=[stage1])

        completion_result = swarm.StageCompletionResult(
            completed=True,
            success=False,
            reason="timeout",
        )

        swarm._handle_workflow_transition(
            workflow_name="test-workflow",
            workflow_state=workflow_state,
            workflow_def=workflow_def,
            stage_def=stage1,
            completion_result=completion_result,
            workflow_dir=self.workflow_dir,
        )

        mock_transition.assert_called_once()
        # For retry, start_next_stage should be called with is_retry=True
        mock_start_next.assert_called_once()
        call_kwargs = mock_start_next.call_args
        self.assertTrue(call_kwargs[1].get('is_retry', False))

    @patch('swarm.start_next_stage')
    @patch('swarm.handle_stage_transition')
    @patch('swarm.save_workflow_state')
    @patch('swarm.load_workflow_state')
    def test_handle_transition_for_fail_action(self, mock_load, mock_save, mock_transition, mock_start_next):
        """Test _handle_workflow_transition with fail action."""
        workflow_state = swarm.WorkflowState(
            name="test-workflow",
            status="running",
            stages={"plan": swarm.StageState(status="running")},
        )
        mock_load.return_value = workflow_state

        mock_transition.return_value = swarm.StageTransitionResult(
            action="fail",
            message="Workflow failed",
        )

        stage1 = self._make_stage_def("plan")
        workflow_def = swarm.WorkflowDefinition(name="test-workflow", stages=[stage1])

        completion_result = swarm.StageCompletionResult(
            completed=True,
            success=False,
            reason="error",
        )

        swarm._handle_workflow_transition(
            workflow_name="test-workflow",
            workflow_state=workflow_state,
            workflow_def=workflow_def,
            stage_def=stage1,
            completion_result=completion_result,
            workflow_dir=self.workflow_dir,
        )

        mock_transition.assert_called_once()
        mock_save.assert_called()
        # start_next_stage should NOT be called for fail action
        mock_start_next.assert_not_called()

    @patch('swarm.handle_stage_transition')
    @patch('swarm.save_workflow_state')
    @patch('swarm.load_workflow_state')
    def test_handle_transition_exits_when_workflow_not_found(self, mock_load, mock_save, mock_transition):
        """Test _handle_workflow_transition exits gracefully when workflow is not found."""
        mock_load.return_value = None

        workflow_state = swarm.WorkflowState(
            name="test-workflow",
            status="running",
            stages={"plan": swarm.StageState(status="running")},
        )

        stage1 = self._make_stage_def("plan")
        workflow_def = swarm.WorkflowDefinition(name="test-workflow", stages=[stage1])

        completion_result = swarm.StageCompletionResult(
            completed=True,
            success=True,
            reason="done_pattern",
        )

        # Should not raise
        swarm._handle_workflow_transition(
            workflow_name="test-workflow",
            workflow_state=workflow_state,
            workflow_def=workflow_def,
            stage_def=stage1,
            completion_result=completion_result,
            workflow_dir=self.workflow_dir,
        )

        # handle_stage_transition should NOT be called
        mock_transition.assert_not_called()


class TestCmdWorkflowStatus(unittest.TestCase):
    """Test cmd_workflow_status function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_workflows_dir = swarm.WORKFLOWS_DIR
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.WORKFLOWS_DIR = swarm.SWARM_DIR / "workflows"
        swarm.WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.WORKFLOWS_DIR = self.original_workflows_dir
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_workflow_state(self, name, **kwargs):
        """Create a workflow state and save it."""
        defaults = {
            "name": name,
            "status": "running",
            "current_stage": "plan",
            "current_stage_index": 0,
            "created_at": "2026-02-04T10:00:00+00:00",
            "started_at": "2026-02-04T10:00:00+00:00",
            "scheduled_for": None,
            "completed_at": None,
            "stages": {
                "plan": swarm.StageState(
                    status="running",
                    started_at="2026-02-04T10:00:00+00:00",
                    worker_name=f"{name}-plan",
                    attempts=1,
                ),
                "build": swarm.StageState(
                    status="pending",
                ),
            },
            "workflow_file": "/path/to/workflow.yaml",
            "workflow_hash": "abc123",
        }
        defaults.update(kwargs)
        workflow_state = swarm.WorkflowState(**defaults)
        swarm.save_workflow_state(workflow_state)
        return workflow_state

    def test_status_workflow_not_found(self):
        """Test status for non-existent workflow."""
        args = Namespace(
            name="nonexistent",
            format="text"
        )
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_status(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_status_text_format_running(self):
        """Test text format output for running workflow."""
        self._create_workflow_state("test-workflow")

        args = Namespace(
            name="test-workflow",
            format="text"
        )

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_status(args)

        output = captured.getvalue()
        self.assertIn("Workflow: test-workflow", output)
        self.assertIn("Status: running", output)
        self.assertIn("Current: plan", output)
        self.assertIn("Started: 2026-02-04T10:00:00+00:00", output)
        self.assertIn("Source: /path/to/workflow.yaml", output)
        self.assertIn("Stages:", output)
        self.assertIn("plan", output)
        self.assertIn("build", output)

    def test_status_text_format_scheduled(self):
        """Test text format output for scheduled workflow."""
        # Use a future timestamp for scheduled_for
        future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        self._create_workflow_state(
            "scheduled-workflow",
            status="scheduled",
            current_stage=None,
            started_at=None,
            scheduled_for=future_time,
            stages={},
        )

        args = Namespace(
            name="scheduled-workflow",
            format="text"
        )

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_status(args)

        output = captured.getvalue()
        self.assertIn("Workflow: scheduled-workflow", output)
        self.assertIn("Status: scheduled", output)
        self.assertIn("Scheduled:", output)

    def test_status_text_format_completed(self):
        """Test text format output for completed workflow."""
        self._create_workflow_state(
            "completed-workflow",
            status="completed",
            current_stage=None,
            completed_at="2026-02-04T12:00:00+00:00",
            stages={
                "plan": swarm.StageState(
                    status="completed",
                    started_at="2026-02-04T10:00:00+00:00",
                    completed_at="2026-02-04T11:00:00+00:00",
                    worker_name="completed-workflow-plan",
                    attempts=1,
                    exit_reason="done_pattern",
                ),
                "build": swarm.StageState(
                    status="completed",
                    started_at="2026-02-04T11:00:00+00:00",
                    completed_at="2026-02-04T12:00:00+00:00",
                    worker_name="completed-workflow-build",
                    attempts=2,
                    exit_reason="done_pattern",
                ),
            },
        )

        args = Namespace(
            name="completed-workflow",
            format="text"
        )

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_status(args)

        output = captured.getvalue()
        self.assertIn("Workflow: completed-workflow", output)
        self.assertIn("Status: completed", output)
        self.assertIn("Completed: 2026-02-04T12:00:00+00:00", output)
        self.assertIn("done_pattern", output)

    def test_status_json_format(self):
        """Test JSON format output."""
        self._create_workflow_state("json-workflow")

        args = Namespace(
            name="json-workflow",
            format="json"
        )

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_status(args)

        output = captured.getvalue()
        data = json.loads(output)

        self.assertEqual(data["name"], "json-workflow")
        self.assertEqual(data["status"], "running")
        self.assertEqual(data["current_stage"], "plan")
        self.assertIn("plan", data["stages"])
        self.assertIn("build", data["stages"])
        self.assertEqual(data["stages"]["plan"]["status"], "running")
        self.assertEqual(data["stages"]["plan"]["worker_name"], "json-workflow-plan")

    def test_status_json_format_complete_structure(self):
        """Test JSON format contains all expected fields."""
        self._create_workflow_state(
            "full-json-workflow",
            status="failed",
            current_stage="build",
            current_stage_index=1,
            completed_at="2026-02-04T14:00:00+00:00",
            stages={
                "plan": swarm.StageState(
                    status="completed",
                    started_at="2026-02-04T10:00:00+00:00",
                    completed_at="2026-02-04T11:00:00+00:00",
                    worker_name="full-json-workflow-plan",
                    attempts=1,
                    exit_reason="done_pattern",
                ),
                "build": swarm.StageState(
                    status="failed",
                    started_at="2026-02-04T11:00:00+00:00",
                    completed_at="2026-02-04T14:00:00+00:00",
                    worker_name="full-json-workflow-build",
                    attempts=3,
                    exit_reason="error",
                ),
            },
        )

        args = Namespace(
            name="full-json-workflow",
            format="json"
        )

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_status(args)

        output = captured.getvalue()
        data = json.loads(output)

        # Check all top-level fields
        self.assertIn("name", data)
        self.assertIn("status", data)
        self.assertIn("current_stage", data)
        self.assertIn("current_stage_index", data)
        self.assertIn("created_at", data)
        self.assertIn("started_at", data)
        self.assertIn("scheduled_for", data)
        self.assertIn("completed_at", data)
        self.assertIn("stages", data)
        self.assertIn("workflow_file", data)
        self.assertIn("workflow_hash", data)

        # Check stage fields
        build_stage = data["stages"]["build"]
        self.assertEqual(build_stage["status"], "failed")
        self.assertEqual(build_stage["attempts"], 3)
        self.assertEqual(build_stage["exit_reason"], "error")

    def test_status_stages_table_format(self):
        """Test that stages are shown in table format."""
        self._create_workflow_state(
            "table-workflow",
            stages={
                "plan": swarm.StageState(
                    status="completed",
                    started_at="2026-02-04T10:00:00+00:00",
                    completed_at="2026-02-04T11:00:00+00:00",
                    worker_name="table-workflow-plan",
                    attempts=1,
                    exit_reason="done_pattern",
                ),
                "build": swarm.StageState(
                    status="running",
                    started_at="2026-02-04T11:00:00+00:00",
                    worker_name="table-workflow-build",
                    attempts=1,
                ),
                "validate": swarm.StageState(
                    status="pending",
                ),
            },
        )

        args = Namespace(
            name="table-workflow",
            format="text"
        )

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_status(args)

        output = captured.getvalue()
        # Check table headers
        self.assertIn("Name", output)
        self.assertIn("Status", output)
        self.assertIn("Worker", output)
        self.assertIn("Attempts", output)
        self.assertIn("Exit Reason", output)

        # Check stage data
        self.assertIn("plan", output)
        self.assertIn("completed", output)
        self.assertIn("table-workflow-plan", output)

        self.assertIn("build", output)
        self.assertIn("running", output)
        self.assertIn("table-workflow-build", output)

        self.assertIn("validate", output)
        self.assertIn("pending", output)

    def test_status_no_stages(self):
        """Test status with empty stages."""
        self._create_workflow_state(
            "empty-stages-workflow",
            status="created",
            current_stage=None,
            started_at=None,
            stages={},
        )

        args = Namespace(
            name="empty-stages-workflow",
            format="text"
        )

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_status(args)

        output = captured.getvalue()
        self.assertIn("Workflow: empty-stages-workflow", output)
        self.assertIn("Status: created", output)
        # Should not have stages table if no stages
        self.assertNotIn("Stages:", output)


class TestCmdWorkflowList(unittest.TestCase):
    """Test cmd_workflow_list function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_workflows_dir = swarm.WORKFLOWS_DIR
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.WORKFLOWS_DIR = swarm.SWARM_DIR / "workflows"
        swarm.WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.WORKFLOWS_DIR = self.original_workflows_dir
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_workflow_state(self, name, **kwargs):
        """Create a workflow state and save it."""
        defaults = {
            "name": name,
            "status": "running",
            "current_stage": "plan",
            "current_stage_index": 0,
            "created_at": "2026-02-04T10:00:00+00:00",
            "started_at": "2026-02-04T10:00:00+00:00",
            "scheduled_for": None,
            "completed_at": None,
            "stages": {
                "plan": swarm.StageState(
                    status="running",
                    started_at="2026-02-04T10:00:00+00:00",
                    worker_name=f"{name}-plan",
                    attempts=1,
                ),
            },
            "workflow_file": "/path/to/workflow.yaml",
            "workflow_hash": "abc123",
        }
        defaults.update(kwargs)
        workflow_state = swarm.WorkflowState(**defaults)
        swarm.save_workflow_state(workflow_state)
        return workflow_state

    def test_list_no_workflows_table(self):
        """Test listing when no workflows exist (table format)."""
        args = Namespace(format="table")

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_list(args)

        output = captured.getvalue()
        self.assertIn("No workflows found", output)

    def test_list_no_workflows_json(self):
        """Test listing when no workflows exist (JSON format)."""
        args = Namespace(format="json")

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_list(args)

        output = captured.getvalue()
        self.assertEqual(output.strip(), "[]")

    def test_list_single_workflow_table(self):
        """Test listing a single workflow (table format)."""
        self._create_workflow_state("my-workflow")

        args = Namespace(format="table")

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_list(args)

        output = captured.getvalue()
        # Check headers
        self.assertIn("NAME", output)
        self.assertIn("STATUS", output)
        self.assertIn("CURRENT", output)
        self.assertIn("STARTED", output)
        self.assertIn("SOURCE", output)
        # Check workflow data
        self.assertIn("my-workflow", output)
        self.assertIn("running", output)
        self.assertIn("plan", output)

    def test_list_single_workflow_json(self):
        """Test listing a single workflow (JSON format)."""
        self._create_workflow_state("my-workflow")

        args = Namespace(format="json")

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_list(args)

        output = captured.getvalue()
        data = json.loads(output)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "my-workflow")
        self.assertEqual(data[0]["status"], "running")
        self.assertEqual(data[0]["current_stage"], "plan")

    def test_list_multiple_workflows_table(self):
        """Test listing multiple workflows (table format)."""
        self._create_workflow_state("workflow-a", status="running", current_stage="build")
        self._create_workflow_state("workflow-b", status="completed", current_stage=None)
        self._create_workflow_state("workflow-c", status="scheduled", current_stage=None, started_at=None)

        args = Namespace(format="table")

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_list(args)

        output = captured.getvalue()
        # Check all workflows are listed
        self.assertIn("workflow-a", output)
        self.assertIn("workflow-b", output)
        self.assertIn("workflow-c", output)
        # Check various statuses
        self.assertIn("running", output)
        self.assertIn("completed", output)
        self.assertIn("scheduled", output)

    def test_list_multiple_workflows_json(self):
        """Test listing multiple workflows (JSON format)."""
        self._create_workflow_state("workflow-a")
        self._create_workflow_state("workflow-b")

        args = Namespace(format="json")

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_list(args)

        output = captured.getvalue()
        data = json.loads(output)
        self.assertEqual(len(data), 2)
        names = [wf["name"] for wf in data]
        self.assertIn("workflow-a", names)
        self.assertIn("workflow-b", names)

    def test_list_sorted_by_name(self):
        """Test that workflows are sorted by name."""
        self._create_workflow_state("zebra-workflow")
        self._create_workflow_state("alpha-workflow")
        self._create_workflow_state("middle-workflow")

        args = Namespace(format="json")

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_list(args)

        output = captured.getvalue()
        data = json.loads(output)
        names = [wf["name"] for wf in data]
        self.assertEqual(names, ["alpha-workflow", "middle-workflow", "zebra-workflow"])

    def test_list_shows_current_stage_when_none(self):
        """Test that current stage shows '-' when None."""
        self._create_workflow_state(
            "completed-workflow",
            status="completed",
            current_stage=None,
        )

        args = Namespace(format="table")

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_list(args)

        output = captured.getvalue()
        self.assertIn("completed-workflow", output)
        # Current stage should show as "-" when None
        lines = output.strip().split("\n")
        # Find the data line (skip header)
        data_line = [l for l in lines if "completed-workflow" in l][0]
        self.assertIn("-", data_line)

    def test_list_shows_started_when_none(self):
        """Test that started shows '-' when workflow hasn't started."""
        self._create_workflow_state(
            "scheduled-workflow",
            status="scheduled",
            current_stage=None,
            started_at=None,
        )

        args = Namespace(format="table")

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_list(args)

        output = captured.getvalue()
        self.assertIn("scheduled-workflow", output)
        self.assertIn("scheduled", output)

    def test_list_truncates_long_source_path(self):
        """Test that very long source paths are truncated."""
        self._create_workflow_state(
            "long-path-workflow",
            workflow_file="/very/long/path/that/goes/on/and/on/and/never/seems/to/end/workflow.yaml",
        )

        args = Namespace(format="table")

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_list(args)

        output = captured.getvalue()
        self.assertIn("long-path-workflow", output)
        # Path should be truncated with "..."
        self.assertIn("...", output)

    def test_list_all_status_values(self):
        """Test listing workflows with all possible status values."""
        statuses = ["created", "scheduled", "running", "completed", "failed", "cancelled"]
        for i, status in enumerate(statuses):
            self._create_workflow_state(
                f"workflow-{i}",
                status=status,
                current_stage="plan" if status == "running" else None,
            )

        args = Namespace(format="json")

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_list(args)

        output = captured.getvalue()
        data = json.loads(output)
        self.assertEqual(len(data), len(statuses))
        found_statuses = [wf["status"] for wf in data]
        for status in statuses:
            self.assertIn(status, found_statuses)


class TestCmdWorkflowCancel(unittest.TestCase):
    """Test cmd_workflow_cancel function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_workflows_dir = swarm.WORKFLOWS_DIR
        self.original_state_file = swarm.STATE_FILE
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.WORKFLOWS_DIR = swarm.SWARM_DIR / "workflows"
        swarm.WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"
        swarm.STATE_FILE = swarm.SWARM_DIR / "state.json"
        swarm.HEARTBEATS_DIR = swarm.SWARM_DIR / "heartbeats"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.WORKFLOWS_DIR = self.original_workflows_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"
        swarm.HEARTBEATS_DIR = swarm.SWARM_DIR / "heartbeats"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_workflow_state(self, name, **kwargs):
        """Create a workflow state and save it."""
        defaults = {
            "name": name,
            "status": "running",
            "current_stage": "plan",
            "current_stage_index": 0,
            "created_at": "2026-02-04T10:00:00+00:00",
            "started_at": "2026-02-04T10:00:00+00:00",
            "scheduled_for": None,
            "completed_at": None,
            "stages": {
                "plan": swarm.StageState(
                    status="running",
                    started_at="2026-02-04T10:00:00+00:00",
                    worker_name=f"{name}-plan",
                    attempts=1,
                ),
                "build": swarm.StageState(
                    status="pending",
                ),
            },
            "workflow_file": "/path/to/workflow.yaml",
            "workflow_hash": "abc123",
        }
        defaults.update(kwargs)
        workflow_state = swarm.WorkflowState(**defaults)
        swarm.save_workflow_state(workflow_state)
        return workflow_state

    def test_cancel_workflow_not_found(self):
        """Test cancel for non-existent workflow."""
        args = Namespace(
            name="nonexistent",
            force=False
        )
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_cancel(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_cancel_completed_workflow_fails(self):
        """Test that cancelling a completed workflow fails."""
        self._create_workflow_state(
            "completed-workflow",
            status="completed",
        )

        args = Namespace(
            name="completed-workflow",
            force=False
        )
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_cancel(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_cancel_failed_workflow_fails(self):
        """Test that cancelling a failed workflow fails."""
        self._create_workflow_state(
            "failed-workflow",
            status="failed",
        )

        args = Namespace(
            name="failed-workflow",
            force=False
        )
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_cancel(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_cancel_already_cancelled_workflow_fails(self):
        """Test that cancelling an already cancelled workflow fails."""
        self._create_workflow_state(
            "cancelled-workflow",
            status="cancelled",
        )

        args = Namespace(
            name="cancelled-workflow",
            force=False
        )
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_cancel(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_cancel_running_workflow_success(self):
        """Test cancelling a running workflow (no worker)."""
        self._create_workflow_state("test-workflow")

        args = Namespace(
            name="test-workflow",
            force=False
        )

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_cancel(args)

        output = captured.getvalue()
        self.assertIn("Workflow 'test-workflow' cancelled", output)

        # Verify workflow state was updated
        workflow_state = swarm.load_workflow_state("test-workflow")
        self.assertEqual(workflow_state.status, "cancelled")
        self.assertIsNotNone(workflow_state.completed_at)

    def test_cancel_scheduled_workflow_success(self):
        """Test cancelling a scheduled workflow."""
        self._create_workflow_state(
            "scheduled-workflow",
            status="scheduled",
            current_stage=None,
            started_at=None,
            stages={},
        )

        args = Namespace(
            name="scheduled-workflow",
            force=False
        )

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_cancel(args)

        output = captured.getvalue()
        self.assertIn("Workflow 'scheduled-workflow' cancelled", output)

        # Verify workflow state was updated
        workflow_state = swarm.load_workflow_state("scheduled-workflow")
        self.assertEqual(workflow_state.status, "cancelled")
        self.assertIsNotNone(workflow_state.completed_at)

    def test_cancel_updates_stage_status(self):
        """Test that cancel marks the current stage as failed with 'cancelled' exit reason."""
        self._create_workflow_state("test-workflow")

        args = Namespace(
            name="test-workflow",
            force=False
        )

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_cancel(args)

        # Verify stage state was updated
        workflow_state = swarm.load_workflow_state("test-workflow")
        stage_state = workflow_state.stages["plan"]
        self.assertEqual(stage_state.status, "failed")
        self.assertEqual(stage_state.exit_reason, "cancelled")
        self.assertIsNotNone(stage_state.completed_at)

    def test_cancel_pending_stages_remain_pending(self):
        """Test that pending stages remain pending after cancel."""
        self._create_workflow_state("test-workflow")

        args = Namespace(
            name="test-workflow",
            force=False
        )

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_cancel(args)

        # Verify pending stage wasn't changed
        workflow_state = swarm.load_workflow_state("test-workflow")
        build_stage = workflow_state.stages["build"]
        self.assertEqual(build_stage.status, "pending")
        self.assertIsNone(build_stage.exit_reason)

    def test_cancel_kills_worker(self):
        """Test that cancel kills the stage worker if it exists."""
        self._create_workflow_state("test-workflow")

        # Create a mock worker in state
        state = swarm.State()
        worker = swarm.Worker(
            name="test-workflow-plan",
            status="running",
            cmd=["bash", "-c", "sleep 60"],
            started="2026-02-04T10:00:00+00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(
                session="swarm",
                window="test-workflow-plan",
                socket=None,
            )
        )
        state.workers.append(worker)
        state.save()

        args = Namespace(
            name="test-workflow",
            force=False
        )

        # Mock the subprocess.run call to avoid actually trying to kill tmux
        with patch('subprocess.run') as mock_run:
            import io
            captured = io.StringIO()
            with patch('sys.stdout', captured):
                swarm.cmd_workflow_cancel(args)

            # Verify tmux kill-window was called
            mock_run.assert_called()
            call_args = mock_run.call_args[0][0]
            self.assertIn("kill-window", call_args)

    def test_cancel_stops_heartbeat(self):
        """Test that cancel stops the heartbeat if active."""
        self._create_workflow_state("test-workflow")

        # Create a heartbeat state for the worker
        swarm.HEARTBEATS_DIR.mkdir(parents=True, exist_ok=True)
        heartbeat_state = swarm.HeartbeatState(
            worker_name="test-workflow-plan",
            interval_seconds=60,
            message="continue",
            status="active",
            created_at="2026-02-04T10:00:00+00:00",
            monitor_pid=12345,  # Fake PID
        )
        swarm.save_heartbeat_state(heartbeat_state)

        # Create a mock worker in state
        state = swarm.State()
        worker = swarm.Worker(
            name="test-workflow-plan",
            status="running",
            cmd=["bash", "-c", "sleep 60"],
            started="2026-02-04T10:00:00+00:00",
            cwd="/tmp",
        )
        state.workers.append(worker)
        state.save()

        args = Namespace(
            name="test-workflow",
            force=False
        )

        # Mock stop_heartbeat_monitor to avoid actually trying to kill process
        with patch.object(swarm, 'stop_heartbeat_monitor', return_value=True) as mock_stop:
            import io
            captured = io.StringIO()
            with patch('sys.stdout', captured):
                swarm.cmd_workflow_cancel(args)

            # Verify stop_heartbeat_monitor was called
            mock_stop.assert_called_once()

        # Verify heartbeat state was updated
        heartbeat_state = swarm.load_heartbeat_state("test-workflow-plan")
        self.assertEqual(heartbeat_state.status, "stopped")
        self.assertIsNone(heartbeat_state.monitor_pid)

    def test_cancel_with_no_current_stage(self):
        """Test cancelling a workflow that has no current stage set."""
        self._create_workflow_state(
            "test-workflow",
            current_stage=None,
            stages={},
        )

        args = Namespace(
            name="test-workflow",
            force=False
        )

        import io
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            swarm.cmd_workflow_cancel(args)

        output = captured.getvalue()
        self.assertIn("Workflow 'test-workflow' cancelled", output)

        # Verify workflow state was updated
        workflow_state = swarm.load_workflow_state("test-workflow")
        self.assertEqual(workflow_state.status, "cancelled")

    def test_cancel_with_force_flag(self):
        """Test that force flag is passed to worker kill."""
        self._create_workflow_state("test-workflow")

        # Create a mock worker in state with PID
        state = swarm.State()
        worker = swarm.Worker(
            name="test-workflow-plan",
            status="running",
            cmd=["bash", "-c", "sleep 60"],
            started="2026-02-04T10:00:00+00:00",
            cwd="/tmp",
            pid=12345,  # Non-tmux worker with PID
        )
        state.workers.append(worker)
        state.save()

        args = Namespace(
            name="test-workflow",
            force=True
        )

        # Mock os.kill to avoid actually trying to kill process
        with patch('os.kill') as mock_kill:
            import io
            captured = io.StringIO()
            with patch('sys.stdout', captured):
                swarm.cmd_workflow_cancel(args)

            # When force=True, should use SIGKILL directly
            import signal
            mock_kill.assert_called_with(12345, signal.SIGKILL)


class TestCmdWorkflowResume(unittest.TestCase):
    """Test cmd_workflow_resume function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_workflows_dir = swarm.WORKFLOWS_DIR
        self.original_state_file = swarm.STATE_FILE
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.WORKFLOWS_DIR = swarm.SWARM_DIR / "workflows"
        swarm.WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"
        swarm.STATE_FILE = swarm.SWARM_DIR / "state.json"
        swarm.HEARTBEATS_DIR = swarm.SWARM_DIR / "heartbeats"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.WORKFLOWS_DIR = self.original_workflows_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.WORKFLOW_LOCK_FILE = swarm.SWARM_DIR / "workflow.lock"
        swarm.HEARTBEATS_DIR = swarm.SWARM_DIR / "heartbeats"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_workflow_state(self, name, **kwargs):
        """Create a workflow state and save it."""
        defaults = {
            "name": name,
            "status": "failed",
            "current_stage": "build",
            "current_stage_index": 1,
            "created_at": "2026-02-04T10:00:00+00:00",
            "started_at": "2026-02-04T10:00:00+00:00",
            "scheduled_for": None,
            "completed_at": "2026-02-04T11:00:00+00:00",
            "stages": {
                "plan": swarm.StageState(
                    status="completed",
                    started_at="2026-02-04T10:00:00+00:00",
                    completed_at="2026-02-04T10:30:00+00:00",
                    worker_name=f"{name}-plan",
                    attempts=1,
                    exit_reason="done_pattern",
                ),
                "build": swarm.StageState(
                    status="failed",
                    started_at="2026-02-04T10:30:00+00:00",
                    completed_at="2026-02-04T11:00:00+00:00",
                    worker_name=f"{name}-build",
                    attempts=1,
                    exit_reason="error",
                ),
                "validate": swarm.StageState(
                    status="pending",
                ),
            },
            "workflow_file": "/path/to/workflow.yaml",
            "workflow_hash": "abc123",
        }
        defaults.update(kwargs)
        workflow_state = swarm.WorkflowState(**defaults)
        swarm.save_workflow_state(workflow_state)
        return workflow_state

    def _create_workflow_yaml(self, name):
        """Create a workflow YAML file in the state directory."""
        yaml_content = f"""name: {name}
stages:
  - name: plan
    type: worker
    prompt: "Plan the work"
    done-pattern: "/done"
    timeout: 1h
  - name: build
    type: worker
    prompt: "Build the feature"
    done-pattern: "/done"
    timeout: 2h
  - name: validate
    type: worker
    prompt: "Validate the work"
    done-pattern: "/done"
    timeout: 1h
"""
        yaml_path = swarm.get_workflow_yaml_copy_path(name)
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with open(yaml_path, "w") as f:
            f.write(yaml_content)
        return yaml_path

    def test_resume_workflow_not_found(self):
        """Test resume for non-existent workflow."""
        args = Namespace(
            name="nonexistent",
            from_stage=None
        )
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_resume(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_resume_running_workflow_fails(self):
        """Test that resuming a running workflow fails."""
        self._create_workflow_state(
            "running-workflow",
            status="running",
        )
        self._create_workflow_yaml("running-workflow")

        args = Namespace(
            name="running-workflow",
            from_stage=None
        )
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_resume(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_resume_completed_workflow_fails(self):
        """Test that resuming a completed workflow fails."""
        self._create_workflow_state(
            "completed-workflow",
            status="completed",
        )
        self._create_workflow_yaml("completed-workflow")

        args = Namespace(
            name="completed-workflow",
            from_stage=None
        )
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_resume(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_resume_scheduled_workflow_fails(self):
        """Test that resuming a scheduled workflow fails."""
        self._create_workflow_state(
            "scheduled-workflow",
            status="scheduled",
        )
        self._create_workflow_yaml("scheduled-workflow")

        args = Namespace(
            name="scheduled-workflow",
            from_stage=None
        )
        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_resume(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_resume_failed_workflow_from_current_stage(self):
        """Test resuming a failed workflow from the current stage."""
        self._create_workflow_state("failed-workflow")
        self._create_workflow_yaml("failed-workflow")

        args = Namespace(
            name="failed-workflow",
            from_stage=None
        )

        # Mock spawn_workflow_stage and run_workflow_monitor
        with patch.object(swarm, 'spawn_workflow_stage') as mock_spawn:
            with patch.object(swarm, 'run_workflow_monitor') as mock_monitor:
                mock_worker = MagicMock()
                mock_worker.name = "failed-workflow-build"
                mock_spawn.return_value = mock_worker

                import io
                captured = io.StringIO()
                with patch('sys.stdout', captured):
                    swarm.cmd_workflow_resume(args)

                output = captured.getvalue()
                self.assertIn("Workflow 'failed-workflow' resumed from stage 'build'", output)
                self.assertIn("Spawned worker 'failed-workflow-build'", output)

        # Verify workflow state was updated
        workflow_state = swarm.load_workflow_state("failed-workflow")
        self.assertEqual(workflow_state.status, "running")
        self.assertEqual(workflow_state.current_stage, "build")
        self.assertIsNone(workflow_state.completed_at)

        # Verify build stage was reset to running
        build_stage = workflow_state.stages["build"]
        self.assertEqual(build_stage.status, "running")
        self.assertIsNotNone(build_stage.started_at)
        self.assertEqual(build_stage.worker_name, "failed-workflow-build")
        self.assertEqual(build_stage.attempts, 2)  # Incremented from 1

        # Verify validate stage was reset to pending
        validate_stage = workflow_state.stages["validate"]
        self.assertEqual(validate_stage.status, "pending")
        self.assertEqual(validate_stage.attempts, 0)

        # Verify plan stage was NOT modified (completed before resume point)
        plan_stage = workflow_state.stages["plan"]
        self.assertEqual(plan_stage.status, "completed")

    def test_resume_cancelled_workflow(self):
        """Test resuming a cancelled workflow."""
        self._create_workflow_state(
            "cancelled-workflow",
            status="cancelled",
        )
        self._create_workflow_yaml("cancelled-workflow")

        args = Namespace(
            name="cancelled-workflow",
            from_stage=None
        )

        with patch.object(swarm, 'spawn_workflow_stage') as mock_spawn:
            with patch.object(swarm, 'run_workflow_monitor') as mock_monitor:
                mock_worker = MagicMock()
                mock_worker.name = "cancelled-workflow-build"
                mock_spawn.return_value = mock_worker

                import io
                captured = io.StringIO()
                with patch('sys.stdout', captured):
                    swarm.cmd_workflow_resume(args)

                output = captured.getvalue()
                self.assertIn("resumed from stage 'build'", output)

        # Verify workflow is now running
        workflow_state = swarm.load_workflow_state("cancelled-workflow")
        self.assertEqual(workflow_state.status, "running")

    def test_resume_from_specific_stage(self):
        """Test resuming from a specified stage."""
        self._create_workflow_state("test-workflow")
        self._create_workflow_yaml("test-workflow")

        args = Namespace(
            name="test-workflow",
            from_stage="plan"  # Resume from the first stage
        )

        with patch.object(swarm, 'spawn_workflow_stage') as mock_spawn:
            with patch.object(swarm, 'run_workflow_monitor') as mock_monitor:
                mock_worker = MagicMock()
                mock_worker.name = "test-workflow-plan"
                mock_spawn.return_value = mock_worker

                import io
                captured = io.StringIO()
                with patch('sys.stdout', captured):
                    swarm.cmd_workflow_resume(args)

                output = captured.getvalue()
                self.assertIn("resumed from stage 'plan'", output)

        # Verify workflow state was updated
        workflow_state = swarm.load_workflow_state("test-workflow")
        self.assertEqual(workflow_state.current_stage, "plan")
        self.assertEqual(workflow_state.current_stage_index, 0)

        # All stages should be reset
        plan_stage = workflow_state.stages["plan"]
        self.assertEqual(plan_stage.status, "running")

        build_stage = workflow_state.stages["build"]
        self.assertEqual(build_stage.status, "pending")

        validate_stage = workflow_state.stages["validate"]
        self.assertEqual(validate_stage.status, "pending")

    def test_resume_from_invalid_stage_fails(self):
        """Test that resuming from an invalid stage fails."""
        self._create_workflow_state("test-workflow")
        self._create_workflow_yaml("test-workflow")

        args = Namespace(
            name="test-workflow",
            from_stage="nonexistent-stage"
        )

        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_resume(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_resume_missing_yaml_fails(self):
        """Test that resuming without YAML file fails."""
        self._create_workflow_state("test-workflow")
        # Intentionally don't create the YAML file

        args = Namespace(
            name="test-workflow",
            from_stage=None
        )

        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_workflow_resume(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_resume_preserves_attempt_count_on_resume_stage(self):
        """Test that attempt count is preserved and incremented on the resume stage."""
        self._create_workflow_state(
            "test-workflow",
            stages={
                "plan": swarm.StageState(
                    status="completed",
                    attempts=1,
                    exit_reason="done_pattern",
                ),
                "build": swarm.StageState(
                    status="failed",
                    attempts=3,  # Multiple previous attempts
                    exit_reason="error",
                ),
                "validate": swarm.StageState(
                    status="pending",
                    attempts=0,
                ),
            },
        )
        self._create_workflow_yaml("test-workflow")

        args = Namespace(
            name="test-workflow",
            from_stage=None
        )

        with patch.object(swarm, 'spawn_workflow_stage') as mock_spawn:
            with patch.object(swarm, 'run_workflow_monitor') as mock_monitor:
                mock_worker = MagicMock()
                mock_worker.name = "test-workflow-build"
                mock_spawn.return_value = mock_worker
                swarm.cmd_workflow_resume(args)

        workflow_state = swarm.load_workflow_state("test-workflow")
        build_stage = workflow_state.stages["build"]
        self.assertEqual(build_stage.attempts, 4)  # 3 + 1

    def test_resume_clears_completed_at(self):
        """Test that completed_at is cleared when resuming."""
        self._create_workflow_state(
            "test-workflow",
            completed_at="2026-02-04T12:00:00+00:00",
        )
        self._create_workflow_yaml("test-workflow")

        args = Namespace(
            name="test-workflow",
            from_stage=None
        )

        with patch.object(swarm, 'spawn_workflow_stage') as mock_spawn:
            with patch.object(swarm, 'run_workflow_monitor') as mock_monitor:
                mock_worker = MagicMock()
                mock_worker.name = "test-workflow-build"
                mock_spawn.return_value = mock_worker
                swarm.cmd_workflow_resume(args)

        workflow_state = swarm.load_workflow_state("test-workflow")
        self.assertIsNone(workflow_state.completed_at)

    def test_resume_calls_spawn_workflow_stage(self):
        """Test that resume spawns the stage worker correctly."""
        self._create_workflow_state("test-workflow")
        self._create_workflow_yaml("test-workflow")

        args = Namespace(
            name="test-workflow",
            from_stage=None
        )

        with patch.object(swarm, 'spawn_workflow_stage') as mock_spawn:
            with patch.object(swarm, 'run_workflow_monitor') as mock_monitor:
                mock_worker = MagicMock()
                mock_worker.name = "test-workflow-build"
                mock_spawn.return_value = mock_worker
                swarm.cmd_workflow_resume(args)

                # Verify spawn was called with correct arguments
                mock_spawn.assert_called_once()
                call_kwargs = mock_spawn.call_args[1]
                self.assertEqual(call_kwargs['workflow_name'], "test-workflow")
                self.assertEqual(call_kwargs['stage_def'].name, "build")

    def test_resume_calls_workflow_monitor(self):
        """Test that resume starts the workflow monitor."""
        self._create_workflow_state("test-workflow")
        self._create_workflow_yaml("test-workflow")

        args = Namespace(
            name="test-workflow",
            from_stage=None
        )

        with patch.object(swarm, 'spawn_workflow_stage') as mock_spawn:
            with patch.object(swarm, 'run_workflow_monitor') as mock_monitor:
                mock_worker = MagicMock()
                mock_worker.name = "test-workflow-build"
                mock_spawn.return_value = mock_worker
                swarm.cmd_workflow_resume(args)

                # Verify monitor was called
                mock_monitor.assert_called_once()
                call_kwargs = mock_monitor.call_args[1]
                self.assertEqual(call_kwargs['workflow_name'], "test-workflow")

    def test_resume_spawn_failure_updates_state(self):
        """Test that spawn failure updates workflow state to failed."""
        self._create_workflow_state("test-workflow")
        self._create_workflow_yaml("test-workflow")

        args = Namespace(
            name="test-workflow",
            from_stage=None
        )

        with patch.object(swarm, 'spawn_workflow_stage') as mock_spawn:
            mock_spawn.side_effect = RuntimeError("Spawn failed")

            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_workflow_resume(args)
            self.assertEqual(ctx.exception.code, 1)

        # Verify workflow state was updated to failed
        workflow_state = swarm.load_workflow_state("test-workflow")
        self.assertEqual(workflow_state.status, "failed")
        self.assertEqual(workflow_state.stages["build"].status, "failed")
        self.assertEqual(workflow_state.stages["build"].exit_reason, "error")


if __name__ == "__main__":
    unittest.main()
