"""Optional read-only Cypher adapter with explicit evidence projections.

Cypher remains the database's language; this adapter does not parse or rewrite
arbitrary queries. EXPLAIN verifies the database classifies a supplied query as
read-only before it is run. Inference operates on an immutable exported graph.
"""

from collections.abc import Mapping

import numpy as np

from ._validation import names, positive_int
from .bindings import BindingResult, iter_score_bindings
from .graph import GraphSnapshot
from .model import ResourceLimitError


def _read_query(transaction, cypher, parameters):
    if type(cypher) is not str or not cypher.strip():
        raise ValueError("Cypher must be a nonempty read query")
    if not isinstance(parameters, Mapping):
        # Public argument validation consistently raises ValueError.
        raise ValueError("parameters must be a mapping")  # noqa: TRY004
    # EXPLAIN compiles without executing the supplied query, including writes.
    summary = transaction.run("EXPLAIN " + cypher, dict(parameters)).consume()
    if summary.query_type != "r":
        raise ValueError("The database must classify the candidate/evidence query as read-only")
    return transaction.run(cypher, dict(parameters))


class Neo4jSource:
    """Owns query sessions, but never owns or closes the caller's driver."""

    def __init__(self, driver, *, database=None, fetch_size=1000):
        positive_int(fetch_size, "fetch_size")
        self.driver, self.database, self.fetch_size = driver, database, fetch_size

    def _session(self):
        return self.driver.session(database=self.database, default_access_mode="READ",
                                   fetch_size=self.fetch_size)

    def iter_candidates(self, cypher, parameters=None):
        """Stream bindings, closing the transaction on exhaustion/error/close()."""
        with self._session() as connection, connection.begin_transaction() as transaction:
            for record in _read_query(transaction, cypher, {} if parameters is None else parameters):
                yield dict(record)

    def snapshot(self, *, nodes, edges, relations, parameters=None,
                 max_nodes=1_000_000, max_edges=10_000_000):
        """Export explicit model evidence, including declared isolated nodes.

        `nodes` returns `id`; `edges` returns `head`, `relation`, `target`.
        IDs are stable application strings, not Neo4j internal integer IDs.
        Queries run in one read transaction, but this does not promise stronger
        isolation than the server provides. The returned snapshot identity hashes
        the exported content. Coordinate concurrent writes externally when a
        database-wide point-in-time projection is required.
        """
        positive_int(max_nodes, "max_nodes")
        positive_int(max_edges, "max_edges", minimum=0)
        relations = names(relations, "relations")
        relation_index = {key: i for i, key in enumerate(relations)}
        parameters = {} if parameters is None else parameters
        node_ids, triples = [], []
        with self._session() as connection, connection.begin_transaction() as transaction:
            for row in _read_query(transaction, nodes, parameters):
                # Neo4j Record membership tests values; explicitly inspect keys.
                if "id" not in row.keys():  # noqa: SIM118
                    raise ValueError("Evidence node query must return id")
                node_ids.append(row["id"])
                if len(node_ids) > max_nodes:
                    raise ResourceLimitError("Evidence export exceeds max_nodes")
            node_ids = names(node_ids, "exported node IDs", allow_empty=True)
            node_index = {key: i for i, key in enumerate(node_ids)}
            for row in _read_query(transaction, edges, parameters):
                try:
                    triples.append((node_index[row["head"]], relation_index[row["relation"]],
                                    node_index[row["target"]]))
                except (KeyError, TypeError):
                    raise ValueError("Evidence edge has missing columns or an undeclared endpoint/relation") from None
                if len(triples) > max_edges:
                    raise ResourceLimitError("Evidence export exceeds max_edges")
        return GraphSnapshot(np.array(triples, dtype=np.int64).reshape(-1, 3),
                              node_ids=node_ids, relations=relations)

    def iter_score_pairs(self, session, cypher, parameters=None, **options):
        candidates = self.iter_candidates(cypher, parameters)
        try:
            yield from iter_score_bindings(session, candidates, **options)
        finally:
            candidates.close()

    def score_pairs(self, session, cypher, parameters=None, **options):
        rows, profiles = [], []
        for batch in self.iter_score_pairs(session, cypher, parameters, **options):
            rows.extend(batch.rows)
            profiles.extend(batch.profiles)
        return BindingResult(tuple(rows), tuple(profiles))
