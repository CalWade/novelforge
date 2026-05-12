"""Web upload — encoding detection + UTF-8 normalisation.

The novels/ library accepts source material in whatever encoding the user
happened to have locally (GB18030 for simplified-Chinese web novels, Big5
for traditional Chinese, Shift-JIS for Japanese imports, …). Everything
downstream (ChapterStream, Extractor, LLM prompts) expects UTF-8, so we
normalise on the way in and keep one invariant on disk:

    every file under novels/*.txt is UTF-8, always.

These tests pin that invariant by actually constructing raw byte streams
with e.g. '某某港综'.encode('gbk') and asserting round-trip equality —
no mocks, no hand-waving about "if charset_normalizer said so".
"""
from __future__ import annotations

import io
import os

import pytest

from web.app import app, _normalize_to_utf8


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def tmp_novels(tmp_path, monkeypatch):
    novels = tmp_path / "novels"
    novels.mkdir()
    from web import app as webapp_mod
    monkeypatch.setattr(webapp_mod, "NOVELS_DIR", novels)
    yield novels


def _file_arg(name: str, content: bytes):
    return (io.BytesIO(content), name)


# A long enough sample that charset_normalizer has signal to work with.
# The short-sample bug (小 sample mis-detected as cp949 / EUC-KR) is a known
# gotcha with Chinese detection — realistic novel uploads are never 40 bytes.
_GBK_SAMPLE_TEXT = (
    "某某港综·林家耀 第1章 起\n"
    "他在九龙的夜市里转身，霓虹灯打在脸上，霓虹汗味兄弟情。\n"
    "第2章 承\n"
    "阿耀蹲在唐楼天台抽烟，远处的维港船笛拉得很长。\n"
) * 30

_BIG5_SAMPLE_TEXT = (
    "林家耀港漫 第一章\n"
    "他在九龍的夜市裡轉身，霓虹燈打在臉上，霓虹汗味兄弟情。\n"
    "第二章\n"
    "阿耀蹲在唐樓天台抽煙，遠處的維港船笛拉得很長。\n"
) * 30

_SHIFT_JIS_SAMPLE_TEXT = (
    "第一章\n"
    "渋谷の夜に彼は立っていた。ネオンの雨が静かに降り注いでいた。\n"
    "第二章\n"
    "居酒屋で友と語らう。ウイスキーのロックが溶けていく。\n"
) * 30


# ---------------------------------------------------------------------------
# _normalize_to_utf8 — pure-function tests
# ---------------------------------------------------------------------------

def test_normalize_utf8_plain_returns_unchanged():
    """UTF-8 input must be the fast path: zero copies, normalized=False."""
    text = _GBK_SAMPLE_TEXT  # any text — we encode as utf-8 here
    raw = text.encode("utf-8")
    out_bytes, info = _normalize_to_utf8(raw)
    assert out_bytes is raw or out_bytes == raw, "UTF-8 input should pass through untouched"
    assert info["normalized"] is False
    # Accept either 'utf_8' or 'utf-8' — charset_normalizer uses underscore
    assert info["detected_encoding"].lower().replace("-", "_") == "utf_8"


def test_normalize_utf8_bom_stripped():
    """UTF-8-BOM files: BOM must be recognised and normalized=True."""
    text = "第1章 起\n" * 20
    raw = b"\xef\xbb\xbf" + text.encode("utf-8")
    out_bytes, info = _normalize_to_utf8(raw)
    # On disk we want BOM-free utf-8
    assert not out_bytes.startswith(b"\xef\xbb\xbf"), (
        "BOM should be stripped so downstream tools don't see U+FEFF as content"
    )
    assert out_bytes.decode("utf-8") == text
    assert info["normalized"] is True
    assert "bom" in info.get("warning", "").lower() or \
           info["detected_encoding"].lower().replace("-", "_") in {"utf_8", "utf_8_sig"}


def test_normalize_gbk_real_sample():
    raw = _GBK_SAMPLE_TEXT.encode("gbk")
    out_bytes, info = _normalize_to_utf8(raw)
    assert info["normalized"] is True
    # The detected encoding may be reported as gbk OR gb18030 (superset).
    # Either is correct because gb18030 is a strict superset of gbk.
    assert info["detected_encoding"].lower().replace("-", "_") in {
        "gb18030", "gbk", "gb2312"
    }, f"unexpected detection: {info}"
    # Round-trip: the utf-8 bytes must decode to the ORIGINAL text
    assert out_bytes.decode("utf-8") == _GBK_SAMPLE_TEXT


def test_normalize_gb18030_real_sample():
    raw = _GBK_SAMPLE_TEXT.encode("gb18030")
    out_bytes, info = _normalize_to_utf8(raw)
    assert info["normalized"] is True
    assert out_bytes.decode("utf-8") == _GBK_SAMPLE_TEXT


