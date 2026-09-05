"""On-disk cache for semantic-checker responses.

The model is asked a deterministic question: given these constraints and this
cart, which are satisfied? The same pair always produces the same prompt, so
the same answer can be reused.

Three reasons this is not just an optimisation:

1. **Reproducibility.** 04 §7 promises `make eval` reproduces every number from
   a clean clone. With a committed cache a reviewer gets the reported numbers
   without an API key and without paying for ~2,400 calls.
2. **The sealed test run.** 05 §Day-20 says the test set runs once. Caching is
   what makes "once" literal — a re-run reads the recorded answers rather than
   asking again and quietly getting different ones.
3. **Prompt iteration on train.** Changing the prompt changes the cache key, so
   only genuinely new questions cost anything.

The key covers the model, the system prompt and the user prompt. Change any of
them and every entry misses, which is the correct behaviour: a cached answer
from a different prompt is a different experiment.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

DEFAULT_PATH = Path(
    os.environ.get("WARRANT_CACHE_PATH", "data/cache/semantic_responses.jsonl")
)


def cache_key(model: str, system: str, user: str) -> str:
    payload = json.dumps(
        {"model": model, "system": system, "user": user}, sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResponseCache:
    """Append-only JSONL, loaded into memory on open.

    JSONL rather than SQLite so the file diffs readably in review — a reviewer
    can see exactly what the model was asked and what it answered.
    """

    def __init__(self, path: Path | str = DEFAULT_PATH, enabled: bool = True):
        self.path = Path(path)
        self.enabled = enabled
        self._entries: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        if self.enabled:
            self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a partial final line from an interrupted run
                if "key" in row:
                    self._entries[row["key"]] = row.get("response")

    def get(self, key: str) -> dict | None:
        if not self.enabled:
            return None
        with self._lock:
            if key in self._entries:
                self.hits += 1
                return self._entries[key]
            self.misses += 1
        return None

    def put(self, key: str, response: dict, note: str = "") -> None:
        """Record an answer. Failures are never cached.

        A cached failure would turn one transient 503 into a permanent
        escalation on that pair for every future run.
        """
        if not self.enabled or response is None:
            return
        with self._lock:
            if key in self._entries:
                return
            self._entries[key] = response
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(
                    {"key": key, "response": response, "note": note},
                    ensure_ascii=False,
                ) + "\n")

    @property
    def size(self) -> int:
        return len(self._entries)

    def stats(self) -> str:
        total = self.hits + self.misses
        rate = self.hits / total if total else 0.0
        return (f"cache {self.size:,} entries — {self.hits:,} hits / "
                f"{self.misses:,} misses ({rate:.0%})")
