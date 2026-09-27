"""Strong full-source feature/score LRU control for multi-model plan experiments.

This is benchmark code, not a supported runtime cache. The byte budget counts
retained numeric arrays, excluding Python containers and the current transient
source. Process RSS must be measured separately. Features are shared across
compatible models; scores remain keyed by model identity and relation.
"""

from collections import OrderedDict
from dataclasses import dataclass, field

from orbweaver_query._validation import positive_int


@dataclass
class Entry:
    features: object
    scores: dict = field(default_factory=dict)
    resident: bool = False

    @property
    def numeric_bytes(self):
        return self.features.numeric_bytes + sum(v.nbytes for v in self.scores.values())


@dataclass(frozen=True)
class CachedFeatures:
    entry: Entry
    type_visits: int
    neighbor_visits: int
    peak_states: int

    @property
    def candidates(self):
        return self.entry.features.candidates

    @property
    def numeric_bytes(self):
        return self.entry.features.numeric_bytes


class SharedFeatureLRU:
    def __init__(self, max_bytes):
        positive_int(max_bytes, 'max_bytes')
        self.max_bytes = max_bytes
        self.entries = OrderedDict()
        self.bytes = self.peak_bytes = 0
        self.expansions = self.feature_hits = self.score_calls = self.score_hits = self.evictions = 0

    def info(self):
        return {'numeric_bytes':self.bytes, 'peak_retained_numeric_bytes':self.peak_bytes,
                'entries':len(self.entries), 'expansions':self.expansions,
                'feature_hits':self.feature_hits, 'score_calls':self.score_calls,
                'score_hits':self.score_hits, 'evictions':self.evictions}

    def clear(self):
        for entry in self.entries.values():
            entry.resident = False
        self.entries.clear()
        self.bytes = self.peak_bytes = 0
        self.expansions = self.feature_hits = self.score_calls = self.score_hits = self.evictions = 0

    def _trim(self):
        while self.bytes > self.max_bytes:
            _, entry = self.entries.popitem(last=False)
            entry.resident = False
            self.bytes -= entry.numeric_bytes
            self.evictions += 1
        self.peak_bytes = max(self.peak_bytes, self.bytes)

    def features(self, model, graph, head, limits):
        key = graph.snapshot_id, getattr(model,'feature_id',model.model_id), head
        if key in self.entries:
            self.entries.move_to_end(key)
            self.feature_hits += 1
            return CachedFeatures(self.entries[key], 0, 0, 0)
        self.expansions += 1
        features = model.expand(graph, head, limits)
        entry = Entry(features)
        if entry.numeric_bytes <= self.max_bytes:
            self.entries[key] = entry
            entry.resident = True
            self.bytes += entry.numeric_bytes
            self._trim()
        return CachedFeatures(entry, features.type_visits, getattr(features,'neighbor_visits',0),
                              features.peak_states)

    def score(self, model, features, relation):
        entry = features.entry
        key = model.model_id, relation
        if key in entry.scores:
            self.score_hits += 1
            return entry.scores[key]
        self.score_calls += 1
        values = model.score(entry.features, relation)
        # An evicted entry may remain alive as the current source. Its bytes no
        # longer belong to the retained cache; the current-source cost is separate.
        entry.scores[key] = values
        if entry.resident:
            self.bytes += values.nbytes
            self._trim()
        return values


class CachedModel:
    """Request-independent full source preparation with cross-model feature reuse."""

    def __init__(self, model, cache):
        self.model, self.cache = model, cache
        self.model_id, self.relations = model.model_id, model.relations
        self.feature_id = 'full-cache:' + getattr(model,'feature_id',model.model_id)
        self.candidate_support = getattr(model,'candidate_support','backend_defined')
        self.score_kind = getattr(model,'score_kind','backend_score')

    def expand(self, graph, head, limits):
        return self.cache.features(self.model, graph, head, limits)

    def expand_targets(self, graph, head, targets, limits):
        return self.expand(graph, head, limits)

    def score(self, features, relation):
        return self.cache.score(self.model, features, relation)

    def rejects_pair(self, graph, head, target):
        reject = getattr(self.model, 'rejects_pair', None)
        return callable(reject) and reject(graph, head, target)
