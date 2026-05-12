"""Backward-compat shim — Blackboard moved to src/core/blackboard.py on 2026-05-11.

Existing imports like `from src.blackboard import Blackboard, bb` keep working
via the re-exports below. New code should import from src.core.blackboard.

The `os` module is also re-exported at module level because one existing test
(tests/test_blackboard.py::test_atomic_write_no_partial_on_failure) monkey-patches
`src.blackboard.os.replace`. Removing this would break a passing test.
"""
from .core.blackboard import Blackboard, bb  # noqa: F401
from .core import blackboard as _core_bb
os = _core_bb.os  # noqa: F401  # re-export for monkeypatch compatibility
