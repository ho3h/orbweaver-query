# Matched GDS application confirmation

Declared on 2026-09-27 before inspecting confirmation labels. This is the next
quality evaluation for gate B of [ACCEPTANCE.md](ACCEPTANCE.md), not a change to
that gate or permission to retune on its outcomes. The running development
application campaign must complete and pass archived numerical replay first.
No confirmation array was copied, parsed or evaluated to write this protocol.

## Frozen choices and prerequisites

Use the original three SNAP graph families, outer evidence graphs and 64 sources
per family. The source sample was selected independently of edges, labels and
scores, before development fitting. Keep the original 80/10/10 unordered-pair
split (seed 20260926), source seed 20260927 and fitting seed 71. Do not select new
sources or restrict the denominator to sources with successful predictions.

The original input manifest SHA256 is
`0d5bf2f247943e66aa0f05ceb50eb710ef94d16f83655a0fdd2d6c9e6a2defac`.
The completed development-selection record SHA256 is
`0061cf0e47e0d49c46692a014555c9be1caa4ef9fc5475ff87ff66d52d19c05e`.
The new application manifest SHA256 is
`8d7cf9d8cdf429c190782559e045873953e35cc16dc46df469b125b9b020aba1`.
These references identify inputs and choices; they do not assert that the
currently running application campaign has passed.

| Application | Selected Orbweaver method | Selected learned GDS pipeline |
|---|---|---|
| Collaboration | Resource allocation | Rich FastRP256, negative ratio 16 |
| Friendship | Resource allocation | FastRP64, negative ratio 1 |
| Communication | Existing fitted path model | FastRP64, negative ratio 1 |

Keep each worker's native internally selected classifier and fitted model. Do
not select a preferred process repetition, average score matrices into a new
ensemble, change cutoffs, calibrate scores or reopen the four-configuration
development search. Report one- and four-thread conditions separately; the
three fresh processes repeat seed 71 and are not three independent training
seeds or three new datasets.

Evaluate the selected method against the selected learned GDS pipeline and all
three conventional controls: common neighbors, resource allocation and
Adamic–Adar. All four comparisons are declared now. A control that performs well
on confirmation cannot be silently omitted. Computing the strongest control's
observed score is a reporting rule, not permission to select a new release model.

Before reading labels, freeze a separate confirmation manifest containing this
protocol, evaluation source, verified application archive identity, all 18 worker
and score identities, selected-model identities, original split-file identities,
and the source IDs. Verify graph/source identity and complete score domains
against the development application evidence. The old development manifest and
its `confirmation_evaluation_permitted: false` declaration remain unchanged;
confirmation is a separately identified evaluation, never a relabeled development
run. Any failed prerequisite leaves confirmation unopened.
The local model has its recorded content identity. GDS's saved training record
and complete score matrix identify the frozen prediction artifact; the earlier
application workers did not export native classifier weights. Do not describe
that artifact identity as a serialized, reloadable GDS model.

## Labels, candidate domains and outputs

Only after that freeze, load each original `confirmation-sealed.npz` pair array.
Verify canonical non-self unordered pairs, valid node indices, no duplicates,
and disjointness from outer-training and development positives. Check against
the original split identities; never regenerate or repair a split silently.

For every held-out unordered pair, retain each direction whose source is in the
original 64-source sample. Evaluate every such positive. Exclude only self-pairs
and existing outer-training neighbors from candidates. Do not remove other
held-out positives from ranking. Unsupported path predictions count as misses;
zero-valued structural and GDS scores remain supported predictions. Empty
positive denominators must be reported as unevaluable, never as a perfect score.

Reuse the verified full-domain score matrices from all 18 application workers.
These predictions depend on the frozen outer evidence, models and source IDs,
not on which held-out labels are used to assess them. Reuse therefore avoids
refitting or introducing a different prediction contract. Compute common-neighbor
scores directly from the same outer graph as an untimed structural quality
control, with an independent small-graph correctness check before label access.

Primary quality remains expected recall@16 per positive query under uniform
raw-score ties. Also retain recall@64, reciprocal average tie rank, support,
per-positive contributions, and each source's positive denominator. Separately
report rounded-score expected recall and the actual application's deterministic
string-ID top-16 recall. Do not replace the primary metric after seeing outcomes,
and do not claim deployed answer quality using only a favorable tie convention.
Independently rebuild each saved deterministic request output before evaluating
its held-out recall.

## Aggregation, uncertainty and interpretation

Report every worker's metrics and an arithmetic mean across its three process
repetitions for each application/thread condition. For comparisons, pair methods
on the same positive queries. Average per-positive contributions across process
repetitions before estimating label-sample uncertainty; do not count repetitions
as extra labeled observations. Report both equal-application and positive-count
weighted pooled differences across the three families, separately by thread count.

Use 100,000 paired bootstrap draws with seed 20260928, resampling the 64 source
IDs with replacement independently within each application. Retain zero-positive
sources. Recompute recall as total contribution divided by total positive count
in each draw; exclude and count any draw with a zero application denominator.
Use identical resampled sources for every method and repetition. Report 95%
percentile intervals and conservative Bonferroni simultaneous intervals over the
40 declared primary differences: four controls, two thread settings, and five
views (three applications plus both pooled views). Preserve bootstrap settings
and all exclusion counts in the result. This source-block analysis is conditional
on three fixed graphs and does not establish independence of connected nodes or
generalization to other graph populations.

Apply the original gate without redefining it: the selected method's primary
quality must be within one percentage point of the strongest observed declared
control on every application, with no statistically supported pooled quality
loss. Report each thread setting. Use the simultaneous intervals for any claim
of a supported loss or improvement. An interval crossing zero is inconclusive
about the sign; it does not prove equality. A stronger one-point noninferiority
claim additionally requires the relevant interval's lower bound to exceed -0.01.
Report that conclusion separately, even when the gate's point-estimate condition
passes. Keep all secondary and deterministic-output regressions visible.
Decision comparisons use absolute tolerance 1e-12 solely for floating-point
roundoff: the inclusive point-estimate boundary allows that tolerance, whereas
claims of a signed effect or strict noninferiority must clear their boundary by
more than it. Retain unrounded estimates and intervals.

Attach quality to the corresponding application campaign's separately reported
request, preparation, export and fitting costs. Those measurements concern fixed
source requests whose predictions are independent of held-out labels; they are
not new confirmation timing trials or evidence about unseen query shapes. Whole
worker RSS is not per-arm memory. The rest of gate B's useful cost-advantage
requirement and gates A, C and D still need their own evidence.
Carry observed application-protocol deviations forward with those costs. In
particular, the recorded overlap with unrelated host computation makes timing
descriptive; exact answer replay does not establish isolated performance.

Publish complete results, failures and replayable inputs. If confirmation fails
or is inconclusive, retain that outcome. Any subsequent model development needs
a new uncontaminated confirmation design; the opened labels cannot become a
repeated test to optimize until it passes. This protocol does not establish
Quail throughput parity or replace the pending GPU headroom investigation.
