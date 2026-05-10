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

