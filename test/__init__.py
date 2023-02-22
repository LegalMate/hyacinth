"""Provides hyacinth test suite."""
import unittest


def run():
    """Run hyacinth test suite."""
    loader = unittest.TestLoader()
    tests = loader.discover(".")
    runner = unittest.runner.TextTestRunner()
    runner.run(tests)
