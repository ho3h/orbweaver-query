"""Independent truth cases for the labeled semantic graph application."""

import importlib.util
from pathlib import Path

import pytest

source = Path(__file__).resolve().parents[1] / "benchmarks/v1/scifact_reference.py"
spec = importlib.util.spec_from_file_location("scifact_reference", source)
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


def test_graph_queries_distinguish_existence_veto_and_shared_document_witness():
    inputs = {"claims": [1, 2, 3, 4, 5], "edges": [
        {"claim_id": 1, "document_id": 10}, {"claim_id": 1, "document_id": 20},
        {"claim_id": 2, "document_id": 10}, {"claim_id": 3, "document_id": 20},
        {"claim_id": 4, "document_id": 30}]}
    labels = ["SUPPORT", "CONTRADICT", "CONTRADICT", "SUPPORT", "NOT_ENOUGH_INFO"]
    assert reference.query_answers(inputs, labels) == {
        "supported": [1, 3], "uncontested": [3], "disagreement": [[1, 10, 2], [3, 20, 1]]}
    with pytest.raises(ValueError, match="every edge"):
        reference.query_answers(inputs, labels[:-1])


def test_gold_labels_and_rationales_are_not_model_inputs():
    corpus = [{"doc_id": 10, "title": "Title", "abstract": ["Sentence one."]},
              {"doc_id": 20, "title": "Other", "abstract": ["Sentence two."]}]
    claims = [{"id": 1, "claim": "Claim text.", "cited_doc_ids": [20, 10, 10],
               "evidence": {"10": [{"label": "SUPPORT", "sentences": [0]}]}},
              {"id": 2, "claim": "Isolated.", "cited_doc_ids": [], "evidence": {}}]
    inputs, labels = reference.graph_inputs(claims, corpus)
    assert inputs["claims"] == [1, 2]
    assert labels == ["SUPPORT", "NOT_ENOUGH_INFO"]
    assert [r["document_id"] for r in inputs["edges"]] == [10, 20]
    assert [r["source_occurrences"] for r in inputs["edges"]] == [2, 1]
    for row in inputs["edges"]:
        assert set(row) == {"claim_id", "document_id", "claim", "title", "abstract", "source_occurrences"}
        assert "SUPPORT" not in reference.prompt(row)
    claims[0]["evidence"]["30"] = [{"label": "SUPPORT"}]
    with pytest.raises(ValueError, match="outside"):
        reference.graph_inputs(claims, corpus)


def test_metrics_keep_false_positives_and_missing_witnesses_in_denominators():
    metrics = reference.set_metrics([1, 2, 3], [1, 4])
    assert metrics["true_positive"] == 1
    assert metrics["precision"] == 1/3
    assert metrics["recall"] == .5
    assert metrics["f1"] == .4
    assert reference.set_metrics([], [])['f1'] == 1
    assert reference.set_metrics([1], [])['f1'] == 0
