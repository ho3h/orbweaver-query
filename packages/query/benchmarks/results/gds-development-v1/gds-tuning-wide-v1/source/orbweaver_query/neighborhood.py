"""Conventional structural link scorers with exact bound-pair intersection."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ._validation import immutable_array, names
from .model import ResourceLimitError


@dataclass(frozen=True)
class NeighborhoodFeatures:
    candidates: np.ndarray
    values: np.ndarray
    neighbor_visits: int
    peak_states: int
    type_visits: int = 0

    @property
    def numeric_bytes(self):
        return self.candidates.nbytes + self.values.nbytes


@dataclass(frozen=True, eq=False, init=False)
class NeighborhoodModel:
    """Common neighbors, Adamic–Adar or resource allocation on topology.

    Edge labels and direction do not affect these conventional metrics. Scores
    exist for every non-self, non-adjacent pair, including zero scores between
    disconnected nodes. Zero is a ranking value, not a claim of nonexistence.
    Three compatible metrics share one explicit feature contract. These models
    require no training and make no claim to a new link prediction algorithm.
    """

    relations: tuple[str, ...]
    metric: str
    model_id: str
    feature_id = "orbweaver-neighborhood-features-v1"
    candidate_support = "all_nonself_nonadjacent_nodes"
    score_kind = "structural_link_score"
    metrics = ("common_neighbors", "adamic_adar", "resource_allocation")

    def __init__(self, *, relations, metric="resource_allocation"):
        relations = names(relations, "relations")
        if metric not in self.metrics:
            raise ValueError(f"metric must be one of {self.metrics}")
        digest = hashlib.sha256(b"orbweaver-neighborhood-model-v1\0")
        digest.update(json.dumps([relations, metric], separators=(",", ":")).encode())
        object.__setattr__(self, "relations", relations)
        object.__setattr__(self, "metric", metric)
        object.__setattr__(self, "model_id", digest.hexdigest())

    def save(self, path):
        with Path(path).open("x") as stream:
            json.dump({"format": "orbweaver-neighborhood-model-v1", "relations": self.relations,
                       "metric": self.metric, "model_id": self.model_id}, stream, sort_keys=True)
            stream.write("\n")

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text())
        if (not isinstance(data, dict) or set(data) != {"format", "relations", "metric", "model_id"}
                or data["format"] != "orbweaver-neighborhood-model-v1"):
            raise ValueError("Unsupported neighborhood artifact format")
        model = cls(relations=data["relations"], metric=data["metric"])
        if model.model_id != data["model_id"]:
            raise ValueError("Neighborhood artifact content identity mismatch")
        return model

    def rejects_pair(self, graph, head, target):
        if head == target:
            return True
        neighbors = graph.neighbors(head)
        index = int(np.searchsorted(neighbors, target))
        return index < len(neighbors) and int(neighbors[index]) == target

    def expand(self, graph, head, limits):
        return self._expand(graph, head, None, limits)

    def expand_targets(self, graph, head, targets, limits):
        targets = tuple(targets)
        if any(type(n) is not int or not 0 <= n < len(graph.node_ids) for n in targets):
            raise ValueError("Target index outside graph")
        return self._expand(graph, head, targets, limits)

    def _expand(self, graph, head, targets, limits):
        if graph.relations != self.relations:
            raise ValueError("Graph and model ordered relation schemas differ")
        if type(head) is not int or not 0 <= head < len(graph.node_ids):
            raise ValueError("Source index outside graph")
        neighbors = graph.neighbors(head)
        excluded = {head, *neighbors.tolist()}
        count = len(graph.node_ids) - len(excluded) if targets is None else len(set(targets) - excluded)
        if count > limits.max_expansion_states:
            raise ResourceLimitError("Neighborhood features exceed max_expansion_states")
        candidates = np.array(sorted(set(range(len(graph.node_ids)) if targets is None else targets)
                                     - excluded), dtype=np.int64)
        values = np.zeros((len(candidates), 3))
        visits, peak = 0, len(candidates)
        total = int(graph.degree[neighbors].sum())
        if targets is None and total > limits.max_neighbor_visits:
            raise ResourceLimitError("Neighborhood expansion exceeds max_neighbor_visits")
        if not len(candidates):
            pass
        elif targets is None and max(total, len(graph.node_ids)) <= limits.max_expansion_states:
            # A single fused scatter replaces Python work for every intermediate
            # vertex. The input order remains source-neighbor then destination.
            destinations = np.concatenate([graph.neighbors(int(n)) for n in neighbors]) \
                if len(neighbors) else np.empty(0, dtype=np.int64)
            degrees = graph.degree[neighbors]
            n = len(graph.node_ids)
            values[:, 0] = np.bincount(destinations, minlength=n)[candidates]
            for column, weights in ((1, 1 / np.log(np.maximum(degrees, 2))),
                                    (2, 1 / np.maximum(degrees, 1))):
                values[:, column] = np.bincount(
                    destinations, weights=np.repeat(weights, degrees), minlength=n)[candidates]
            visits, peak = total, max(peak, total)
        elif targets is None:
            for common in neighbors:
                destinations = graph.neighbors(int(common))
                visits += len(destinations)
                if visits > limits.max_neighbor_visits:
                    raise ResourceLimitError("Neighborhood expansion exceeds max_neighbor_visits")
                positions = np.searchsorted(candidates, destinations)
                valid = positions < len(candidates)
                positions, destinations = positions[valid], destinations[valid]
                positions = positions[candidates[positions] == destinations]
                degree = int(graph.degree[common])
                values[positions] += (1., 1 / np.log(max(degree, 2)), 1 / degree)
        else:
            for row, target in enumerate(candidates):
                other = graph.neighbors(int(target))
                visits += len(neighbors) + len(other)
                if visits > limits.max_neighbor_visits:
                    raise ResourceLimitError("Neighborhood intersection exceeds max_neighbor_visits")
                common = np.intersect1d(neighbors, other, assume_unique=True)
                peak = max(peak, len(common))
                if peak > limits.max_expansion_states:
                    raise ResourceLimitError("Neighborhood intersection exceeds max_expansion_states")
                # cumsum retains the scatter's sequential addition order.
                if len(common):
                    degrees = graph.degree[common]
                    values[row] = (len(common), np.cumsum(1 / np.log(degrees))[-1],
                                   np.cumsum(1 / degrees)[-1])
        return NeighborhoodFeatures(immutable_array(candidates), immutable_array(values), visits, peak)

    def score(self, features, relation):
        if type(relation) is not int or not 0 <= relation < len(self.relations):
            raise ValueError("Relation index outside model schema")
        if not isinstance(features, NeighborhoodFeatures):
            raise TypeError("Expected neighborhood features")
        return immutable_array(features.values[:, self.metrics.index(self.metric)])
