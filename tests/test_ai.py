"""Tests for knowledge/ai.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from knowledge.ai import (
    _query_needs_web_search, build_system_prompt,
    _build_context, SCHOOL_KEYWORDS,
)


class TestQueryNeedsWebSearch(unittest.TestCase):
    def test_school_query(self):
        self.assertTrue(_query_needs_web_search("美国大学学费多少"))
        self.assertTrue(_query_needs_web_search("MIT计算机专业排名"))
        self.assertTrue(_query_needs_web_search("英国G5大学申请要求"))

    def test_general_query(self):
        self.assertFalse(_query_needs_web_search("你好"))
        self.assertFalse(_query_needs_web_search("如何提高学习效率"))
        self.assertFalse(_query_needs_web_search("留学值不值得"))

    def test_case_insensitive(self):
        self.assertTrue(_query_needs_web_search("UCLA Admission requirements"))
        self.assertTrue(_query_needs_web_search("gpa 3.5 能申请什么学校"))


class TestBuildSystemPrompt(unittest.TestCase):
    def test_contains_key_elements(self):
        prompt = build_system_prompt()
        self.assertIn("留学生课业规划", prompt)
        self.assertIn("学管", prompt, "system prompt should mention 学管 service")

    def test_contains_rules(self):
        prompt = build_system_prompt()
        self.assertIn("【案例库】", prompt)
        self.assertIn("【网络搜索】", prompt)
        self.assertIn("同理心", prompt)


class TestBuildContext(unittest.TestCase):
    def test_kb_only(self):
        context = _build_context("选课建议", [
            {"entry": {"title": "选课策略", "content": "建议优先选必修课", "category": "course"}}
        ])
        self.assertIn("【案例库】", context)
        self.assertIn("选课策略", context)
        self.assertIn("选课建议", context)
        # Web section only appears when web results present
        self.assertNotIn("网络搜索结果", context)

    def test_kb_and_web(self):
        context = _build_context("学校申请", [
            {"entry": {"title": "申请流程", "content": "先提交材料", "category": "apply"}}
        ], web_results=[
            {"title": "大学官网", "url": "https://example.com", "snippet": "最新申请要求"}
        ])
        self.assertIn("【案例库】", context)
        self.assertIn("网络搜索结果", context)
        self.assertIn("大学官网", context)

    def test_no_kb_results(self):
        context = _build_context("罕见问题", [])
        self.assertIn("未找到直接相关的案例", context)

    def test_web_search_empty(self):
        context = _build_context("test", [
            {"entry": {"title": "t", "content": "c", "category": "g"}}
        ], web_results=[])
        self.assertNotIn("网络搜索结果", context)


class TestSchoolKeywords(unittest.TestCase):
    def test_keywords_are_strings(self):
        for kw in SCHOOL_KEYWORDS:
            self.assertIsInstance(kw, str)
            self.assertGreater(len(kw), 0)


if __name__ == "__main__":
    unittest.main()
