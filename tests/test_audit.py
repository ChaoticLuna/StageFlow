"""Tests for AuditLogger with rotation support."""
from __future__ import annotations

import json

from stageflow.core.audit import AuditLogger


class TestAuditLogger:
    def test_write_and_read(self, tmp_path):
        logger = AuditLogger(str(tmp_path))
        logger._write({"event": "test", "value": 42})
        logger._write({"event": "test", "value": 99})
        summary = logger.get_summary()
        assert summary["total_events"] == 2

    def test_max_entries_default_unlimited(self, tmp_path):
        logger = AuditLogger(str(tmp_path))
        assert logger._max_entries == 0
        for i in range(1000):
            logger._write({"event": "bench", "i": i})
        assert logger.get_summary()["total_events"] == 1000

    def test_max_entries_keeps_last_n(self, tmp_path):
        logger = AuditLogger(str(tmp_path), max_entries=100)
        # Write 1000 entries — should truncate to keep last ~100
        for i in range(1000):
            logger._write({"event": "spam", "i": i})
        total = logger.get_summary()["total_events"]
        assert 90 <= total <= 200, f"Expected ~100 entries after truncation, got {total}"

        # The last entry should have i=999
        lines = logger.log_path.read_text(encoding="utf-8").strip().split("\n")
        last = json.loads(lines[-1])
        assert last["i"] == 999

    def test_exact_max_entries_boundary(self, tmp_path):
        logger = AuditLogger(str(tmp_path), max_entries=10)
        for i in range(30):
            logger.log_transition("a", "b", True, [f"step {i}"])
        events = logger.get_summary()["total_events"]
        assert events <= 20, f"Should be ≤ 20 (max 2× check), got {events}"

    def test_log_transition_failed(self, tmp_path):
        logger = AuditLogger(str(tmp_path))
        logger.log_transition("a", "b", False, ["blocked"])
        s = logger.get_summary()
        assert s["failed_transitions"] == 1

    def test_log_transition_forced(self, tmp_path):
        logger = AuditLogger(str(tmp_path))
        logger.log_transition("a", "b", True, forced=True)
        s = logger.get_summary()
        assert s["successful_transitions"] == 1

    def test_log_condition_check(self, tmp_path):
        logger = AuditLogger(str(tmp_path))
        logger.log_condition_check("a->b", "file_exists", True, "found it")
        s = logger.get_summary()
        assert s["total_events"] == 1

    def test_log_tool_violation(self, tmp_path):
        logger = AuditLogger(str(tmp_path))
        logger.log_tool_violation("Write", "analyze", "not allowed")
        s = logger.get_summary()
        assert s["tool_violations"] == 1
        assert s["most_violated_stage"] == "analyze"

    def test_log_stage_enter_exit_with_duration(self, tmp_path):
        logger = AuditLogger(str(tmp_path))
        logger.log_stage_enter("test_stage")
        logger.log_stage_exit("test_stage")
        s = logger.get_summary()
        assert s["stages_visited"] == 1
        assert "test_stage" in s["stage_durations"]
        assert s["stage_durations"]["test_stage"] >= 0

    def test_log_stage_exit_unknown_stage(self, tmp_path):
        logger = AuditLogger(str(tmp_path))
        logger.log_stage_exit("never_entered")
        s = logger.get_summary()
        assert s["total_events"] == 0  # stage not in timers, nothing written

    def test_log_hook_execution_success(self, tmp_path):
        logger = AuditLogger(str(tmp_path))
        logger.log_hook_execution("build", "on_enter", "shell", True, "ran ok")
        s = logger.get_summary()
        assert s["total_events"] == 1

    def test_log_hook_execution_failure(self, tmp_path):
        logger = AuditLogger(str(tmp_path))
        logger.log_hook_execution("build", "on_exit", "python", False, "crashed")
        s = logger.get_summary()
        assert s["total_events"] == 1

    def test_log_error(self, tmp_path):
        logger = AuditLogger(str(tmp_path))
        logger.log_error("ValueError", "something broke", {"stage": "build"})
        s = logger.get_summary()
        assert s["total_events"] == 1

    def test_get_summary_empty_log(self, tmp_path):
        logger = AuditLogger(str(tmp_path))
        s = logger.get_summary()
        assert s["total_events"] == 0

    def test_get_summary_corrupt_lines_skipped(self, tmp_path):
        logger = AuditLogger(str(tmp_path))
        logger.log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.log_path.write_text("not valid json\n", encoding="utf-8")
        logger._write({"event": "good"})
        s = logger.get_summary()
        assert s["total_events"] == 1

