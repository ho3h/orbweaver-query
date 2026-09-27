# Native-runtime comparison correction

2026-09-26. The original structural campaign's frozen manifest records an
x86_64 Temurin 21.0.10+7 Java runtime. The executable is x86_64, and executing
`java -XshowSettings:properties -version` reports `os.arch=x86_64`. Python is
arm64 on this Apple M5 Max. Neo4j therefore ran under architecture translation
while Orbweaver's local computation ran natively.

The original 1.229x local cold-request ratio cannot establish a fair native
performance advantage. The correctness outputs remain evidence of numerical and
binding agreement for those runs; correctness does not repair timing fairness.
The historical archive, including its original findings, is deliberately unchanged.
Read its latency interpretation together with this correction.

The same local Java installation was used for the earlier learned GDS runs.
Their fitting/prediction stage times must not establish native cost parity either;
they already had different result-transfer boundaries and remained diagnostic.
This finding does not justify discarding their retained quality outputs or
claiming that changing architecture leaves learned outputs bitwise identical.
The structural rerun does not close learned-pipeline cost or four-thread gates.

The replacement uses the same Temurin 21.0.10+7-LTS version for macOS aarch64,
downloaded from the [official Adoptium release](https://github.com/adoptium/temurin21-binaries/releases/tag/jdk-21.0.10%2B7).
The tarball SHA-256 is
`c3be8c87f1a5cdc727903546eb810e112f94cd7222dac6a9d3f3146ee932008d`,
matching the release checksum. The old installation remains intact. The benchmark
checks the actual VM properties, Python architecture and Apple Silicon hardware
before freezing and again in every worker; mismatches fail before measurement.
The learned GDS worker applies the same preflight before fitting.

The replacement campaign uses the original graph/query inputs, Neo4j/GDS versions,
request semantics and nine-worker protocol, with the current Orbweaver source.
It is a new native comparison, not an isolated estimate of Rosetta overhead:
Orbweaver source has also changed since the original campaign. The replacement
manifest is `0064e96a644954fc880273156bc463504f78296760ff911acbb42d1656db877e`.
Original and replacement runtime identities are retained in `runtime-identities.json`.

The [replacement campaign](../native-structural-arm64-development-v1/FINDINGS.md)
completed all nine workers and 432 physical conditions. Every output agrees within
1.43e-14. Current local cold requests show only a descriptive 1.059x ratio against
the strongest native control before export; charging export over 1,000 requests
gives 0.970x. Warm local execution is 0.889x against the strongest warm control.
These results establish neither a substantial native advantage nor a 1.0 gate.
