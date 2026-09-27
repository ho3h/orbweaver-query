"""Explicit bounded memoization of exact pair scores across requests."""

from collections import OrderedDict
from dataclasses import dataclass

from ._validation import positive_int


@dataclass(frozen=True)
class CacheInfo:
    entries: int
    max_entries: int
    hits: int
    misses: int
    evictions: int


class BindingCache:
    """LRU of deterministic pair scores, including unsupported endpoints.

    Entries are keyed by immutable graph/model identities and endpoint/relation
    indices. Replacing either artifact cannot return a stale value. The bound
    counts entries, not process bytes; outputs and transient inference state are
    separate. Cache use is explicit and confined to the caller's object. This
    mutable cache is intended for sequential calls, not concurrent mutation.
    """

    def __init__(self, *, max_entries=16384):
        positive_int(max_entries, "max_entries")
        self._maximum = max_entries
        self._entries = OrderedDict()
        self._hits = self._misses = self._evictions = 0

    def _get(self, key):
        if key not in self._entries:
            self._misses += 1
            return False, None
        self._hits += 1
        value = self._entries.pop(key)
        self._entries[key] = value
        return True, value

    def _put(self, key, value):
        self._entries.pop(key, None)
        self._entries[key] = value
        if len(self._entries) > self._maximum:
            self._entries.popitem(last=False)
            self._evictions += 1

    def _contains(self, key):
        """Plan remaining feature work without changing LRU order or read counters."""
        return key in self._entries

    def clear(self):
        """Drop all retained predictions and reset statistics."""
        self._entries.clear()
        self._hits = self._misses = self._evictions = 0

    def info(self):
        return CacheInfo(len(self._entries), self._maximum,
                         self._hits, self._misses, self._evictions)
