# Installation verification, 2026-09-26

Built `orbweaver_query-0.1.0.dev0.tar.gz`, then the wheel through that sdist using
`uv build packages/query --out-dir packages/query/dist`. Installed the wheel into
a fresh virtual environment with no editable source package. Confirmed imports
resolve to that environment's `site-packages`.

- Wheel SHA256: `674d152049bf2fc3efac463c48b74bb89a0148b9f5c7152fc02ac193245efd6d`.
- Wheel size: 16,200 bytes, excluding dependencies and model artifacts.
- Python 3.11.15, NumPy 2.4.6, pytest 9.1.1, macOS Apple Silicon.
- `python -I -m pytest -q packages/query/tests -o pythonpath=`: **36 passed,
  1 skipped** (the opt-in live fixture).
- Installed Neo4j driver 6.3.1; ran `tools/disposable_neo4j.py --installed`
  against a new isolated Neo4j 5.26 instance: **1 passed**. The process was stopped
  and the disposable data directory removed by the runner's `finally` block.
- Current implementation, tools and test Ruff scope: passed.
- Wheel metadata includes the Apache-2.0 license file, Python >=3.11 and NumPy
  as the sole required dependency; Neo4j and development tools are optional.
  No research modules, tests, or benchmark modules are present in the wheel.

This verifies installation and the declared fixture behavior on one platform.
The cross-platform CI definition has not yet run remotely. Public model
reproduction, realistic database performance and launch readiness remain open.
