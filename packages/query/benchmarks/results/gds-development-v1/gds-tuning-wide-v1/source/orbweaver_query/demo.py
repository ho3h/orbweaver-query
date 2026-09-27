"""Run a bundled trained model on reproducible public evidence (NumPy only)."""

import argparse
import hashlib
import json
from importlib import resources
from pathlib import Path

import numpy as np

from .datasets import WN18RR_TRAIN_SHA256, fetch_wn18rr_train, load_triples, split_pairs
from .graph import GraphSnapshot
from .model import ExplicitPathModel
from .session import LinkQuery, Session


def bundled_model():
    """Load fixed coefficients and their bundled provenance without training."""
    assets = resources.files("orbweaver_query") / "assets"
    metadata = json.loads((assets / "wn18rr-path71.json").read_text())
    artifact = assets / "wn18rr-path71.npz"
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != metadata["artifact_sha256"]:
        raise ValueError("Bundled example artifact checksum mismatch")
    with resources.as_file(artifact) as path:
        model = ExplicitPathModel.load(path)
    if model.model_id != metadata["model_id"] or list(model.relations) != metadata["relations"]:
        raise ValueError("Bundled model provenance mismatch")
    return model, metadata


def load_example(data_dir):
    """Download training member when absent and rebuild the exact seed-71 context."""
    model, metadata = bundled_model()
    path = fetch_wn18rr_train(data_dir)
    triples, nodes, relations = load_triples(path, expected_sha256=WN18RR_TRAIN_SHA256)
    context = split_pairs(triples, metadata["seed"])[0]
    graph = GraphSnapshot(context, node_ids=nodes, relations=relations)
    if graph.snapshot_id != metadata["snapshot_id"]:
        raise ValueError("Example evidence differs from the model's recorded context")
    return Session(graph, model), metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path,
                        default=Path.home() / ".cache" / "orbweaver-query" / "wn18rr")
    parser.add_argument("--head", help="Optional WN18RR entity ID")
    parser.add_argument("--relation", default="_hypernym", help="WN18RR relation name")
    parser.add_argument("--top", type=int, default=3)
    args = parser.parse_args()
    session, metadata = load_example(args.data_dir)
    if args.head is None:
        # Input-only selection: no fitting/development targets or scores inspected.
        nonisolated = np.flatnonzero(session.graph.degree)
        indices = np.random.default_rng(2026).choice(nonisolated, 4, replace=False)
        heads = [session.graph.node_ids[i] for i in indices]
    else:
        heads = [args.head]
    queries = [LinkQuery(head, args.relation) for _ in range(2) for head in heads]
    result = session.run(queries)
    print(json.dumps({"example": metadata["name"], "score_kind": "ranking_logit",
        "untrained_relations": metadata["untrained_relations"], "plan": session.explain(),
        "profile": result.report(), "rows": [
            {"head": row.query.head, "relation": row.query.relation,
             "candidate_count": len(row.candidate_ids), "top": row.top(args.top)}
            for row in result.rows]}, indent=2))


if __name__ == "__main__":
    main()
