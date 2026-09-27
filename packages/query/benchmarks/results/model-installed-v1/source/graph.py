"""Immutable packed graph evidence with content and ordered-schema identities."""

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from pathlib import Path

import numpy as np

from ._validation import immutable_array, names


@dataclass(frozen=True, eq=False, init=False)
class GraphSnapshot:
    """Set of directed typed edges; traversal also exposes inverse symbols.

    Integers in triples index the supplied ordered node/relation names. Parallel
    distinct types survive; duplicate triples collapse. Self edges are rejected
    because the current learned path model was trained without them.
    """

    node_ids: tuple[str, ...]
    relations: tuple[str, ...]
    snapshot_id: str
    indptr: np.ndarray
    indices: np.ndarray
    type_indptr: np.ndarray
    symbols: np.ndarray
    degree: np.ndarray
    _node_index: object
    _relation_index: object

    def __init__(self, triples, *, node_ids, relations):
        node_ids = names(node_ids, "node_ids", allow_empty=True)
        relations = names(relations, "relations")
        edges = np.asarray(triples)
        if edges.ndim != 2 or edges.shape[1] != 3 or not np.issubdtype(edges.dtype, np.integer):
            raise ValueError("triples must be an integer array with shape (edges, 3)")
        n, r = len(node_ids), len(relations)
        if (np.any(edges < 0) or np.any(edges[:, (0, 2)] >= n)
                or np.any(edges[:, 1] >= r) or np.any(edges[:, 0] == edges[:, 2])):
            raise ValueError("triples contain out-of-schema indices or self edges")
        forward = edges.astype(np.int64, copy=False)
        inverse = forward[:, (2, 1, 0)].copy()
        inverse[:, 1] += r
        directed = np.concatenate((forward, inverse))
        # Sort by source, destination, then symbol, removing duplicate evidence.
        order = np.lexsort((directed[:, 1], directed[:, 2], directed[:, 0]))
        directed = directed[order]
        unique = np.r_[True, np.any(directed[1:] != directed[:-1], axis=1)] if len(directed) else []
        directed = directed[np.asarray(unique, dtype=bool)]
        first = np.r_[True, np.any(directed[1:, (0, 2)] != directed[:-1, (0, 2)], axis=1)] if len(directed) else []
        starts = np.flatnonzero(first)
        sources, destinations = directed[starts, 0], directed[starts, 2]
        degree = np.bincount(sources, minlength=n)
        arrays = {
            "indptr": np.r_[0, np.cumsum(degree)], "indices": destinations,
            "type_indptr": np.r_[starts, len(directed)], "symbols": directed[:, 1],
            "degree": degree,
        }
        digest = hashlib.sha256(b"orbweaver-query-graph-v1\0")
        digest.update(json.dumps([node_ids, relations], separators=(",", ":")).encode())
        for key, value in arrays.items():
            array = immutable_array(value, "<i8")
            object.__setattr__(self, key, array)
            digest.update(key.encode() + array.tobytes())
        object.__setattr__(self, "node_ids", node_ids)
        object.__setattr__(self, "relations", relations)
        object.__setattr__(self, "snapshot_id", digest.hexdigest())
        object.__setattr__(self, "_node_index", MappingProxyType({v: i for i, v in enumerate(node_ids)}))
        object.__setattr__(self, "_relation_index", MappingProxyType({v: i for i, v in enumerate(relations)}))

    @property
    def numeric_bytes(self):
        return sum(getattr(self, k).nbytes for k in
                   ("indptr", "indices", "type_indptr", "symbols", "degree"))

    def node_index(self, node_id):
        try:
            return self._node_index[node_id]
        except (KeyError, TypeError):
            raise ValueError(f"Unknown node ID: {node_id!r}") from None

    def relation_index(self, relation):
        try:
            return self._relation_index[relation]
        except (KeyError, TypeError):
            raise ValueError(f"Unknown relation: {relation!r}") from None

    def neighbors(self, node):
        if type(node) is not int or not 0 <= node < len(self.node_ids):
            raise ValueError("Node index outside graph")
        return self.indices[self.indptr[node]:self.indptr[node + 1]]

    def triples(self):
        """Recover the canonical directed evidence, excluding generated inverses."""
        source = np.repeat(np.arange(len(self.node_ids)), self.degree)
        edge = np.repeat(np.arange(len(self.indices)), np.diff(self.type_indptr))
        keep = self.symbols < len(self.relations)
        return immutable_array(np.column_stack((source[edge[keep]], self.symbols[keep],
                                                self.indices[edge[keep]])), "<i8")

    def save(self, path):
        with Path(path).open("xb") as stream:
            np.savez_compressed(stream, format=np.array("orbweaver-query-graph-v1"),
                                node_ids=np.array(self.node_ids, dtype=str),
                                relations=np.array(self.relations), triples=self.triples(),
                                snapshot_id=np.array(self.snapshot_id))

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as artifact:
            if (set(artifact.files) != {"format", "node_ids", "relations", "triples", "snapshot_id"}
                    or artifact["format"].shape != ()
                    or artifact["format"].item() != "orbweaver-query-graph-v1"):
                raise ValueError("Unsupported graph artifact format")
            graph = cls(artifact["triples"], node_ids=artifact["node_ids"].tolist(),
                        relations=artifact["relations"].tolist())
            if artifact["snapshot_id"].shape != () or artifact["snapshot_id"].item() != graph.snapshot_id:
                raise ValueError("Graph artifact content identity mismatch")
            return graph
