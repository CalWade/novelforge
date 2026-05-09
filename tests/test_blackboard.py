"""Tests for blackboard filesystem API."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.blackboard import Blackboard


@pytest.fixture
def bb(tmp_path: Path) -> Blackboard:
    return Blackboard(root=tmp_path)


def test_text_roundtrip(bb: Blackboard):
    bb.write_text("hello.txt", "你好")
    assert bb.read_text("hello.txt") == "你好"


def test_json_roundtrip(bb: Blackboard):
    obj = {"a": 1, "nested": {"list": [1, 2, 3]}, "中文": "港综"}
    bb.write_json("x.json", obj)
    assert bb.read_json("x.json") == obj


def test_yaml_roundtrip(bb: Blackboard):
    obj = {"characters": [{"name": "林家耀", "age": 22}]}
    bb.write_yaml("chars.yaml", obj)
    assert bb.read_yaml("chars.yaml") == obj


def test_jsonl_order_and_append(bb: Blackboard):
    for i in range(5):
        bb.append_jsonl("log.jsonl", {"i": i})
    items = bb.read_jsonl("log.jsonl")
    assert [x["i"] for x in items] == [0, 1, 2, 3, 4]


def test_atomic_write_no_partial_on_failure(bb: Blackboard, monkeypatch):
    """If write fails mid-way, the original file must remain intact."""
    bb.write_text("safe.txt", "original")
    # Monkeypatch os.replace to raise so we simulate a crash after fdopen.write
    import src.blackboard as bbmod

    original_replace = bbmod.os.replace

    def boom(src, dst):
        # Simulate partial failure — the tmp file exists but replace fails
        raise OSError("disk full")

    monkeypatch.setattr(bbmod.os, "replace", boom)
    with pytest.raises(OSError):
        bb.write_text("safe.txt", "new content")

    # Original should still be readable and intact
    monkeypatch.setattr(bbmod.os, "replace", original_replace)
    assert bb.read_text("safe.txt") == "original"


def test_list_files(bb: Blackboard):
    for n in ("ch001.md", "ch002.md", "notes.txt"):
        bb.write_text(f"chapters/{n}", "x")
    md_files = bb.list_files("chapters", "*.md")
    assert [p.name for p in md_files] == ["ch001.md", "ch002.md"]
