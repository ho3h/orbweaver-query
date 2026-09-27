# SciFact semantic graph reference

The complete development reference classifies **339 distinct claim/document
pairs** with a fixed zero-shot Qwen3-4B prompt, then evaluates three graph query
sets. Macro F1 is **0.77846**; every class recall exceeds the predeclared 0.50
qualification threshold. All **12 native Cypher checks match** the independent
set-based graph reference. This qualifies the model for continued application
work, not competitive parity, a release gate, or a speedup claim.

## Application and independent labels

The official SciFact development data supplies 300 claims, 283 cited abstracts,
and 340 citation occurrences. Claim 1245 lists document 7662395 twice. The audit
records that source multiplicity and classifies each distinct pair once. Labels
are SUPPORT (138 pairs), CONTRADICT (71), and NOT_ENOUGH_INFO (130).

The candidate domain is the supplied cited documents. Gold rationale spans and
edge labels never enter model prompts. Input and truth files are separate; the
inference command verifies both by hash but only parses inputs. The frozen
source's comment saying it never opens the truth file is imprecise: verification
reads its bytes for hashing. The current source/protocol clarify that distinction.
No test claims or cross-validation contents were read. This is development data;
no independent confirmation or open-corpus retrieval result is claimed.

Each prompt contains the complete abstract and title followed by the claim.
There are 157,177 input tokens; prompt lengths range from 176 to 1,553, with
median 391. No prompt was truncated. The ordinary MLX-LM BatchGenerator uses
batches of four and greedy choice among A/B/C through the original vocabulary
head. All conditional class probabilities and decisions are retained.

## Quality

| Edge label | Precision | Recall | F1 |
|---|---:|---:|---:|
| SUPPORT | 0.9091 | 0.7246 | 0.8065 |
| CONTRADICT | 0.8545 | 0.6620 | 0.7460 |
| NOT_ENOUGH_INFO | 0.6839 | 0.9154 | 0.7829 |

The training-majority SUPPORT control has macro F1 0.19287; all-NEI has 0.18479.
These are denominator and class-imbalance sanity checks, not strong competitors.

| Query set | Gold rows | Predicted rows | Correct rows | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Claims supported by at least one cited abstract | 124 | 98 | 89 | 0.9082 | 0.7177 | 0.8018 |
| Supported claims with no contradicting cited abstract | 124 | 98 | 89 | 0.9082 | 0.7177 | 0.8018 |
| Shared abstract supporting one claim and contradicting another | 23 | 15 | 13 | 0.8667 | 0.5652 | 0.6842 |

The first two queries coincide on these gold and model outputs; they are not two
independent quality wins. A separate synthetic unit fixture exercises an actual
contradiction veto and an isolated claim. The third query exposes compounded
model errors: only 13 of 23 gold witnesses are returned. Different support labels
on two claims do not establish that those claims are logical negations.

Native Neo4j 5.26 independently executes EXISTS, EXISTS/NOT EXISTS, and a two-edge
shared-document match for gold, Qwen, training-majority and all-NEI labels. All
ordered result sets agree. The database is disposable and contains no user data.
This verifies graph execution for fixed classifications, not model accuracy.

## Architectural decision and next comparator

Use this application as a labeled, low-fanout reference. It does not supply a
large early-termination opportunity: 277/300 claims have one distinct cited
abstract, and only 45 abstracts have more than one incoming development claim.
The earlier raw-occurrence audit counted 276 and 46 respectively; the retained
`application-selection.json` corrects those figures after duplicate normalization.

The MultiCite development audit found 252 target contexts and 1,764 questions,
but only three groups containing repeated source-paper text after removing target
markup. It remains a possible text-operator fixture, not evidence of a broad
citation network. The audit also identified gold-dependent marker selection in
its question-generation code, which needs care in a label-independent prompt.

The next quality comparator is the authors' VeriSci rationale model
`rationale_roberta_large_scifact` (threshold 0.5), followed by
`label_roberta_large_fever_scifact`. This choice was recorded before inspecting
Qwen predictions. Model URLs are pinned to S3 object versions in
`baseline-source.json`; those weights have not yet been downloaded or evaluated.
Their original oracle retrieval stage reads gold evidence IDs, so it must be
replaced with our same complete cited domain, including NEI edges. Do not compare
our numbers directly with published oracle-retrieval scores.

Only after that comparison should the application motivate a production semantic
model boundary and a performance reference combining batching, prefix reuse,
restricted readout and early termination. None of those optimizations is new
merely because the candidates come from a graph. This reference is outside the
production runtime; no AI-Cypher syntax or new core backend is implemented here.

## Reproduction and limits

`evidence.tar.gz` contains 357 checksummed files: the completed run, raw outputs,
source, input/model manifests, native verification, selection audit, and the
initial freeze rejection of the duplicated source citation. Base weights are
represented by checksums and revision, not redistributed. The completed manifest
is `545ec1d7e96da95d914b99693d174ff61e7a093dde85d9184580f220d1b9018a`.

```sh
python packages/query/benchmarks/results/scifact-reference-development-v1/verify.py
```

Verification checks every artifact and regenerates results byte for byte using
frozen source. NumPy, MLX and model weights are unnecessary for this evaluation
replay. To repeat inference, extract the evidence and use the frozen script's
`infer` command with the pinned local model; use a fresh output directory. Native
graph verification requires the retained helper plus local Neo4j and Java.

The model pass took 323.85 seconds and peaked at 5.13 GB of MLX allocation on the
local Apple M5 Max. This single pass includes ordinary backend/output overhead,
excludes database loading, has no performance repetitions, and is not a matched
comparison with Quail/vLLM or any specialized model. Quality scores are also
development-only and do not establish real-world factual reliability.

Source validation: **180 tests pass, four optional skips**. Pinned Ruff and
whitespace checks pass. Data attribution and licenses are in
[DATA_LICENSES.md](DATA_LICENSES.md). All original 1.0 gates remain open.
