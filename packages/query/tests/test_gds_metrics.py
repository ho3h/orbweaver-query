"""A comparator must retain misses and use the same candidate-domain denominator."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


def evaluator():
    path = Path(__file__).resolve().parents[1]/'benchmarks/v1/gds_quality.py'
    spec = importlib.util.spec_from_file_location('gds_quality_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.evaluate


def test_uniform_ties_and_unsupported_positives_stay_in_denominator():
    scores = np.zeros((2, 101))
    scores[1] = np.nan
    candidates = np.ones(scores.shape, bool)
    candidates[:, 0] = False
    # A disallowed high-scoring self/training node must not change the ranking.
    scores[:, 0] = 100
    result = evaluator()(scores, candidates, np.array([0, 1]), np.array([[0, 5], [1, 6]]))
    assert result['positive_queries'] == 2
    assert result['metrics']['recall16'] == pytest.approx(.08)
    assert result['metrics']['recall64'] == pytest.approx(.32)
    assert result['metrics']['supported'] == .5
    assert result['outcomes'][0]['rank'] == 50.5
    assert result['outcomes'][1]['rank'] is None


def test_zero_probability_is_a_valid_score_and_other_positives_are_not_filtered():
    scores = np.zeros((1, 25))
    scores[0, 1:18] = 1
    candidates = np.ones(scores.shape, bool)
    candidates[0, 0] = False
    result = evaluator()(scores, candidates, np.array([0]), np.array([[0, 18], [0, 1]]))
    assert result['metrics']['supported'] == 1
    assert result['outcomes'][0]['recall16'] == 0
    assert result['outcomes'][1]['recall16'] == pytest.approx(16/17)
    assert result['outcomes'][0]['rank'] == 21
