# Native Mac distribution validation

Candidate wheel `c4293575816a657ca043706c402deab6139e251c11f4701f3d8e58a53825ed7e`,
built through the source archive at commit `dbd287e`. No runtime code was changed
by the release preparation. All tests below import the installed wheel under
`python -I`, with the source import path cleared. Minimal tests ran from the
extracted source distribution, verifying that its test/benchmark helpers exist.

| Native ARM Python | NumPy | Installed tests | Trained demo |
| --- | --- | --- | --- |
| 3.11.15 | 2.4.6 | 301 passed, 12 optional skips | Passed, fresh verified data |
| 3.12.13 | 2.4.6 | 301 passed, 12 optional skips | Passed, fresh verified data |
| 3.13.12 | 2.4.6 | 301 passed, 12 optional skips | Passed, fresh verified data |
| 3.14.3 | 2.4.6 | 301 passed, 12 optional skips | Passed, fresh verified data |
| 3.11.15 | 1.26.4 | 301 passed, 12 optional skips | Passed, fresh verified data |

A separate installed scientific environment (SciPy 1.17.1, scikit-learn 1.9.1,
threadpoolctl 3.7.0) passes 305 tests with eight optional skips. It exercises the
independent sparse scoring oracle and training tests. The full existing source
environment, which also has MLX, passes 306 tests with seven optional skips.
Skips include opt-in database/GDS and optional research-backend dependencies;
these counts do not imply CUDA/Quail inference ran.

Both Neo4j Python driver 5.28.0 and 6.1.0 pass all three live integration tests
against newly created disposable Neo4j Community 2026.09.0 instances. The helper
verifies matching native ARM Python and Java 21.0.10+7-LTS, isolates database
storage and ports, and terminates each owned server afterward. These tests cover
read-only rejection, pair scoring, composed plans and dependent expansions.
They do not rerun the historical GDS performance campaigns.

The first clean-install test attempt found an unguarded SciPy import in a
benchmark oracle test. Its failure logs are retained under `initial-minimal-failure/`.
The fix marks that one scientific test optional in a NumPy-only environment;
it passes in the scientific environment. The runtime did not acquire a SciPy
dependency. All five clean installations above passed after that correction.

The build yields a 100,028-byte wheel with 25 members and NumPy as its only core
runtime dependency. The initial validated sdist has 149 members / 1,019,865 bytes.
A final documentation/tool-only rebuild is audited separately; its wheel must
remain byte-identical to the tested and benchmarked candidate. Metadata checks
(`twine check`) pass. Historical worker archives, local runs, environments and
bytecode are excluded. Nine small frozen demonstration inputs are included.

`VALIDATION.json` retains commands, versions and original archive hashes. Logs
retain outcomes; local home paths are redacted. The hosted matrix could not start
because of an account billing/spending limit; it is not counted as validation.

All three README Python examples run using the installed wheel, including the
real Cypher example on a new disposable database. The public helper now exposes
the Neo4j 2026.09 entrypoint and checks native architecture from its CLI. Its
installed-runtime command passed the three live tests:

```sh
python tools/disposable_neo4j.py --installed \
  --neo4j-home /path/to/neo4j-community-2026.09.0 \
  --java /path/to/native-arm-java21/bin/java \
  --entrypoint org.neo4j.server.Neo4jCommunity
```

The default entrypoint is retained for older Neo4j distributions. These paths
refer to caller-provided software; the helper creates its own temporary database
and never opens an existing data directory.
