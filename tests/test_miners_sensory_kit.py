"""SensoryKitMiner — 单元测试（Python 侧逻辑，LLM 用 monkeypatch 打桩）."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def fake_book(tmp_path, monkeypatch):
    """Create projects/<book>/state/chapters/ 含 2 章 plan+md 的 fixture."""
    from src import config
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    book_dir = tmp_path / "projects" / "demo-book"
    chapters_dir = book_dir / "state" / "chapters"
    chapters_dir.mkdir(parents=True)

    # Plan 1: 九龙城寨 出现 2 次，油麻地 出现 1 次
    plan1 = {
        "ch": 1,
        "scenes": [
            {"scene_id": 1, "location": "九龙城寨 · 东头村道口"},
            {"scene_id": 2, "location": "九龙城寨 · 大排档"},
            {"scene_id": 3, "location": "油麻地 · 果栏"},
        ],
    }
    (chapters_dir / "ch001.plan.json").write_text(
        json.dumps(plan1, ensure_ascii=False), encoding="utf-8",
    )
    # Plan 2: 九龙城寨 再 1 次
    plan2 = {
        "ch": 2,
        "scenes": [
            {"scene_id": 1, "location": "九龙城寨"},
        ],
    }
    (chapters_dir / "ch002.plan.json").write_text(
        json.dumps(plan2, ensure_ascii=False), encoding="utf-8",
    )
    # 对应正文，含 location 关键词
    (chapters_dir / "ch001.md").write_text(
        "# 第一章\n\n"
        "林家耀走进九龙城寨，铁皮檐上锈水痕。\n\n"
        "大排档飘来柱侯牛腩味，混着沟渠的腐臭。冷气机滴水声不绝。\n\n"
        "（其他无关段落）天气晴朗。\n\n"
        "油麻地的果栏凌晨三点最繁忙。\n",
        encoding="utf-8",
    )
    (chapters_dir / "ch002.md").write_text(
        "# 第二章\n\n"
        "九龙城寨又一次出现，碱水云吞面的香气和潮湿水泥墙的触感。\n",
        encoding="utf-8",
    )
    return book_dir


def test_collect_locations_dedupes_and_counts(fake_book):
    from src.genre_extractor.miners.sensory_kit import (
        _collect_locations_from_plans,
    )
    counts = _collect_locations_from_plans(fake_book / "state" / "chapters")
    # 九龙城寨 3 次（跨 plan1 的两条 + plan2 的一条，都归到主地名）
    assert counts["九龙城寨"] == 3
    assert counts["油麻地"] == 1


def test_extract_excerpts_finds_relevant_paragraphs(fake_book):
    from src.genre_extractor.miners.sensory_kit import (
        _extract_excerpts,
        _load_all_chapter_texts,
    )
    texts = _load_all_chapter_texts(fake_book / "state" / "chapters")
    excerpts = _extract_excerpts("九龙城寨", texts)
    # 至少抽到了含"九龙城寨"的段落
    assert len(excerpts) >= 2
    assert all("九龙城寨" in e for e in excerpts)
    # "天气晴朗" 不含地名，不应被抽
    assert not any("天气晴朗" in e for e in excerpts)


def test_extract_excerpts_skips_duplicates(fake_book):
    from src.genre_extractor.miners.sensory_kit import (
        _extract_excerpts,
        _load_all_chapter_texts,
    )
    # 手工追加完全重复段落
    ch3 = fake_book / "state" / "chapters" / "ch003.md"
    ch3.write_text(
        "林家耀走进九龙城寨，铁皮檐上锈水痕。\n",  # 与 ch001 某段前缀相同
        encoding="utf-8",
    )
    texts = _load_all_chapter_texts(fake_book / "state" / "chapters")
    excerpts = _extract_excerpts("九龙城寨", texts)
    # 去重基于前 200 字的 hash，这条重复应被跳过
    hashes = {e.partition("\n")[2][:200] for e in excerpts}
    assert len(hashes) == len(excerpts)


def test_parse_llm_output_handles_code_fences():
    from src.genre_extractor.miners.sensory_kit import _parse_llm_output
    fenced = '```json\n{"visual": ["x"]}\n```'
    assert _parse_llm_output(fenced) == {"visual": ["x"]}


def test_parse_llm_output_bad_json_returns_none():
    from src.genre_extractor.miners.sensory_kit import _parse_llm_output
    assert _parse_llm_output("not json") is None
    assert _parse_llm_output("") is None


def test_mine_end_to_end_writes_yaml(fake_book, monkeypatch):
    """Full run, LLM stubbed."""
    from src.genre_extractor.miners import sensory_kit as mod

    # Stub LLM：按 location 给不同回复
    def fake_chat(*, system, user, agent_name, **_):
        assert agent_name == "sensory_kit_miner"
        if "九龙城寨" in user:
            return json.dumps({
                "visual": ["铁皮檐锈水痕", "冷气机密密麻麻"],
                "auditory": ["冷气机滴水声"],
                "olfactory": ["沟渠腐臭", "大排档镬气"],
                "tactile": ["潮湿水泥墙"],
                "gustatory": ["柱侯牛腩", "碱水云吞面"],
            }, ensure_ascii=False)
        if "油麻地" in user:
            return json.dumps({
                "visual": ["果栏灯光黄"],
                "auditory": ["拖板车木轮声"],
                "olfactory": ["腐果汽油"],
                "tactile": [],
                "gustatory": [],
            }, ensure_ascii=False)
        return "{}"

    monkeypatch.setattr(mod.llm, "chat", fake_chat)

    out_path = mod.mine_sensory_kit("demo-book", top_n=5)
    assert out_path.exists()
    data = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert "九龙城寨" in data["locations"]
    assert "油麻地" in data["locations"]
    klcz = data["locations"]["九龙城寨"]
    assert "铁皮檐锈水痕" in klcz["visual"]
    assert "柱侯牛腩" in klcz["gustatory"]
    # 油麻地 tactile/gustatory 空，应被过滤掉
    ymd = data["locations"]["油麻地"]
    assert "tactile" not in ymd or ymd["tactile"] == []
    assert "gustatory" not in ymd or ymd["gustatory"] == []


def test_mine_raises_when_no_chapters(tmp_path, monkeypatch):
    from src import config
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    (tmp_path / "projects" / "empty-book" / "state" / "chapters").mkdir(parents=True)
    from src.genre_extractor.miners.sensory_kit import mine_sensory_kit
    with pytest.raises(RuntimeError, match="scene locations"):
        mine_sensory_kit("empty-book")


def test_mine_raises_when_project_missing(tmp_path, monkeypatch):
    from src import config
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    from src.genre_extractor.miners.sensory_kit import mine_sensory_kit
    with pytest.raises(FileNotFoundError):
        mine_sensory_kit("ghost-book")


def test_mine_filters_overlong_items(fake_book, monkeypatch):
    """LLM 返回过长条目（>30字）应被清洗掉."""
    from src.genre_extractor.miners import sensory_kit as mod

    def fake_chat(**_):
        return json.dumps({
            "visual": [
                "x",  # too short but we didn't add min-len check; accepted
                "铁皮檐锈水痕",
                "这条是一整段句子不符合词组规范因为它超过了三十字限制应当被清洗掉的",
            ],
            "auditory": [], "olfactory": [], "tactile": [], "gustatory": [],
        }, ensure_ascii=False)

    monkeypatch.setattr(mod.llm, "chat", fake_chat)
    out = mod.mine_sensory_kit("demo-book", top_n=2)
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    for items in data["locations"].values():
        for key in ("visual",):
            if key in items:
                assert all(len(x) <= 30 for x in items[key])
