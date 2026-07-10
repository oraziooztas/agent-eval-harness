"""Fixture model: a self-contained eval task on disk.

Layout of a fixture directory:

    fx-001-example/
    ├── task.json          id, title, prompt, entry_files, timeout_seconds, taxonomy
    ├── seed/              the buggy/incomplete repo the agent starts from
    ├── tests_public/      test_public*.py — visible to the agent (happy path)
    ├── tests_hidden/      test_hidden*.py — NEVER shown to the agent (edge cases)
    └── reference/         known-good solution for the entry files

Design contract (validated by `aeh validate`): the seed passes the public tests
but fails at least one hidden test; the reference passes everything.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

REQUIRED_DIRS = ("seed", "tests_public", "tests_hidden", "reference")
PUBLIC_PREFIX = "test_public"
HIDDEN_PREFIX = "test_hidden"


class FixtureError(Exception):
    """Raised when a fixture directory is malformed."""


@dataclass(frozen=True)
class Fixture:
    root: Path
    id: str
    title: str
    prompt: str
    entry_files: tuple[str, ...]
    timeout_seconds: int
    taxonomy: tuple[str, ...]

    @classmethod
    def load(cls, root: str | Path) -> Fixture:
        rootp = Path(root).resolve()
        meta_path = rootp / "task.json"
        if not meta_path.is_file():
            raise FixtureError(f"task.json non trovato in {rootp}")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FixtureError(f"task.json non è JSON valido: {exc}") from exc

        for key in ("id", "title", "prompt", "entry_files"):
            if key not in meta:
                raise FixtureError(f"task.json: campo obbligatorio mancante '{key}'")
        if not isinstance(meta["entry_files"], list) or not meta["entry_files"]:
            raise FixtureError("task.json: entry_files deve essere una lista non vuota")

        for d in REQUIRED_DIRS:
            if not (rootp / d).is_dir():
                raise FixtureError(f"directory obbligatoria mancante: {d}/")

        for name in meta["entry_files"]:
            for base in ("seed", "reference"):
                if not (rootp / base / name).is_file():
                    raise FixtureError(f"entry file '{name}' mancante in {base}/")

        for prefix, d in ((PUBLIC_PREFIX, "tests_public"), (HIDDEN_PREFIX, "tests_hidden")):
            files = list((rootp / d).glob("*.py"))
            if not files:
                raise FixtureError(f"{d}/ non contiene file .py")
            bad = [f.name for f in files if not f.name.startswith(prefix)]
            if bad:
                raise FixtureError(f"{d}/: i file devono iniziare con '{prefix}': {bad}")

        return cls(
            root=rootp,
            id=str(meta["id"]),
            title=str(meta["title"]),
            prompt=str(meta["prompt"]),
            entry_files=tuple(str(n) for n in meta["entry_files"]),
            timeout_seconds=int(meta.get("timeout_seconds", 300)),
            taxonomy=tuple(str(t) for t in meta.get("taxonomy", [])),
        )

    def hidden_sha256(self) -> str:
        """Hash of the hidden test set: proves WHICH checks graded a run."""
        return _hash_tree(self.root / "tests_hidden")

    def public_sha256(self) -> str:
        return _hash_tree(self.root / "tests_public")


def _hash_tree(path: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(file.name.encode("utf-8"))
        digest.update(file.read_bytes())
    return digest.hexdigest()
