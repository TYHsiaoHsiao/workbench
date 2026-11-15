"""M6：项目状态锁与事务日志。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.project import create_project  # noqa: E402
from flow import LockError, log_transaction, state_lock  # noqa: E402
from flow.locks import LOCK_NAME, STALE_SECONDS  # noqa: E402


class FlowLocksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name) / "projects"
        report = create_project("锁测试", base=base)
        self.project = Path(report["path"])
        self.lock_path = self.project / "00_project" / ".locks" / LOCK_NAME

    def test_acquire_and_release(self) -> None:
        with state_lock(self.project, timeout=2.0):
            self.assertTrue(self.lock_path.exists())
        self.assertFalse(self.lock_path.exists())

    def test_reacquire_after_release(self) -> None:
        with state_lock(self.project, timeout=2.0):
            pass
        with state_lock(self.project, timeout=2.0):
            pass
        self.assertFalse(self.lock_path.exists())

    def test_stale_lock_is_removed(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text('{"pid": 1}', encoding="utf-8")
        old = time.time() - STALE_SECONDS - 60
        os.utime(self.lock_path, (old, old))
        with state_lock(self.project, timeout=2.0):
            self.assertTrue(self.lock_path.exists())
        self.assertFalse(self.lock_path.exists())

    def test_timeout_raises(self) -> None:
        with state_lock(self.project, timeout=2.0):
            with self.assertRaises(LockError) as ctx:
                with state_lock(self.project, timeout=0.2):
                    pass
        self.assertIn("超时", str(ctx.exception))

    def test_log_transaction_appends_jsonl(self) -> None:
        first = log_transaction(
            self.project,
            {"action": "artifact_register", "node_id": "n1", "stage": "01"},
        )
        second = log_transaction(
            self.project,
            {"action": "artifact_register", "node_id": "n2", "stage": "01"},
        )
        self.assertEqual(first, second)
        lines = [line for line in first.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(2, len(lines))
        record = json.loads(lines[0])
        for key in ("action", "node_id", "txn_id", "at"):
            self.assertIn(key, record)
        self.assertEqual("n2", json.loads(lines[1])["node_id"])


if __name__ == "__main__":
    unittest.main()
