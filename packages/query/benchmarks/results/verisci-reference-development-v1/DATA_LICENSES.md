# VeriSci comparator attribution

The evidence includes the SciFact development input subset and labels already
attributed in the [SciFact reference](../scifact-reference-development-v1/DATA_LICENSES.md).
Claims and annotations are CC BY 4.0; abstracts derived from S2ORC are ODC-By 1.0.
Transformations add token IDs, sentence selections, model decisions and evaluation
results. This artifact does not imply endorsement by the original authors.

The published models and inference scripts are from David Wadden and colleagues,
*Fact or Fiction: Verifying Scientific Claims*, EMNLP 2020.
[Paper](https://aclanthology.org/2020.emnlp-main.609/),
[pinned source](https://github.com/allenai/scifact/tree/68b98a56d93e0f9da0d2aab4e6c3294699a0f72e).
Their code is Apache 2.0. Model weights are represented by URLs, object versions
and checksums; the weights are not redistributed.

The retained Transformers 2.7.0 `modeling_roberta.py` is from
[Hugging Face Transformers](https://github.com/huggingface/transformers/blob/v2.7.0/src/transformers/modeling_roberta.py),
with its original copyright notices. It is included for compatibility inspection,
not executed by the comparator. Its license is Apache 2.0; a copy is included as
[APACHE-2.0.txt](APACHE-2.0.txt). Upstream scripts in the evidence are unmodified;
the new runner documents the compatibility adaptations it implements separately.
