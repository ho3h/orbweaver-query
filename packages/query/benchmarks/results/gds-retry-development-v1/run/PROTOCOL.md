# Matched link prediction: development protocol

Written before external held-out measurements. This is development, not the
final confirmation campaign required by ACCEPTANCE.md.

## Applications and evidence

Use public SNAP ca-GrQc (scientific collaboration), facebook_combined (social
friendship), and email-Eu-core (institutional communication). Only anonymized
edge IDs are used; node profile/department attributes are not loaded. Canonicalize
unordered non-self pairs. Email is explicitly evaluated as existence of any
communication between two people, not prediction of email direction. Preserve
all declared endpoints, including nodes isolated after splitting.

Assign canonical pairs to outer train/development/confirmation roles in an
80/10/10 split using NumPy RNG seed 20260926. Save confirmation pairs separately;
the development evaluator must not load them. Fit both arms only from outer
training edges and score using that same outer training graph. GDS's native
internal splitting and Orbweaver's internal evidence/fitting split are recorded
separately: equal outer information access does not imply identical internal
training algorithms or examples. Reverse directions cannot cross outer roles.

Initial probe: ca-GrQc, seed 71. Before fitting, select 64 query sources uniformly
from the full node schema using RNG 20260927, independently of edges/labels/scores.
Evaluate every outer-development positive incident to those sources, in each
queried direction. Candidate domain is every other node not adjacent in the
outer-training graph. Unsupported Orbweaver positives count as misses.

## Arms and selection

Native GDS 2026.09.0 on Neo4j Community 2026.09.0 / Java 21: FastRP 64-dimensional
features, Hadamard link features, logistic regression (penalty .1, 200 epochs)
and random forest (50 trees, depth 10), selected by the native pipeline's internal
three-fold AUCPR. Internal test fraction .2, training fraction .3, negative ratio
1.0, seed 71, concurrency 1. Exhaustive prediction (sampleRate 1) with sufficient
topN to retain the complete requested candidate domain. Verify returned pair
coverage explicitly; output truncation or label-domain changes invalidate the run.

Orbweaver path baseline: independently split outer training pairs into 56%
feature evidence, 24% fitting positives and 20% unused internal validation using
seed 71, matching the native GDS role proportions. Fit one logistic model using
the existing conventional explicit-path features and sampled ranking contrasts.
Represent undirected evidence with both asserted directions, so arbitrary node-ID
ordering cannot create predictive direction features. Score on outer training
only. Record unsupported positives and fitting coverage.

Also evaluate common-neighbor, Adamic–Adar and resource-allocation controls on
exactly the outer-training graph and candidate domain. These need no fitting.
The initial probe diagnoses gaps; broader tuning must give every arm a declared
comparable selection budget before final confirmation.

## Metrics and cost

Primary: mean expected recall@16 per positive query under uniform score ties.
Also report recall@64, MRR, support coverage, and all per-query outcomes. Existing
training neighbors and self-pairs are outside the shared candidate domain.
Do not remove other development positives from ranking. GDS zero-probability
predictions remain valid scores, not unsupported results.

Record graph ingestion/projection, fitting/preparation and prediction separately.
Initial GDS wall time includes streaming all scores to the client; report that
boundary explicitly rather than comparing it to pure kernel time as if equal.
The later application benchmark must align returned results and query boundaries,
repeat fresh processes and run GDS at both one and four threads. Do not infer
performance superiority from the initial diagnostic timings.

Never overwrite a failed attempt. Freeze source, parameters, splits and data
hashes before execution; retain errors and complete metric denominators.

Sources: [ca-GrQc](https://snap.stanford.edu/data/ca-GrQc.html),
[Facebook](https://snap.stanford.edu/data/ego-Facebook.html),
[email](https://snap.stanford.edu/data/email-Eu-core.html),
[GDS splits](https://neo4j.com/docs/graph-data-science/current/machine-learning/linkprediction-pipelines/config/),
[GDS prediction](https://neo4j.com/docs/graph-data-science/current/machine-learning/linkprediction-pipelines/predict/).

## Declared development expansion after the initial diagnostic

Before additional native GDS runs, add three fixed configurations to the original
64-dimensional pipeline: (1) FastRP 256 with Hadamard; (2) FastRP 256 with
Hadamard, cosine similarity and an internal feature-input degree product;
(3) configuration 2 with negativeSamplingRatio 16. Keep the native two-classifier
selection, split proportions and random seeds fixed. Increase the JVM heap cap
to 8 GiB on the 128 GiB development host to avoid handicapping the larger native
training matrix. This is a resource ceiling, not measured memory consumption.

Reuse the frozen path/structural outcomes only after checking exact outer-graph
and development-query file identities. Reused costs are not new timing samples.
Choose the best of the four native pipeline configurations using development
recall@16, and separately consider the four Orbweaver choices (path, common
neighbors, Adamic–Adar, resource allocation). Native GDS also gets its internal
classifier selection; this is not a claim of identical fitting budgets. No
confirmation outcomes may be read until the final selection protocol and all
configurations are frozen. Secondary MRR uses reciprocal average tie rank.

## Resource-budget retry

The 256-dimensional rich-feature pipeline with negative ratio 16 completed on
collaboration and communication, but the friendship attempt terminated at the
900-second transaction ceiling. Preserve that failed attempt and its source,
logs and manifest. Retry only friendship in a fresh frozen directory with a
3,600-second transaction ceiling; keep data, random seeds, model settings,
8 GiB heap and single-threaded fitting unchanged. A longer training allowance
is a resource-budget change, not another quality-tuning configuration. Run it
after the composed-plan timing campaign to avoid local CPU contention.
