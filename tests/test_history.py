"""Tests for knowledge/history.py"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import knowledge.history as history_mod
import knowledge.store as store_mod


class TestHistory(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_db = history_mod.DB_PATH
        self._orig_store_db = store_mod.DB_PATH
        history_mod.DB_PATH = os.path.join(self._tmp, "knowledge.db")
        store_mod.DB_PATH = os.path.join(self._tmp, "knowledge.db")
        if hasattr(history_mod._local, "conn"):
            history_mod._local.conn = None
        if hasattr(store_mod._local, "conn"):
            store_mod._local.conn = None

    def tearDown(self):
        history_mod.DB_PATH = self._orig_db
        store_mod.DB_PATH = self._orig_store_db
        if hasattr(history_mod._local, "conn"):
            history_mod._local.conn = None
        if hasattr(store_mod._local, "conn"):
            store_mod._local.conn = None
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_create_session(self):
        sid = history_mod.create_session("u-test")
        self.assertTrue(sid.startswith("s-"))

    def test_add_message(self):
        sid = history_mod.create_session("u-test")
        mid = history_mod.add_message(sid, "user", "hello")
        self.assertTrue(mid.startswith("m-"))

    def test_get_messages(self):
        sid = history_mod.create_session("u-test")
        history_mod.add_message(sid, "user", "你好")
        history_mod.add_message(sid, "assistant", "你好！有什么可以帮助你的？")
        msgs = history_mod.get_messages(sid)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[0]["content"], "你好")

    def test_get_sessions(self):
        history_mod.create_session("u-test")
        sessions = history_mod.get_sessions("u-test")
        self.assertEqual(len(sessions), 1)
        self.assertIn("id", sessions[0])
        self.assertIn("message_count", sessions[0])

    def test_get_recent_messages(self):
        uid = "u-recent-test"
        sid = history_mod.create_session(uid)
        history_mod.add_message(sid, "user", "q1")
        history_mod.add_message(sid, "assistant", "a1")
        history_mod.add_message(sid, "user", "q2")
        msgs = history_mod.get_recent_messages(uid, max_messages=10)
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[-1]["content"], "q2")  # newest last

    def test_get_or_create_current_session(self):
        uid = "u-session-test"
        s1 = history_mod.get_or_create_current_session(uid)
        self.assertIn("id", s1)
        # Same user should get same session
        s2 = history_mod.get_or_create_current_session(uid)
        self.assertEqual(s1["id"], s2["id"])

    def test_save_conversation(self):
        uid = "u-save-test"
        messages = [
            {"role": "user", "content": "第一个问题"},
            {"role": "assistant", "content": "第一个回答"},
            {"role": "user", "content": "第二个问题"},
            {"role": "assistant", "content": "第二个回答"},
        ]
        sid = history_mod.save_conversation(uid, messages)
        self.assertTrue(sid.startswith("s-"))
        msgs = history_mod.get_messages(sid)
        self.assertEqual(len(msgs), 4)

    def test_save_conversation_append_only_new(self):
        uid = "u-append-test"
        history_mod.save_conversation(uid, [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
        ])
        # Save again with additional messages
        history_mod.save_conversation(uid, [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
        ])
        sid = history_mod.get_or_create_current_session(uid)
        msgs = history_mod.get_messages(sid["id"])
        self.assertEqual(len(msgs), 4)

    def test_empty_messages(self):
        uid = "u-empty"
        sid = history_mod.save_conversation(uid, [])
        self.assertTrue(sid.startswith("s-"))


if __name__ == "__main__":
    unittest.main()
