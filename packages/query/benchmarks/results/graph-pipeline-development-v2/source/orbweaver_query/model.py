"""Model boundary and the conventional learned explicit-path implementation."""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from ._validation import immutable_array, names, positive_int
from .graph import GraphSnapshot


class ResourceLimitError(RuntimeError):
    """Exact inference exceeded its explicit budget; no approximate result exists."""


@dataclass(frozen=True)
class Limits:
    window_size: int = 256
    max_expansion_states: int = 1_000_000
    max_type_visits: int = 10_000_000
    max_neighbor_visits: int = 10_000_000
    max_intermediate_rows: int = 100_000
    max_prepared_bytes: int = 16 * 2**20

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            positive_int(getattr(self, name), name, minimum=0 if name == "max_prepared_bytes" else 1)


@dataclass(frozen=True)
class PathFeatures:
    candidates: np.ndarray
    base: np.ndarray
    row: np.ndarray
    column: np.ndarray
    proportions: np.ndarray
    type_visits: int
    peak_states: int

    @property
    def numeric_bytes(self):
        return sum(getattr(self, key).nbytes for key in
                   ("candidates", "base", "row", "column", "proportions"))


def _path_features(graph, symbols, terminal, visits, peak_states):
    candidates = np.array(sorted({n for n, _ in terminal}), dtype=np.int64)
    positions = {int(n): i for i, n in enumerate(candidates)}
    entries = sorted(terminal.items())
    row = np.array([positions[n] for (n, _), _ in entries], dtype=np.int64)
    column = np.array([c for (_, c), _ in entries], dtype=np.int64)
    values = np.array([v for _, v in entries], dtype=np.float64)
    mass = np.bincount(row, weights=values, minlength=len(candidates))
    if np.any(mass <= 0) or not np.isfinite(mass).all():
        raise ValueError("Nonpositive or nonfinite candidate walk mass")
    proportions = values / mass[row]
    short = column < symbols * symbols
    length2 = np.bincount(row[short], weights=proportions[short], minlength=len(candidates))
    base = np.column_stack((np.ones(len(candidates)), np.log(mass),
                            np.log1p(graph.degree[candidates]), length2))
    return PathFeatures(*(immutable_array(a) for a in
                          (candidates, base, row, column, proportions)), visits, peak_states)


