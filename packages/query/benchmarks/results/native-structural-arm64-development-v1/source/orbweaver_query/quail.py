"""Experimental candidate-pair bridge to Quail's existing semantic join.

Quail and Arrow are optional and imported only when binding/executing a query.
This module does not implement an inference backend or parse AI-Cypher syntax.
"""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
from string import Formatter

from ._validation import positive_int
from .model import ResourceLimitError


def _template(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("predicate must be a nonempty two-document prompt")
    parts = list(Formatter().parse(value))
    fields = [name for _, name, _, _ in parts if name is not None]
    if sorted(fields) != ["0", "1"] or any(spec or conversion for _, _, spec, conversion in parts):
        raise ValueError("predicate must contain {0} and {1} exactly once, without formatting")


@dataclass(frozen=True)
class _PairRestriction:
    """Only supplied graph edges between the callback's surviving document IDs."""

    left_ids: frozenset[str]
    right_ids: frozenset[str]
    adjacency: dict[str, tuple[str, ...]]

    def __call__(self, tables):
        import pyarrow as pa

        indices = {}
        for alias, domain in (("l", self.left_ids), ("r", self.right_ids)):
            table = tables[alias]
            entries = list(zip(table.column(alias).to_pylist(), table.column("id").to_pylist()))
            if len({index for index, _ in entries}) != len(entries):
                raise ValueError("Quail supplied duplicate document row indices")
            if len({key for _, key in entries}) != len(entries):
                raise ValueError("Quail supplied duplicate application IDs")
            if any(type(index) is not int or not 0 <= index < 2**31 or type(key) is not str or key not in domain
                   for index, key in entries):
                raise ValueError("Quail supplied an invalid document ID")
            indices[alias] = {key: index for index, key in entries}
        pairs = [(left, indices["r"][target]) for key, left in indices["l"].items()
                 for target in self.adjacency.get(key, ()) if target in indices["r"]]
        return pa.table({"l": pa.array([left for left, _ in pairs], type=pa.int32()),
                         "r": pa.array([right for _, right in pairs], type=pa.int32())})


@dataclass(frozen=True, init=False, eq=False)
class QuailPairs:
    """Bounded immutable model inputs plus an ordered bag of source bindings.

    Each row supplies head, target, head_text and target_text. Non-null IDs must
    be nonempty application strings. Text and IDs are copied; an ID must have
    one text value within its side of the projection. Rows with any null input
    have unknown predicate truth and do not survive the semantic WHERE filter.
    Payload fields are copied and restored without entering the model prompt.

    The identity covers document content and ordered candidate bindings. It does
    not claim a database-wide transaction snapshot or hash arbitrary payloads.
    """

    _left: tuple[tuple[str, str], ...]
    _right: tuple[tuple[str, str], ...]
    _pairs: tuple[tuple[str, str], ...]
    _rows: tuple[dict, ...] = field(repr=False)
    _row_pairs: tuple[tuple[str, str] | None, ...] = field(repr=False)
    identity: str

    def __init__(self, rows, *, max_bindings=1_000_000, max_documents=1_000_000,
                 max_text_bytes=256*1024*1024):
        for name, limit in (("max_bindings", max_bindings), ("max_documents", max_documents),
                            ("max_text_bytes", max_text_bytes)):
            positive_int(limit, name, minimum=0)
        left, right, bindings, row_pairs, unique = {}, {}, [], [], {}
        text_bytes = 0
        iterator = iter(rows)
        try:
            for row in iterator:
                if len(bindings) >= max_bindings:
                    raise ResourceLimitError("Semantic candidate export exceeds max_bindings")
                if not isinstance(row, Mapping):
                    raise ValueError("Candidate bindings must be mappings")
                required = ("head", "target", "head_text", "target_text")
                if any(key not in row for key in required):
                    raise ValueError("Candidate must supply head, target, head_text and target_text")
                for key in required:
                    value = row[key]
                    if value is not None and (type(value) is not str or (key in required[:2] and not value)):
                        raise ValueError(f"{key} must be a string or null; IDs must be nonempty")
                pair = None
                if all(row[key] is not None for key in required):
                    for documents, key, text in ((left, row["head"], row["head_text"]),
                                                  (right, row["target"], row["target_text"])):
                        if key in documents and documents[key] != text:
                            raise ValueError(f"Conflicting document content for {key!r}")
                        if key not in documents:
                            if len(left)+len(right) >= max_documents:
                                raise ResourceLimitError("Semantic candidate export exceeds max_documents")
                            text_bytes += len(text.encode("utf-8"))
                            if text_bytes > max_text_bytes:
                                raise ResourceLimitError("Semantic candidate export exceeds max_text_bytes")
                            documents[key] = text
                    pair = row["head"], row["target"]
                    unique[pair] = None
                bindings.append(deepcopy(dict(row)))
                row_pairs.append(pair)
        finally:
            close = getattr(iterator, "close", None)
            if callable(close):
                close()
        values = {"_left": tuple(left.items()), "_right": tuple(right.items()),
                  "_pairs": tuple(unique), "_rows": tuple(bindings), "_row_pairs": tuple(row_pairs)}
        encoded = json.dumps({"version": 1, "left": values["_left"], "right": values["_right"],
                              "bindings": row_pairs}, ensure_ascii=True, separators=(",", ":")).encode()
        for name, value in values.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "identity", sha256(encoded).hexdigest())

    @classmethod
    def from_neo4j(cls, source, cypher, parameters=None, **limits):
        """Capture one read-only candidate export; the caller owns the driver."""
        return cls(source.iter_candidates(cypher, parameters), **limits)

    @property
    def candidate_pairs(self):
        return self._pairs

    def describe(self):
        return {"identity": self.identity, "input_bindings": len(self._rows),
                "candidate_pairs": len(self._pairs), "null_bindings": self._row_pairs.count(None),
                "left_documents": len(self._left), "right_documents": len(self._right),
                "text_bytes": sum(len(text.encode("utf-8")) for _, text in (*self._left, *self._right))}

    def restore(self, positive_pairs):
        """Validate returned positive pairs and restore original ordered bindings."""
        allowed, seen = set(self._pairs), set()
        for value in positive_pairs:
            if not isinstance(value, (list, tuple)) or len(value) != 2 or any(type(x) is not str for x in value):
                raise ValueError("A positive pair must contain two application string IDs")
            pair = tuple(value)
            if pair not in allowed:
                raise ValueError("Quail returned a pair outside the captured graph candidates")
            if pair in seen:
                raise ValueError("Quail returned a duplicate pair")
            seen.add(pair)
        return tuple(deepcopy(row) for row, pair in zip(self._rows, self._row_pairs) if pair in seen)

    def bind(self, session, predicate, *, namespace="orbweaver", kind="per_batch"):
        """Build a full Boolean semantic join using Quail's allowed-pair interface.

        {0} is head_text and {1} target_text. The caller owns a local Quail
        Session. Each binding uses a fresh namespace in that session. Nothing is
        evaluated here; CUDA execution happens when the bound query is run.
        """
        _template(predicate)
        if type(namespace) is not str or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", namespace) is None:
            raise ValueError("namespace must be a simple identifier")
        if kind not in ("per_batch", "barrier"):
            raise ValueError("kind must be per_batch or barrier")
        if not self._pairs:
            return QuailPairQuery(self, None)
        import pyarrow as pa
        from quail import DocumentProvider, col, prompt

        providers = [f"{namespace}_left", f"{namespace}_right"]
        function_name = f"{namespace}_candidates"
        if any(name in session.catalog.providers for name in providers) or function_name in session.registry.functions:
            raise ValueError("Quail namespace is already in use; choose a fresh namespace")
        adjacency = {}
        for head, target in self._pairs:
            adjacency.setdefault(head, []).append(target)
        restriction = _PairRestriction(frozenset(key for key, _ in self._left),
            frozenset(key for key, _ in self._right), {key: tuple(values) for key, values in adjacency.items()})
        for name, documents in zip(providers, (self._left, self._right)):
            session.register(name, DocumentProvider.from_table(pa.table({
                "id": [key for key, _ in documents], "text": [text for _, text in documents]}), id_col="id"))
        query = (session.docs(providers[0]).alias("l")
                 .join(session.docs(providers[1]).alias("r"))
                 .apply(restriction, columns=[col("l.id"), col("r.id")],
                        name=function_name, ids="pairs", kind=kind)
                 .ai_if(prompt(predicate, col("l.text"), col("r.text")))
                 .select("l.id", "r.id"))
        return QuailPairQuery(self, query)


@dataclass(frozen=True)
class QuailPairResult:
    rows: tuple[dict, ...]
    candidate_identity: str
    backend_result: object = field(repr=False)


@dataclass(frozen=True)
class QuailPairQuery:
    candidates: QuailPairs
    query: object = field(repr=False)

    def run(self):
        if self.query is None:
            return QuailPairResult((), self.candidates.identity, None)
        result = self.query.run()
        table = result.collect()
        if table.column_names != ["l.id", "r.id"]:
            raise ValueError("Unexpected Quail result schema")
        pairs = zip(table.column("l.id").to_pylist(), table.column("r.id").to_pylist())
        return QuailPairResult(self.candidates.restore(pairs), self.candidates.identity, result)

    def collect(self):
        return self.run().rows
