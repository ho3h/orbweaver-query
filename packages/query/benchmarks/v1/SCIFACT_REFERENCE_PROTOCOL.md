# SciFact: labeled semantic graph application, development reference

This establishes application semantics and model quality before optimization.
It is not a performance campaign or a claim of graph-specific novelty.

Use the official SciFact archive, SHA-256
`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be`.
Read only corpus, training claims (majority baseline) and development claims.
Do not extract or inspect test claims or cross-validation files. Claims and
annotations are CC BY 4.0; abstracts are S2ORC material under ODC-By 1.0.
Source: https://github.com/allenai/scifact/tree/68b98a56d93e0f9da0d2aab4e6c3294699a0f72e

The development graph contains every development claim, its supplied CITES
edges, and the corresponding abstracts. This is an explicitly restricted
candidate domain: the supplied cited documents, not corpus retrieval. Missing
evidence on a supplied cited edge means NOT_ENOUGH_INFO according to the dataset
annotation. Do not label arbitrary unjudged claim/document combinations negative.
Preserve all 300 claims and 340 source citation occurrences. Claim 1245 repeats
document 7662395. Record that multiplicity and classify each of the 339 distinct
claim/document pairs once; report quality over those distinct pairs and graph
query sets. The initial duplicate-rejection audit is retained. There is no
selection on model outcomes.

Questions over this graph:

1. Supported claims: at least one cited abstract SUPPORTS the claim.
2. Uncontested supported claims: at least one SUPPORTS and none CONTRADICT.
3. Disagreement witnesses: two distinct claims cite the same abstract, which
   SUPPORTS the first and CONTRADICTS the second. Return ordered claim/document/
   other-claim triples. This uses declared graph incidence, not inferred global
   citation links or a claim that the two claims are logical negations.

Keep model inputs and gold labels in separate frozen files. The inference
command verifies all frozen files by hash, but parses only model inputs; gold
labels are never supplied to the model. Every prompt contains the complete title and
abstract, followed by the claim. It contains no gold rationale, annotation or
label. The system asks for A=SUPPORT, B=CONTRADICT, C=NOT_ENOUGH_INFO. Use the
existing pinned local Qwen3-4B Instruct 2507 4-bit model at revision
`50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b`, with its original vocabulary head and
MLX-LM's ordinary BatchGenerator. Mask output choices to the three single-token
letters; greedy generation returns exactly one token. Preserve the loaded model
precision, use prefill batch 4, completion batch 4, and prefill step 2048.
Reject rather than truncate any prompt longer than 8192 tokens.

One fixed zero-shot prompt is evaluated on the complete development graph.
Record conditional probabilities over A/B/C; these are not calibrated confidence
estimates. No prompt/model tuning on these outcomes in this run. This is a
quality qualification of a conventional backend, not the proposed strong final
execution control. Later performance comparisons must also enable joint prefix
caching/batching, restricted readout where appropriate, and early termination.

Record all predictions, failures, source/input/model/runtime checksums, elapsed
time and peak MLX allocation. Timing is diagnostic and excludes graph loading;
there are no repetitions or speedup claims. Failed model rows remain failures,
not missing denominator entries. Do not run other model jobs/tests during the
inference pass. Do not stage or apply graph repairs.

Evaluation reports the complete edge confusion matrix, per-class precision/
recall/F1, macro F1, and exact query-set precision/recall/F1 against gold. Include
the majority class determined from training cited edges and an all-NEI control.
These sanity controls do not establish parity with specialized SciFact systems.
Qualification for continuing with this model requires macro F1 at least 0.70 and
each class recall at least 0.50; even passing is not a release gate. Author-provided
rationale-selection/label-prediction models and independent confirmation remain
required for a competitive quality claim. The public test labels are not supplied
in this archive; future confirmation needs an explicit valid evaluation path.

The next specialized comparator is the authors' published VeriSci pipeline:
`rationale_roberta_large_scifact` with threshold 0.5, followed by
`label_roberta_large_fever_scifact`. Use the same supplied cited-document domain
and predicted rationales, never gold rationale spans. Preserve their documented
label order and 512-token, first-sequence truncation for the label model. Record
any compatibility adaptation needed by the installed Transformers version.
This comparator choice precedes inspection of the Qwen predictions. Author source:
https://github.com/allenai/scifact/blob/68b98a56d93e0f9da0d2aab4e6c3294699a0f72e/script/pipeline.sh
Their `abstract_retrieval/oracle.py` selects gold evidence document IDs. Do not
run that gold-dependent retrieval stage here: feed the same complete supplied
cited edges to both models, including NEI edges. Consequently this comparison
will not be a reproduction of their published oracle-retrieval numbers.

Verify all three graph query results against native Cypher in an owned disposable
Neo4j database, using identical edge classifications. This is independent graph
execution verification, not a second model-quality evaluation. Charge graph,
transfer, setup and update costs in any eventual end-to-end performance campaign.

The data audit already limits the performance hypothesis: 277/300 claims cite
one distinct abstract, so existence termination has little headroom. Use this as a real low-fanout case,
not a manufactured 2x performance demonstration. MultiCite's development QA data
was also inspected: 252 target contexts, but only three repeated source-paper
groups under exact markup-neutral text identity. It remains useful for text
operator coverage, not yet a richer graph-traversal benchmark.
