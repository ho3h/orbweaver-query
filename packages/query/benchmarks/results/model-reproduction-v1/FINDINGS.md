# Standalone model reproduction v1

All 12 fits completed before any development evaluation. All 24 predeclared
Recall@16/64 comparisons passed. An independent replay rebuilt all graph
snapshots, sampled examples and sparse features, and reproduced every saved
outcome, candidate-score digest, aggregate and gate. Exported NumPy scores and
the fitted sparse predictor differed by at most 4.44e-15 (tolerance 1e-12).

Input: checksum-pinned WN18RR training file only, 86,835 triples, 40,559 entities
and 11 relations. Seven self links excluded. Seeds 71, 83, 97 assign every
unordered endpoint pair to evidence/fitting/development with probabilities
80/10/10. The official validation/test files were not extracted or read.

Unweighted mean across the three reused development splits:

| Method | Recall@16 | Recall@64 | Recall@256 |
| --- | ---: | ---: | ---: |
| Full typed paths | 28.550% | 33.059% | 34.806% |
| Positional marginals | 26.775% | 32.577% | 34.697% |
| Base descriptors | 24.867% | 31.326% | 34.389% |
| Shuffled path control | 24.272% | 31.121% | 34.326% |
| Uniform walk mass | 20.719% | 29.221% | 33.646% |

Every held-out target contributes to the denominator; unreachable targets score
zero recall. Candidate coverage is 34.442%, 35.788%, 35.685% respectively. Ties
use expected recall under uniform tie-breaking; this is distinct from the public
API's deterministic external-ID tie-break. Raw and known-positive-filtered MRR,
per-relation metrics and all counts are in `results.json`.

The sampling rows/labels/groups/origins exactly match the historical research
run for every split. Base, marginal and pattern recall at all three budgets also
match that run. Shuffled/uniform results differ by at most 0.000183 absolute
recall, associated with floating-point accumulation and exact ties. The new
results are preserved rather than relabeled as bitwise reproduction of those
older controls. The portable scorer is the evaluated implementation.

This is a standalone reproduction of existing training choices on reused
development splits, not new held-out confirmation, a new architecture, or a
claim against state-of-the-art link-prediction systems. `_similar_to` has no
reachable fitting positives in any split and has no learned useful scoring rule.
All scores are rankings; unobserved sampled pairs are not certified false facts.

Preparation took approximately 3.15–3.18 s per split, four-control fitting
0.64–1.05 s per split, and peak process RSS was 245.9 MiB on the recorded local
environment. These are operational observations, not isolated runtime benchmarks.
The preselected seed-71 model is 38,610 compressed bytes; its 122,496 coefficients
occupy 979,968 bytes as float64. Data, graph and model identities are in the report.

The source snapshot, protocol, manifest, results and replay receipt are preserved
here. Large feature/outcome arrays remain in the run directory and are regenerated
by the public `python -m orbweaver_query.reproduce` commands. This pipeline imports
no research modules or artifacts. Current source changes must not overwrite these
measurements; use a fresh run directory for another reproduction.
