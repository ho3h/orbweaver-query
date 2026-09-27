# Complete GDS development application evidence; timing isolation not established

All 18 frozen workers completed without recorded failures: three public graph
families, one/four configured threads, and three process repetitions. The frozen
summary validates all 48 application/thread/arm outcomes and 432 timed request
samples. Every request matches its own full-score reference. This compares
application quality/cost across different methods, not numerical equivalence
between learned GDS and Orbweaver.

**This campaign does not close a release gate or establish competitive latency.**
A host snapshot during worker 10 showed unrelated Python computation. The retained
`HOST_ACTIVITY_OBSERVATION.json` records this workload-isolation protocol deviation.
Its magnitude and duration are not measured; do not remove particular samples,
correct ratios speculatively, or describe these observations as isolated timing.
Exact replay verifies calculations and answers, not uncontended performance.

The selected local method is resource allocation for collaboration/friendship and
the existing path model for communication. GDS configurations, evidence graphs,
64 sources per graph, and fitting seed remain the original development choices.
No confirmation labels were opened for this campaign or its independent audit.

## Development quality

Arithmetic means over all three process repetitions; repeats reuse fitting seed
71 and are not independent label samples. Positive-query denominators are 46,
225 and 208 respectively. Raw-score ties use expected uniform-tie recall; actual
answers use scores rounded to 12 decimal places, then ascending application ID.
Full rounded-score metrics and all positive outcomes remain in the archive.
These are development-selection observations, not held-out superiority evidence.

| Application | Threads | Selected raw recall@16 | GDS raw | RA raw | AA raw | Selected actual ID recall@16 | GDS actual ID recall@16 |
|---|---:|---:|---:|---:|---:|---:|---:|
| collaboration | 1 | 0.810544 | 0.748188 | 0.810544 | 0.796051 | 0.804348 | 0.739130 |
| collaboration | 4 | 0.810544 | 0.748188 | 0.810544 | 0.796051 | 0.804348 | 0.739130 |
| friendship | 1 | 0.564444 | 0.480000 | 0.564444 | 0.551111 | 0.564444 | 0.480000 |
| friendship | 4 | 0.564444 | 0.480000 | 0.564444 | 0.551111 | 0.564444 | 0.480000 |
| communication | 1 | 0.466346 | 0.379808 | 0.442308 | 0.456731 | 0.466346 | 0.379808 |
| communication | 4 | 0.466346 | 0.379808 | 0.442308 | 0.456731 | 0.466346 | 0.379808 |

## Descriptive request latency, milliseconds

Each cell is the median of three process medians, each from three timed requests
following a warmup. These numbers include request-boundary operations and JSON
serialization. Native structural arms rank in Neo4j; learned GDS uses adaptive
per-source queues followed by transfer and Python ranking. Ordinary answer lookup
is intentionally retained as a repeated-request control.

| Arm | Collaboration / 1 | Collaboration / 4 | Friendship / 1 | Friendship / 4 | Communication / 1 | Communication / 4 |
|---|---:|---:|---:|---:|---:|---:|
| Orbweaver selected | 549.878 | 518.909 | 220.027 | 98.953 | 4,661.275 | 2,012.797 |
| Manual selected method | 395.335 | 332.031 | 165.774 | 78.402 | 4,659.985 | 2,001.912 |
| Native scalar RA | 8,538.718 | 8,667.267 | 36,849.350 | 16,297.625 | 6,259.847 | 2,942.916 |
| Native shared-traversal RA | 573.185 | 529.576 | 117.371 | 57.472 | 103.571 | 47.392 |
| Native shared-traversal AA | 476.181 | 537.838 | 122.498 | 52.567 | 94.809 | 40.685 |
| Learned GDS | 49,829.094 | 15,092.513 | 7,624.892 | 1,596.454 | 1,615.425 | 654.829 |
| Cached selected answers | 16.331 | 22.231 | 8.577 | 4.118 | 14.771 | 4.169 |
| Cached GDS answers | 16.564 | 15.981 | 10.481 | 3.979 | 16.910 | 4.562 |

The selected local method has higher development recall than learned GDS on all
three graphs. That does not establish an execution advantage: native structural
controls are much faster on friendship and communication in these observations;
manual execution also avoids local wrapper overhead. On communication, learned
GDS requests are faster than the selected path model despite lower recall.
None of these timing differences has been isolated from the observed host activity.

## Preparation, seconds

Median of recorded per-process preparation costs. Local/manual preparation includes
snapshot export and local fitting; learned GDS includes source-label preparation,
projection and training. Shared-traversal structural arms charge native degrees.
Cached arms additionally charge actual answer construction. Common database
startup/import is recorded separately in every worker and excluded for all arms.
Native arms do not pay graph export. These are different algorithms and fitting
requirements; setup is not interchangeable work.

