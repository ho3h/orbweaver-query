# WN18RR explicit-path example

This small, conventional linear model demonstrates query-aware structured graph
inference. It ranks candidate missing links for the ordered WN18RR relation
schema. It is not a general model for arbitrary databases, factual confidence,
entity merging, or autonomous graph editing. The initial release model was
preselected as split seed 71 before comparing results.

## Data and evidence

Training source is `train.txt` from the [ConvE WN18RR distribution](https://github.com/TimDettmers/ConvE/tree/f3c0eb286025410fa5b4c04696c918264163d0ca),
revision `f3c0eb286025410fa5b4c04696c918264163d0ca`, SHA-256
`038612e783c215ee5f3ca9fbfca27b8d0739be1028fe4ee7c174aecf0b83d5df`.
It contains 86,835 directed triples, 40,559 entity IDs and 11 relation names.
See [third-party notices](src/orbweaver_query/assets/THIRD_PARTY_NOTICES.md).
The download archive also contains official validation/test files; the provided
loader extracts and reads only the training member.

All directions and relations of each unordered endpoint pair share one role:
80% evidence, 10% fitting, 10% development, with seeds 71, 83 and 97. Seven self
links are excluded. Nodes are shared across roles: this is a transductive
experiment, not a new-node, new-domain, or new-schema test. The same development
splits were used in earlier research, so these results are reproduction evidence.

The bundled model uses seed-71 evidence: 69,420 triples. It fits 3,079 reached
positive queries and their sampled unobserved contrasts (50,646 rows), from
8,686 fitting triples. Only evidence/fitting positives exclude sampled contrasts;
development targets never enter sampling or the evidence graph.

## Model and output

Uniform walks choose a neighboring endpoint, then a type on that endpoint pair.
Each directed relation has an inverse traversal symbol. Two- and three-step
walks contribute with weights 2/3 and 1/3. Complete path-type features are
normalized per candidate; four base features describe constant, log walk mass,
log(1 + target degree) and the two-step fraction. Relation-specific logistic
weights use C=10, no extra intercept and group-balanced sample weights.

The model only scores nodes reached within two or three steps, excluding the
source and every already adjacent node. Thus it cannot predict an additional
relation between an already connected pair. Null inputs and unsupported targets
are represented separately by the binding API. A missing score is not a negative
prediction. Ranking logits are not calibrated probabilities, including after
applying a sigmoid. Relation `_similar_to` has no usable fitting positives in
any of these splits; its zero coefficients provide no learned discrimination.

Ordered relation names and graph input features must match. The example loader
also checks the exact evidence snapshot. A schema match alone does not establish
useful behavior on a different graph. The model contains no natural-language
encoder and cannot infer semantic equivalence between new relation names.

## Evaluation and limitations

The [frozen reproduction](benchmarks/results/model-reproduction-v1/FINDINGS.md)
fits all four controls before any development scoring and replays all results.
Mean recall@16 is 28.55%, versus 24.87% for base descriptors, 26.78% for positional
marginals, 24.27% for shuffled paths and 20.72% for uniform walks. Full patterns
beat each control at recall@16 and recall@64 on every split. These controls test
the value of ordered paths; they do not establish superiority over other graph
learning architectures.

Average candidate coverage is only 35.30%; roughly 65% of held-out targets are
unreachable by this model. All targets remain in reported recall denominators.
Recall uses expected uniform tie-breaking; the API returns deterministic ID ties.
Filtering known positives is used only for the separately reported filtered MRR.
These metrics are specific to this pair-holdout task and cannot be compared
directly with standard WN18RR leaderboards.

The model has 122,496 float64 coefficients (979,968 bytes), compressed to 38,610
bytes in a nonexecutable numeric artifact. Its content ID is
`64d5c3f7652b84f3d24f22beeaf7f7cd49d5a2218af91b4ee89942584674506a`.
Its training dependencies are optional; inference needs NumPy only. CPU/native
library versions can affect newly fitted coefficients and exact ties. The bundled
artifact has fixed coefficients. Hash validation detects inconsistent content;
it does not authenticate an arbitrary external artifact's publisher.

## Rebuild

From this repository, install `./packages/query[train]`, then run:

```sh
python -m orbweaver_query.reproduce freeze model-run
python -m orbweaver_query.reproduce execute model-run
python -m orbweaver_query.reproduce verify model-run
```

The first command downloads the checksum-pinned public archive unless `--train`
points to an existing verified training file. Keep the same installed source
through all three commands. Run directories are exclusive: failures and prior
measurements are never silently overwritten. The protocol is included in the
wheel as `orbweaver_query/MODEL_REPRODUCTION_PROTOCOL.md`.
