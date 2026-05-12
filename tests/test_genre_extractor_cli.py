"""CLI dispatch for `python -m src.genre_extractor`."""
from __future__ import annotations

import pytest


def test_parser_accepts_to_preset():
    from src.genre_extractor.__main__ import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["--to-preset", "myp", "--sources", "a.txt,b.txt"])
    assert args.to_preset == "myp"
    assert args.sources == "a.txt,b.txt"


def test_parser_rejects_both_to_preset_and_audit():
    from src.genre_extractor.__main__ import _build_parser
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--to-preset", "a", "--audit-preset", "b"])


def test_parser_has_phase_rerun_flags():
    from src.genre_extractor.__main__ import _build_parser
    parser = _build_parser()
    for flag in ("--extract-only", "--merge-only", "--draft-only", "--validate-only"):
        args = parser.parse_args([flag, "myp"])
        # Exactly one of the mutex group should be set
        assert getattr(args, flag.lstrip("-").replace("-", "_")) == "myp"


def test_main_dispatches_to_preset(monkeypatch, capsys):
    captured = {}
    def fake(preset_id, *, sources, with_trial):
        captured.update(preset_id=preset_id, sources=sources, with_trial=with_trial)
        return {"preset_id": preset_id}
    monkeypatch.setattr("src.genre_extractor.to_preset.extract_to_preset", fake)
    monkeypatch.setattr("sys.argv", ["prog", "--to-preset", "myp", "--sources", "a.txt,b.txt"])
    from src.genre_extractor.__main__ import main
    assert main() == 0
    assert captured["preset_id"] == "myp"
    assert captured["sources"] == ["a.txt", "b.txt"]


def test_main_dispatches_fill_preset(monkeypatch):
    called = {}
    monkeypatch.setattr(
        "src.genre_extractor.pipeline.fill_preset",
        lambda pid: called.setdefault("pid", pid) or {"preset_id": pid},
    )
    monkeypatch.setattr("sys.argv", ["prog", "--fill-preset", "myp"])
    from src.genre_extractor.__main__ import main
    assert main() == 0
    assert called["pid"] == "myp"


def test_main_dispatches_audit_preset(monkeypatch):
    called = {}
    monkeypatch.setattr(
        "src.genre_extractor.pipeline.audit_preset",
        lambda pid: called.setdefault("pid", pid) or {"preset_id": pid},
    )
    monkeypatch.setattr("sys.argv", ["prog", "--audit-preset", "myp"])
    from src.genre_extractor.__main__ import main
    assert main() == 0
    assert called["pid"] == "myp"


def test_main_requires_sources_for_to_preset(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["prog", "--to-preset", "myp"])
    from src.genre_extractor.__main__ import main
    assert main() == 2
    err = capsys.readouterr().err
    assert "sources" in err.lower()