def test_normalize_big5_real_sample():
    raw = _BIG5_SAMPLE_TEXT.encode("big5")
    out_bytes, info = _normalize_to_utf8(raw)
    assert info["normalized"] is True
    # big5 / big5hkscs / cp950 are all acceptable (all Chinese-traditional encodings)
    enc = info["detected_encoding"].lower().replace("-", "_")
    assert "big5" in enc or enc == "cp950", f"unexpected detection: {info}"
    assert out_bytes.decode("utf-8") == _BIG5_SAMPLE_TEXT


def test_normalize_gb2312_real_sample():
    """GB2312 is a strict subset of GB18030 — same bytes decode under both."""
    # Use text restricted to gb2312 code points (simplified, no 〇 extended chars)
    text = "第一章 起\n他在夜市里转身，霓虹灯打在脸上。\n" * 30
    raw = text.encode("gb2312")
    out_bytes, info = _normalize_to_utf8(raw)
    assert info["normalized"] is True
    assert out_bytes.decode("utf-8") == text


def test_normalize_shift_jis_real_sample():
    raw = _SHIFT_JIS_SAMPLE_TEXT.encode("shift_jis")
    out_bytes, info = _normalize_to_utf8(raw)
    assert info["normalized"] is True
    # shift_jis / cp932 — both fine
    enc = info["detected_encoding"].lower().replace("-", "_")
    assert "shift" in enc or "sjis" in enc or enc == "cp932", f"unexpected: {info}"
    assert out_bytes.decode("utf-8") == _SHIFT_JIS_SAMPLE_TEXT


def test_normalize_pure_garbage_raises():
    """Random bytes that are no real text in any encoding → ValueError."""
    # Deterministic seed so the test is reproducible
    import random as _r
    _r.seed(42)
    garbage = bytes(_r.randint(0x80, 0xFF) for _ in range(4096))
    # No run of ascii so nothing looks text-ish
    with pytest.raises(ValueError):
        _normalize_to_utf8(garbage)


def test_normalize_truncated_utf8_tail():
    """A real upload can arrive with its last multi-byte sequence cut off
    (network hiccup, truncated scrape). We tolerate via errors='replace'
    because the rest of the file is fine — do NOT fall back to another codec
    just because of a single bad byte at EOF.
    """
    text = "第1章 起\n" * 100
    raw = text.encode("utf-8")
    # Cut one byte of the last 3-byte UTF-8 char
    truncated = raw[:-1]
    out_bytes, info = _normalize_to_utf8(truncated)
    decoded = out_bytes.decode("utf-8")
    replacement_count = decoded.count("\ufffd")
    # Exactly 1-2 replacement chars expected (depending on where the cut landed)
    assert replacement_count <= 2, f"too many replacements: {replacement_count}"
    # Should have stayed on utf_8 — not fallen back to gb18030/big5 because
    # the corruption is <5% of the file.
    assert info["detected_encoding"].lower().replace("-", "_") == "utf_8"


def test_normalize_large_file_uses_head_for_detection():
    """A 10MB gbk file must decode correctly without blowing memory/CPU on
    detection. Implementation detail: head-only detection + full-file decode
    with the detected codec.
    """
    chunk = _GBK_SAMPLE_TEXT  # ~3KB per copy
    big_text = chunk * 3500   # ~10MB
    raw = big_text.encode("gbk")
    assert len(raw) > 10 * 1024 * 1024, f"need >10MB, got {len(raw)}"
    import time as _t
    t0 = _t.time()
    out_bytes, info = _normalize_to_utf8(raw)
    elapsed = _t.time() - t0
    assert info["normalized"] is True
    assert out_bytes.decode("utf-8") == big_text
    # Don't benchmark strictly, but flag if absurdly slow (10MB < 3s is healthy)
    assert elapsed < 10.0, f"10MB normalise took {elapsed:.2f}s — head-sampling broken?"


# ---------------------------------------------------------------------------
# upload route integration — bytes-on-disk invariant
# ---------------------------------------------------------------------------

