"""Tests for knowledge/pending_qa.py"""
import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import knowledge.store as store_mod
from knowledge import pending_qa


class TestAutoCategorize(unittest.TestCase):
    def test_basic(self):
        result = pending_qa.auto_categorize("美国大学选课有什么建议", [
            {"type": "kb", "category": "course-selection", "tags": ["选课", "美国"]},
        ])
        self.assertEqual(result["auto_category"], "course-selection")
        self.assertIn("选课", result["auto_tags"])
        self.assertTrue(result["auto_title"].startswith("美国大学选课"))

    def test_no_sources(self):
        result = pending_qa.auto_categorize("测试问题", [])
        self.assertEqual(result["auto_category"], "user-qa")
        self.assertEqual(result["auto_tags"], [])

    def test_multiple_sources_majority_category(self):
        sources = [
            {"type": "kb", "category": "visa", "tags": ["签证"]},
            {"type": "kb", "category": "visa", "tags": ["签证"]},
            {"type": "web", "category": "", "tags": []},
            {"type": "kb", "category": "course", "tags": ["选课"]},
        ]
        result = pending_qa.auto_categorize("F1签证", sources)
        self.assertEqual(result["auto_category"], "visa")

    def test_title_truncation(self):
        long_q = "这是一段超过80个字的文字用来测试标题截断功能...补充一些内容让它真的超过80个字以便验证截断逻辑是否正确" * 3
        result = pending_qa.auto_categorize(long_q, [])
        self.assertLessEqual(len(result["auto_title"]), 83)  # 80 + '...'

    def test_tags_deduplicated(self):
        sources = [
            {"type": "kb", "category": "cat1", "tags": ["tag1", "tag2"]},
            {"type": "kb", "category": "cat2", "tags": ["tag1", "tag3"]},
        ]
        result = pending_qa.auto_categorize("q", sources)
        self.assertEqual(result["auto_tags"], ["tag1", "tag2", "tag3"])
        self.assertEqual(len(result["auto_tags"]), 3)


class TestAutoApproveCheck(unittest.TestCase):
    def test_approves_valid_entry(self):
        entry = {
            "answer": "这是一段超过五十个字的回答内容用来测试自动审核功能是否正常工作。补充一些文字以确保满足最低长度要求。",
            "sources": [{"type": "kb", "title": "test"}],
        }
        ok, reason = pending_qa._auto_approve_check(entry)
        self.assertTrue(ok, f"should approve but got: {reason}")

    def test_rejects_short_answer(self):
        entry = {
            "answer": "太短了",
            "sources": [{"type": "kb", "title": "test"}],
        }
        ok, reason = pending_qa._auto_approve_check(entry)
        self.assertFalse(ok)
        self.assertIn("过短", reason)

    def test_rejects_no_kb_source(self):
        entry = {
            "answer": "这是一段超过五十个字的回答内容用来测试自动审核功能是否正常工作。补充一些文字以确保满足最低长度要求。",
            "sources": [{"type": "web", "title": "test"}],
        }
        ok, reason = pending_qa._auto_approve_check(entry)
        self.assertFalse(ok)
        self.assertIn("知识库", reason)

    def test_rejects_error_keywords(self):
        # Must be >= 50 chars AND contain error keyword in first 100 chars
        entry = {
            "answer": "error: 无法连接到服务器，请稍后重试。这是一段很长很长的补充内容用来确保整个回答的长度确实能够满足自动审核的最低标准和要求。",
            "sources": [{"type": "kb", "title": "test"}],
        }
        ok, reason = pending_qa._auto_approve_check(entry)
        self.assertFalse(ok)
        self.assertIn("拒绝", reason)

    def test_empty_sources(self):
        entry = {
            "answer": "这是一段超过五十个字的回答内容用来测试自动审核功能是否正常工作。补充一些文字以确保满足最低长度要求。",
            "sources": [],
        }
        ok, reason = pending_qa._auto_approve_check(entry)
        self.assertFalse(ok)


