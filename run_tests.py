#!/usr/bin/env python3
"""Test runner - runs all tests using stdlib unittest."""
import os
import sys
import unittest

test_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, test_dir)

loader = unittest.TestLoader()
suite = unittest.TestSuite()

# Discover all tests in tests/ directory
tests = loader.discover(os.path.join(test_dir, "tests"), pattern="test_*.py")
suite.addTests(tests)

runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