def test_upload_gbk_file_lands_as_utf8(client, tmp_novels):
    """The core invariant: whatever the user sends, disk holds UTF-8."""
    raw = _GBK_SAMPLE_TEXT.encode("gbk")
    resp = client.post(
        "/api/novels/upload",
        data={"files": _file_arg("gbk-sample.txt", raw)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201, resp.get_json()
    path = tmp_novels / "gbk-sample.txt"
    assert path.exists()
    # Read as utf-8 — must succeed and equal original text
    disk_text = path.read_text(encoding="utf-8")
    assert disk_text == _GBK_SAMPLE_TEXT


def test_upload_reports_detected_encoding_in_response(client, tmp_novels):
    raw = _GBK_SAMPLE_TEXT.encode("gbk")
    resp = client.post(
        "/api/novels/upload",
        data={"files": _file_arg("whatever.txt", raw)},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    u = data["uploaded"][0]
    assert "detected_encoding" in u
    assert u["normalized"] is True
    assert u["detected_encoding"].lower().replace("-", "_") in {"gb18030", "gbk", "gb2312"}
    assert u["original_size_bytes"] == len(raw)
    # UTF-8 bytes will be LARGER than gbk for Chinese (3 bytes vs 2)
    assert u["size_bytes"] > u["original_size_bytes"]


def test_upload_pure_garbage_rejected(client, tmp_novels):
    """Random bytes → skipped with an encoding-related reason."""
    import random as _r
    _r.seed(7)
    garbage = bytes(_r.randint(0x80, 0xFF) for _ in range(4096))
    resp = client.post(
        "/api/novels/upload",
        data={"files": _file_arg("junk.txt", garbage)},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["uploaded"] == []
    assert len(data["skipped"]) == 1
    reason = data["skipped"][0]["reason"].lower()
    assert "encoding" in reason or "unsupported" in reason


def test_upload_mixed_encodings_batch(client, tmp_novels):
    """Three files, three encodings — all three land as UTF-8 on disk."""
    payloads = {
        "utf8-novel.txt": _GBK_SAMPLE_TEXT.encode("utf-8"),
        "gbk-novel.txt": _GBK_SAMPLE_TEXT.encode("gbk"),
        "big5-novel.txt": _BIG5_SAMPLE_TEXT.encode("big5"),
    }
    resp = client.post(
        "/api/novels/upload",
        data={"files": [_file_arg(n, b) for n, b in payloads.items()]},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert len(data["uploaded"]) == 3

    # Every file on disk reads as UTF-8 and matches its original text
    assert (tmp_novels / "utf8-novel.txt").read_text("utf-8") == _GBK_SAMPLE_TEXT
    assert (tmp_novels / "gbk-novel.txt").read_text("utf-8") == _GBK_SAMPLE_TEXT
    assert (tmp_novels / "big5-novel.txt").read_text("utf-8") == _BIG5_SAMPLE_TEXT

    # utf8-novel should have normalized=false (fast path)
    by_name = {u["name"]: u for u in data["uploaded"]}
    assert by_name["utf8-novel.txt"]["normalized"] is False
    assert by_name["gbk-novel.txt"]["normalized"] is True
    assert by_name["big5-novel.txt"]["normalized"] is True


def test_upload_truncated_multi_byte_at_end(client, tmp_novels):
    """Slightly corrupt UTF-8 should NOT trigger an encoding fallback."""
    text = _GBK_SAMPLE_TEXT  # reuse the 3KB sample
    raw = text.encode("utf-8")[:-1]  # chop one tail byte
    resp = client.post(
        "/api/novels/upload",
        data={"files": _file_arg("slightly-corrupt.txt", raw)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    u = resp.get_json()["uploaded"][0]
    # Should still be classified as UTF-8 (not misrouted to gb18030)
    assert u["detected_encoding"].lower().replace("-", "_") == "utf_8"


def test_list_novels_after_normalize_shows_utf8(client, tmp_novels):
    """/api/novels after upload always reports encoding_ok=true — because the
    disk file is guaranteed UTF-8, the encoding-detection column is now a
    tautology. Keep the field for backward-compat; assert the invariant.
    """
    raw = _GBK_SAMPLE_TEXT.encode("gbk")
    client.post(
        "/api/novels/upload",
        data={"files": _file_arg("gbk-on-disk-utf8.txt", raw)},
        content_type="multipart/form-data",
    )
    resp = client.get("/api/novels")
    rows = resp.get_json()["novels"]
    row = next(r for r in rows if r["name"] == "gbk-on-disk-utf8.txt")
    assert row["encoding_ok"] is True
    # Chapter detection should now find 第1章 / 第2章 markers because the
    # on-disk bytes are UTF-8 — this was the whole point of normalisation.
    assert row["estimated_chapters"] >= 2
    assert row["detected_format"] == "zh-standard"


def test_upload_utf8_bom_file_lands_without_bom(client, tmp_novels):
    text = "第1章 起\n" * 20
    raw = b"\xef\xbb\xbf" + text.encode("utf-8")
    resp = client.post(
        "/api/novels/upload",
        data={"files": _file_arg("bom.txt", raw)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    disk_bytes = (tmp_novels / "bom.txt").read_bytes()
    assert not disk_bytes.startswith(b"\xef\xbb\xbf")
    assert disk_bytes.decode("utf-8") == text
