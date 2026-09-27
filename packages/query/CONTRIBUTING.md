# Contributing to Orbweaver Query

Start with a small issue or pull request containing the graph shape, query rows,
expected behavior and a runnable reproducer. Share synthetic or public evidence;
remove credentials, private graph contents and unrelated research material.
Use the repository's bug-report template for correctness or installation issues.

The preview focuses on exact graph scoring, bounded Python plans and read-only
Neo4j integration. Useful contributions include semantics bugs, evidence-backed
performance fixes, clearer examples and compatibility fixes. Discuss a new model
backend or language surface before implementing it.

## Local checks

From the repository root using native ARM Python 3.11+ on a Mac:

```sh
python -m pip install build './packages/query[dev,train,neo4j]'
python -m pytest -q packages/query/tests
ruff check packages/query/src packages/query/tests packages/query/tools \
  packages/query/examples packages/query/benchmarks/movie_workflow.py
python -m build packages/query --outdir packages/query/dist/review
python packages/query/tools/audit_distribution.py packages/query/dist/review
```

Use a fresh distribution output directory. Validate installed artifacts separately:

```sh
python -m pip install packages/query/dist/review/orbweaver_query-1.0.0.dev1-py3-none-any.whl
python -I -m pytest -q packages/query/tests -o pythonpath=
```

The live adapter checks require a newly created disposable Neo4j instance. Follow
`tools/disposable_neo4j.py --help` and the public movie example; never point fixture
writes at a production graph. Optional training, database and research-backend
checks may skip when their dependencies are absent. Report the actual pass/skip
counts and which environments were exercised.

## Performance changes

State the work removed and the complete timing boundary. Keep native/manual,
well-sized cache and precomputed controls where applicable. Check output support,
order, duplicates, nulls and graph/model identities, not just floating-point scores.
Publish adverse cases and setup/refresh costs. Do not tune on opened confirmation
labels or use a favorable cache ablation as evidence of universal superiority.

Freeze workloads/configuration before timing, retain raw samples and failures,
and use a quiet host interval for final comparisons. These [protocols](benchmarks/MAC_RELEASE_PROTOCOL.md)
show the expected level of disclosure. Avoid starting another broad benchmark
campaign unless a concrete hypothesis and a bounded cost breakdown justify it.

The project uses Apache-2.0 for code; include applicable upstream notices when
adding third-party artifacts. Conventional structural metrics and existing query
optimization techniques should be credited accurately.
