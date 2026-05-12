"""向后兼容 shim 保护：即使 Blackboard / BaseAgent 搬到了 src/core/，
旧导入路径必须继续工作。
"""
from pathlib import Path

import pytest


def test_legacy_blackboard_import_still_works():
    """from src.blackboard import Blackboard 必须能用。"""
    from src.blackboard import Blackboard  # noqa: F401
    assert Blackboard is not None


def test_legacy_blackboard_module_instance_still_works():
    from src.blackboard import bb
    assert bb is not None


def test_core_and_shim_are_same_class():
    """shim 必须 re-export 同一个 class object，不是两个不同的类。"""
    from src.blackboard import Blackboard as Shim
    from src.core.blackboard import Blackboard as Core
    assert Shim is Core


def test_blackboard_still_works_after_move(tmp_path: Path):
    from src.core.blackboard import Blackboard
    bb = Blackboard(root=tmp_path)
    bb.write_text("x.txt", "hi")
    assert bb.read_text("x.txt") == "hi"
