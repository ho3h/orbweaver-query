"""Checks for the public corpus harness's comparison and statement boundaries."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def harness():
    directory = Path(__file__).resolve().parents[1] / "tools"
    sys.path.insert(0, str(directory))
    try:
        spec = importlib.util.spec_from_file_location("corpus_execution", directory / "text2cypher_execute.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(directory))


def test_fixture_statement_boundaries_preserve_literals():
    m = harness()
    script = "CREATE (a {x: ';', y: \"a;b\"});\nRETURN `a;b`; /* ; */ RETURN 1;"
    assert list(m.statements(script)) == [
        "CREATE (a {x: ';', y: \"a;b\"})", "RETURN `a;b`", "/* ; */ RETURN 1"]


def test_comparison_preserves_bags_and_reports_failures():
    m = harness()
    inventory = [{"query_sha256": "a", "indicators": dict.fromkeys(m.REQUIRED, True)},
                 {"query_sha256": "b", "indicators": {}}]
    a = {"status": "ok", "row_count": 3, "bag_sha256": m.digest(sorted(["x", "y", "x"])),
         "sequence_sha256": m.digest(["x", "y", "x"])}
    b = {**a, "sequence_sha256": m.digest(["x", "x", "y"])}
    error = {"status": "error", "class": "SyntaxError", "code": "syntax"}
    rows = [{"query_sha256": "a", "adapter": a, "direct": b},
            {"query_sha256": "b", "adapter": error, "direct": error}]
    report = m.aggregate(rows, inventory)
    assert report["gate_passed"] and report["identical_sequences"] == 0
    rows[0]["direct"] = {**b, "row_count": 2, "bag_sha256": m.digest(["x", "y"])}
    assert m.aggregate(rows, inventory)["mismatches"] == ["a"]
    rows[0]["direct"] = error
    assert m.aggregate(rows, inventory)["counts"]["one_path_failure"] == 1


def test_row_cap_closes_stream_and_retains_failure():
    m = harness()
    pytest.importorskip("neo4j")
    closed = []

    def stream():
        try:
            for _ in range(m.CAP + 1):
                yield {"x": 1}
        finally:
            closed.append(True)

    result, raw = m.capture(stream())
    assert result["status"] == "error" and result["class"] == "RowLimit"
    assert len(raw) == m.CAP and closed == [True]


def test_virtual_schema_comparison_renames_ids_preserving_topology_and_properties():
    m = harness()

    def schema(a, b, edge, *, reverse=False, title="A"):
        nodes = [{"$node": a, "labels": ["A"], "properties": {"$map": [["name", title]]}},
                 {"$node": b, "labels": ["B"], "properties": {"$map": [["name", "B"]]}}]
        rel = {"$relationship": edge, "start": b if reverse else a,
               "end": a if reverse else b, "type": "R", "properties": {"$map": []}}
        return json.dumps({"$map": [["nodes", {"$list": nodes}],
                                    ["relationships", {"$list": [rel]}]]})

    a = m.normalize_virtual_schema(schema("-1", "-2", "-3"))
    assert a == m.normalize_virtual_schema(schema("-20", "-30", "-100"))
    assert a != m.normalize_virtual_schema(schema("-1", "-2", "-3", reverse=True))
    assert a != m.normalize_virtual_schema(schema("-1", "-2", "-3", title="changed"))
    with pytest.raises(ValueError, match="virtual"):
        m.normalize_virtual_schema(schema("ordinary-id", "-2", "-3"))
