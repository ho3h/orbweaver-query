# Independent backend verification

Production structural scores match the frozen SciPy sparse-matrix controls on
all 654,309 eligible source/target pairs across three public graphs and all three
metrics: 1,962,927 scores, maximum absolute error zero. Separately, 1,042 composed
rows per graph were checked in fused and unfused plans against the saved path
and structural matrices, with duplicate/null/unsupported/provenance checks.
The four-model plan uses 132 expansions per graph with fusion versus 264 without.
These are correctness and work-count checks, not latency claims.

`receipt.json` pins every Python runtime module and the verification script.
The source is retained under its original package-relative paths. Input graphs,
models and independently computed scores are in the GDS development archive.
Confirmation labels are never loaded by this verifier.

To replay from the repository root, use the frozen source:

```sh
PYTHONPATH=packages/query/benchmarks/results/v1-development/backend-verification-v1/src \
  python packages/query/benchmarks/results/v1-development/backend-verification-v1/benchmarks/v1/verify_backends.py \
  packages/query/benchmarks/results/gds-development-v1/gds-quality-development-v1 \
  /tmp/backend-verification-replay.json
```

Validation at this checkpoint: 91 tests passed with one optional live-database
skip; a fresh NumPy-only wheel built from the source distribution passed 88 tests
with four optional-dependency/live-database skips. Ruff 0.16.9 passed.
