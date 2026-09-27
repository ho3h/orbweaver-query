"""Pinned training-only corpus audit; never executes dataset Cypher."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import urllib.request


SOURCES = (
    {"dataset": "neo4j/text2cypher-2024v1", "revision": "d9f15541ab2f99a0f54797a0109b50663554f512",
     "file": "data/train-00000-of-00001.parquet",
     "sha256": "12218000576ed793e468417333b4499517c3d7869c94504941c6741acc229bce"},
    {"dataset": "neo4j/text2cypher-2025v1", "revision": "d88b8a7d477c8c1809218f6c566bd31f1ad1e504",
     "file": "data/train.parquet",
     "sha256": "03cef89e121a577faac6ab8a3f010114e71c364a78a6d7ee39ccbdddd5922791"},
)

# These are lexical coverage indicators, not a Cypher parser or a read-only guard.
# Comments/quoted strings/escaped identifiers cannot supply keyword indicators.
TOKEN = re.compile(
    r"(?P<ignore>//[^\n]*|/\*[\s\S]*?\*/|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:``|[^`])*`)"
    r"|(?P<word>[A-Za-z_][A-Za-z_0-9]*)|(?P<symbol>[^\s])")


def indicators(query):
    tokens = [match.group().upper() for match in TOKEN.finditer(query) if not match.group("ignore")]
    words = set(tokens)
    adjacent = set(zip(tokens, tokens[1:]))
    features = {word: word in words for word in
                ("MATCH", "WHERE", "WITH", "UNWIND", "UNION", "CALL", "LIMIT", "SKIP", "DISTINCT")}
    features.update({"OPTIONAL_MATCH": ("OPTIONAL", "MATCH") in adjacent,
                     "ORDER_BY": ("ORDER", "BY") in adjacent,
                     "AGGREGATE_CALL": any((name, "(") in adjacent for name in
                                           ("COUNT", "SUM", "AVG", "MIN", "MAX", "COLLECT")),
                     "SHORTEST_PATH_CALL": ("SHORTESTPATH", "(") in adjacent,
                     "WRITE_KEYWORD": bool(words & {"CREATE", "MERGE", "SET", "DELETE", "REMOVE", "DROP"}),
                     "STAR_IN_RELATION_PATTERN": bool(re.search(r"\[[^\]]*\*[^\]]*\]", " ".join(tokens)))})
    return features


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(data_dir):
    import pyarrow.parquet as pq

    output, query_sets, paired_sets = [], [], []
    for spec in SOURCES:
        path = data_dir / (spec["dataset"].split("/")[-1] + "-train.parquet")
        if sha(path) != spec["sha256"]:
            raise ValueError("Training dataset checksum mismatch")
        table = pq.read_table(path)
        counts, aliases, examples = Counter(), Counter(), {}
        queries, pairs, schemas, invalid = set(), set(), set(), 0
        rows_with_alias = 0
        for row in table.to_pylist():
            cypher, schema = row["cypher"], row["schema"]
            if not isinstance(cypher, str) or not cypher.strip():
                invalid += 1
                continue
            queries.add(cypher)
            pairs.add((schema, cypher))
            schemas.add(schema)
            alias = row["database_reference_alias"]
            if isinstance(alias, str) and alias.strip():
                rows_with_alias += 1
                aliases[alias] += 1
            for feature, present in indicators(cypher).items():
                if present:
                    counts[feature] += 1
                    examples.setdefault(feature, [])
                    if len(examples[feature]) < 3:
                        examples[feature].append(row["instance_id"])
        output.append({**spec, "declared_license": "Apache-2.0", "rows": table.num_rows,
                       "columns": table.column_names, "empty_or_nonstring_cypher": invalid,
                       "unique_exact_queries": len(queries), "unique_schema_query_pairs": len(pairs),
                       "unique_exact_schemas": len(schemas), "rows_with_database_alias": rows_with_alias,
                       "database_alias_counts": dict(sorted(aliases.items())),
                       "lexical_feature_counts": dict(sorted(counts.items())),
                       "training_example_ids_by_feature": examples})
        query_sets.append(queries)
        paired_sets.append(pairs)
    return {"format": "orbweaver-query-text2cypher-audit-v1", "sources": output,
            "exact_query_overlap": len(query_sets[0] & query_sets[1]),
            "schema_query_pair_overlap": len(paired_sets[0] & paired_sets[1]),
            "combined_unique_queries": len(query_sets[0] | query_sets[1]),
            "test_splits_downloaded_or_read": False, "queries_executed": 0,
            "scope": "training corpus coverage/provenance; no parser, execution or graph-model accuracy claim",
            "source_sha256": sha(__file__)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    if args.download:
        for spec in SOURCES:
            path = args.data_dir / (spec["dataset"].split("/")[-1] + "-train.parquet")
            if not path.exists():
                url = f"https://huggingface.co/datasets/{spec['dataset']}/resolve/{spec['revision']}/{spec['file']}"
                with urllib.request.urlopen(url) as response:
                    content = response.read()
                if hashlib.sha256(content).hexdigest() != spec["sha256"]:
                    raise ValueError("Download checksum mismatch")
                path.write_bytes(content)
    result = audit(args.data_dir)
    content = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output.exists() and args.output.read_text() != content:
        raise ValueError("Existing audit differs; preserve it and use a new output path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content)
    print(json.dumps({"rows": sum(s["rows"] for s in result["sources"]),
                      "unique_queries": result["combined_unique_queries"],
                      "query_overlap": result["exact_query_overlap"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
