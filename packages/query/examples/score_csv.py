"""Score candidate pairs from three CSV files with a conventional structural model."""

import argparse
import csv
import json
from pathlib import Path

from orbweaver_query import (
    GraphSnapshot,
    Limits,
    NeighborhoodModel,
    Session,
    iter_score_bindings,
)


def records(path, required):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not set(required).issubset(reader.fieldnames):
            raise ValueError(f"{path}: required columns are {required}")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"{path}: duplicate header names")
        for ordinal, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{path}:{ordinal}: row does not match its header")
            yield row


def load_graph(nodes, edges, relations, *, max_nodes=100000, max_edges=1000000):
    ids = []
    for row in records(nodes, ("id",)):
        if len(ids) >= max_nodes:
            raise ValueError("Node input exceeds max_nodes")
        ids.append(row["id"])
    index = {name: i for i, name in enumerate(ids)}
    schema = {name: i for i, name in enumerate(relations)}
    triples = []
    for row in records(edges, ("head", "relation", "target")):
        if len(triples) >= max_edges:
            raise ValueError("Edge input exceeds max_edges")
        if row["head"] not in index or row["target"] not in index or row["relation"] not in schema:
            raise ValueError("An edge has an undeclared node ID or relation")
        triples.append((index[row["head"]], schema[row["relation"]], index[row["target"]]))
    return GraphSnapshot(triples, node_ids=ids, relations=relations)


def candidate_rows(path):
    for row in records(path, ("head", "relation", "target")):
        yield {
            key: None if key in ("head", "relation", "target") and value == "" else value
            for key, value in row.items()
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("nodes", "edges", "candidates"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument(
        "--relation",
        action="append",
        required=True,
        help="Declare ordered relation names; repeat for multiple types",
    )
    parser.add_argument(
        "--metric", choices=NeighborhoodModel.metrics, default="resource_allocation"
    )
    parser.add_argument("--window-size", type=int, default=256)
    args = parser.parse_args()
    graph = load_graph(args.nodes, args.edges, args.relation)
    model = NeighborhoodModel(relations=graph.relations, metric=args.metric)
    session = Session(graph, model, limits=Limits(window_size=args.window_size))
    for batch in iter_score_bindings(session, candidate_rows(args.candidates)):
        for row in batch.to_records():
            print(json.dumps(row, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
