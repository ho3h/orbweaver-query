"""Pinned public training data and deterministic evidence/fit/evaluation roles."""

from collections import defaultdict
import hashlib
import io
from pathlib import Path
import tarfile
import urllib.request

import numpy as np

from ._validation import positive_int


WN18RR_REVISION = "f3c0eb286025410fa5b4c04696c918264163d0ca"
WN18RR_URL = f"https://raw.githubusercontent.com/TimDettmers/ConvE/{WN18RR_REVISION}/WN18RR.tar.gz"
WN18RR_ARCHIVE_SHA256 = "1eb9152f804c140d163462c0d49f65e5a0b30ab5fbb375c5e3353c11a6249060"
WN18RR_TRAIN_SHA256 = "038612e783c215ee5f3ca9fbfca27b8d0739be1028fe4ee7c174aecf0b83d5df"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fetch_wn18rr_train(directory):
    """Checksum and extract only train.txt; never extract validation/test members."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "train.txt"
    if target.exists():
        if sha256(target) != WN18RR_TRAIN_SHA256:
            raise ValueError("Existing WN18RR training file checksum differs")
        return target
    with urllib.request.urlopen(WN18RR_URL, timeout=60) as response:
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != WN18RR_ARCHIVE_SHA256:
        raise ValueError("WN18RR download checksum mismatch")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as source:
        member = source.extractfile("train.txt")
        if member is None:
            raise ValueError("Pinned archive has no training file")
        content = member.read()
    if hashlib.sha256(content).hexdigest() != WN18RR_TRAIN_SHA256:
        raise ValueError("Extracted WN18RR training checksum mismatch")
    with target.open("xb") as stream:
        stream.write(content)
    return target


def load_triples(path, *, expected_sha256=None):
    """Load a TSV/whitespace triple file; caller supplies its data identity."""
    path = Path(path)
    if expected_sha256 is not None and sha256(path) != expected_sha256:
        raise ValueError("Training data checksum mismatch")
    rows = [line.split() for line in path.read_text().splitlines()]
    if not rows or any(len(row) != 3 for row in rows):
        raise ValueError("Expected nonempty head/relation/target rows")
    if len(set(map(tuple, rows))) != len(rows):
        raise ValueError("Duplicate training triples")
    nodes = sorted({node for h, _, t in rows for node in (h, t)})
    relations = sorted({r for _, r, _ in rows})
    node_index, relation_index = ({v: i for i, v in enumerate(values)}
                                  for values in (nodes, relations))
    triples = np.array([(node_index[h], relation_index[r], node_index[t])
                        for h, r, t in rows], dtype=np.int64)
    return triples, nodes, relations


def split_pairs(triples, seed):
    """80/10/10 evidence/fit/development roles, grouped by unordered endpoint pair.

    All directions and relation types of a pair share one role. Self links are
    excluded explicitly. These are transductive splits of one training graph,
    not independent entity, schema or dataset holdouts.
    """
    positive_int(seed, "seed", minimum=0)
    triples = np.asarray(triples)
    if triples.ndim != 2 or triples.shape[1] != 3 or not np.issubdtype(triples.dtype, np.integer):
        raise ValueError("Expected integer triples[edges,3]")
    if np.any(triples < 0):
        raise ValueError("Triple indices must be nonnegative")
    pairs = sorted({(min(h, t), max(h, t)) for h, _, t in triples})
    roles = dict(zip(pairs, np.searchsorted([.8, .9], np.random.default_rng(seed).random(len(pairs)))))
    split = np.array([roles[min(h, t), max(h, t)] if h != t else -1 for h, _, t in triples])
    return tuple(triples[split == role] for role in range(3))


def positives_by_query(triples):
    known = defaultdict(set)
    for head, relation, target in triples:
        known[int(head), int(relation)].add(int(target))
    return known