class TestAddPending(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_file = pending_qa.PENDING_FILE
        self._orig_pqa_db = pending_qa.DB_PATH
        self._orig_store_db = store_mod.DB_PATH
        self._orig_store = store_mod._store
        pending_qa.PENDING_FILE = os.path.join(self._tmp, "pending_qa.json")
        pending_qa.DB_PATH = os.path.join(self._tmp, "knowledge.db")
        store_mod.DB_PATH = os.path.join(self._tmp, "knowledge.db")
        store_mod._store = None
        # Clear thread-local connections
        if hasattr(store_mod._local, "conn"):
            store_mod._local.conn = None
        if hasattr(pending_qa._local, "conn"):
            pending_qa._local.conn = None

    def tearDown(self):
        pending_qa.PENDING_FILE = self._orig_file
        pending_qa.DB_PATH = self._orig_pqa_db
        store_mod.DB_PATH = self._orig_store_db
        store_mod._store = self._orig_store
        if hasattr(store_mod._local, "conn"):
            store_mod._local.conn = None
        if hasattr(pending_qa._local, "conn"):
            pending_qa._local.conn = None
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_add_pending_skips_empty(self):
        eid, status = pending_qa.add_pending("", "answer", [])
        self.assertEqual(status, "skipped")
        self.assertIsNone(eid)

        eid, status = pending_qa.add_pending("question", "", [])
        self.assertEqual(status, "skipped")

    @patch("knowledge.store.get_store")
    def test_add_pending_auto_approve(self, mock_get_store):
        mock_store = unittest.mock.MagicMock()
        mock_get_store.return_value = mock_store

        eid, status = pending_qa.add_pending(
            "美国留学费用",
            "美国留学一年的费用因学校和地区不同而有较大差异。公立大学约2-4万美元/年，私立大学约3-6万美元/年。生活费在大城市约1.5-2万美元/年。这是超过五十个字的回答。",
            [{"type": "kb", "category": "us-life", "title": "美国留学费用", "tags": ["费用", "美国"]}],
            auto_approve=True,
        )
        self.assertEqual(status, "approved")
        self.assertTrue(mock_store.add_entry.called)
        self.assertTrue(mock_store.save.called)

    @patch("knowledge.store.get_store")
    def test_add_pending_auto_approve_fails_then_pending(self, mock_get_store):
        mock_store = unittest.mock.MagicMock()
        mock_get_store.return_value = mock_store

        eid, status = pending_qa.add_pending(
            "太短的测试",
            "回答太短",
            [{"type": "kb", "category": "test", "title": "test"}],
            auto_approve=True,
        )
        self.assertEqual(status, "pending")
        self.assertIsNotNone(eid)

    def test_list_pending(self):
        pending_qa.add_pending("q1", "这是一段超过五十个字的回答用来测试pending列表。补充内容确保长度达标。",
                               [{"type": "kb", "title": "t"}], auto_approve=False)
        pending_qa.add_pending("q2", "这是一段超过五十个字的回答用来测试pending列表。补充内容确保长度达标。",
                               [{"type": "kb", "title": "t"}], auto_approve=False)
        items = pending_qa.list_pending()
        self.assertEqual(len(items), 2)

    def test_get_pending(self):
        eid, _ = pending_qa.add_pending("q", "这是一段超过五十个字的回答用来测试获取单个pending。补充内容确保长度达标。",
                                         [{"type": "kb", "title": "t"}], auto_approve=False)
        entry = pending_qa.get_pending(eid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["question"], "q")

    def test_get_pending_not_found(self):
        self.assertIsNone(pending_qa.get_pending("nonexistent"))

    def test_reject_pending(self):
        eid, _ = pending_qa.add_pending("q", "这是一段超过五十个字的回答用来测试拒绝功能。补充内容确保长度达标。",
                                         [{"type": "kb", "title": "t"}], auto_approve=False)
        self.assertTrue(pending_qa.reject_pending(eid))
        self.assertIsNone(pending_qa.get_pending(eid))

    def test_reject_nonexistent(self):
        self.assertFalse(pending_qa.reject_pending("nonexistent"))

    @patch("knowledge.store.get_store")
    def test_approve_pending(self, mock_get_store):
        mock_store = unittest.mock.MagicMock()
        mock_get_store.return_value = mock_store

        eid, _ = pending_qa.add_pending("q", "answer here with enough length to pass the minimum check for auto approval test.",
                                         [{"type": "kb", "title": "t"}], auto_approve=False)
        result = pending_qa.approve_pending(eid, {
            "title": "edited title",
            "category": "edited-cat",
            "tags": ["tag1"],
            "content": "edited content",
        })
        self.assertTrue(result)
        self.assertTrue(mock_store.add_entry.called)
        # Verify the store entry used the edits
        call_kwargs = mock_store.add_entry.call_args[0][0]
        self.assertEqual(call_kwargs["title"], "edited title")
        self.assertEqual(call_kwargs["category"], "edited-cat")
        self.assertEqual(call_kwargs["tags"], ["tag1"])

    @patch("knowledge.store.get_store")
    def test_approve_pending_not_found(self, mock_get_store):
        result = pending_qa.approve_pending("nonexistent", {})
        self.assertFalse(result)


class TestPendingFile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_db = store_mod.DB_PATH
        store_mod.DB_PATH = os.path.join(self._tmp, "knowledge.db")
        self._orig_pqa_db = pending_qa.DB_PATH
        pending_qa.DB_PATH = os.path.join(self._tmp, "knowledge.db")
        if hasattr(store_mod._local, "conn"):
            store_mod._local.conn = None
        if hasattr(pending_qa._local, "conn"):
            pending_qa._local.conn = None

    def tearDown(self):
        store_mod.DB_PATH = self._orig_db
        pending_qa.DB_PATH = self._orig_pqa_db
        if hasattr(store_mod._local, "conn"):
            store_mod._local.conn = None
        if hasattr(pending_qa._local, "conn"):
            pending_qa._local.conn = None
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_load_missing_file(self):
        """_load() returns [] when PENDING_FILE doesn't exist."""
        orig = pending_qa.PENDING_FILE
        pending_qa.PENDING_FILE = "/nonexistent/pending_qa.json"
        try:
            entries = pending_qa._load()
            self.assertEqual(entries, [])
        finally:
            pending_qa.PENDING_FILE = orig

    def test_load_invalid_json(self):
        orig = pending_qa.PENDING_FILE
        tmp = os.path.join(self._tmp, "pending_qa.json")
        pending_qa.PENDING_FILE = tmp
        try:
            with open(tmp, "w") as f:
                f.write("not json")
            entries = pending_qa._load()
            self.assertEqual(entries, [])
        finally:
            pending_qa.PENDING_FILE = orig


if __name__ == "__main__":
    unittest.main()
