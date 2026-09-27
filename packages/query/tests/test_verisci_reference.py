"""Comparator checks for evidence selection and paired quality accounting."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

source = Path(__file__).resolve().parents[1] / "benchmarks/v1/verisci_reference.py"
spec = importlib.util.spec_from_file_location("verisci_reference", source)
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


def test_selected_evidence_preserves_author_sentence_order_and_rejects_invalid_indices():
    row = {"abstract": ["First.", "Second.", "Third."]}
    assert reference.selected_evidence(row, [0, 2]) == "First. Third."
    assert reference.selected_evidence(row, []) == ""
    for indices in ([2, 0], [1, 1], [-1], [3]):
        with pytest.raises(ValueError, match="rationale"):
            reference.selected_evidence(row, indices)


def test_macro_f1_includes_off_diagonal_errors_and_bootstrap_preserves_pairing():
    assert reference.macro_f1([2, 1, 0, 0, 1, 0, 0, 0, 2]) == pytest.approx((.8+2/3+1)/3)
    labels = list(reference.LABELS)*2
    inputs = {"edges": [{"claim_id": i//2} for i in range(6)]}
    result = reference.paired_bootstrap(inputs, labels, labels, labels, repetitions=100)
    assert result["claim_groups"] == 3
    assert result["interval_95"] == [0, 0]


def test_only_label_evidence_can_be_truncated_and_claim_is_second_sequence():
    calls = []

    def tokenizer(texts, claims, **kwargs):
        calls.append((texts, claims, kwargs))
        return {"input_ids": SimpleNamespace(shape=(1, kwargs.get("max_length", 513)))}

    with pytest.raises(ValueError, match="Rationale"):
        reference.encode(tokenizer, ["evidence"], ["claim"])
    assert len(calls) == 1
    _, truncated = reference.encode(tokenizer, ["evidence"], ["claim"], truncate=True)
    assert truncated
    assert calls[-1] == (["evidence"], ["claim"], {
        "padding": True, "truncation": "only_first", "max_length": 512, "return_tensors": "pt"})
