# Mac installed-distribution demonstration, version 1

Frozen before this campaign's timings. This validates a public development
preview; it does not replace the original competitive 1.0 acceptance gates.
No training, new model selection, CUDA, cloud execution or confirmation-label
access occurs. Run on native Apple Silicon Python, never through Rosetta.

## Fixed inputs and controls

Use the unchanged three graph/model artifacts and eight query sets from
`results/v1-development/inputs` and `targeted-development-v4`. The source archive
includes just these small inputs, not the historical worker archives. WordNet
uses its trained seed-71 model. Movies and collaboration use deterministic random
coefficients for runtime testing, not predictive-quality evidence. These are
reused development fixtures. Sources and transformations are documented in the
[original findings](results/v1-development/FINDINGS.md); data retains its original
providers' terms, including the bundled WordNet/ConvE notices.

Eight workloads per graph: single, distinct128, interleaved256, clustered256,
many_targets256, hubs16, duplicates256 and reachable_distinct. They exercise
source reuse, target density, duplicates, hubs and unsupported endpoints. Do not
select only the supported or favorable cases for the aggregate.

Nine arms: full source expansion; independent feature/score LRUs at 64 KiB and
16 MiB; full/LRU controls with cheap self/adjacency rejection; exact targeted
execution; initially empty pair cache; warm pair cache; oracle full-score
precomputation for the known source/relation working set. The on-demand denominator
is the fastest of the five full/LRU controls in each condition. Warm pair cache
and warm precomputation remain visible separately. The oracle omits repeated
schema validation; its numeric-array accounting omits Python dictionary overhead,
which is reflected only in process RSS. Every arm receives identical inputs.

## Boundary and repetitions

648 fresh subprocesses: three processes × three graphs × eight workloads × nine
arms, shuffled with seed 2026092702. Set all six recorded native thread variables
to one. Each process loads graph/model artifacts, performs its arm's preparation,
and executes four calls. Retain first-call latency separately; summarize the
following three calls by their median. No answer cache persists between requests
except in the explicitly warm arms. Intra-request LRU/source reuse is allowed.

Request timing includes scoring, result materialization, `to_records`, JSON
serialization and UTF-8 encoding. It excludes interpreter/import startup,
artifact loading, disk output, checksum verification and diagnostics. Artifact
loading/session construction and warm preparation are timed separately; report
their sum with first request as loaded first use. This is not a Neo4j end-to-end
measurement and does not include data download or graph export. Report process
peak RSS and numeric retention separately, never equating the two.

Verify installed package members against the supplied wheel before freezing and
before every worker. Freeze helper code, inputs, wheel, protocol, hardware and
dependency identities in a SHA-256 manifest. Record aggregate process CPU use,
load averages and available thermal status before/after every worker. These
observations cannot certify isolation. `normal-mixed-use` is the default label;
`quiet-requested` requires the operator to arrange a quiet interval, and still
is not proof that no background work occurred. No deletion of slow samples,
selective repeats or automatic continuation after failure.

## Correctness and reporting

Compare all returned rows, order, bags, support/status and provenance with full
expansion. Numeric tolerance is 1e-12 absolute and relative. Reject changed
outputs within a worker. Separate unit tests compare path scores against an
independent walk enumerator; matching this benchmark's full arm alone is not
independent algorithm verification.

Report every condition and arm, all samples, preparation, RSS, first-call cost,
all regressions over 10% and the geometric mean of per-condition speedups.
Bootstrap 10,000 draws with seed 2026092703, resampling the three process medians
within each condition/arm and reselecting its fastest control. The 95% interval
is conditional on these reused workloads and this host session. It does not
quantify contention bias or generalization to other graphs/MacBooks.

## Commands from an extracted source archive

```sh
python -m pip install build
python -m build
python -m pip install dist/orbweaver_query-1.0.0.dev1-py3-none-any.whl
python -I benchmarks/mac_release.py freeze mac-run \
  --wheel dist/orbweaver_query-1.0.0.dev1-py3-none-any.whl
python -I mac-run/mac_release.py execute mac-run
python -I mac-run/mac_release.py verify mac-run
```

Use a new run directory. Verification writes `results.json` for the reused
correctness evaluator and `mac-results.json` for the full Mac measurement record.
Run numerical verification once per restored copy; outputs are write-once.
For replay, copy the frozen run without generated result summaries and invoke its
`verify` command. Performance replication requires installing the recorded wheel
and matching native Python/NumPy and host identity, then a fresh freeze/execute.
