# Data and tokenizer provenance

The archive contains the same SciFact development claim/cited-abstract domain as
the earlier application reference, with source multiplicity preserved. Claims
and annotations are CC BY 4.0; abstracts originate from S2ORC under ODC-By 1.0.
See [SciFact](https://github.com/allenai/scifact/tree/68b98a56d93e0f9da0d2aab4e6c3294699a0f72e)
and [S2ORC](https://github.com/allenai/s2orc). Cite Wadden et al.,
“Fact or Fiction: Verifying Scientific Claims,” EMNLP 2020. No test claims were
read. The original source input and truth identities are in the frozen manifest.

Tokenizer/configuration files are from
[Qwen/Qwen3-4B-FP8](https://huggingface.co/Qwen/Qwen3-4B-FP8/tree/96b30dc13593a244a5e59e84687309f53c375cfa),
revision `96b30dc13593a244a5e59e84687309f53c375cfa`, licensed Apache 2.0.
The upstream model LICENSE is included as `QWEN_LICENSE.txt` in the archive.
Model weights are not included or downloaded by the local preparation; their
expected Hub LFS SHA-256 hashes are recorded for the future CUDA worker.

The external execution engine is Quail, MIT licensed, source revision
`41b883b838687cfbf018080f068f3e81bf2f8e64`. Its source is not vendored in this archive.
The included Orbweaver benchmark code is covered by the repository's Apache 2.0 license.
