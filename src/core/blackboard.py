"""Blackboard — filesystem-backed shared state for all agents.

Moved from src/blackboard.py in the 2026-05-11 refactor to let both the
novel pipeline and the new genre pipeline share the same primitive without
either depending on the other.

Design principle: no agent touches files directly. Every read and write
goes through this module so we can (a) enforce atomic writes, (b) keep
the path conventions in one place, and (c) later swap the backend
(e.g., to a DB) in one spot without touching agent logic.

All paths passed in are RELATIVE to the state directory unless marked
absolute.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .. import config


class Blackboard:
    def __init__(self, root: Path | None = None) -> None:
        self.root: Path = Path(root) if root else config.STATE_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    # ---------- path helpers ----------
    def _abs(self, path: str | Path) -> Path:
        p = Path(path)
        return p if p.is_absolute() else (self.root / p)

    def exists(self, path: str | Path) -> bool:
        return self._abs(path).exists()

    def list_files(self, subdir: str, pattern: str = "*") -> list[Path]:
        """List files under state/<subdir> matching glob. Sorted."""
        d = self._abs(subdir)
        if not d.exists():
            return []
        return sorted(p for p in d.glob(pattern) if p.is_file())

    # ---------- atomic write primitive ----------
    def _atomic_write(self, path: Path, data: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same dir, then rename (atomic on POSIX)
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp_path, path)
        except Exception:
            # Clean up on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ---------- text ----------
    def read_text(self, path: str | Path) -> str:
        return self._abs(path).read_text(encoding="utf-8")

    def write_text(self, path: str | Path, content: str) -> None:
        self._atomic_write(self._abs(path), content)

    # ---------- json ----------
    def read_json(self, path: str | Path) -> Any:
        return json.loads(self.read_text(path))

    def write_json(self, path: str | Path, obj: Any) -> None:
        self.write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))

    # ---------- yaml ----------
    def read_yaml(self, path: str | Path) -> Any:
        return yaml.safe_load(self.read_text(path))

    def write_yaml(self, path: str | Path, obj: Any) -> None:
        self.write_text(
            path,
            yaml.safe_dump(obj, allow_unicode=True, sort_keys=False, default_flow_style=False),
        )

    # ---------- jsonl (append-only log) ----------
    def append_jsonl(self, path: str | Path, obj: Any) -> None:
        p = self._abs(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def read_jsonl(self, path: str | Path) -> list[Any]:
        p = self._abs(path)
        if not p.exists():
            return []
        out = []
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out


# A module-level default instance for convenience.
bb = Blackboard()
