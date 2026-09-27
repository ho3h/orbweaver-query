"""Typed graph expansion interleaved with exact, dependency-aware inference."""

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from itertools import islice
from types import MappingProxyType

import numpy as np

from .cache import BindingCache
from .model import ResourceLimitError
from .plan import PlanResult, QueryPlan, StepProfile, _name
from .preparation import PreparationScope


@dataclass(frozen=True)
class Expand:
    source: str
    target: str
    relation: str | None = None
    direction: str = "out"
    edge_relation: str | None = None
    optional: bool = False

    def __post_init__(self):
        _name(self.source)
        _name(self.target)
        if self.relation is not None:
            _name(self.relation)
        if self.edge_relation is not None:
            _name(self.edge_relation)
        if len({self.source, *self.outputs}) != 1 + len(self.outputs):
            raise ValueError("Expansion input and output columns must be distinct")
        if self.direction not in ("out", "in", "both") or type(self.optional) is not bool:
            raise ValueError("Invalid expansion direction or optional flag")

    @property
    def outputs(self):
        return (self.target,) if self.edge_relation is None else (self.target, self.edge_relation)


@dataclass(frozen=True)
class GraphPipeline:
    """A bounded, bag-preserving sequence of inference and typed expansion stages.

    Construct with ``QueryPlan.expand``. Expansion joins the immutable evidence,
    not the live database. Score predicates independent of an expansion's new
    columns may move before it. Every stage preserves parent order and each
    parent's canonical target-index/edge-symbol order, including parallel types
    and reciprocal edges. No intermediate or output limit silently truncates.
    """

    stages: tuple[QueryPlan, ...]
    expansions: tuple[Expand, ...]
    projection: tuple[str, ...] | None = None

    def __post_init__(self):
        if (not self.expansions or len(self.stages) != len(self.expansions) + 1
                or any(not isinstance(s, QueryPlan) for s in self.stages)
                or any(not isinstance(e, Expand) for e in self.expansions)):
            raise ValueError("Expected inference stages separated by graph expansions")
        for s in self.stages:
            if (s.graph.snapshot_id != self.graph.snapshot_id or s.limits != self.limits
                    or s.projection is not None):
                raise ValueError("Pipeline stages need identical evidence/limits and no projection")
        outputs = self.output_columns
        if len(set(outputs)) != len(outputs):
            raise ValueError("Pipeline output names must be unique")
        generated, predictions = {}, set(self.prediction_columns)
        for i, stage in enumerate(self.stages):
            for p in stage.predictions:
                for column, role in ((p.head, "node"), (p.relation, "relation"), (p.target, "node")):
                    self._check_dependency(column, role, generated, outputs, predictions)
            if i < len(self.expansions):
                e = self.expansions[i]
                self._check_dependency(e.source, "node", generated, outputs, predictions)
                if e.relation is not None:
                    self.graph.relation_index(e.relation)
                generated[e.target] = "node"
                if e.edge_relation is not None:
                    generated[e.edge_relation] = "relation"
        if self.projection is not None:
            for c in self.projection:
                _name(c)
            if len(set(self.projection)) != len(self.projection):
                raise ValueError("Projection columns must be unique")

    @staticmethod
    def _check_dependency(column, role, generated, outputs, predictions):
        if column in predictions:
            raise ValueError("Prediction objects cannot be node or relation inputs")
        if column in outputs and column not in generated:
            raise ValueError(f"Column {column!r} is used before its expansion")
        if column in generated and generated[column] != role:
            raise ValueError("Expanded column has the wrong node/relation role")

    @property
    def graph(self):
        return self.stages[0].graph

    @property
    def limits(self):
        return self.stages[0].limits

    @property
    def prediction_columns(self):
        return tuple(p.name for s in self.stages for p in s.predictions)

    @property
    def output_columns(self):
        columns = []
        for i, s in enumerate(self.stages):
            columns.extend(p.name for p in s.predictions)
            if i < len(self.expansions):
                columns.extend(self.expansions[i].outputs)
        return tuple(columns)

    @property
    def plan_id(self):
        payload = {"format": "orbweaver-graph-pipeline-v1",
                   "stages": [s.plan_id for s in self.stages],
                   "expansions": [vars(e) for e in self.expansions],
                   "projection": self.projection}
        return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                         separators=(",", ":")).encode()).hexdigest()

    def _terminal(self):
        if self.projection is not None:
            raise ValueError("Projection must be terminal")

    def predict(self, name, model, *, head="head", relation="relation", target="target"):
        self._terminal()
        last = self.stages[-1].predict(name, model, head=head, relation=relation, target=target)
        return replace(self, stages=(*self.stages[:-1], last))

    def where_score(self, name, minimum):
        self._terminal()
        last = self.stages[-1].where_score(name, minimum)
        return replace(self, stages=(*self.stages[:-1], last))

    def expand(self, *, source, target, relation=None, direction="out",
               edge_relation=None, optional=False):
        self._terminal()
        return replace(self, stages=(*self.stages, QueryPlan(self.graph, limits=self.limits)),
                       expansions=(*self.expansions,
                                   Expand(source, target, relation, direction,
                                          edge_relation, optional)))

    def project(self, *columns):
        return replace(self, projection=tuple(columns))

    def _physical(self, optimize):
        if type(optimize) is not bool:
            raise ValueError("optimize must be a boolean")
        if not optimize:
            return self.stages, []
        available = {c: i + 1 for i, e in enumerate(self.expansions) for c in e.outputs}
        predictions = [[] for _ in self.stages]
        filters = [[] for _ in self.stages]
        moves = []
        for i, logical in enumerate(self.stages):
            thresholds = dict(logical.thresholds)
            for p in logical.predictions:
                destination = i
                if optimize and p.name in thresholds:
                    destination = max(available.get(c, 0) for c in (p.head, p.relation, p.target))
                predictions[destination].append(p)
                if p.name in thresholds:
                    filters[destination].append((p.name, thresholds[p.name]))
                if destination != i:
                    moves.append({"prediction": p.name, "from_stage": i, "to_stage": destination,
                                  "reason": "filter inputs available before expansion"})
        stages = tuple(QueryPlan(self.graph, tuple(p), tuple(t), limits=self.limits)
                       for p, t in zip(predictions, filters))
        return stages, moves

    def explain(self, *, fused=True, optimize=True, reuse_preparation=True, coalesce_targets=True):
        if type(reuse_preparation) is not bool:
            raise ValueError("reuse_preparation must be a boolean")
        if type(coalesce_targets) is not bool:
            raise ValueError("coalesce_targets must be a boolean")
        stages, moves = self._physical(optimize)
        return {"plan_id": self.plan_id, "graph_snapshot": self.graph.snapshot_id,
                "logical_stages": [s.explain(fused=fused) for s in self.stages],
                "physical_stages": [s.explain(fused=fused) for s in stages],
                "expansions": [asdict(e) for e in self.expansions], "predicate_moves": moves,
                "projection": self.projection, "preserves_order_and_bags": True,
                "materialization": "bounded stages per root input window",
                "validation": "root dependencies before execution; generated bindings per stage",
                "cache_commit": "after the entire root input window succeeds",
                "source_preparation": ("reuse model-internal state across scoring batches"
                                       if reuse_preparation else "disabled"),
                "target_coalescing": reuse_preparation and coalesce_targets,
                "limits": asdict(self.limits)}

    def _validate_roots(self, window):
        generated = set(self.output_columns)
        rows = []
        for binding in window:
            if not isinstance(binding, Mapping):
                raise ValueError("Expected candidate mappings")  # noqa: TRY004
            if generated.intersection(binding):
                raise ValueError("Pipeline output collides with an input column")
            row = dict(binding)
            for stage in self.stages:
                for p in stage.predictions:
                    inputs = ((p.head, "node"), (p.relation, "relation"), (p.target, "node"))
                    external = [(c, role) for c, role in inputs if c not in generated]
                    if any(c not in row for c, _ in external):
                        raise ValueError("Prediction needs a missing root input column")
                    if any(row[c] is None for c, _ in external):
                        continue
                    for c, role in external:
                        self._validate_value(row[c], role)
            for e in self.expansions:
                if e.source not in generated:
                    if e.source not in row:
                        raise ValueError("Expansion needs a missing root input column")
                    self._validate_value(row[e.source], "node")
            if self.projection is not None and any(
                    c not in row and c not in generated for c in self.projection):
                raise ValueError("Projection contains a missing input column")
            rows.append(MappingProxyType(row))
        return rows

    def _validate_value(self, value, role):
        if value is None:
            return
        if type(value) is not str:
            raise ValueError("Candidate node IDs and relations must be strings or null")
        (self.graph.node_index if role == "node" else self.graph.relation_index)(value)

    def _expand(self, rows, e, stage):
        before = time.perf_counter()
        graph, result = self.graph, []
        r = len(graph.relations)
        relation = None if e.relation is None else graph.relation_index(e.relation)
        visits = neighbors = 0

        def append(row, target, edge_type):
            if len(result) >= self.limits.max_intermediate_rows:
                raise ResourceLimitError("Graph expansion exceeds max_intermediate_rows")
            value = {**row, e.target: target}
            if e.edge_relation is not None:
                value[e.edge_relation] = edge_type
            result.append(MappingProxyType(value))

        for row in rows:
            count = len(result)
            if row[e.source] is not None:
                source = graph.node_index(row[e.source])
                begin, end = graph.indptr[source:source + 2]
                lo, hi = int(graph.type_indptr[begin]), int(graph.type_indptr[end])
                neighbors += int(end - begin)
                visits += hi - lo
                if neighbors > self.limits.max_neighbor_visits:
                    raise ResourceLimitError("Graph expansion exceeds max_neighbor_visits")
                if visits > self.limits.max_type_visits:
                    raise ResourceLimitError("Graph expansion exceeds max_type_visits")
                symbols = graph.symbols[lo:hi]
                if e.direction == "both" and relation is None:
                    count_matches = hi - lo
                    if len(result) + count_matches > self.limits.max_intermediate_rows:
                        raise ResourceLimitError("Graph expansion exceeds max_intermediate_rows")
                    destinations = np.repeat(graph.indices[begin:end],
                                             np.diff(graph.type_indptr[begin:end + 1]))
                else:
                    matches = np.ones(len(symbols), dtype=bool)
                    if e.direction != "both":
                        matches &= symbols < r if e.direction == "out" else symbols >= r
                    if relation is not None:
                        matches &= symbols % r == relation
                    positions = np.flatnonzero(matches)
                    if len(result) + len(positions) > self.limits.max_intermediate_rows:
                        raise ResourceLimitError("Graph expansion exceeds max_intermediate_rows")
                    edges = np.searchsorted(graph.type_indptr[begin:end + 1],
                                            positions + lo, side="right") - 1
                    destinations = graph.indices[begin + edges]
                    symbols = symbols[positions]
                if e.edge_relation is None:
                    result.extend(MappingProxyType({**row, e.target: graph.node_ids[n]})
                                  for n in destinations.tolist())
                else:
                    for target, symbol in zip(destinations.tolist(), symbols.tolist()):
                        append(row, graph.node_ids[target], graph.relations[symbol % r])
            if e.optional and len(result) == count:
                append(row, None, None)
        return result, StepProfile(e.outputs, len(rows), len(result), 0, 0, 0, 0, neighbors,
                                   time.perf_counter() - before, operator="expand", stage=stage,
                                   edge_visits=visits)

    def iter_batches(self, bindings, *, fused=True, optimize=True, cache=None, reuse_preparation=True,
                     coalesce_targets=True):
        if cache is not None and not isinstance(cache, BindingCache):
            raise TypeError("cache must be a BindingCache")
        if type(reuse_preparation) is not bool:
            raise ValueError("reuse_preparation must be a boolean")
        if type(coalesce_targets) is not bool:
            raise ValueError("coalesce_targets must be a boolean")
        stages, _ = self._physical(optimize)
        groups = [s._ordered(fused, None) for s in stages]
        identity = self.plan_id
        iterator, size = iter(bindings), self.limits.window_size
        generated = set(self.output_columns)
        while window := tuple(islice(iterator, size)):
            if len(window) > self.limits.max_intermediate_rows:
                raise ResourceLimitError("Root window exceeds max_intermediate_rows")
            rows = self._validate_roots(window)
            profiles, pending = [], {}
            preparation = (PreparationScope(self.limits.max_prepared_bytes,
                                             coalesce_targets=coalesce_targets)
                           if reuse_preparation else None)
            for i, stage in enumerate(stages):
                if stage.predictions and rows:
                    scored = []
                    if preparation is not None:
                        preparation.hint(self.graph, rows, groups[i], size,
                                         cache=cache, pending=pending)
                    for offset in range(0, len(rows), size):
                        batch = stage._execute_window(rows[offset:offset + size], groups[i],
                                                      cache=cache, pending=pending,
                                                      preparation=preparation, plan_id=identity,
                                                      owned=True,
                                                      projection=self.projection if i == len(stages)-1 else None)
                        scored.extend(batch.rows)
                        profiles.extend(replace(s, stage=i) for s in batch.steps)
                    rows = scored
                if i < len(self.expansions):
                    rows, profile = self._expand(rows, self.expansions[i], i)
                    profiles.append(profile)
            # Restore logical output-column order after predicate movement.
            if self.projection is not None and stages[-1].predictions:
                result = rows
            else:
                result = []
                for row in rows:
                    columns = (self.projection if self.projection is not None else
                               (*[c for c in row if c not in generated], *self.output_columns))
                    result.append(MappingProxyType({c: row[c] for c in columns}))
            if cache is not None:
                for key, value in pending.items():
                    cache._put(key, value)
            # A root window is atomic for results and cache writes. Each stage
            # has an explicit row bound; output batches still obey window_size.
            for offset in range(0, max(1, len(result)), size):
                yield PlanResult(tuple(result[offset:offset + size]),
                                 tuple(profiles) if offset == 0 else (),
                                 identity, self.prediction_columns)

    def run(self, bindings, *, fused=True, optimize=True, cache=None, reuse_preparation=True,
            coalesce_targets=True):
        rows, profiles, identity = [], [], None
        for batch in self.iter_batches(bindings, fused=fused, optimize=optimize, cache=cache,
                                       reuse_preparation=reuse_preparation,
                                       coalesce_targets=coalesce_targets):
            rows.extend(batch.rows)
            profiles.extend(batch.steps)
            identity = batch.plan_id
        return PlanResult(tuple(rows), tuple(profiles),
                          self.plan_id if identity is None else identity, self.prediction_columns)
