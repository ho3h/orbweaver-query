"""Score candidate bindings without altering the model's evidence domain."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from itertools import islice
from types import MappingProxyType

from .cache import BindingCache
from .session import LinkQuery


@dataclass(frozen=True)
class ScoredBinding:
    binding: Mapping
    score: float | None
    status: str
    snapshot_id: str
    model_id: str
    score_kind: str = "ranking_logit"

    def to_record(self, *, prediction_column="prediction"):
        if prediction_column in self.binding:
            raise ValueError(f"Prediction column collides with input: {prediction_column}")
        return {**self.binding, prediction_column: {
            "score": self.score, "status": self.status, "score_kind": self.score_kind,
            "snapshot_id": self.snapshot_id, "model_id": self.model_id,
        }}


@dataclass(frozen=True)
class BindingResult:
    rows: tuple[ScoredBinding, ...]
    profiles: tuple

    def where_score(self, minimum):
        if type(minimum) not in (float, int) or not math.isfinite(minimum):
            raise ValueError("minimum must be a finite number")
        return BindingResult(tuple(row for row in self.rows
                                   if row.score is not None and row.score >= minimum), self.profiles)

    def to_records(self, *, prediction_column="prediction"):
        return [row.to_record(prediction_column=prediction_column) for row in self.rows]

    def project(self, *columns):
        """Select input fields while retaining prediction/provenance and row bags."""
        if (any(type(c) is not str or not c for c in columns)
                or len(set(columns)) != len(columns)):
            raise ValueError("Projection columns must be distinct nonempty strings")
        projected = []
        for row in self.rows:
            if any(column not in row.binding for column in columns):
                raise ValueError("Projection contains a missing input column")
            projected.append(replace(row, binding=MappingProxyType(
                {column: row.binding[column] for column in columns})))
        return BindingResult(tuple(projected), self.profiles)


def iter_score_bindings(session, bindings, *, head="head", relation="relation", target="target",
                        strategy="grouped", execution="auto", cache=None):
    """Preserve bag/order/null inputs, with bounded preparation and output windows.

    Any null argument short-circuits that row to a null score. Otherwise IDs must
    belong to the evidence/model schema. Unknown IDs are errors; known endpoints
    outside path support return `unsupported`. Candidate selection never crops evidence.
    """
    session._strategy(strategy)
    if execution not in ("auto", "full", "targeted"):
        raise ValueError("execution must be auto, full, or targeted")
    can_target = callable(getattr(session.model, "expand_targets", None))
    if execution == "targeted" and not can_target:
        raise ValueError("Backend does not support exact target expansion")
    if cache is not None and not isinstance(cache, BindingCache):
        raise TypeError("cache must be a BindingCache")
    columns = (head, relation, target)
    if any(type(c) is not str or not c for c in columns) or len(set(columns)) != 3:
        raise ValueError("head, relation and target must be distinct nonempty column names")
    iterator = iter(bindings)
    while window := tuple(islice(iterator, session.limits.window_size)):
        copied, validated = [], []
        for index, binding in enumerate(window):
            if not isinstance(binding, Mapping) or any(key not in binding for key in columns):
                raise ValueError(f"Each candidate binding needs columns {columns}")
            row = MappingProxyType(dict(binding))
            copied.append(row)
            if any(row[key] is None for key in columns):
                validated.append(None)
                continue
            if any(type(row[key]) is not str for key in columns):
                raise ValueError("Candidate node IDs and relations must be strings or null")
            # Validate both endpoints even when no candidate reaches the target.
            validated.append((session.graph.snapshot_id, session.model.model_id,
                              session.graph.node_index(row[head]),
                              session.graph.relation_index(row[relation]),
                              session.graph.node_index(row[target])))
        requests, positions, request_for, ready = [], [], {}, {}
        for index, (row, key) in enumerate(zip(copied, validated)):
            if key is None:
                continue
            if key in ready or (strategy == "grouped" and key in request_for):
                continue
            found, value = (False, None) if cache is None else cache._get(key)
            if found:
                ready[key] = value
            else:
                request_for[key] = len(requests)
                requests.append(LinkQuery(row[head], row[relation]))
                positions.append(index)
        if execution != "full" and can_target and requests:
            scored = session._execute_window(
                requests, strategy, targets=[copied[i][target] for i in positions])
        else:
            scored = session.run(requests, strategy=strategy)
        for index, prediction in zip(positions, scored.rows):
            key = validated[index]
            value = prediction.score_for(copied[index][target])
            ready[key] = value
        # Commit only after every required expansion and score in this window
        # succeeded; failures do not leave partially computed cache entries.
        if cache is not None:
            for key in request_for:
                cache._put(key, ready[key])
        output = []
        for index, row in enumerate(copied):
            if validated[index] is not None:
                score = ready[validated[index]]
                status = "scored" if score is not None else "unsupported"
            else:
                score, status = None, "null_input"
            output.append(ScoredBinding(row, score, status, session.graph.snapshot_id,
                                         session.model.model_id,
                                         getattr(session.model, "score_kind", "backend_score")))
        yield BindingResult(tuple(output), (scored.profile,))


def score_bindings(session, bindings, **options):
    rows, profiles = [], []
    for result in iter_score_bindings(session, bindings, **options):
        rows.extend(result.rows)
        profiles.extend(result.profiles)
    return BindingResult(tuple(rows), tuple(profiles))
