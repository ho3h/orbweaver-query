# Mac public-preview release audit

Scope: `orbweaver-query` **1.0.0.dev1**, an independent NumPy graph-scoring runtime,
Python plans and an optional read-only Neo4j adapter. The user has chosen an
exclusively MacBook development/release path. H100 access is not a prerequisite.
This is preparation of a public development preview, not certification that the
original competitive 1.0 objective has been achieved.

The [0.1 audit](RELEASE_AUDIT_0_1.md) is historical. Its wheel sizes, test counts
and hosted matrix do not certify this larger candidate. Current [walkthrough and publication checks](benchmarks/results/launch-preview-v2/FINDINGS.md),
the [earlier runtime matrix](benchmarks/results/mac-release-validation-v1/FINDINGS.md)
and [performance evidence](benchmarks/results/mac-installed-v1/FINDINGS.md)
are recorded with this release's artifacts.

## Claim audit

- The runtime scores exact bound pairs, composes graph/model operations and
  exposes provenance, unsupported/null states and explicit resource limits.
- The [Mac demonstration](benchmarks/MAC_RELEASE_PROTOCOL.md) checks the actual
  installed wheel and includes JSON serialization, loading/setup disclosure,
  strong on-demand caches, warm controls, regressions and process RSS.
- The [performance page](PERFORMANCE.md) preserves favorable and adverse results.
  No generic 2× claim, Quail parity, universal GDS superiority or new general
  learning/inference algorithm is asserted.
- The trained WordNet model is a limited example; model quality and runtime
  speed are separate claims. Text2Cypher results concern adapter conformance,
  not natural-language query generation or missing-link supervision.
- The optional Quail bridge is experimental and outside Mac inference validation.
  No cloud/GPU experiment is required to publish the stated NumPy preview.

## Distribution and validation

The source archive includes runtime, tests, benchmark/tool code, protocols and
small pinned demonstration inputs. Historical worker archives, development runs,
bytecode and environment directories are excluded. The wheel contains the runtime,
bundled numeric model, Apache license and third-party notices. Build the wheel
through the sdist and test that wheel from outside the source import path.

The earlier tested wheel passes 301 tests with 12 optional skips in each of five native
ARM environments: Python 3.11–3.14 with NumPy 2.4.6, plus Python 3.11 with NumPy
1.26.4. Every installed trained quickstart passes. The scientific environment
passes 305 tests with eight optional skips, including the independent sparse
oracle and training tests. Both Neo4j driver 5.28.0 and 6.1.0 pass all three live
integration checks on native Java/Neo4j 2026.09.0. All three README Python examples
execute against the installed wheel, including a disposable live database.

The 648-worker Mac demonstration has exact status/order/bag/provenance agreement
and maximum score error 8.88e-16. Its observed 2.59× on-demand aggregate is
conditional on reused fixtures and a contended host session; it does not close
an isolated-performance gate. Warm lookup and five >10% regressions are retained.
The runtime is unchanged during this packaging/claims work.

The new walkthrough build retains byte-identical runtime members. From its
extracted sdist, the installed wheel passes 318 tests/eight skips with scientific
extras on Python 3.11 and 314 tests/12 skips with minimal dependencies on Python
3.14. Its movie demo verifies 28 rows against native Cypher; its CSV recipe and
trained quickstart execute successfully. All seven end-to-end comparison controls
pass preflight. The [fixed 63-client campaign](benchmarks/results/movie-workflow-v2/FINDINGS.md)
is complete and passes every answer check. Request ratios against the strongest
on-demand controls are 0.86×, 0.71× and 1.23× across the three workloads; native
Cypher has lower median first-use cost throughout. Background activity remained
substantial in the requested quiet window, so isolated performance remains unproven.

Current hosted CI is blocked before execution by the GitHub account's billing or
spending limit: [run 36303358551](https://github.com/ho3h/orbweaver/actions/runs/36303358551).
That is not a passing or failed code test. Native Mac local validation supplies
the current evidence; earlier cross-platform CI remains historical.

## Open decisions and gates

The [original gates](benchmarks/v1/ACCEPTANCE.md) remain open. Held-out GDS quality
meets its original quality conditions, but useful competitive cost advantage is
not proven. Composed execution still loses to the strongest manual control.
No direct Quail throughput comparison exists. Public claims must retain these gaps.

The standalone release destination is `ho3h/orbweaver-query`; the broader research
repository stays private. Package registry upload and a stable 1.0 release remain
outside this preview. No unrelated research history is copied. The
[publication procedure](PUBLICATION.md) exports a
focused repository without history, scans private exclusions including nested
evidence, and requires separate validation of the exported distribution. The
standalone repository receives only that selected snapshot and its own new history.
