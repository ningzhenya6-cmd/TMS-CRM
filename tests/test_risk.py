"""Tests for knowledge/risk.py"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from knowledge.risk import (
    check_sensitive, BLOCKED_RESPONSES, DEFAULT_BLOCKED,
    RateLimiter, HealthTracker,
)


class TestCheckSensitive(unittest.TestCase):
    def test_normal_query_passes(self):
        is_s, cat, matched = check_sensitive("美国大学选课需要注意什么")
        self.assertFalse(is_s)
        self.assertEqual(cat, "")
        self.assertEqual(matched, "")

    def test_empty_text(self):
        is_s, cat, matched = check_sensitive("")
        self.assertFalse(is_s)

    def test_none_text(self):
        is_s, cat, matched = check_sensitive(None)
        self.assertFalse(is_s)

    def test_academic_dishonesty(self):
        is_s, cat, matched = check_sensitive("能帮我代写作业吗")
        self.assertTrue(is_s)
        self.assertEqual(cat, "academic_dishonesty")
        self.assertIn("代写", matched)

    def test_self_harm(self):
        is_s, cat, matched = check_sensitive("我不想活了")
        self.assertTrue(is_s)
        self.assertEqual(cat, "self_harm")

    def test_self_harm_variants(self):
        for term in ["轻生", "自尽", "活不下去"]:
            is_s, cat, _ = check_sensitive(term)
            self.assertTrue(is_s, f"{term} should be detected")
            self.assertEqual(cat, "self_harm")

    def test_academic_crisis(self):
        tests = [
            ("被学校退学怎么办", "退学"),
            ("劝退", "劝退"),
            ("被开除了", "开除"),
            ("挂科太多面临学业警告", "学业警告"),
        ]
        for text, expected_match in tests:
            is_s, cat, matched = check_sensitive(text)
            self.assertTrue(is_s, f"{text} should be detected")
            self.assertEqual(cat, "academic_crisis", f"{text} should be academic_crisis")

    def test_political_sensitive(self):
        tests = ["六四", "法轮功", "台独", "疆独", "藏独", "港独"]
        for text in tests:
            is_s, cat, _ = check_sensitive(text)
            self.assertTrue(is_s, f"{text} should be detected")
            self.assertEqual(cat, "political_sensitive")

    def test_harassment_drugs(self):
        tests = ["吸毒", "大麻", "冰毒", "摇头丸"]
        for text in tests:
            is_s, cat, _ = check_sensitive(text)
            self.assertTrue(is_s, f"{text} should be detected")
            self.assertEqual(cat, "harassment")

    def test_illegal(self):
        tests = ["签证欺诈", "洗钱", "伪造学历", "假结婚"]
        for text in tests:
            is_s, cat, _ = check_sensitive(text)
            self.assertTrue(is_s, f"{text} should be detected")
            self.assertEqual(cat, "illegal")

    def test_all_categories_have_blocked_response(self):
        """Every sensitive category must have a corresponding blocked response."""
        from knowledge.risk import SENSITIVE_PATTERNS
        for category in SENSITIVE_PATTERNS:
            self.assertIn(category, BLOCKED_RESPONSES,
                          f"{category} missing from BLOCKED_RESPONSES")

    def test_blocked_responses_not_empty(self):
        for cat, msg in BLOCKED_RESPONSES.items():
            self.assertGreater(len(msg), 20, f"{cat} response too short")


class TestRateLimiter(unittest.TestCase):
    def setUp(self):
        self.limiter = RateLimiter(max_requests=5, window_seconds=60)

    def test_allows_within_limit(self):
        for _ in range(5):
            allowed, remaining, _ = self.limiter.check("test-ip")
            self.assertTrue(allowed)
        self.assertEqual(remaining, 0)

    def test_blocks_over_limit(self):
        for _ in range(5):
            self.limiter.check("test-ip")
        allowed, remaining, reset = self.limiter.check("test-ip")
        self.assertFalse(allowed)
        self.assertEqual(remaining, 0)
        self.assertGreater(reset, 0)

    def test_different_ips_independent(self):
        for _ in range(5):
            self.limiter.check("ip-a")
        allowed, _, _ = self.limiter.check("ip-b")
        self.assertTrue(allowed)

    def test_window_slides(self):
        tight = RateLimiter(max_requests=2, window_seconds=1)
        tight.check("ip")
        tight.check("ip")
        allowed, _, _ = tight.check("ip")
        self.assertFalse(allowed)
        time.sleep(1.1)
        allowed, _, _ = tight.check("ip")
        self.assertTrue(allowed)


class TestHealthTracker(unittest.TestCase):
    def setUp(self):
        self.health = HealthTracker()

    def test_initial_state(self):
        s = self.health.status()
        self.assertEqual(s["status"], "ok")
        self.assertEqual(s["total_requests"], 0)
        self.assertEqual(s["blocked_requests"], 0)

    def test_record_request(self):
        self.health.record_request()
        s = self.health.status()
        self.assertEqual(s["total_requests"], 1)

    def test_record_blocked(self):
        self.health.record_request(blocked=True)
        s = self.health.status()
        self.assertEqual(s["total_requests"], 1)
        self.assertEqual(s["blocked_requests"], 1)

    def test_block_rate(self):
        for _ in range(3):
            self.health.record_request()
        self.health.record_request(blocked=True)
        s = self.health.status()
        self.assertEqual(s["block_rate_pct"], 25.0)

    def test_record_error(self):
        self.health.record_error("test error")
        s = self.health.status()
        self.assertEqual(len(s["recent_errors"]), 1)
        self.assertIn("test error", s["recent_errors"][0]["msg"])

    def test_uptime_increases(self):
        s1 = self.health.status()
        time.sleep(0.01)
        s2 = self.health.status()
        self.assertGreaterEqual(s2["uptime"], s1["uptime"])

    def test_errors_truncated(self):
        for i in range(150):
            self.health.record_error(f"error {i}")
        s = self.health.status()
        self.assertLessEqual(len(s["recent_errors"]), 10)

    def test_zero_requests_block_rate(self):
        s = self.health.status()
        self.assertEqual(s["block_rate_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
