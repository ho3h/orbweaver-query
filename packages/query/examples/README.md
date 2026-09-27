# A movie recommendation you can inspect

Choose films, ask Neo4j for related candidates through shared cast, and compare a
composed local scoring plan with equivalent native Cypher. The output is a local
HTML report with film titles, cast evidence, scores and inspectable work counts,
plus JSON containing every returned row. No external assets or network calls are
used by the report itself.

A [checked sample report](../benchmarks/results/launch-preview-v2/movie-demo/index.html)
and its [JSON records](../benchmarks/results/launch-preview-v2/movie-demo/results.json)
are included in the repository. Download/open the HTML locally; GitHub displays
its source. The upstream fixture's metadata is kept as supplied, including its
incomplete coverage and occasional incorrect film years.

The fixture is the pinned [Neo4j movies example](https://github.com/neo4j-graph-examples/movies/tree/51cf90d18c1a7f74bce7a77083543697dfb0139d).
The script downloads it from its upstream source on first use, verifies SHA-256,
and executes it **only in a newly created temporary database**. It never connects
to or modifies an existing database's data. Your Neo4j distribution is reused as
software; temporary data/configuration and the owned server are cleaned up on exit.

## Run on an Apple Silicon Mac

Install native ARM Python 3.11+, a native ARM Java 21 runtime, and Neo4j Community
2026.09.0. From this repository's root:

```sh
python -m pip install './packages/query[neo4j]'
python -I packages/query/examples/movie_recommendations.py \
  --neo4j-home /path/to/neo4j-community-2026.09.0 \
  --java /path/to/native-java21/bin/java \
  --output movie-demo
open movie-demo/index.html
```

The Java/Python architecture check rejects a Rosetta/native mismatch. For Neo4j
5.26, pass `--entrypoint org.neo4j.server.CommunityEntryPoint`; the current Mac
release validation uses 2026.09.0. Choose a new output directory each time.
You can repeat `--title` to choose films from the fixture, use `--since` to set
a release-year floor, and `--minimum-shared-cast` to control the cast-count filter.
Unknown titles produce an error, not a misleading empty recommendation report.

```sh
python -I packages/query/examples/movie_recommendations.py \
  --neo4j-home /path/to/neo4j-community-2026.09.0 \
  --java /path/to/native-java21/bin/java \
  --title 'The Matrix' --since 2000 --minimum-shared-cast 2 \
  --output matrix-demo
```

## What the result means

The evidence projection contains movies, people with acting credits, and ACTED_IN
edges. Candidate selection constrains output films by year but retains all acting
evidence for degree normalization. Common-neighbor counts supply the cast-count
filter; resource allocation sums `1 / actor's film count` over shared cast. Both
are conventional structural methods, not a fitted recommender or probability.

Compatible predictions share neighborhood preparation. The report compares work
with that sharing disabled and verifies all bindings, scores and provenance
against independent native Cypher. Fewer expansions do not by themselves prove
lower wall time. The fixture is small; the [end-to-end protocol](../benchmarks/MOVIE_WORKFLOW_PROTOCOL.md)
includes native/manual controls, complete serialization and snapshot/setup costs.

The [CSV recipe](../BRING_YOUR_OWN_GRAPH.md) shows how to replace this fixture with
your own evidence and candidate rows, without requiring a database for the first
integration check.
