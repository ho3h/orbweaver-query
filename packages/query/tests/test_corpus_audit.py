import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "corpus_audit", Path(__file__).parents[1] / "tools" / "text2cypher_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_coverage_indicators_ignore_quoted_strings_comments_and_identifiers():
    query = """MATCH (n:`CREATE`) // DELETE n
    WHERE n.text = 'MERGE (x) OPTIONAL MATCH' /* UNWIND [] */
    RETURN n, "SET n.x = 'WITH'" ORDER BY n.id LIMIT 5"""
    found = audit.indicators(query)
    assert found["MATCH"] and found["ORDER_BY"] and found["LIMIT"]
    assert not found["WRITE_KEYWORD"] and not found["OPTIONAL_MATCH"]
    assert not found["UNWIND"] and not found["WITH"]


def test_coverage_identifies_optional_aggregation_and_path_queries():
    found = audit.indicators("MATCH (a) OPTIONAL MATCH (a)-[*2..4]->(b) WITH a, count(b) AS n RETURN n")
    assert found["OPTIONAL_MATCH"] and found["AGGREGATE_CALL"]
    assert found["STAR_IN_RELATION_PATTERN"] and found["WITH"]


def test_encoded_newlines_are_normalized_only_outside_quoted_values():
    query = r"MATCH (n)\\nWHERE n.text = 'keep\nthis  text'\\nRETURN n ORDER BY n.id\\nLIMIT 2"
    normalized = audit.normalize_layout(query)
    assert "\nWHERE" in normalized and "\nRETURN" in normalized
    assert r"'keep\nthis  text'" in normalized
    assert audit.normalize_layout(normalized) == normalized
    assert audit.indicators(query)["WHERE"] and audit.indicators(query)["LIMIT"]
    flat = r"MATCH (n) WHERE n.text = 'keep\nthis  text' RETURN n ORDER BY n.id LIMIT 2"
    assert audit.layout_key(query) == audit.layout_key(flat)
    assert audit.layout_key(flat) != audit.layout_key(flat.replace("  text", " text"))
