# Security and data handling

The preview operates on caller-supplied graph projections and immutable numeric
model artifacts. The core inference runtime needs no external inference service.
The example download commands fetch pinned public datasets only when invoked.
Their HTML reports load no remote assets; graph/result data stays in the output
directory you select.

Use database credentials with read-only access for the Neo4j adapter. Query
classification is an additional guard, not a substitute for database permissions.
The public demo starts its own loopback-only temporary database with fixture data;
it does not expose a service or connect to an existing database.

Snapshots, query bindings and result exports may contain sensitive application
data. Keep them out of public issues and benchmark artifacts. Content IDs identify
artifacts; they do not anonymize their contents. Validate data provenance and
configure resource limits before processing untrusted inputs.

For a suspected vulnerability, use the repository's
[private vulnerability reporting form](https://github.com/ho3h/orbweaver-query/security/advisories/new).
Do not post credentials or private graph records in a public issue. The release
owner enables and verifies this channel as part of making the standalone repository
public; no monitored external security mailbox is promised.

The project is a development preview. It does not promise a production support
SLA or an audited sandbox for arbitrary Python model implementations.
