# Standalone path-model reproduction v1

Purpose: remove the public package's dependence on a pre-existing research run.
Reimplement the previously declared conventional training procedure using the
portable feature extractor and publicly available input. This is a reproduction
on reused development splits, not fresh accuracy confirmation or a new model.

Input is only the checksum-pinned WN18RR `train.txt` at ConvE revision
`f3c0eb286025410fa5b4c04696c918264163d0ca`. Extract no official validation/test
members. Retain WordNet and source notices. Sort node/relation names; reject
duplicate triples. Exclude seven self links. Group every direction/relation
of an unordered pair together, with fixed RNG seeds 71, 83, 97 and probabilities
80% evidence, 10% fitting, 10% development, matching the prior procedure.

Use the complete two/three-hop path representation and existing evidence rules.
Sort fitting positives by source, relation, target. For each reached positive,
sample at most 16 unobserved alternatives from the full pool, excluding known
evidence/fitting positives. Sampling seed = split + 710000. No development
targets may influence sampling or features. Unobserved alternatives are ranking
contrasts, not certified negative facts. Record reachability and unsupported
relation counts.

Fit four controls per split: base descriptors, positional marginals, full
patterns, shuffled patterns. Use the same examples, per-group weights 1/group
size, C=10, liblinear, no additional intercept, tol=1e-6, max_iter=2000,
random_state=0 and one native thread. Permutation seed = split + 720000.
Convergence warnings fail the run. Finish all 12 fits before development scoring.

Evaluate every development triple against every reached candidate, including
unreachable targets in the denominator. Compare all four controls and uniform
walk mass. Report candidate coverage, raw and known-positive-filtered average
rank MRR, expected tied-budget recall@16/64/256, and per-relation results.
Known full-training positives are used for filtered evaluation only. Shuffled
development seed = 730000 + split + head*relation_count + relation.

Gate: pattern must beat base, marginal, shuffled and uniform controls at
Recall@16/64 on every split, and portable exported-model scores must match
the fitted sparse predictor at atol=rtol=1e-12. This retains the existing
reference's useful ranking behavior; it is not a superiority claim against
all graph-learning methods. Seed71 is the preselected distributable example,
regardless of comparative results. Do not select the most favorable seed.

Freeze source/protocol/config/data identity before fitting. Save graph snapshots,
model artifacts, all fitted controls, sampling rows, sparse feature identities,
all per-query outcome arrays and candidate-score digests. Replay independently
from saved model coefficients, including rebuilding examples/features and
recomputing every evaluation/aggregate/gate. Compare prior sampled examples and
metrics descriptively without making them an input to fitting or selecting
new hyperparameters. Preserve failures and avoid silently changing thresholds.

Record dependency versions, timing and peak process memory. These operational
training timings do not replace isolated runtime or database benchmarks.
