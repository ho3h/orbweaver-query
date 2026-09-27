"""Completeness guards for the bounded native-reference check, without timing."""

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def diagnostic(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]/'benchmarks/v1'))
    return importlib.import_module('gds_queue_diagnostic')


@pytest.mark.parametrize('dataset,threads', [('unknown', 1), ('friendship', 2), ('friendship', True)])
def test_undeclared_condition_is_rejected_before_reading_or_writing(tmp_path, diagnostic, dataset, threads):
    with pytest.raises(ValueError, match='declared graph'):
        diagnostic.freeze(tmp_path/'output', tmp_path/'absent', dataset, threads)
    assert not (tmp_path/'output').exists()


def test_six_conditions_required_before_summary(tmp_path, diagnostic):
    (tmp_path/'suite.json').write_text(json.dumps({'files': {}, 'jobs': [
        {'dataset': d, 'threads': t} for d in diagnostic.DATASETS for t in (1, 4)][:-1]}))
    with pytest.raises(ValueError, match='six declared'):
        diagnostic.summarize_suite(tmp_path)


def test_duplicate_condition_cannot_replace_missing_graph_thread(tmp_path, diagnostic):
    jobs = [{'dataset': d, 'threads': t} for d in diagnostic.DATASETS for t in (1, 4)]
    jobs[-1] = jobs[0]
    (tmp_path/'suite.json').write_text(json.dumps({'files': {}, 'jobs': jobs}))
    with pytest.raises(ValueError, match='six declared'):
        diagnostic.checked_suite(tmp_path)
