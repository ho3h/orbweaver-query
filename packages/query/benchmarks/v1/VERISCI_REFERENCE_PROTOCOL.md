# Published VeriSci comparator on the complete SciFact cited domain

Compare the previously selected authors' models with the frozen Qwen development
reference. Use all 339 distinct supplied claim/document pairs, including NEI;
never use oracle retrieval or gold rationale sentences. This is a development
quality comparison, not a reproduction of published oracle-retrieval metrics,
a latest-state-of-the-art claim, or an inference-performance comparison.

The choice of models and threshold was recorded before inspecting Qwen outputs
in `scifact-reference-development-v2/baseline-source.json`. Download those exact
S3 object versions, verify their recorded byte lengths and response version IDs,
and record archive and extracted-file SHA-256 values. Preserve the published
weights and tokenizer files. Freeze source, input/truth files, prior predictions,
model checksums, protocol, and authors' inference scripts before inference.

Run `rationale_roberta_large_scifact` on each abstract sentence paired with the
claim, in that order. As in the authors' script, batch the sentences of one
abstract together, pad to the longest pair, and select every sentence with class-1
softmax probability >= 0.5. Do not truncate rationale inputs; fail explicitly if
a pair exceeds the model's 512-token context. Retain every sentence probability,
input token sequence and selected index. Titles are not input to this model;
Qwen's previously frozen prompt includes the title and complete abstract.

Run `label_roberta_large_fever_scifact` on the selected sentences joined by one
space, paired with the claim. With no selected sentences, return NEI as the
authors do, without a model call. Otherwise preserve their label order:
CONTRADICT, NOT_ENOUGH_INFO, SUPPORT. When a pair exceeds 512 tokens, truncate only
the evidence sequence to 512 total tokens. Retain token IDs, truncation status,
unrounded probabilities and the decision. Do not tune either model or threshold.

Use local CPU execution with four Torch threads, one interop thread, float32
weights and eager attention, eval mode and inference mode. Use installed Torch
2.11.0 and Transformers 5.5.4. Adapt `pad_to_max_length=True` to explicit longest
padding, and `truncation_strategy='only_first'` to `truncation='only_first'` on
overlength label inputs. `.logits` replaces tuple element 0. Check loading reports
and reject missing, mismatched or unexplained unexpected weights. Old serialized
position-ID buffers may be ignored when the installed implementation generates
identical positions. The original Transformers 2.7.0 classifier creates a pooler
but passes sequence output directly to its classification head, never using the
pooler result. Permit its two unused `roberta.pooler.dense` weights as unexpected
keys; retain the original implementation as evidence. No quantization, fine-tuning
or remote model-code execution.

The runner hashes frozen truth for integrity but parses only model inputs during
inference. Evaluate after all 339 outputs are present. Failed attempts and partial
outputs remain retained and cannot be reported as a complete denominator. Do not
run other model jobs or tests while this model pass is active. Record environment,
load reports and diagnostic elapsed time; different backend/hardware utilization,
precision and batching prohibit a speed comparison with the earlier Qwen pass.

Reuse the frozen edge and graph-set evaluation from the Qwen reference. Report
macro F1, each class's precision/recall/F1 and all three graph-query metrics. Add
a descriptive paired bootstrap for the Qwen-minus-VeriSci macro-F1 difference:
2,000 resamples of the 300 claim groups with replacement, seed 0, retaining all
edges per sampled claim. This conditional development interval is not independent
confirmation and does not close a 1.0 gate. Do not tune on the comparison result.

The next decision depends on both quality and application structure. A strong
specialized model may be a better backend for this domain. Neither model result
creates high-fanout graph work absent from the data. Preserve this low-fanout case
and require application-derived residual headroom before optimizer development.