@dataclass(frozen=True)
class PreparedPaths:
    """Immutable two-hop walk state; no target features or prediction answers.

    Completion reports only new type visits. ``type_visits`` records the initial
    preparation work, which the execution owner must charge once. Every completion
    checks its total preparation-plus-completion work against the supplied limits.
    """

    graph: GraphSnapshot
    head: int
    nodes: np.ndarray
    codes: np.ndarray
    values: np.ndarray
    type_visits: int
    peak_states: int

    @property
    def numeric_bytes(self):
        return self.nodes.nbytes + self.codes.nbytes + self.values.nbytes

    def expand_targets(self, targets, limits):
        graph, s = self.graph, 2 * len(self.graph.relations)
        targets = tuple(targets)
        if any(type(n) is not int or not 0 <= n < len(graph.node_ids) for n in targets):
            raise ValueError("Target index outside graph")
        if self.peak_states > limits.max_expansion_states:
            raise ResourceLimitError("Prepared path state exceeds max_expansion_states")
        if self.type_visits > limits.max_type_visits:
            raise ResourceLimitError("Prepared path state exceeds max_type_visits")
        targets = frozenset(targets) - {self.head, *graph.neighbors(self.head).tolist()}
        if not targets:
            return _path_features(graph, s, {}, 0, self.peak_states)
        predecessors = None
        if sum(int(graph.degree[n]) for n in targets) <= limits.max_expansion_states:
            predecessors = {int(n) for target in targets for n in graph.neighbors(target)}
        terminal, following = defaultdict(float), defaultdict(float)
        visits, adjacency = 0, {}
        for node, code, value in zip(self.nodes.tolist(), self.codes.tolist(), self.values.tolist()):
            if node in targets:
                terminal[node, code] += (2 / 3) * value
                if len(terminal) > limits.max_expansion_states:
                    raise ResourceLimitError("Path features exceed max_expansion_states")
            if not targets or (predecessors is not None and node not in predecessors):
                continue
            if node not in adjacency:
                begin, end = graph.indptr[node:node + 2]
                symbols_in_node = int(graph.type_indptr[end] - graph.type_indptr[begin])
                if self.type_visits + visits + symbols_in_node > limits.max_type_visits:
                    raise ResourceLimitError("Prepared path completion exceeds max_type_visits")
                neighbors = []
                for edge in range(begin, end):
                    destination = int(graph.indices[edge])
                    if destination in targets:
                        lo, hi = graph.type_indptr[edge:edge + 2]
                        neighbors.append((destination, int(hi - lo), graph.symbols[lo:hi].tolist()))
                adjacency[node] = int(graph.degree[node]), neighbors, symbols_in_node
            degree, neighbors, symbols_in_node = adjacency[node]
            visits += symbols_in_node
            if self.type_visits + visits > limits.max_type_visits:
                raise ResourceLimitError("Prepared path completion exceeds max_type_visits")
            for destination, multiplicity, symbols in neighbors:
                increment = value / degree / multiplicity
                for symbol in symbols:
                    following[destination, code * s + symbol] += increment
                    if len(following) > limits.max_expansion_states:
                        raise ResourceLimitError("Path expansion exceeds max_expansion_states")
        for (node, code), value in sorted(following.items()):
            terminal[node, s * s + code] += (1 / 3) * value
            if len(terminal) > limits.max_expansion_states:
                raise ResourceLimitError("Path features exceed max_expansion_states")
        return _path_features(graph, s, terminal, visits, max(self.peak_states, len(following)))


class SourceFeatures(Protocol):
    """Minimal result envelope; each backend owns its feature representation."""

    candidates: np.ndarray
    type_visits: int
    peak_states: int

    @property
    def numeric_bytes(self) -> int: ...


class GraphModel(Protocol):
    """Deterministic pure scoring with source-only shared features.

    A model with relation-conditioned features needs a different reuse key and
    must not implement this contract by silently ignoring that dependence.

    Optionally expose ``feature_id`` to share preparation with other models.
    Equal feature IDs promise identical candidate support, representation, and
    values for the same snapshot, source, requested targets, and limits. Features
    must be immutable and scoring must not mutate them. The contract includes
    both ``expand`` and optional ``expand_targets``. Without a feature ID, reuse
    remains scoped to the model ID. Model identity includes every scoring choice.

    An optional ``prepare_source(graph, head, limits)`` may return immutable
    intermediate state with ``expand_targets(targets, limits)``, ``numeric_bytes``
    and initial ``type_visits``. Its completions obey the same exact feature
    contract and report only newly executed work. Equal ``preparation_id`` values
    additionally promise compatible intermediate state; without that identity,
    its lifetime/reuse is confined to one model identity. Limits still apply to
    a complete inference, even when its initial state was prepared earlier.
    """

    model_id: str
    relations: tuple[str, ...]

    def expand(self, graph: GraphSnapshot, head: int, limits: Limits) -> SourceFeatures: ...

    def score(self, features: SourceFeatures, relation: int) -> np.ndarray: ...


