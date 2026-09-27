"""Independent bounded LRU reference for benchmarking, not a production strategy."""

from collections import OrderedDict
from types import MappingProxyType

import numpy as np

from orbweaver_query._validation import immutable_array, positive_int
from orbweaver_query.bindings import BindingResult, ScoredBinding
from orbweaver_query.session import LinkQuery, LinkResult


def lru_predict(session, queries, *, max_sources=256, max_numeric_bytes=16*2**20):
    """One batch with an initially empty multi-source feature/score cache.

    The numeric limit covers retained feature and score arrays, not Python
    containers, outputs, temporary expansion state or total process memory.
    Oversize entries execute uncached. Cache entries are invalid outside this
    fixed snapshot/model call and are never reused by another call.
    """
    positive_int(max_sources, "max_sources")
    positive_int(max_numeric_bytes, "max_numeric_bytes")
    cache, output = OrderedDict(), []
    retained = peak = expansions = calls = visits = peak_source = 0
    for query in queries:
        if not isinstance(query, LinkQuery):
            raise TypeError("Expected LinkQuery")
        head = session.graph.node_index(query.head)
        relation = session.graph.relation_index(query.relation)
        if head in cache:
            entry = cache.pop(head)
            retained -= entry[3]
        else:
            features = session.model.expand(session.graph, head, session.limits)
            entry = [features, {}, tuple(session.graph.node_ids[i] for i in features.candidates),
                     features.numeric_bytes]
            expansions += 1
            visits += features.type_visits
            peak_source = max(peak_source, features.numeric_bytes)
        features, scores_by_relation, candidate_ids, _ = entry
        if relation not in scores_by_relation:
            scores = session.model.score(features, relation)
            if scores.shape != features.candidates.shape or not np.isfinite(scores).all():
                raise ValueError("Backend returned invalid scores")
            scores = immutable_array(scores)
            scores_by_relation[relation] = scores
            entry[3] += scores.nbytes
            calls += 1
        scores = scores_by_relation[relation]
        if entry[3] <= max_numeric_bytes:
            while cache and (len(cache) >= max_sources or retained + entry[3] > max_numeric_bytes):
                _, victim = cache.popitem(last=False)
                retained -= victim[3]
            cache[head] = entry
            retained += entry[3]
            peak = max(peak, retained)
        output.append(LinkResult(query, candidate_ids, scores, session.graph.snapshot_id,
                                 session.model.model_id))
    return tuple(output), {"expansions": expansions, "model_calls": calls, "type_visits": visits,
        "peak_cached_numeric_bytes": peak, "peak_source_feature_bytes": peak_source,
        "cached_sources_at_end": len(cache), "max_sources": max_sources,
        "max_numeric_bytes": max_numeric_bytes}


def lru_score_bindings(session, bindings, **options):
    copied, queries, positions = [], [], []
    for index, binding in enumerate(bindings):
        row = MappingProxyType(dict(binding))
        copied.append(row)
        if any(row[key] is None for key in ("head", "relation", "target")):
            continue
        if any(type(row[key]) is not str for key in ("head", "relation", "target")):
            raise ValueError("Expected string binding IDs")
        session.graph.node_index(row["target"])
        queries.append(LinkQuery(row["head"], row["relation"]))
        positions.append(index)
    predictions, work = lru_predict(session, queries, **options)
    by_position = dict(zip(positions, predictions))
    output = []
    for index, row in enumerate(copied):
        if index in by_position:
            score = by_position[index].score_for(row["target"])
            status = "scored" if score is not None else "unsupported"
        else:
            score, status = None, "null_input"
        output.append(ScoredBinding(row, score, status, session.graph.snapshot_id, session.model.model_id))
    return BindingResult(tuple(output), ()), work
