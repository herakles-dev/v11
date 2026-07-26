"""Tests for math_utils — ground truth for benchmark validation."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from math_utils import add, multiply


def test_add():
    assert add(2, 3) == 5


def test_add_negative():
    assert add(-1, 1) == 0


def test_multiply():
    assert multiply(3, 4) == 12
