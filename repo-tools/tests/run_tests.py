#!/usr/bin/env python3
import unittest
import os
import sys
from pathlib import Path

# Add repo-tools to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Discover and run all tests
if __name__ == '__main__':
    # Locate the tests directory
    tests_dir = os.path.dirname(os.path.abspath(__file__))

    # Discover tests and run them
    test_suite = unittest.defaultTestLoader.discover(tests_dir, pattern='test_*.py')
    test_runner = unittest.TextTestRunner(verbosity=2)
    result = test_runner.run(test_suite)

    # Set exit code based on test results
    sys.exit(not result.wasSuccessful())
