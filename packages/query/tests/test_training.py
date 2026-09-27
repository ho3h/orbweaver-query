"""Data isolation, artifact integrity and independently checkable ranking behavior."""

import numpy as np
import pytest

from orbweaver_query import ExplicitPathModel, GraphSnapshot, Limits
from orbweaver_query.datasets import load_triples, positives_by_query, split_pairs


def chain():
    return GraphSnapshot(np.array([[i, 0, i+1] for i in range(7)]),
                         node_ids=list("abcdefgh"), relations=["r"])


def test_graph_artifact_roundtrip_and_integrity(tmp_path):
    graph = GraphSnapshot(np.array([[0, 0, 1], [1, 0, 0], [0, 1, 1], [0, 0, 1]]),
                          node_ids=["a", "b", "isolated"], relations=["r", "s"])
    path = tmp_path / "graph.npz"
    graph.save(path)
    loaded = GraphSnapshot.load(path)
    assert loaded.snapshot_id == graph.snapshot_id
    assert set(map(tuple, loaded.triples())) == {(0, 0, 1), (1, 0, 0), (0, 1, 1)}
    with pytest.raises(ValueError):
        loaded.triples().setflags(write=True)
    with pytest.raises(FileExistsError):
        graph.save(path)
    with np.load(path, allow_pickle=False) as data:
        changed = dict(data)
    changed["node_ids"] = np.array(["changed", "b", "isolated"])
    np.savez(path, **changed)
    with pytest.raises(ValueError, match="identity"):
        GraphSnapshot.load(path)
    empty = GraphSnapshot(np.empty((0, 3), int), node_ids=[], relations=["r"])
    empty.save(tmp_path / "empty.npz")
    assert GraphSnapshot.load(tmp_path / "empty.npz").snapshot_id == empty.snapshot_id


def test_bundled_trained_model_metadata():
    from orbweaver_query.demo import bundled_model

    model, metadata = bundled_model()
    assert model.model_id == metadata["model_id"]
    assert model.coefficient.shape == (11, 11136)
    assert np.count_nonzero(model.coefficient) > 1000
    assert not np.any(model.coefficient[model.relations.index("_similar_to")])
    assert metadata["untrained_relations"] == ["_similar_to"]


def test_dataset_pair_roles_order_and_leakage(tmp_path):
    triples = np.array([[h, r, t] for h in range(15) for t in range(15) for r in range(2)])
    splits = split_pairs(triples, 71)
    pair_sets = [{tuple(sorted((h, t))) for h, _, t in part} for part in splits]
    assert all(pair_sets)
    assert all(not pair_sets[i] & pair_sets[j] for i in range(3) for j in range(i))
    assert sum(map(len, splits)) == len(triples) - 30
    shuffled = split_pairs(triples[::-1], 71)
    assert all(set(map(tuple, a)) == set(map(tuple, b)) for a, b in zip(splits, shuffled))
    raw = tmp_path / "train.txt"
    raw.write_text("b z a\na y c\n")
    edges, nodes, relations = load_triples(raw)
    assert nodes == ["a", "b", "c"] and relations == ["y", "z"]
    np.testing.assert_array_equal(edges, [[1, 1, 0], [0, 0, 2]])
    raw.write_text("a r b\na r b\n")
    with pytest.raises(ValueError, match="Duplicate"):
        load_triples(raw)


def test_sampling_excludes_known_and_sparse_export_matches():
    pytest.importorskip("scipy")
    from orbweaver_query.training import prepare_examples, sparse_features

    graph = chain()
    fit = np.array([[0, 0, 2], [7, 0, 5], [0, 0, 7]])
    known = positives_by_query(np.concatenate((graph.triples(), fit)))
    examples, x, audit = prepare_examples(graph, fit, known, seed=71)
    assert audit["positive_queries"] == 3 and audit["covered_queries"] == 2
    for group in np.unique(examples["groups"]):
        mask = examples["groups"] == group
        assert examples["labels"][mask].tolist() == [1, 0]
        for head, relation, target in examples["queries"][mask][1:]:
            assert target not in known[head, relation]
    weight = np.random.default_rng(14).normal(size=(1, 16))
    model = ExplicitPathModel(weight, relations=graph.relations)
    for head in range(8):
        features = model.expand(graph, head, Limits())
        expected = sparse_features(features, 16) @ weight[0]
        np.testing.assert_allclose(model.score(features, 0), expected, atol=1e-12, rtol=1e-12)
    expected = []
    for h, r, t in examples["queries"]:
        f = model.expand(graph, int(h), Limits())
        expected.append(model.score(f, int(r))[np.searchsorted(f.candidates, t)])
    np.testing.assert_allclose(x @ weight[0], expected, atol=1e-12, rtol=1e-12)


def test_fitted_controls_and_tie_metrics():
    pytest.importorskip("sklearn")
    from orbweaver_query.training import fit_controls, prepare_examples, rank_target

    graph = chain()
    fit = np.array([[0, 0, 2], [7, 0, 5]])
    examples, x, _ = prepare_examples(graph, fit, positives_by_query(fit), seed=71)
    model, controls, audit = fit_controls(x, examples, graph.relations, seed=72)
    np.testing.assert_array_equal(model.coefficient, controls["pattern"])
    assert set(audit) == {"base", "marginal", "pattern", "permuted"}
    raw, filtered, recall = rank_target([0, 1, 2, 3], [4, 2, 2, 2], 2, {0, 1, 2}, (1, 2, 3, 4))
    assert raw == 3 and filtered == 1.5
    np.testing.assert_allclose(recall, [0, 1/3, 2/3, 1])
    assert np.isinf(rank_target([0], [4], 1, set())[0])
    with pytest.raises(ValueError, match="budget"):
        rank_target([0], [4], 1, set(), (0,))
