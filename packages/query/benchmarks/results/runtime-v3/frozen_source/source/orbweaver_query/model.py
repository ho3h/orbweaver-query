"""Model boundary and the conventional learned explicit-path implementation."""

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
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

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            positive_int(getattr(self, name), name)


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


class GraphModel(Protocol):
    """Deterministic pure scoring with source-only shared features.

    A model with relation-conditioned features needs a different reuse key and
    must not implement this contract by silently ignoring that dependence.
    """

    model_id: str
    relations: tuple[str, ...]

    def expand(self, graph: GraphSnapshot, head: int, limits: Limits) -> PathFeatures: ...

    def score(self, features: PathFeatures, relation: int) -> np.ndarray: ...


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
        if graph.relations != self.relations:
            raise ValueError("Graph and model ordered relation schemas differ")
        if type(head) is not int or not 0 <= head < len(graph.node_ids):
            raise ValueError("Source index outside graph")
        s = 2 * len(self.relations)
        excluded = {head, *graph.neighbors(head).tolist()}
        state, terminal = {(head, 0): 1.0}, defaultdict(float)
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
                    if node not in excluded:
                        terminal[node, offset + code] += weight * value
                        if len(terminal) > limits.max_expansion_states:
                            raise ResourceLimitError("Path features exceed max_expansion_states")
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
        short = column < s*s
        length2 = np.bincount(row[short], weights=proportions[short], minlength=len(candidates))
        base = np.column_stack((np.ones(len(candidates)), np.log(mass),
                                np.log1p(graph.degree[candidates]), length2))
        return PathFeatures(*(immutable_array(a) for a in
                              (candidates, base, row, column, proportions)), visits, peak_states)

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
