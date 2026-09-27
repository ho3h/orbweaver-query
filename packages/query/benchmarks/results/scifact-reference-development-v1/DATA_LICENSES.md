# SciFact evidence attribution

This research artifact contains a subset and transformation of the official
[SciFact dataset](https://github.com/allenai/scifact), introduced in:

David Wadden, Shanchuan Lin, Kyle Lo, Lucy Lu Wang, Madeleine van Zuylen,
Arman Cohan, and Hannaneh Hajishirzi. 2020. *Fact or Fiction: Verifying Scientific
Claims*. EMNLP. [Paper](https://aclanthology.org/2020.emnlp-main.609/).

The [source license](https://github.com/allenai/scifact/blob/68b98a56d93e0f9da0d2aab4e6c3294699a0f72e/LICENSE.md)
states:

- Claims and evidence annotations: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Abstract corpus from Semantic Scholar's [S2ORC](https://github.com/allenai/s2orc):
  [ODC-By 1.0](https://opendatacommons.org/licenses/by/1-0/).
- Source code: Apache 2.0.

This artifact uses development claims and their cited abstracts, separates gold
labels from model inputs, normalizes one duplicated citation while retaining its
occurrence count, and adds token IDs, predictions and graph-query evaluations.
It does not reproduce the full corpus or imply endorsement by the dataset authors.

The MultiCite selection audit stores only counts, checksums and provenance;
its paper texts and annotations are not included. Its source is
[MultiCite](https://github.com/allenai/multicite/tree/120671924b5ab968b98c7f696c4b67b4f8118948).
