"""Novels / material library routes.

A thin HTTP face for novels/: a flat, UTF-8-only .txt dustbin that the
genre pipeline's --extract-from-novel consumes. Invariants enforced
across every route:

  1. filenames NEVER escape novels/ (tested in test_web_novels_api.py)
  2. we never read more than 1MB of a file on list (use ChapterStream for >5MB)
  3. partial uploads never leak — .tmp + atomic rename pattern

Also hosts the /novels SPA view.
"""
from __future__ import annotations

import os
import re as _novels_re
from pathlib import Path

from flask import Blueprint, abort, jsonify, render_template, request

from src import config

from web._shared import NOVEL_MAX_BYTES, READONLY_MODE

bp = Blueprint("novels", __name__)

# Accept letters (incl. CJK), digits, dot, dash, underscore, space.
# Everything else becomes underscore. Kept as a compiled re because we hit
# it once per uploaded file, and the alternative (repeated str.translate) is
# less legible for the reviewer.
_NOVEL_NAME_KEEP = _novels_re.compile(
    r"[^"
    r"A-Za-z0-9"
    r"\u4e00-\u9fff"       # CJK Unified Ideographs
    r"\u3400-\u4dbf"       # CJK Extension A
    r"\u3040-\u309f"       # Hiragana (Japanese)
    r"\u30a0-\u30ff"       # Katakana
    r"\uac00-\ud7af"       # Hangul
    r"\s\-_.()"
    r"]"
)


def _novels_dir() -> Path:
    """Indirection so tests can monkeypatch ``web.app.NOVELS_DIR`` and we pick it up.

    Tests point NOVELS_DIR at tmp_path via ``monkeypatch.setattr(web_app, ...)``;
    reading the attribute freshly on every call keeps that monkeypatch
    effective without forcing us to re-import this blueprint module.

    Fallback chain: web.app.NOVELS_DIR (if import succeeded) → _shared.NOVELS_DIR.
    We don't import web.app at module load to avoid a circular import
    (web.app imports this module to register the blueprint).
    """
    try:
        from web import app as _app  # lazy, request-time
        return _app.NOVELS_DIR
    except (ImportError, AttributeError):
        from web import _shared
        return _shared.NOVELS_DIR


def _human_size(n: int) -> str:
    """'1234567' → '1.2 MB'. Keeps one decimal; never returns '0.0 B'."""
    for unit, step in (("B", 1), ("KB", 1024), ("MB", 1024 ** 2), ("GB", 1024 ** 3)):
        if n < step * 1024 or unit == "GB":
            if unit == "B":
                return f"{n} B"
            return f"{n / step:.1f} {unit}"
    return f"{n} B"


def _sanitize_novel_name(raw: str) -> str:
    """Turn a user-supplied filename into a safe, same-directory name.

    We deliberately DON'T use werkzeug.secure_filename alone because it
    strips all non-ASCII (a Chinese 某某港综.txt becomes 'txt' — useless).

    Steps:
      1. drop directory components — os.path.basename handles both / and \\
      2. strip leading dots (prevents '.hidden' and '..')
      3. replace control chars + path separators + anything not in our
         permissive allow-list with '_'
      4. collapse runs of whitespace to single '_'
      5. if result is empty or just punctuation → fall back to 'upload.txt'
    """
    if not raw:
        return "upload.txt"
    # Step 1: take last path component (defends against any separator)
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    # Step 2: strip leading dots / whitespace — 'hidden' and '..' both
    #         collapse to empty below.
    name = name.lstrip(". \t\r\n")
    # Step 3: allow-list filter
    name = _NOVEL_NAME_KEEP.sub("_", name)
    # Step 4: collapse whitespace runs
    name = _novels_re.sub(r"\s+", "_", name).strip("_. ")
    if not name or name in {".", ".."}:
        return "upload.txt"
    # enforce .txt suffix at this layer? No — caller checks extension
    # separately so skipped-reason can say 'not a .txt file' clearly.
    return name