@dataclass(frozen=True, eq=False, init=False)
class ExplicitPathModel:
    """Linear learned scores over complete two/three-hop typed path features.

    Coefficients have one row per query relation. Each row contains four base
    terms, (2R)^2 pair terms, and (2R)^3 triple terms. Schema order is binding.
    This model provides ranking logits, not factual probabilities.
    """

    relations: tuple[str, ...]
    coefficient: np.ndarray
    model_id: str
    candidate_support = "two_or_three_hops_excluding_source_and_existing_neighbors"
    score_kind = "ranking_logit"
    feature_id = "orbweaver-explicit-path-features-v1"
    preparation_id = "orbweaver-explicit-path-prefix-v1"

    def __init__(self, coefficient, *, relations):
        relations = names(relations, "relations")
        r, s = len(relations), 2 * len(relations)
        coefficient = np.asarray(coefficient, dtype=np.float64)
        if coefficient.shape != (r, 4 + s*s + s**3) or not np.isfinite(coefficient).all():
            raise ValueError(f"Expected finite coefficients with shape {(r, 4 + s*s + s**3)}")
        coefficient = immutable_array(coefficient, "<f8")
        digest = hashlib.sha256(b"orbweaver-query-explicit-path-v1\0")
        digest.update(json.dumps(relations, separators=(",", ":")).encode())
        digest.update(coefficient.tobytes())
        object.__setattr__(self, "relations", relations)
        object.__setattr__(self, "coefficient", coefficient)
        object.__setattr__(self, "model_id", digest.hexdigest())

    def save(self, path):
        with Path(path).open("xb") as stream:
            np.savez_compressed(stream, format=np.array("orbweaver-query-explicit-path-v1"),
                                relations=np.array(self.relations), coefficient=self.coefficient,
                                model_id=np.array(self.model_id))

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as artifact:
            if (set(artifact.files) != {"format", "relations", "coefficient", "model_id"}
                    or artifact["format"].shape != ()
                    or artifact["format"].item() != "orbweaver-query-explicit-path-v1"):
                raise ValueError("Unsupported model artifact format")
            model = cls(artifact["coefficient"], relations=artifact["relations"].tolist())
            if artifact["model_id"].shape != () or model.model_id != artifact["model_id"].item():
                raise ValueError("Model artifact content identity mismatch")
            return model

    def expand(self, graph, head, limits):
        return self._expand(graph, head, limits, targets=None)

    def rejects_pair(self, graph, head, target):
        """Cheap sufficient rejection; False does not promise reachability."""
        if head == target:
            return True
        neighbors = graph.neighbors(head)
        index = int(np.searchsorted(neighbors, target))
        return index < len(neighbors) and int(neighbors[index]) == target

    def expand_targets(self, graph, head, targets, limits):
        """Exact features for requested endpoints using the full evidence graph.

        Intermediate vertices and degrees retain their original meaning. Only
        states unable to terminate at a requested endpoint are discarded. The
        retained sums have the same iteration order as full expansion.
        """
        targets = tuple(targets)
        if any(type(n) is not int or not 0 <= n < len(graph.node_ids) for n in targets):
            raise ValueError("Target index outside graph")
        return self._expand(graph, head, limits, targets=frozenset(targets))

    def prepare_source(self, graph, head, limits):
        """Prepare exact target-independent walk prefixes for multiple completions."""
        if graph.relations != self.relations:
            raise ValueError("Graph and model ordered relation schemas differ")
        if type(head) is not int or not 0 <= head < len(graph.node_ids):
            raise ValueError("Source index outside graph")
        state, visits, peak, adjacency = {(head, 0): 1.0}, 0, 1, {}
        s = 2 * len(self.relations)
        for _ in range(2):
            following = defaultdict(float)
            for (node, prefix), value in sorted(state.items()):
                if node not in adjacency:
                    begin, end = graph.indptr[node:node + 2]
                    count = int(graph.type_indptr[end] - graph.type_indptr[begin])
                    if visits + count > limits.max_type_visits:
                        raise ResourceLimitError("Path preparation exceeds max_type_visits")
                    neighbors = []
                    for edge in range(begin, end):
                        lo, hi = graph.type_indptr[edge:edge + 2]
                        neighbors.append((int(graph.indices[edge]), int(hi - lo),
                                          graph.symbols[lo:hi].tolist()))
                    adjacency[node] = int(graph.degree[node]), neighbors, count
                degree, neighbors, count = adjacency[node]
                visits += count
                if visits > limits.max_type_visits:
                    raise ResourceLimitError("Path preparation exceeds max_type_visits")
                for dest, multiplicity, symbols in neighbors:
                    increment = value / degree / multiplicity
                    for symbol in symbols:
                        following[dest, prefix * s + symbol] += increment
                        if len(following) > limits.max_expansion_states:
                            raise ResourceLimitError("Path preparation exceeds max_expansion_states")
            state = following
            peak = max(peak, len(state))
        entries = sorted(state.items())
        return PreparedPaths(graph, head,
                             immutable_array([n for (n, _), _ in entries], np.int64),
                             immutable_array([c for (_, c), _ in entries], np.int64),
                             immutable_array([v for _, v in entries], np.float64), visits, peak)

    def _expand(self, graph, head, limits, targets):
        if graph.relations != self.relations:
            raise ValueError("Graph and model ordered relation schemas differ")
        if type(head) is not int or not 0 <= head < len(graph.node_ids):
            raise ValueError("Source index outside graph")
        s = 2 * len(self.relations)
        excluded = {head, *graph.neighbors(head).tolist()}
        if targets is not None:
            targets = targets - excluded
        # A two-hop state can contribute to the three-hop answer only if its
        # vertex neighbors a target. Reverse reachability is sound because the
        # snapshot stores inverse traversal symbols for every asserted edge.
        # Avoid an unbounded secondary index for a large target set: terminal
        # filtering alone remains exact, even without this extra optimization.
        predecessors = None
        if targets is not None:
            degree_sum = sum(int(graph.degree[n]) for n in targets)
            if degree_sum <= limits.max_expansion_states:
                predecessors = {int(n) for target in targets for n in graph.neighbors(target)}
        state, terminal = {(head, 0): 1.0}, defaultdict(float)
        if targets == frozenset():
            state = {}
        visits, peak_states = 0, 1
        adjacency = {}
        for step in range(3):
            following = defaultdict(float)
            for (node, prefix), value in sorted(state.items()):
                if node not in adjacency:
                    begin, end = graph.indptr[node:node + 2]
                    symbols_in_node = int(graph.type_indptr[end] - graph.type_indptr[begin])
                    if visits + symbols_in_node > limits.max_type_visits:
                        raise ResourceLimitError("Path expansion exceeds max_type_visits")
                    neighbors = []
                    for edge in range(begin, end):
                        lo, hi = graph.type_indptr[edge:edge + 2]
                        neighbors.append((int(graph.indices[edge]), int(hi - lo),
                                          graph.symbols[lo:hi].tolist()))
                    adjacency[node] = int(graph.degree[node]), neighbors, symbols_in_node
                degree, neighbors, symbols_in_node = adjacency[node]
                if visits + symbols_in_node > limits.max_type_visits:
                    raise ResourceLimitError("Path expansion exceeds max_type_visits")
                visits += symbols_in_node
                for dest, multiplicity, symbols in neighbors:
                    if targets is not None and (
                        (step == 2 and dest not in targets)
                        or (step == 1 and predecessors is not None
                            and dest not in predecessors and dest not in targets)
                    ):
                        continue
                    increment = value / degree / multiplicity
                    for symbol in symbols:
                        key = dest, prefix*s + symbol
                        following[key] += increment
                        if len(following) > limits.max_expansion_states:
                            raise ResourceLimitError("Path expansion exceeds max_expansion_states")
            state = following
            peak_states = max(peak_states, len(state))
            if step >= 1:
                weight, offset = (2/3, 0) if step == 1 else (1/3, s*s)
                for (node, code), value in sorted(state.items()):
                    if node not in excluded and (targets is None or node in targets):
                        terminal[node, offset + code] += weight * value
                        if len(terminal) > limits.max_expansion_states:
                            raise ResourceLimitError("Path features exceed max_expansion_states")
        return _path_features(graph, s, terminal, visits, peak_states)

    def score(self, features, relation):
        if type(relation) is not int or not 0 <= relation < len(self.relations):
            raise ValueError("Relation index outside model schema")
        weight = self.coefficient[relation]
        scores = features.base @ weight[:4] + np.bincount(
            features.row, weights=features.proportions * weight[features.column + 4],
            minlength=len(features.candidates))
        if not np.isfinite(scores).all():
            raise ValueError("Nonfinite model scores")
        return immutable_array(scores)
