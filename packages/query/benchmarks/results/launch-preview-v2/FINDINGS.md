# Public walkthrough and publication validation

This pass adds a usable movie walkthrough, CSV/Neo4j integration documentation,
public entry files and a fixed end-to-end protocol. Runtime source and all 21
runtime members of the wheel are byte-identical to the previously validated
Mac candidate. The package remains `1.0.0.dev1`; no competitive gate is closed.

## Installed distribution and examples

The wheel was built through the source archive at `5996446`. Archive hashes and
member counts are in [distribution.json](distribution.json). The 100,413-byte
wheel retains NumPy as its only core dependency; the 1,048,611-byte sdist includes
the new examples, publication templates, tests and benchmark. Distribution audit
and Twine metadata checks pass. This build still identifies the private research
origin in package metadata; the publication tool changes the proposed repository
URL only in the separate export, which requires its own build receipt.

Tests ran with isolated Python against that installed wheel, from the extracted
sdist rather than the source import path:

| Environment | Passed | Optional skips |
| --- | ---: | ---: |
| Native Python 3.11.15, NumPy 2.4.6, scientific/Neo4j extras | 318 | 8 |
| Native Python 3.14.3, NumPy 2.4.6, no package extras | 314 | 12 |

The earlier five-environment matrix remains applicable to unchanged runtime
members; it is not represented as a rerun of these 13 new example/export checks.
The Python 3.14 installed trained quickstart and the literal CSV guide both pass.
The five CSV rows retain documented scores, null/unsupported states and duplicate
request identity. [Validation](validation.json), the test logs and CSV output are
retained beside this report. Lint and whitespace checks pass.

The [generated movie report](movie-demo/index.html) contains 28 recommendations
from 28 candidates on a 140-node, 172-edge acting projection. Every record agrees
with native Cypher and the unfused plan within 1e-12. Shared preparation uses
three source expansions versus six without sharing; model calls remain six.
This is a work-count demonstration, not a latency claim. Its layout, cast filter
and expandable physical plan were inspected in the local browser. The upstream
fixture's original values are retained, including its intentionally incomplete
and sometimes inaccurate film metadata.

## End-to-end comparison status

The [protocol](../../MOVIE_WORKFLOW_PROTOCOL.md) freezes three workloads, seven
arms and three fresh-process repetitions: 63 campaign clients, each with first
use plus seven request samples. Native Cypher, independent manual intersections
and shared full-source expansion are the competitive on-demand controls.
Warm caches and unfused execution are separate controls. Export, connection,
preparation, transfer, materialization, JSON and subprocess costs are explicit.

Freeze `movie-workflow-v2` at source `b9a405e` has manifest SHA-256
`14e36defbafcd71e549aae278daa2913c90ee8684520cdf17de3e9039fc244ee`.
Neo4j Community 2026.09.0, native Java 21.0.10 and driver 6.1.0 are pinned.
The seven-arm preflight passes native-reference checks for every arm on the
36-row repeated-input basket. The frozen single/filtered workloads return eight
and four rows respectively; those answer checks happened before measurement.

**The quiet campaign is pending. Zero of its 63 clients have been measured.**
Preflight timings are incidental and are not aggregated into a performance claim.
The earlier 648-worker mixed-use study remains unchanged and separately labeled.

[preflight-evidence.tar.gz](preflight-evidence.tar.gz) retains the frozen scripts,
protocol, wheel, graph, native expected outputs, manifest, all seven preflight
records and campaign metadata. SHA-256:
`aa0aca075d1da2a83de0a96562fdc7ea37c8f05ed2e9645d74cf740ac612ac24`.
The original upstream `movies.cypher` is omitted from distribution; fetch it
from the pinned URL in the example and verify its manifest checksum before replay.

To restore the omitted input after extracting the evidence archive into a new
directory, run from that directory with the installed wheel and Neo4j extra:

```sh
python -I -c 'import pathlib,sys; sys.path.insert(0,"examples"); from movie_recommendations import fetch_fixture; pathlib.Path("movies.cypher").write_bytes(fetch_fixture(pathlib.Path("fixture-cache")).read_bytes())'
```

Use the protocol's execute/verify commands only during the arranged quiet window.
Existing preflight records are retained; use a new freeze for a new preflight.

## Publication boundary and retained attempts

The first export stopped safely at the 512 MiB decoded-stream limit. Historical
adverse JSONL evidence includes streams up to about 726 MiB; the scanner was
changed to a bounded 1 GiB per payload and then completed without exclusions
matching any filename or readable nested payload. Nothing was omitted to pass.
The [initial successful export receipt](initial-publication-check.json) covers
1,526 files, 3,088 unique payloads and 3,656 archive members at `f343494`.
It is an intermediate check, not certification of later unscanned additions.

The first benchmark freeze was superseded before client measurements to pin the
driver version and retain outputs before correctness checks. Its manifest hash
is retained in validation.json. No timing-based input/arm selection occurred.

The export contains selected paths and no Git history. Its destination URL is
proposed local metadata only. No remote creation, public visibility change,
package upload, merge or release tag has occurred. Hosted CI remains blocked by
the previously recorded account billing/spending limitation; local results do
not imply a hosted CI pass.
