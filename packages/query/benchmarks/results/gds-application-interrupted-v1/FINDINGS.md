# Interrupted native recommendation attempt

2026-09-26. This attempt is incomplete and supplies no aggregate timing claim.
Four of the 18 declared workers completed and validated all eight request arms.
Worker 4 was intentionally interrupted after training, full-score verification
and cache construction. Workers 5–17 were not attempted. The owned worker and
database processes exited; all original frozen inputs remain unchanged.

The reason for stopping was a source audit of GDS 2026.09.0, commit
`1317dc9fcc12322d55c11dc598f024debeea18c8`. Its global topN queue uses sorted arrays;
our exhaustive per-source ranking control retained the full candidate domain in
that global queue. A [new bounded diagnostic](../gds-queue-diagnostic-development-v1/FINDINGS.md)
demonstrates a materially stronger native formulation with identical answers.
Continuing the original repetitions would have measured a weak reference more
precisely. Do not use this attempt to claim an Orbweaver speedup over strong GDS.

`evidence.tar.gz` retains 55 files: immutable source/protocol/input snapshots,
the declared 18-job manifest, four completed workers and raw score matrices,
partial worker-4 scores and logs, its explicit interruption record, and
`CANCELLATION.json`. No aggregate `results.json` is present. The manifest SHA256 is
`8d9e6f1572998e5c2cfd90de00fa999ed13972496d12b2ccc60287923b4cbe28`.
`ARCHIVE.json` indexes every retained byte. Confirmation data were not opened.

From `packages/query`, verify or restore without starting a database:

```sh
python benchmarks/v1/gds_application_archive.py verify benchmarks/results/gds-application-interrupted-v1
python benchmarks/v1/gds_application_archive.py restore benchmarks/results/gds-application-interrupted-v1 --output /tmp/gds-interrupted-evidence
```

Verification checks byte integrity, all frozen input hashes, completed-worker
coverage/output agreement, raw-score hashes and explicit interrupted/unattempted
accounting. It does not refit models or recompute application quality. Restoring
preserves the cancellation and partial results; it does not turn this into a
successful campaign. All release gates remain open.
