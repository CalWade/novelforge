"""Pipeline flag-gating: CastUpdater runs only when setting.cast_tracking_enabled=true.

Mocks every agent at the class level on src.pipeline so the test never
touches real LLM. Verifies the pipeline branches on `setting.yaml` flag.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src import pipeline
from src.blackboard import Blackboard


def _make_bb(tmp_path: Path, *, cast_flag: bool) -> Blackboard:
    """Seed a tmp blackboard with the minimum files run_chapter needs."""
    bb = Blackboard(root=tmp_path)
    setting = {"genre": "g", "era": "e", "chapter_count_target": 3}
    if cast_flag:
        setting["cast_tracking_enabled"] = True
    bb.write_yaml("setting.yaml", setting)
    bb.write_json("outline.json", {
        "title": "x",
        "chapters": [
            {"ch": 1, "title": "ch1", "beats": []},
            {"ch": 2, "title": "ch2", "beats": []},
            {"ch": 3, "title": "ch3", "beats": []},
        ],
    })
    bb.write_json("progress.json", {
        "completed_chapters": [],
        "current_chapter": 0,
        "total_llm_calls": 0,
    })
    bb.write_yaml("characters.yaml", {"protagonist": {"name": "x"}})
    bb.write_yaml("timeline.yaml", {"events": []})
    (tmp_path / "chapters").mkdir(exist_ok=True)
    (tmp_path / "summaries").mkdir(exist_ok=True)
    (tmp_path / "fixes").mkdir(exist_ok=True)
    return bb


def _passing_evaluator_factory(bb: Blackboard, chapter: int = 1):
    """Generate an Evaluator mock that writes a passing verdict.json to bb."""
    def fake_run(*_args, **_kwargs):
        ch = _kwargs.get("chapter", chapter)
        bb.write_json(
            f"chapters/ch{ch:03d}.verdict.json",
            {"overall_pass": True, "landmines": {}, "top_3_fixes": []},
        )
    return fake_run


def _all_agent_patches(bb: Blackboard):
    """Patch every agent class on src.pipeline to a MagicMock instance.

    Returns (patches, mocks) where mocks is a dict[name -> MagicMock]
    so the test can assert call counts.
    """
    names = [
        "Planner", "Generator", "Evaluator", "Fixer", "Summarizer",
        "StatusCardUpdater", "CastUpdater", "HookKeeper",
        "ArcSummarizer", "BookSummarizer",
        "AISlopGuard", "CharacterGuard",
    ]
    mocks: dict[str, MagicMock] = {}
    patches: list = []
    for n in names:
        m = MagicMock()
        instance = MagicMock()
        if n == "Evaluator":
            instance.run.side_effect = _passing_evaluator_factory(bb)
        else:
            instance.run.return_value = None
        m.return_value = instance
        mocks[n] = m
        p = patch(f"src.pipeline.{n}", m)
        patches.append(p)
    # setting_has_resource_schema returns False so ResourceLedger doesn't run
    p2 = patch("src.pipeline.setting_has_resource_schema", return_value=False)
    patches.append(p2)
    # FactChecker should_run returns False
    p3 = patch("src.pipeline.fact_checker_should_run", return_value=False)
    patches.append(p3)
    return patches, mocks


def test_pipeline_skips_cast_updater_when_flag_disabled(tmp_path):
    bb = _make_bb(tmp_path, cast_flag=False)
    patches, mocks = _all_agent_patches(bb)
    for p in patches:
        p.start()
    try:
        pipeline.run_chapter(bb, chapter=1)
    finally:
        for p in patches:
            p.stop()
    # CastUpdater class was NOT instantiated (zero calls)
    mocks["CastUpdater"].assert_not_called()
    # StatusCard / HookKeeper still ran (sanity)
    mocks["StatusCardUpdater"].assert_called()
    mocks["HookKeeper"].assert_called()


def test_pipeline_runs_cast_updater_when_flag_enabled(tmp_path):
    bb = _make_bb(tmp_path, cast_flag=True)
    patches, mocks = _all_agent_patches(bb)
    for p in patches:
        p.start()
    try:
        pipeline.run_chapter(bb, chapter=1)
    finally:
        for p in patches:
            p.stop()
    # CastUpdater was instantiated AND its run() invoked
    mocks["CastUpdater"].assert_called()  # constructor
    instance = mocks["CastUpdater"].return_value
    instance.run.assert_called_once()
    # And it received chapter kwarg
    _, kwargs = instance.run.call_args
    assert kwargs.get("chapter") == 1
