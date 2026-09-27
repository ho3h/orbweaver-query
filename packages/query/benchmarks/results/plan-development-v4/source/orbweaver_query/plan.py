"""Inspectable conjunctive inference plans with shared features and measured ordering."""

import hashlib
import json
import math
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from itertools import islice
from types import MappingProxyType

import numpy as np

from .cache import BindingCache
from .graph import GraphSnapshot
from .model import GraphModel, Limits


def _name(value):
    if type(value) is not str or not value:
        raise ValueError("Expected a nonempty column name")
    return value


@dataclass(frozen=True)
class Predict:
    name: str
    model: GraphModel
    head: str = "head"
    relation: str = "relation"
    target: str = "target"

    def __post_init__(self):
        for value in (self.name, self.head, self.relation, self.target):
            _name(value)
        if len({self.head, self.relation, self.target}) != 3:
            raise ValueError("Prediction inputs must be distinct columns")


@dataclass(frozen=True)
class Prediction:
    score: float | None
    status: str
    snapshot_id: str
    model_id: str
    score_kind: str

    def to_record(self):
        return {
            "score": self.score,
            "status": self.status,
            "snapshot_id": self.snapshot_id,
            "model_id": self.model_id,
            "score_kind": self.score_kind,
        }


@dataclass(frozen=True)
class CostEstimate:
    outputs: tuple[str, ...]
    seconds_per_row: float
    pass_fraction: float
    sample_rows: int

    def __post_init__(self):
        if (
            not math.isfinite(self.seconds_per_row)
            or self.seconds_per_row < 0
            or not math.isfinite(self.pass_fraction)
            or not 0 <= self.pass_fraction <= 1
            or type(self.sample_rows) is not int
            or self.sample_rows < 1
        ):
            raise ValueError("Invalid cost/selectivity estimate")


@dataclass(frozen=True)
class PlanStatistics:
    plan_id: str
    fused: bool
    estimates: tuple[CostEstimate, ...]


@dataclass(frozen=True)
class StepProfile:
    outputs: tuple[str, ...]
    input_rows: int
    output_rows: int
    expansions: int
    model_calls: int
    feature_bytes: int
    type_visits: int
    neighbor_visits: int
    elapsed_seconds: float
    cache_hits: int = 0
    cache_misses: int = 0


@dataclass(frozen=True)
class PlanResult:
    rows: tuple[Mapping, ...]
    steps: tuple[StepProfile, ...]
    plan_id: str
    prediction_columns: tuple[str, ...]

    def to_records(self):
        return [
            {k: v.to_record() if k in self.prediction_columns else v for k, v in row.items()}
            for row in self.rows
        ]

    def report(self):
        return {
            "plan_id": self.plan_id,
            "output_rows": len(self.rows),
            "expansions": sum(s.expansions for s in self.steps),
            "model_calls": sum(s.model_calls for s in self.steps),
            "cache_hits": sum(s.cache_hits for s in self.steps),
            "cache_misses": sum(s.cache_misses for s in self.steps),
            "steps": [asdict(s) for s in self.steps],
        }


