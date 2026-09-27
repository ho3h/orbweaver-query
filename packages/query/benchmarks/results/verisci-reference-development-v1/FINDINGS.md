# Published VeriSci comparison on the complete cited domain

The fixed Qwen reference has a higher development point estimate than the
published VeriSci pipeline on the same **339 distinct claim/document pairs**:
macro F1 **0.77846 versus 0.72981**, a difference of **0.04865**. A paired bootstrap
over 300 claim groups gives a conditional 95% interval of **[-0.01745, 0.11576]**
for Qwen minus VeriSci. This interval includes zero and does not establish
superiority or noninferiority within one percentage point. No 1.0 gate closes.

This is a comparison with the authors' recommended 2020 pipeline, not a claim
against the latest scientific verification systems. It supports continuing with
the fixed Qwen model as an application reference. It does not justify tuning the
prompt on these outcomes or treating the low-fanout graph as a performance win.

## Matched candidate domain and published model behavior

Both arms classify every supplied cited-document pair in the original frozen
SciFact development reference, including 130 NOT_ENOUGH_INFO edges. The one
duplicated source citation is normalized once with its multiplicity retained.
No oracle retrieval or gold rationale is used. This differs from published
oracle-retrieval experiments, so their headline scores are not comparable here.

The comparator uses the model choices and threshold recorded before inspecting
the Qwen results:

- `rationale_roberta_large_scifact`: classify each abstract sentence paired with
  the claim, selecting class-1 probability >= 0.5.
- `label_roberta_large_fever_scifact`: join selected sentences in document order,
  pair with the claim, and predict CONTRADICT, NOT_ENOUGH_INFO or SUPPORT in the
  authors' label order. An empty rationale yields NEI without a classifier call.

There are 3,106 sentence/claim inputs, with maximum length 299 tokens; none is
truncated. Of 339 pairs, 134 have no selected rationale and 205 reach the label
model. No selected-evidence input exceeds 512 tokens, so the authors' truncation
rule is not exercised on this development data. VeriSci does not use document
titles; Qwen uses the title and full abstract as specified in its frozen prompt.

Every sentence probability, selected index, padded input token sequence, label
probability and classification is retained. Inference parses only model inputs;
frozen truth is read as bytes for integrity checks, then parsed during evaluation.

## Quality

| Label | VeriSci precision | VeriSci recall | VeriSci F1 | Qwen F1 |
|---|---:|---:|---:|---:|
| SUPPORT | 0.8475 | 0.7246 | 0.7813 | 0.8065 |
| CONTRADICT | 0.7755 | 0.5352 | 0.6333 | 0.7460 |
| NOT_ENOUGH_INFO | 0.6802 | 0.9000 | 0.7748 | 0.7829 |

VeriSci's confusion matrix, with both axes in SUPPORT, CONTRADICT, NEI order:

```text
100   8   30
  8  38   25
 10   3  117
```

| Query set | Gold rows | VeriSci rows | VeriSci correct | VeriSci F1 | Qwen F1 |
|---|---:|---:|---:|---:|---:|
| Claims with supporting evidence | 124 | 107 | 90 | 0.7792 | 0.8018 |
| Supported claims without contradicting evidence | 124 | 106 | 89 | 0.7739 | 0.8018 |
| Shared abstract supporting one claim and contradicting another | 23 | 13 | 10 | 0.5556 | 0.6842 |

Unlike the previous gold/Qwen outputs, VeriSci has one claim whose predicted
support is vetoed by predicted contradiction. Model uncertainty compounds in the
shared-document query: neither model finds every gold witness. These are exact
sets under the fixed classifications, not claims that the classifications are
correct. The bootstrap is paired by claim, with 2,000 resamples and seed 0; it
does not model all cross-claim document dependence or establish external validity.

Native Neo4j 5.26 matches all 12 query conditions for gold, VeriSci, the training
majority control and all-NEI. This includes the actual contradiction veto in the
VeriSci output. The disposable database contains only this benchmark's graph.
Scikit-learn 1.8.0 independently reproduces both arms' confusion matrices,
per-class precision/recall/F1 and macro F1 within 1e-12.

## Compatibility, provenance and rejected attempts

Model archives are pinned to S3 object versions and verified by response version,
byte length and SHA-256. Weights and tokenizers are unchanged:

| Model archive | SHA-256 |
|---|---|
| Rationale | `f103cf8d63c8724915f410606e5d85f25fedf49ce1a1651a1ec502b17a715178` |
| Label | `1196f65610195977ff6b3abd058c5871200a3509ed15381b1e6cd6ce897da325` |

The authors used Transformers 2.7.0 and Torch 1.5.0. This run uses Transformers
5.5.4 and Torch 2.11.0, eager attention, float32 and four CPU threads. The adapter
preserves sentence/claim order, threshold, evidence joining and label mapping;
it updates padding/truncation arguments and accesses `.logits`. Tokenization uses
the current fast implementation with the original vocabulary and merges. This is
not a bitwise reproduction of the original library stack.

Both loading reports have zero missing or mismatched weights. The only unused
weights are the two `roberta.pooler.dense` tensors. Inspection of the retained
Transformers 2.7.0 source confirms its classifier consumes sequence output and
never the pooler result. Allowing those unused tensors does not remove a component
of the classification calculation.

The archive retains two pre-prediction failures. V1 could not serialize a set in
the loading report. V2 rejected the unexpected pooler tensors before the original
implementation was inspected. V3 includes the documented compatibility fix and
completes every pair. Neither rejected attempt produced model predictions. No
frozen source, raw output or failure was overwritten.

The completed manifest is
`bd5afd54c99638dbf2724e4d6443230c50e224f9c73e0fd93e1dc586dd21e1ca`.
All attempts, source, weights' checksums, inputs, outputs and evaluation are in
the 744-file evidence bundle. Model weights themselves are not redistributed. Attribution
and code licensing are in [DATA_LICENSES.md](DATA_LICENSES.md).

```sh
python packages/query/benchmarks/results/verisci-reference-development-v1/verify.py
```

Replay checks every archived file and regenerates the completed result byte for
byte with frozen source. It needs only the Python standard library, not Torch or
model weights. To repeat inference, copy only `manifest.json` and the files in its
`files` mapping into a fresh run directory, then invoke its frozen
`verisci_reference.py infer <fresh-run> --models <verified-model-cache>`.
Existing prediction directories are deliberately immutable. For native replay,
use the repository's `benchmarks/v1/verify_scifact_graph.py` with a fresh run copy,
`--prediction-folder label --prediction-name verisci`, and the local Neo4j home
and Java arguments used by the SciFact reference. The archived verifier records
the source used for the original check; the live helper also supports shallow
standalone directories without assuming a repository parent layout.

Diagnostic time is 516.66 seconds for rationale selection, 43.04 seconds for label
classification, and 563.89 seconds including model loading and intervening work.
Do not divide this by the earlier Qwen time: that pass uses different precision,
batching and the Apple GPU through MLX. This run is not a matched performance test.

Source validation: 183 tests pass with four optional skips. The production runtime
is unchanged. The next execution experiment must use the same semantic contract
across arms, combine strong inference optimizations, and establish remaining
graph-specific headroom before another optimizer campaign.
