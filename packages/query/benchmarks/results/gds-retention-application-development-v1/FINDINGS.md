# Task retention survives the original collaboration workload

Both fresh native GDS processes completed: the original 5,242-node collaboration
graph, all 64 development sources, at one and four configured threads. Each fit
selected random forest from the unchanged two-model selection budget. The rich
FastRP256 pipeline, negative ratio 16, pinned native binaries and 8 GiB heap match
the earlier failed conditions. Only the supported completed-task retention
setting changes to 60 seconds; the reservation guard stays enabled.

The two saved full-score matrices each cover all **335,071 candidate pairs**.
They match their respective earlier failed run's matrices exactly: maximum
absolute difference **0.0**, with the same saved-array SHA256. All **ten repeated
requests** match independently reconstructed stable-ID top-16 outputs. Each
request uses nine overfetch rounds, 89 native procedure calls and 29,682 returned
pairs. This preserves the earlier exact request formulation.

| Observation | One thread | Four threads |
|---|---:|---:|
| Successful repeated requests | 5 | 5 |
| Outstanding task reservations at all nine checkpoints | 0 bytes | 0 bytes |
| Active tasks at those checkpoints | 0 | 0 |
| Largest observed retained-task count | 679 | 1,321 |
| Retained tasks after the 65-second cleanup wait | 0 | 0 |
| Largest sampled JVM heap use | 609.4 MiB | 675.7 MiB |

The heap observations are samples, not peak-memory measurements. Effective GDS
settings read back as progress tracking enabled and retention `1m`. The retained
task records permit completion listeners to release reservations and are then
removed; they do not accumulate indefinitely over these observed requests.

This validates the opt-in configuration workaround for the reproduced full-graph
failure. It does not establish long-running stability, concurrent-client behavior,
a latency improvement or an Orbweaver advantage. No timing comparison is derived
from the instrumented processes. The original six-condition timing suite remains
failed and unchanged. No confirmation inputs were read and no model was retuned.

## Independent replay

The 115-file archive includes both original failed-run references, frozen input
graphs and sources, complete new model-selection records, scores, every request
and resource checkpoint, process consoles and successful terminal outcomes.
The replay reads raw graph triples and scores directly, without importing the
worker's candidate/ranking functions. It rebuilds the candidate mask, rounded
ID-tiebroken rankings, development metrics and previous-score differences.

Archive verification and numerical replay both pass. The restored summary is
byte-identical. Seven mutation checks reject missing/failed terminal outcomes,
missing requests, changed answers, unreleased reservations, unexpired task records
and changed recorded quality. The audit also rejected the real suite while its
parent had not yet written terminal outcomes. See `REPLAY.json` for the retained
replay and mutation-check results. Core package source is unchanged from the
locally passing 251-test suite (seven optional skips); these resource executions
and replay checks supply the new validation. Ruff and whitespace checks pass.

```sh
python packages/query/benchmarks/results/gds-retention-application-development-v1/verify.py \
  --output /tmp/gds-retention-application-replay
python /tmp/gds-retention-application-replay/gds_retention_application_audit.py \
  /tmp/gds-retention-application-replay
python packages/query/benchmarks/results/gds-retention-application-development-v1/replay_guards.py \
  /tmp/gds-retention-application-replay
```

Archive SHA256:
`3b8a8063821b01dccd3a5eabbd6afaf63b399a07c2bb15d2789ab5d12306f6f7`.
The original frozen suite SHA256 is
`cedab50afebcc9e34a441d0c5182649506a5d43e4c4d441be219aaa37f1ab30d`.

The next performance research decision still requires the matched GPU reference
and a measured graph-specific opportunity. This closes a bounded reference
reliability investigation; all broader 1.0 gates remain open.