@dataclass(frozen=True)
class QueryPlan:
    """A bag-preserving conjunction of pair predictions and score thresholds.

    Cypher supplies candidate rows. Inputs are validated for all declared
    predictions before any model executes. Models must satisfy the deterministic
    feature contract; compatible operators may share source preparation. Cost
    statistics affect physical order only. As with other physical strategies,
    different orders may hit resource limits at different points, never return
    approximate answers. Projection is terminal and does not change evidence.
    """

    graph: GraphSnapshot
    predictions: tuple[Predict, ...] = ()
    thresholds: tuple[tuple[str, float], ...] = ()
    projection: tuple[str, ...] | None = None
    limits: Limits = field(default_factory=Limits)

    def __post_init__(self):
        if not isinstance(self.graph, GraphSnapshot) or not isinstance(self.limits, Limits):
            raise TypeError("Expected GraphSnapshot and Limits")
        names = [p.name for p in self.predictions]
        if len(set(names)) != len(names):
            raise ValueError("Prediction output names must be unique")
        for prediction in self.predictions:
            if prediction.model.relations != self.graph.relations:
                raise ValueError("Graph and model ordered relation schemas differ")
        if len({name for name, _ in self.thresholds}) != len(self.thresholds):
            raise ValueError("Duplicate score thresholds")
        for name, value in self.thresholds:
            if name not in names or type(value) not in (float, int) or not math.isfinite(value):
                raise ValueError("Threshold requires an existing prediction and finite number")
        if self.projection is not None:
            for name in self.projection:
                _name(name)
            if len(set(self.projection)) != len(self.projection):
                raise ValueError("Projection columns must be unique")

    def predict(self, name, model, *, head="head", relation="relation", target="target"):
        if self.projection is not None:
            raise ValueError("Projection must be terminal")
        return replace(
            self, predictions=(*self.predictions, Predict(name, model, head, relation, target))
        )

    def where_score(self, name, minimum):
        if self.projection is not None:
            raise ValueError("Projection must be terminal")
        if type(minimum) not in (float, int) or not math.isfinite(minimum):
            raise ValueError("Threshold must be finite")
        thresholds = dict(self.thresholds)
        thresholds[name] = max(thresholds.get(name, minimum), minimum)
        return replace(self, thresholds=tuple(thresholds.items()))

    def project(self, *columns):
        return replace(self, projection=tuple(columns))

    @property
    def plan_id(self):
        payload = {
            "graph": self.graph.snapshot_id,
            "limits": asdict(self.limits),
            "predictions": [
                {
                    "name": p.name,
                    "model": p.model.model_id,
                    "columns": [p.head, p.relation, p.target],
                    "feature": getattr(p.model, "feature_id", p.model.model_id),
                }
                for p in self.predictions
            ],
            "thresholds": self.thresholds,
            "projection": self.projection,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _groups(self, fused):
        if type(fused) is not bool:
            raise ValueError("fused must be a boolean")
        groups = {}
        for p in self.predictions:
            key = (
                (
                    getattr(p.model, "feature_id", p.model.model_id),
                    getattr(p.model, "candidate_support", "backend_defined"),
                    p.head,
                    p.target,
                )
                if fused
                else p.name
            )
            groups.setdefault(key, []).append(p)
        return tuple(tuple(g) for g in groups.values())

    def _ordered(self, fused, statistics):
        groups = self._groups(fused)
        if statistics is None:
            filtered = {name for name, _ in self.thresholds}
            return tuple(sorted(groups, key=lambda g: not any(p.name in filtered for p in g)))
        if (
            not isinstance(statistics, PlanStatistics)
            or statistics.plan_id != self.plan_id
            or statistics.fused != fused
        ):
            raise ValueError("Statistics do not match this plan and fusion setting")
        estimates = {e.outputs: e for e in statistics.estimates}
        if len(estimates) != len(statistics.estimates) or set(estimates) != {
            tuple(p.name for p in g) for g in groups
        }:
            raise ValueError("Statistics do not cover the physical groups")

        def key(group):
            e = estimates[tuple(p.name for p in group)]
            return math.inf if e.pass_fraction == 1 else e.seconds_per_row / (1 - e.pass_fraction)

        return tuple(sorted(groups, key=key))

    def explain(self, *, fused=True, statistics=None):
        groups = self._ordered(fused, statistics)
        return {
            "plan_id": self.plan_id,
            "graph_snapshot": self.graph.snapshot_id,
            "logical_predictions": [
                {
                    "output": p.name,
                    "model": p.model.model_id,
                    "feature_contract": getattr(p.model, "feature_id", p.model.model_id),
                    "support": getattr(p.model, "candidate_support", "backend_defined"),
                    "score_kind": getattr(p.model, "score_kind", "backend_score"),
                    "columns": [p.head, p.relation, p.target],
                }
                for p in self.predictions
            ],
            "thresholds": dict(self.thresholds),
            "projection": self.projection,
            "physical_groups": [[p.name for p in g] for g in groups],
            "ordering": "cost / rejection_fraction" if statistics else "filtered groups first, stable ties",
            "within_group_order": [[p.name for p in sorted(g,
                key=lambda p: p.name not in dict(self.thresholds))] for g in groups],
            "statistics": None if statistics is None else [asdict(e) for e in statistics.estimates],
            "shared_preparation": fused,
            "preserves_order_and_bags": True,
            "validation": "all declared inputs before model execution",
            "limits": asdict(self.limits),
        }

    def _validate(self, window):
        output_names = {p.name for p in self.predictions}
        shared = {(p.head, p.relation, p.target): [] for p in self.predictions}
        validators = {}
        for p in self.predictions:
            validators.setdefault((p.head, p.relation, p.target), p.name)
        rows, bindings = (
            [],
            {p.name: shared[(p.head, p.relation, p.target)] for p in self.predictions},
        )
        for binding in window:
            if not isinstance(binding, Mapping):
                raise ValueError("Expected candidate mappings")  # noqa: TRY004 - binding validation API
            if output_names.intersection(binding):
                raise ValueError("Prediction output collides with an input column")
            row = MappingProxyType(dict(binding))
            if self.projection is not None and any(
                c not in row and c not in output_names for c in self.projection
            ):
                raise ValueError("Projection contains a missing input column")
            rows.append(row)
            for columns, name in validators.items():
                if any(c not in row for c in columns):
                    raise ValueError(f"Prediction {name} needs columns {columns}")
                if any(row[c] is None for c in columns):
                    shared[columns].append(None)
                    continue
                if any(type(row[c]) is not str for c in columns):
                    raise ValueError("Candidate node IDs and relations must be strings or null")
                shared[columns].append(
                    (
                        self.graph.node_index(row[columns[0]]),
                        self.graph.relation_index(row[columns[1]]),
                        self.graph.node_index(row[columns[2]]),
                    )
                )
        return rows, bindings

    def _evaluate_group(self, group, ordinals, bindings, *, cache=None, pending=None):
        before = time.perf_counter()
        thresholds = dict(self.thresholds)
        evaluation = sorted(group, key=lambda p: p.name not in thresholds)
        pending = {} if pending is None else pending
        heads = {}
        for i in ordinals:
            # Relation columns may differ within a compatible feature group.
            # A null relation in one prediction does not null the other ones.
            head = next((bindings[p.name][i][0] for p in group
                         if bindings[p.name][i] is not None), None)
            heads.setdefault(head, []).append(i)
        output, passed, looked_up = {}, set(), {}
        expansions = calls = peak = type_visits = neighbor_visits = hits = misses = 0
        extractor = group[0].model
        for head, indices in heads.items():
            surviving = indices
            features, positions, scores = None, {}, {}
            predictions = {}
            for p in evaluation:
                reject_pair = getattr(p.model, "rejects_pair", None)
                score_kind = getattr(p.model, "score_kind", "backend_score")
                remaining = []
                for i in surviving:
                    bound = bindings[p.name][i]
                    pair_key = None
                    if bound is None:
                        value, status = None, "null_input"
                        prediction_key = p.name, None
                    else:
                        h, relation, target = bound
                        pair_key = ((self.graph.snapshot_id, p.model.model_id, h, relation, target)
                                    if cache is not None else None)
                        prediction_key = p.name, relation, target
                        found, value = False, None
                        if cache is not None and pair_key in pending:
                            found, value = True, pending[pair_key]
                        elif cache is not None:
                            if pair_key not in looked_up:
                                looked_up[pair_key] = cache._get(pair_key)
                                hits += int(looked_up[pair_key][0])
                                misses += int(not looked_up[pair_key][0])
                            found, value = looked_up[pair_key]
                        if not found:
                            if callable(reject_pair) and reject_pair(self.graph, h, target):
                                value = None
                            else:
                                if features is None:
                                    # Retain one source's preparation across the
                                    # surviving operators, never a whole window
                                    # of expanded source features. The union is
                                    # needed when relation-null patterns differ.
                                    targets = tuple(sorted({bindings[q.name][j][2]
                                        for q in group for j in surviving
                                        if bindings[q.name][j] is not None}))
                                    targeted = getattr(extractor, "expand_targets", None)
                                    features = (targeted(self.graph, h, targets, self.limits)
                                        if callable(targeted)
                                        else extractor.expand(self.graph, h, self.limits))
                                    expansions += 1
                                    type_visits += features.type_visits
                                    neighbor_visits += getattr(features, "neighbor_visits", 0)
                                    peak = max(peak, features.numeric_bytes)
                                    positions = {int(t): j for j, t in enumerate(features.candidates)}
                                key = p.model.model_id, relation
                                if key not in scores:
                                    values = p.model.score(features, relation)
                                    if (values.shape != features.candidates.shape
                                            or not np.isfinite(values).all()):
                                        raise ValueError("Backend returned invalid candidate scores")
                                    scores[key] = values
                                    calls += 1
                                value = float(scores[key][positions[target]]) if target in positions else None
                            if cache is not None:
                                pending[pair_key] = value
                        status = "unsupported" if value is None else "scored"
                    if p.name in thresholds and (value is None or value < thresholds[p.name]):
                        # Rejected rows need neither later predictions nor
                        # their output objects, even inside a fused group.
                        output.pop(i, None)
                        continue
                    if prediction_key not in predictions:
                        predictions[prediction_key] = Prediction(
                            value, status, self.graph.snapshot_id, p.model.model_id, score_kind
                        )
                    output.setdefault(i, {})[p.name] = predictions[prediction_key]
                    remaining.append(i)
                surviving = remaining
                if not surviving:
                    break
            passed.update(surviving)
        passing = [i for i in ordinals if i in passed]
        profile = StepProfile(
            tuple(p.name for p in group), len(ordinals), len(passing), expansions,
            calls, peak, type_visits, neighbor_visits, time.perf_counter() - before, hits, misses
        )
        return output, passing, profile

    def calibrate(self, sample, *, fused=True):
        """Measure each physical group on one bounded sample, without tuning scores."""
        window = tuple(islice(iter(sample), self.limits.window_size))
        if not window:
            raise ValueError("Calibration needs a nonempty sample")
        _, bindings = self._validate(window)
        estimates = []
        for group in self._groups(fused):
            _, passing, profile = self._evaluate_group(group, range(len(window)), bindings)
            estimates.append(
                CostEstimate(
                    profile.outputs,
                    profile.elapsed_seconds / len(window),
                    len(passing) / len(window),
                    len(window),
                )
            )
        return PlanStatistics(self.plan_id, fused, tuple(estimates))

    def iter_batches(self, bindings, *, fused=True, statistics=None, cache=None):
        if cache is not None and not isinstance(cache, BindingCache):
            raise TypeError("cache must be a BindingCache")
        groups = self._ordered(fused, statistics)
        iterator = iter(bindings)
        while window := tuple(islice(iterator, self.limits.window_size)):
            rows, bound = self._validate(window)
            surviving = list(range(len(rows)))
            predictions = {i: {} for i in surviving}
            profiles = []
            pending = {}
            for group in groups:
                if not surviving:
                    break
                values, surviving, profile = self._evaluate_group(
                    group, surviving, bound, cache=cache, pending=pending
                )
                profiles.append(profile)
                for i, columns in values.items():
                    predictions[i].update(columns)
            result = []
            for i in surviving:
                record = {**rows[i], **{p.name: predictions[i][p.name] for p in self.predictions}}
                if self.projection is not None:
                    record = {c: record[c] for c in self.projection}
                result.append(MappingProxyType(record))
            if cache is not None:
                # All operators in this window succeeded. Partial work from a
                # failed later operator must never populate the persistent cache.
                for key, value in pending.items():
                    cache._put(key, value)
            yield PlanResult(
                tuple(result),
                tuple(profiles),
                self.plan_id,
                tuple(p.name for p in self.predictions),
            )

    def run(self, bindings, *, fused=True, statistics=None, cache=None):
        rows, steps = [], []
        for batch in self.iter_batches(bindings, fused=fused, statistics=statistics, cache=cache):
            rows.extend(batch.rows)
            steps.extend(batch.steps)
        return PlanResult(
            tuple(rows), tuple(steps), self.plan_id, tuple(p.name for p in self.predictions)
        )
