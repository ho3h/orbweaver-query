# Installed-wheel reproduction

The source distribution built a 71,231-byte wheel, SHA-256
`c2a387ef67e5c6c5c609fe968aea96862e51d0ac65a8e49456fd6bcf8252674e`.
Inspection confirmed the numeric model, provenance, protocol and third-party
notices were included. The source distribution includes the model card.

An isolated runtime environment used Python 3.11.15, NumPy 2.4.6 and Neo4j driver
6.3.1. The installed package passed 38 tests; the live test and two optional
training tests were skipped in that run. A separate installed-wheel test passed
against a disposable Neo4j 5.26 server. The documented demo downloaded the pinned
data into a fresh directory, reconstructed the expected graph, and produced
learned rankings plus four reused expansions across eight requests. No training
dependencies were installed in that environment.

A second clean environment installed the wheel's training extra with NumPy
2.4.6, SciPy 1.17.1, scikit-learn 1.9.1 and threadpoolctl 3.7.0. It passed 41 tests,
including a subsequently added bundled-model check; only the opt-in live test
was skipped. The documented freeze/execute/verify commands rebuilt all three
models, fitted all 12 controls and replayed every data/example/feature/outcome
check. All quality gates passed. This verifies the installed commands independent
of repository imports and with a newer dependency set than the first reproduction.
All three fitted model content identities and all evaluation metrics/digests
also match the first reproduction exactly.

These are local Apple Silicon observations. Defined Linux/macOS/Windows CI has
not yet run remotely. No cross-platform result is implied by this receipt.