| Arm | Collaboration / 1 | Collaboration / 4 | Friendship / 1 | Friendship / 4 | Communication / 1 | Communication / 4 |
|---|---:|---:|---:|---:|---:|---:|
| Orbweaver selected | 1.290 | 1.674 | 3.708 | 1.454 | 39.796 | 66.272 |
| Manual selected method | 1.290 | 1.674 | 3.708 | 1.454 | 39.796 | 66.272 |
| Native scalar RA | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Native shared-traversal RA | 0.134 | 0.151 | 0.097 | 0.046 | 0.099 | 0.118 |
| Native shared-traversal AA | 0.134 | 0.151 | 0.097 | 0.046 | 0.099 | 0.118 |
| Learned GDS | 629.406 | 179.968 | 62.449 | 9.536 | 11.128 | 9.515 |
| Cached selected answers | 1.988 | 2.774 | 4.087 | 1.576 | 44.756 | 74.656 |
| Cached GDS answers | 683.039 | 199.019 | 73.599 | 11.258 | 14.235 | 12.969 |

## Descriptive amortized latency over 1,000 requests, milliseconds

Median of each process's request latency plus its own preparation cost / 1,000;
not a sum of independently aggregated medians. Results also retain 1, 10 and 100
request counts. No update/invalidation or unseen-query timing is implied.

| Arm | Collaboration / 1 | Collaboration / 4 | Friendship / 1 | Friendship / 4 | Communication / 1 | Communication / 4 |
|---|---:|---:|---:|---:|---:|---:|
| Orbweaver selected | 551.684 | 520.527 | 223.735 | 100.361 | 4,701.071 | 2,080.683 |
| Manual selected method | 397.140 | 333.856 | 169.483 | 79.809 | 4,699.781 | 2,069.798 |
| Native scalar RA | 8,538.718 | 8,667.267 | 36,849.350 | 16,297.625 | 6,259.847 | 2,942.916 |
| Native shared-traversal RA | 573.319 | 529.755 | 117.486 | 57.518 | 103.653 | 47.519 |
| Native shared-traversal AA | 476.315 | 538.016 | 122.613 | 52.610 | 94.908 | 40.812 |
| Learned GDS | 50,458.500 | 15,282.286 | 7,687.341 | 1,605.720 | 1,626.553 | 664.808 |
| Cached selected answers | 19.125 | 25.005 | 12.664 | 5.651 | 59.340 | 80.259 |
| Cached GDS answers | 719.717 | 223.142 | 93.853 | 15.054 | 36.694 | 17.695 |

## Validation and retained limitations

- The 352-file archive verifies all 18 workers and restores outside the checkout.
  Its frozen summary reproduces `results.json` byte for byte.
- A separate implementation reconstructs raw/rounded development quality, all
  per-positive outcomes and deterministic returned rankings from saved score arrays
  and graph triples for all 18 workers. See `INDEPENDENT_AUDIT.json` and `REPLAY.json`.
- All 90 retained native requests match their references. All 144 resource
  checkpoints report no active GDS tasks and zero task reservations, with verified
  one-minute task retention. This is bounded completion evidence, not a service
  longevity or concurrent-load reliability claim.
- Full raw scores, process medians, setup components, outputs, classifier training
  records and whole-worker RSS are retained. RSS is not per-arm memory usage.
  Native GDS classifier weights were not exported; saved predictions are not a
  reloadable classifier artifact.
- The earlier intentionally interrupted campaign and failed queue campaign remain
  separate evidence. This complete run does not replace or erase them.
- Confirmation quality, isolated performance, graph/model update costs, and the
  supported-CUDA investigation remain separate requirements. No 1.0 gate closes.

## Reproduction

From the repository root:

```sh
python packages/query/benchmarks/results/gds-application-development-v2/archive_support.py verify \
  packages/query/benchmarks/results/gds-application-development-v2
python packages/query/benchmarks/results/gds-application-development-v2/archive_support.py restore \
  packages/query/benchmarks/results/gds-application-development-v2 \
  --output /tmp/gds-application-replay
python /tmp/gds-application-replay/gds_application.py summarize /tmp/gds-application-replay
cmp /tmp/gds-application-replay/results.json /tmp/gds-application-replay/recorded-results.json
```

Reconstruction needs the frozen runner's Python dependencies; it requires neither
Neo4j nor refitting. A new timing run additionally needs the pinned Neo4j/GDS/Java
and an otherwise idle host. Do not execute into an existing completed run.

Archive SHA256: `d84d25764c990bebf26d1f867b10c61945bbfa566283981e85f97e7e5b9501f2`.
