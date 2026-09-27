# runtime-v1b: frozen execution evidence

All 60 workers checked against the original reference. Maximum absolute score difference: 0.0. Top-16 ordering matches exactly.

Median complete-batch execution plus JSON serialization, milliseconds. Three fresh processes per arm/workload; five measured batches per worker. Warm caches reset at each batch.

| Workload | Legacy cache | Grouped packed | Legacy / grouped |
| --- | ---: | ---: | ---: |
| single | 1.393 | 1.595 | 0.873x |
| distinct256 | 93.117 | 115.922 | 0.803x |
| shared256 | 23.638 | 25.083 | 0.942x |
| interleaved256 | 96.820 | 25.819 | 3.750x |
| hubs16 | 67.273 | 86.189 | 0.781x |

Primary gate passed: **True**.
Regression gate passed: **not declared in iteration 1**.

Scope: one public WN18RR training-evidence graph, one frozen trained explicit-path model. No new quality evaluation or official test data. Includes Python graph/model preparation in separate cold measurements and full output serialization in warm totals. Database extraction and transfer are excluded. The single-query measurement is one fixed query, not a population latency percentile.

The first freeze `runtime-v1` was never timed: before execution, an asymmetric result-ID conversion in the harness was corrected and the campaign was frozen as `runtime-v1b`. Earlier measured regressions are retained; iteration 2 failed its declared regression gate.

See [protocol](PROTOCOL.md), [all raw timing records and summaries](REPORT.json), [verification](VERIFICATION.json), and [manifest](MANIFEST.json). Frozen source is included for inspection; large input and prediction arrays remain in the local run directory and must be regenerated for external reproduction.
