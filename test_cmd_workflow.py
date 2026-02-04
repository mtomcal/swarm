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


if __name__ == "__main__":
    unittest.main()
