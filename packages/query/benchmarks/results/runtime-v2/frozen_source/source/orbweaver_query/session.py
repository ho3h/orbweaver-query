"""Bounded source grouping, exact output restoration, and measured execution."""

from dataclasses import asdict, dataclass
from itertools import islice
import time

import numpy as np

from ._validation import immutable_array, positive_int
from .graph import GraphSnapshot
from .model import GraphModel, Limits


@dataclass(frozen=True)
class LinkQuery:
    head: str
    relation: str


@dataclass(frozen=True)
class LinkResult:
    query: LinkQuery
    candidate_ids: tuple[str, ...]
    scores: np.ndarray
    snapshot_id: str
    model_id: str
    support: str = "two_or_three_hops_excluding_source_and_existing_neighbors"
    score_kind: str = "ranking_logit"

    def top(self, k):
        positive_int(k, "k", minimum=0)
        # Stable ID tie-breaking does not depend on internal integer assignment.
        order = np.lexsort((np.array(self.candidate_ids, dtype=str), -self.scores))[:k]
        return [(self.candidate_ids[int(i)], float(self.scores[i])) for i in order]

    def score_for(self, target):
        """None denotes absence from candidate support, never a negative score."""
        try:
            return float(self.scores[self.candidate_ids.index(target)])
        except ValueError:
            return None


@dataclass(frozen=True)
class Profile:
    strategy: str
    queries: int
    windows: int
    expansions: int
    model_calls: int
    reused_expansions: int
    reused_scores: int
    candidate_scores: int
    type_visits: int
    peak_feature_bytes: int
    elapsed_seconds: float


@dataclass(frozen=True)
class QueryResult:
    rows: tuple[LinkResult, ...]
    profile: Profile

    def report(self):
        return asdict(self.profile)


class Session:
    """Bind one immutable graph/model; share computation only within a window.

    `independent` evaluates every query separately; `consecutive` is a strong
    one-source cache control; `grouped` also reorders sources within each window
    and memoizes identical relation requests. All restore input order and bags.
    Use `iter_batches` for bounded input/output retention on large workloads.
    """

    def __init__(self, graph: GraphSnapshot, model: GraphModel, *, limits=None):
        if graph.relations != model.relations:
            raise ValueError("Graph and model ordered relation schemas differ")
        self.graph, self.model = graph, model
        self.limits = Limits() if limits is None else limits
        if not isinstance(self.limits, Limits):
            raise TypeError("limits must be Limits")

    def explain(self, *, strategy="grouped"):
        self._strategy(strategy)
        return {
            "operator": "PredictLinks", "strategy": strategy,
            "graph_snapshot": self.graph.snapshot_id, "model": self.model.model_id,
            "reuse_key": ["graph_snapshot", "model", "source"],
            "score_key": ["graph_snapshot", "model", "source", "relation"],
            "limits": asdict(self.limits), "preserves_input_order_and_duplicates": True,
            "candidate_pruning": False,
            "candidate_support": "two_or_three_hops_excluding_source_and_existing_neighbors",
            "score_kind": "ranking_logit",
        }

    @staticmethod
    def _strategy(strategy):
        if strategy not in ("independent", "consecutive", "grouped"):
            raise ValueError("strategy must be independent, consecutive, or grouped")

    def iter_batches(self, queries, *, strategy="grouped"):
        self._strategy(strategy)
        iterator = iter(queries)
        while batch := tuple(islice(iterator, self.limits.window_size)):
            yield self._execute_window(batch, strategy)

    def run(self, queries, *, strategy="grouped"):
        self._strategy(strategy)
        started = time.perf_counter()
        rows, profiles = [], []
        for batch in self.iter_batches(queries, strategy=strategy):
            rows.extend(batch.rows)
            profiles.append(batch.profile)
        sums = {key: sum(getattr(p, key) for p in profiles) for key in
                ("queries", "windows", "expansions", "model_calls", "reused_expansions",
                 "reused_scores", "candidate_scores", "type_visits")}
        return QueryResult(tuple(rows), Profile(
            strategy=strategy, **sums,
            peak_feature_bytes=max((p.peak_feature_bytes for p in profiles), default=0),
            elapsed_seconds=time.perf_counter() - started))

    def _execute_window(self, queries, strategy):
        started = time.perf_counter()
        bound = []
        for query in queries:
            if not isinstance(query, LinkQuery):
                raise TypeError("Expected LinkQuery instances")
            bound.append((self.graph.node_index(query.head),
                          self.graph.relation_index(query.relation)))
        groups = {}
        if strategy == "grouped":
            for index, (head, _) in enumerate(bound):
                groups.setdefault(head, []).append(index)
            order = [i for indices in groups.values() for i in indices]
        else:
            order = range(len(queries))
        output = [None] * len(queries)
        cached_head, features, scores_by_relation, candidate_ids = None, None, {}, ()
        expansions = calls = visits = peak = candidate_scores = 0
        for index in order:
            head, relation = bound[index]
            if strategy == "independent" or head != cached_head:
                # Release previous feature state before allocating the next one.
                features, scores_by_relation, candidate_ids = None, {}, ()
                features = self.model.expand(self.graph, head, self.limits)
                cached_head = head
                candidate_ids = tuple(self.graph.node_ids[int(n)] for n in features.candidates)
                expansions += 1
                visits += features.type_visits
                peak = max(peak, features.numeric_bytes)
            if strategy != "grouped" or relation not in scores_by_relation:
                scores = self.model.score(features, relation)
                if scores.shape != features.candidates.shape or not np.isfinite(scores).all():
                    raise ValueError("Backend returned invalid candidate scores")
                scores = immutable_array(scores)
                calls += 1
                candidate_scores += len(scores)
                if strategy == "grouped":
                    scores_by_relation[relation] = scores
            else:
                scores = scores_by_relation[relation]
            output[index] = LinkResult(queries[index], candidate_ids, scores,
                                       self.graph.snapshot_id, self.model.model_id)
        return QueryResult(tuple(output), Profile(
            strategy, len(queries), 1, expansions, calls, len(queries) - expansions,
            len(queries) - calls, candidate_scores, visits, peak, time.perf_counter() - started))