def _unique_novel_path(name: str) -> Path:
    """If novels/<name> exists, return novels/<stem>-1.txt (or -2, -3…).

    We append BEFORE the extension so tools still see the file as .txt.
    """
    target = _novels_dir() / name
    if not target.exists():
        return target
    stem, _, ext = name.rpartition(".")
    if not stem:                 # names with no dot like 'README'
        stem, ext = name, ""
    else:
        ext = "." + ext
    i = 1
    while True:
        candidate = _novels_dir() / f"{stem}-{i}{ext}"
        if not candidate.exists():
            return candidate
        i += 1


# TODO: _normalize_to_utf8 is ~150 lines — acceptable for now since each
# step (BOM / fast-path UTF-8 / charset_normalizer / manual fallback) is a
# distinct encoding-detection gate and splitting would just shuffle the
# state between helpers. If we ever add a 5th gate, extract then.
def _normalize_to_utf8(raw_bytes: bytes) -> tuple[bytes, dict]:
    """Detect the encoding of ``raw_bytes`` and return UTF-8 bytes + info.

    Returns:
        (utf8_bytes, info) where info keys are:
          - detected_encoding: str (e.g. 'utf_8', 'gb18030', 'big5')
          - confidence: float in [0.0, 1.0]  (charset_normalizer chaos inverse)
          - normalized: True if we actually decoded + re-encoded; False for
            pass-through UTF-8.
          - fallback_used: True if charset_normalizer gave up and we tried
            codecs from a hard-coded list until one decoded cleanly.
          - warning: optional str (currently used for BOM-stripping notice)

    Raises:
        ValueError("unsupported encoding"): every detection avenue failed.

    Strategy (in order):
      1. Try UTF-8 (with BOM variant) — fast path. Bytes are returned
         unchanged unless a BOM was present; BOM is stripped because it's
         just noise for downstream tools.
      2. Use charset_normalizer with an explicit cp_isolation list. Small
         samples (<8KB) often mis-detect Chinese as Korean cp949 without
         isolation; listing the encodings we actually care about fixes
         that.
      3. If (2) returns None or its decoded content is >5% U+FFFD
         replacement chars, fall back to hardcoded codec order:
         gb18030 (superset of gbk/gb2312) → big5 → shift_jis.
      4. Still nothing → raise.

    Large-file optimisation: detection runs on the first 200KB. The
    decision gets applied to the full byte string for the actual decode.
    charset_normalizer re-reading 10MB of text is measurably slower than
    decoding once under a known codec.
    """
    from charset_normalizer import from_bytes

    # Step 1a: BOM. Python's utf-8 decoder accepts BOM as U+FEFF and would
    # silently leak it into our decoded text, so check BEFORE the generic
    # decode. If BOM is present we strip it and re-validate the tail.
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        try:
            stripped = raw_bytes[3:]
            stripped.decode("utf-8")  # validate the rest
            return stripped, {
                "detected_encoding": "utf_8",
                "confidence": 1.0,
                "normalized": True,  # BOM removal counts as normalisation
                "fallback_used": False,
                "warning": "stripped UTF-8 BOM",
            }
        except UnicodeDecodeError:
            pass  # BOM + garbage — fall through to detection

    # Step 1b: pure UTF-8 fast path. Zero-copy return.
    try:
        raw_bytes.decode("utf-8")
        return raw_bytes, {
            "detected_encoding": "utf_8",
            "confidence": 1.0,
            "normalized": False,
            "fallback_used": False,
            "warning": None,
        }
    except UnicodeDecodeError:
        pass

    # Step 2: charset_normalizer with CJK isolation.
    # Large-file sampling: pass only the first 200KB for detection. Once
    # we have a codec verdict, decode the FULL raw_bytes with it — the
    # codec choice doesn't change mid-file for any real upload.
    DETECT_SAMPLE = 200 * 1024
    CP_ISOLATION = [
        "gb18030", "gbk", "gb2312",
        "big5", "big5hkscs", "cp950",
        "shift_jis", "cp932",
        "euc_jp", "euc_kr",
    ]
    sample = raw_bytes[:DETECT_SAMPLE] if len(raw_bytes) > DETECT_SAMPLE else raw_bytes
    best = from_bytes(sample, cp_isolation=CP_ISOLATION).best()

    fallback_used = False
    detected_encoding: str | None = None
    decoded_text: str | None = None

    if best is not None:
        detected_encoding = best.encoding
        # Decode the FULL buffer with the detected codec, not just the
        # sample. errors='replace' tolerates occasional mojibake (a ragged
        # ending, mid-file encoder glitches) without dropping the file.
        try:
            decoded_text = raw_bytes.decode(detected_encoding, errors="replace")
            # Sanity: if >5% is U+FFFD, charset_normalizer guessed wrong.
            # Fall through to the manual codec list.
            if decoded_text.count("\ufffd") > max(10, len(decoded_text) // 20):
                decoded_text = None
                detected_encoding = None
        except (LookupError, UnicodeDecodeError):
            decoded_text = None
            detected_encoding = None

    # Step 3: manual fallback list.
    # Each candidate must clear three gates before we accept it:
    #   (a) low replacement-char ratio (<5%) — codec matches the byte layout
    #   (b) reasonable printable concentration (≥50%) — not mojibake soup
    #   (c) contains ASCII whitespace (space / tab / newline / CR)
    #       Real text — any text — has line breaks and spaces. Random bytes
    #       decoded under gb18030 produce mostly CJK with essentially zero
    #       whitespace (tested: 4096 random bytes → 72 U+FFFD but 0 spaces),
    #       so this gate is what distinguishes a legit upload from junk.
    if decoded_text is None:
        fallback_used = True
        for codec in ("gb18030", "big5", "shift_jis"):
            try:
                candidate = raw_bytes.decode(codec, errors="replace")
            except (LookupError, UnicodeDecodeError):
                continue
            repl_ratio = candidate.count("\ufffd") / max(1, len(candidate))
            printable = sum(
                1 for c in candidate
                if (0x20 <= ord(c) <= 0x7e) or (0x4e00 <= ord(c) <= 0x9fff)
                or c in "\n\r\t"
            )
            printable_ratio = printable / max(1, len(candidate))
            whitespace_count = sum(candidate.count(w) for w in (" ", "\n", "\t", "\r"))
            has_whitespace = whitespace_count >= max(1, len(candidate) // 500)
            if repl_ratio < 0.05 and printable_ratio > 0.5 and has_whitespace:
                decoded_text = candidate
                detected_encoding = codec
                break

    if decoded_text is None or detected_encoding is None:
        raise ValueError("unsupported encoding")

    # Compute a rough confidence: 1.0 if charset_normalizer matched, else
    # (1 - replacement ratio) for fallback. Informational only; UI doesn't
    # currently act on it but the field is stable API.
    if best is not None and not fallback_used:
        # charset_normalizer doesn't expose a 0..1 confidence directly;
        # chaos=0 is perfect, 0.5+ is noise. Map chaos → confidence.
        try:
            chaos = float(best.chaos)
            confidence = max(0.0, 1.0 - min(chaos, 1.0))
        except (TypeError, ValueError):
            confidence = 0.8
    else:
        confidence = 1.0 - (decoded_text.count("\ufffd") / max(1, len(decoded_text)))

    return decoded_text.encode("utf-8"), {
        "detected_encoding": detected_encoding,
        "confidence": confidence,
        "normalized": True,
        "fallback_used": fallback_used,
        "warning": None,
    }


def _is_utf8_ok(path: Path, head_bytes: int = 8192) -> bool:
    """True iff the first head_bytes of the file decode as UTF-8.

    We use an incremental decoder so a chunk that happens to cut in the
    MIDDLE of a valid multi-byte sequence (common at 8KB/multi-MB boundaries
    when the file is mostly CJK) doesn't trigger a false negative.
    """
    import codecs
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    try:
        with path.open("rb") as f:
            chunk = f.read(head_bytes)
        # final=False tolerates an incomplete trailing sequence — we're only
        # sampling the head, not validating the whole file.
        decoder.decode(chunk, final=False)
        return True
    except (OSError, UnicodeDecodeError):
        return False


def _estimate_chapters(path: Path) -> tuple[int, str]:
    """Return (count, format_name). Uses ChapterStream for large files, and
    falls back to count_chapters on head-only content otherwise. If the file
    can't be decoded as UTF-8, return (1, 'none') — count_chapters's default
    for unparseable input.
    """
    from src.genre_extractor import chapter_detector, chapter_stream
    try:
        size = path.stat().st_size
    except OSError:
        return 1, "none"

    # Large file: use the streaming index (bounded memory).
    if size >= chapter_stream.STREAMING_THRESHOLD_BYTES:
        try:
            stream = chapter_stream.ChapterStream(path)
            count = stream.total_chapters
            # chapter_stream.detect_format reads head 1MB; cheap enough.
            head = path.read_bytes()[: 1024 * 1024].decode("utf-8", errors="ignore")
            fmt = chapter_detector.detect_format(head)
            return count, fmt
        except Exception:
            return 1, "none"

    # Small file: read fully (size < 5MB)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 1, "none"
    return chapter_detector.count_chapters(text), chapter_detector.detect_format(text)


def _novel_used_by_presets(name: str) -> list[str]:
    """Return preset ids whose `novels/<name>` file exists (sorted).

    Presets referencing a novel by symlink or by copy under their own
    `novels/` dir both count — the UI just needs to warn the user that
    deleting this file will break the referenced preset's extraction run.
    """
    used: list[str] = []
    if not config.PRESETS_DIR.exists():
        return used
    for p in sorted(config.PRESETS_DIR.iterdir()):
        if p.is_dir() and (p / "novels" / name).exists():
            used.append(p.name)
    return used


@bp.get("/api/novels")
def api_novels_list():
    _novels_dir().mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    # Only top-level *.txt files; skip hidden and non-txt and subdirs.
    for p in sorted(_novels_dir().iterdir()):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        if p.suffix.lower() != ".txt":
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        enc_ok = _is_utf8_ok(p)
        chapters, fmt = _estimate_chapters(p) if enc_ok else (0, "none")
        out.append({
            "name": p.name,
            "path": f"novels/{p.name}",
            "size_bytes": size,
            "size_human": _human_size(size),
            "encoding_ok": enc_ok,
            "estimated_chapters": chapters,
            "detected_format": fmt,
            "used_by_presets": _novel_used_by_presets(p.name),
        })
    return jsonify({"novels": out})


@bp.post("/api/novels/upload")
def api_novels_upload():
    if READONLY_MODE:
        return jsonify({"ok": False, "reason": "readonly_mode"}), 403
    _novels_dir().mkdir(parents=True, exist_ok=True)

    files = request.files.getlist("files")
    if not files:
        return jsonify({"ok": False, "reason": "no files uploaded (field 'files' missing)"}), 400

    uploaded: list[dict] = []
    skipped: list[dict] = []

    for fs in files:
        raw_name = fs.filename or ""
        name = _sanitize_novel_name(raw_name)

        # Extension check (after sanitisation so .. ./ etc. couldn't smuggle one in)
        if not name.lower().endswith(".txt"):
            skipped.append({
                "name": raw_name or name,
                "reason": "not a .txt file (only .txt accepted)",
            })
            continue

        # Read the full byte stream at once so size-check, encoding-detect and
        # atomic write all see the SAME bytes. For 50MB cap this is OK; if we
        # ever raise the cap we should switch to streaming + chunked detect.
        raw_bytes = fs.stream.read()
        original_size = len(raw_bytes)
        if original_size > NOVEL_MAX_BYTES:
            skipped.append({
                "name": raw_name,
                "reason": f"file too large ({_human_size(original_size)} > {_human_size(NOVEL_MAX_BYTES)})",
            })
            continue
        if original_size == 0:
            skipped.append({"name": raw_name, "reason": "empty file"})
            continue

        # Encoding: detect → decode → re-encode as UTF-8. If this fails, we
        # don't write anything — the file's bytes make no textual sense and
        # letting it into novels/ would just crash the pipeline later.
        try:
            utf8_bytes, enc_info = _normalize_to_utf8(raw_bytes)
        except ValueError as e:
            skipped.append({
                "name": raw_name,
                "reason": f"unsupported encoding — tried UTF-8 / GB18030 / Big5 / Shift-JIS ({e})",
            })
            continue

        target = _unique_novel_path(name)
        tmp = target.with_name("." + target.name + ".tmp")
        try:
            # Atomic write: temp file first, then rename. The bytes we write
            # are the UTF-8 normalised form (zero-copy when input was already
            # UTF-8 thanks to the fast path in _normalize_to_utf8).
            with tmp.open("wb") as out_f:
                out_f.write(utf8_bytes)
            os.replace(tmp, target)
        except OSError as e:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            skipped.append({"name": raw_name, "reason": f"write failed: {e}"})
            continue

        uploaded.append({
            "name": target.name,
            "path": f"novels/{target.name}",
            "size_bytes": len(utf8_bytes),
            "size_human": _human_size(len(utf8_bytes)),
            "original_size_bytes": original_size,
            "encoding_ok": True,  # on-disk bytes are now guaranteed UTF-8
            "detected_encoding": enc_info["detected_encoding"],
            "normalized": enc_info["normalized"],
            "fallback_used": enc_info["fallback_used"],
            "encoding_warning": enc_info.get("warning"),
        })

    # 201 iff at least one file landed; otherwise 200 so the UI can still
    # parse `skipped`.
    code = 201 if uploaded else 200
    return jsonify({"uploaded": uploaded, "skipped": skipped}), code


def _resolve_novel_or_abort(name: str) -> Path:
    """Translate a path segment into a novels/<name> Path, refusing anything
    that could escape. Flask routes with <string:name> don't accept '/' so
    the main attack surface is URL-encoded %2F and parent-references.
    """
    if not name or name in (".", ".."):
        abort(400, "invalid name")
    # Reject any separator or parent-ref even after URL-decode
    if "/" in name or "\\" in name or ".." in name:
        abort(403, "path traversal rejected")
    target = (_novels_dir() / name).resolve()
    try:
        target.relative_to(_novels_dir().resolve())
    except ValueError:
        abort(403, "path outside novels/")
    return target


@bp.delete("/api/novels/<path:name>")
def api_novels_delete(name: str):
    if READONLY_MODE:
        return jsonify({"ok": False, "reason": "readonly_mode"}), 403
    target = _resolve_novel_or_abort(name)
    if not target.exists() or not target.is_file():
        return jsonify({"ok": False, "reason": "not found"}), 404

    force = request.args.get("force") == "true"
    used_by = _novel_used_by_presets(target.name)
    if used_by and not force:
        return jsonify({
            "ok": False,
            "reason": "novel is used by presets; pass ?force=true",
            "used_by_presets": used_by,
            "name": target.name,
        }), 409

    try:
        target.unlink()
    except OSError as e:
        return jsonify({"ok": False, "reason": str(e)}), 500
    return jsonify({"ok": True, "deleted": True, "name": target.name, "used_by_presets": used_by})


@bp.get("/api/novels/<path:name>/preview")
def api_novels_preview(name: str):
    target = _resolve_novel_or_abort(name)
    if not target.exists() or not target.is_file():
        return jsonify({"ok": False, "reason": "not found"}), 404

    # Read at most 2000 characters. We over-read bytes (4× chars) so CJK still
    # gives us ~2000 glyphs; trim to exactly 2000 after decode.
    try:
        with target.open("rb") as f:
            raw = f.read(8192)
        text = raw.decode("utf-8", errors="replace")
    except OSError as e:
        return jsonify({"ok": False, "reason": str(e)}), 500

    truncated = target.stat().st_size > len(raw) or len(text) > 2000
    head = text[:2000]
    return jsonify({"name": target.name, "head": head, "truncated": truncated})


@bp.get("/novels")
def view_novels_index():
    return render_template("novels/index.html")
