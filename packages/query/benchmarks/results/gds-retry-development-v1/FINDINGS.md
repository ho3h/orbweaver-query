# Completed native GDS time-budget retry

The friendship run with 256-dimensional FastRP, degree/cosine features and
16 negatives completed under the extended 3,600-second transaction allowance.
Its expected recall@16 is **32.99%** on all 225 development-positive queries.
It returned all 256,664 directed candidates (254,658 undirected streamed pairs,
fanned out to both requested directions). No candidate was missing.

The native selector chose a 50-tree, depth-10 random forest over logistic
regression using its internal three-fold AUCPR. The recorded outer-test AUCPR is
84.89%, which is a different task/metric from the external top-16 ranking result;
it must not replace that external evaluation. The exact training metadata,
all returned scores, per-positive outcomes and console log are retained.

The earlier 900-second termination remains in the linked
[original archive](../gds-development-v1/FINDINGS.md). The retry changed only the
transaction time allowance: model settings, classifiers, seed, thread count,
8 GiB heap ceiling, data splits and candidate domain remained fixed. The worker
source difference adds the timeout argument/manifest field and uses that field
when starting the disposable database. The archive verifier checks model/data
configuration equality and every split's byte identity, including hashing the
unopened confirmation files.

## Completed development grid

| Model/configuration | Collaboration | Friendship | Communication |
|---|---:|---:|---:|
| Path model | 78.26% | 48.44% | **46.63%** |
| Common neighbors | 79.37% | 51.82% | 43.51% |
| Adamic–Adar | 79.61% | 55.11% | 45.67% |
| Resource allocation | **81.05%** | **56.44%** | 44.23% |
| GDS FastRP64 | 64.86% | **48.00%** | **37.98%** |
| GDS FastRP256 | 68.15% | 26.37% | 26.61% |
| GDS FastRP256 + degree/cosine | 65.29% | 25.11% | 28.82% |
| GDS rich features + 16 negatives | **74.82%** | 32.99% | 37.04% |
| Positive query count | 46 | 225 | 208 |

Bold entries identify the strongest Orbweaver-side option and strongest learned
GDS option per column. Resource allocation and Adamic–Adar are also available
natively in GDS, so this table does not show better prediction quality than GDS
as a whole. The native structural execution comparison treats these exact
algorithms as direct competitors.

The fourth GDS configuration does not change the strongest completed selection
on any application. This closes the outstanding development retry, not the 1.0
quality gate. Confirmation remains sealed; the small reused development sample,
selection, unmatched diagnostic timing and missing four-thread comparison still
prevent a final quality/cost claim.

Fitting took 3,037.86 seconds and full-score prediction/streaming took 28.65 seconds
in this run. These are diagnostic stage observations: other correctness work ran
during fitting, and streaming every score is not a top-16 application response.
They are not comparable speedup measurements.

## Reproduction

`summary.json` merges this completed retry with the preceding four-configuration
archive. Historical failed attempts remain listed; the new `retry` field records
the successful result and links the previous archive by checksum. `run/` contains
the exact frozen source, protocol, inputs and raw result. Only friendship was
executed in the retry; the other applications reuse their earlier completed runs.

```sh
python packages/query/benchmarks/v1/quality_retry.py verify \
  packages/query/benchmarks/results/gds-retry-development-v1 \
  --previous packages/query/benchmarks/results/gds-development-v1
python packages/query/benchmarks/v1/quality_retry.py restore \
  packages/query/benchmarks/results/gds-retry-development-v1 \
  --previous packages/query/benchmarks/results/gds-development-v1 \
  --output /tmp/gds-retry-replay
python /tmp/gds-retry-replay/gds_quality.py execute /tmp/gds-retry-replay \
  --dataset friendship --neo4j-home /path/to/neo4j-2026.09.0 \
  --java /path/to/java-21 --gds-jar /path/to/gds-2026.09.0.jar
```

Both archives verify, and the retry was restored into a fresh directory without
another training run. No confirmation arrays were loaded.
