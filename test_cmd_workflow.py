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


if __name__ == "__main__":
    unittest.main()
