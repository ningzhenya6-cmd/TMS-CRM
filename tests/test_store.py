"""Tests for knowledge/store.py"""
import os
import sys
import tempfile
import unittest
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import knowledge.store as store_mod
from knowledge.store import KnowledgeStore, _tokenize


class TestTokenize(unittest.TestCase):
    def test_chinese_unigram(self):
        tokens = _tokenize("学")
        self.assertIn("学", tokens)

    def test_chinese_bigram(self):
        tokens = _tokenize("留学")
        self.assertIn("留学", tokens)

    def test_chinese_trigram(self):
        tokens = _tokenize("留学生")
        self.assertIn("留学", tokens)
        self.assertIn("学生", tokens)

    def test_english_word(self):
        tokens = _tokenize("computer science")
        self.assertIn("computer", tokens)
        self.assertIn("science", tokens)

    def test_mixed(self):
        tokens = _tokenize("GPA 3.5 申请美国")
        self.assertIn("gpa", tokens)
        self.assertIn("申请", tokens)

    def test_empty(self):
        self.assertEqual(_tokenize(""), [])


class TestKnowledgeStore(unittest.TestCase):
    def setUp(self):
        # Use temp dir for SQLite DB and JSON migration
        self.temp_dir = tempfile.mkdtemp()
        self._orig_db_path = store_mod.DB_PATH
        self._orig_kb_file = store_mod.KB_FILE
        self._orig_store = store_mod._store
        store_mod.DB_PATH = os.path.join(self.temp_dir, "knowledge.db")
        store_mod.KB_FILE = os.path.join(self.temp_dir, "kb.json")
        store_mod._store = None
        # Clear thread-local connection
        import knowledge.store as s
        if hasattr(s._local, "conn"):
            s._local.conn = None
        self.store = KnowledgeStore()

    def tearDown(self):
        store_mod.DB_PATH = self._orig_db_path
        store_mod.KB_FILE = self._orig_kb_file
        store_mod._store = self._orig_store
        # Clear thread-local connection
        if hasattr(store_mod._local, "conn"):
            store_mod._local.conn = None
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _add_demo_entry(self):
        self.store.add_entry({
            "title": "美国选课策略",
            "content": "美国大学选课建议优先满足专业必修课，再选通识课程。每学期建议选4-5门课。",
            "category": "course-selection",
            "tags": ["选课", "美国"],
        })

    def test_add_entry(self):
        eid = self.store.add_entry({
            "title": "测试条目",
            "content": "测试内容",
        })
        self.assertIsNotNone(eid)
        self.assertTrue(eid.startswith("kb-"))
        self.assertEqual(len(self.store.entries), 1)

    def test_search_found(self):
        self._add_demo_entry()
        results = self.store.search("选课策略", top_k=5)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0][0]["title"], "美国选课策略")

    def test_search_no_match(self):
        self._add_demo_entry()
        results = self.store.search("xyz_not_exist_12345", top_k=5)
        self.assertEqual(len(results), 0)

    def test_search_empty_query(self):
        results = self.store.search("", top_k=5)
        self.assertEqual(results, [])

    def test_delete_entry(self):
        eid = self.store.add_entry({"title": "del", "content": "x"})
        self.store.delete_entry(eid)
        self.assertIsNone(self.store.get_entry(eid))

    def test_update_entry(self):
        eid = self.store.add_entry({"title": "old", "content": "x"})
        self.store.update_entry(eid, {"title": "new"})
        self.assertEqual(self.store.get_entry(eid)["title"], "new")

    def test_get_all_entries(self):
        self._add_demo_entry()
        entries = self.store.get_all_entries()
        self.assertEqual(len(entries), 1)

    def test_get_categories(self):
        self._add_demo_entry()
        cats = self.store.get_categories()
        self.assertIn("course-selection", cats)

    def test_get_stats(self):
        self._add_demo_entry()
        stats = self.store.get_stats()
        self.assertIn("total", stats)
        self.assertIn("active", stats)
        self.assertEqual(stats["total"], 1)

    def test_save_and_reload(self):
        self._add_demo_entry()
        self.store.save()
        # Create new store instance that loads from same file
        import knowledge.store as mod
        mod._store = None
        store2 = KnowledgeStore()
        self.assertEqual(len(store2.entries), 1)

    def test_add_entries_bulk(self):
        entries = [
            {"title": f"条目{i}", "content": "x"} for i in range(5)
        ]
        self.store.add_entries(entries)
        self.assertEqual(len(self.store.entries), 5)

    def test_delete_nonexistent(self):
        # Should not raise
        self.store.delete_entry("nonexistent")
        self.assertEqual(len(self.store.entries), 0)

    def test_get_nonexistent(self):
        self.assertIsNone(self.store.get_entry("nonexistent"))

    def test_inactive_not_returned_in_search(self):
        eid = self.store.add_entry({"title": "active content", "content": "searchable text here"})
        # Search should find it
        results = self.store.search("searchable text", top_k=5)
        self.assertGreater(len(results), 0)
        # Deactivate
        self.store.update_entry(eid, {"is_active": False})
        results2 = self.store.search("searchable text", top_k=5)
        self.assertEqual(len(results2), 0)


if __name__ == "__main__":
    unittest.main()
