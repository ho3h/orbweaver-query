"""Portable explicit-path training; scientific dependencies are optional.

Supervision consists of observed missing pairs and sampled unobserved ranking
contrasts. Logistic outputs are ranking scores, not calibrated factual beliefs.
"""

import warnings
from collections import Counter

import numpy as np

from .model import ExplicitPathModel, Limits


def sparse_features(features, width):
    from scipy import sparse

    patterns = sparse.csr_matrix((features.proportions, (features.row, features.column)),
                                  shape=(len(features.candidates), width - 4))
    result = sparse.hstack((sparse.csr_matrix(features.base), patterns), format="csr")
    result.sort_indices()
    return result


def prepare_examples(graph, positives, known, *, seed, negatives=16, limits=None):
    """Sample contrasts without inspecting development targets or changing evidence."""
    from scipy import sparse

    from ._validation import positive_int

    positive_int(negatives, "negatives")
    limits = Limits() if limits is None else limits
    r = len(graph.relations)
    width = 4 + (2*r)**2 + (2*r)**3
    extractor = ExplicitPathModel(np.zeros((r, width)), relations=graph.relations)
    positives = np.asarray(positives)
    if (positives.ndim != 2 or positives.shape[1] != 3
            or not np.issubdtype(positives.dtype, np.integer)
            or np.any(positives < 0) or np.any(positives[:, (0, 2)] >= len(graph.node_ids))
            or np.any(positives[:, 1] >= r)):
        raise ValueError("Invalid fitting triples")
    positives = positives[np.lexsort((positives[:, 2], positives[:, 1], positives[:, 0]))]
    rng = np.random.default_rng(seed)
    queries, labels, groups, origins, parts = [], [], [], [], []
    total, covered, usable, sizes = Counter(), Counter(), Counter(), []
    row_offset, prior_head, features, local = 0, None, None, None
    for origin, (head, relation, target) in enumerate(positives):
        head, relation, target = int(head), int(relation), int(target)
        total[relation] += 1
        if head != prior_head:
            features = extractor.expand(graph, head, limits)
            local = sparse_features(features, width)
            pool = set(features.candidates.tolist())
            prior_head = head
        if target not in pool:
            continue
        covered[relation] += 1
        remaining = sorted(pool - known.get((head, relation), set()) - {target})
        if not remaining:
            continue
        usable[relation] += 1
        sampled = [target, *rng.choice(remaining, min(negatives, len(remaining)), replace=False)]
        selected = local[np.searchsorted(features.candidates, sampled)].tocoo()
        parts.append((selected.row + row_offset, selected.col + relation*width, selected.data))
        group = len(sizes)
        sizes.append(len(pool))
        for j, tail in enumerate(sampled):
            queries.append((head, relation, int(tail)))
            labels.append(int(j == 0))
            groups.append(group)
            origins.append(origin)
        row_offset += len(sampled)
    if not queries:
        raise ValueError("No reached fitting positives with available ranking contrasts")
    x = sparse.csr_matrix((np.concatenate([p[2] for p in parts]),
                           (np.concatenate([p[0] for p in parts]),
                            np.concatenate([p[1] for p in parts]))), shape=(len(queries), r*width))
    x.sort_indices()
    examples = {"queries": np.array(queries, np.int64), "labels": np.array(labels, np.int8),
                "groups": np.array(groups, np.int64), "origins": np.array(origins, np.int64)}
    audit = {"positive_queries": len(positives), "covered_queries": sum(covered.values()),
             "usable_queries": len(sizes), "sampled_rows": len(queries),
             "coverage": sum(covered.values()) / len(positives),
             "candidate_pool_sizes": {"min": min(sizes), "median": float(np.median(sizes)), "max": max(sizes)},
             "by_relation": {str(k): {"positive": total[k], "covered": covered[k], "usable": usable[k]}
                             for k in sorted(total)}}
    return examples, x, audit


def marginal_projection(symbols):
    from scipy import sparse

    rows, columns = [], []
    for length, offset, position_offset in ((2, 0, 0), (3, symbols**2, 2)):
        for code in range(symbols**length):
            for pos in range(length):
                symbol = code // symbols**(length - pos - 1) % symbols
                rows.append(offset + code)
                columns.append((position_offset + pos)*symbols + symbol)
    return sparse.csr_matrix((np.ones(len(rows)), (rows, columns)),
                              shape=(symbols**2 + symbols**3, 5*symbols))


def local_view(x, symbols, kind, *, permutation=None, projection=None):
    from scipy import sparse

    if kind == "base":
        return x[:, :4].tocsr()
    if kind == "pattern":
        return x.tocsr()
    if kind == "marginal":
        projection = marginal_projection(symbols) if projection is None else projection
        return sparse.hstack((x[:, :4], x[:, 4:] @ projection), format="csr")
    if kind == "permuted":
        if permutation is None or sorted(permutation.tolist()) != list(range(x.shape[0])):
            raise ValueError("A complete permutation is required for the shuffled control")
        return sparse.hstack((x[:, :4], x[permutation, 4:]), format="csr")
    raise ValueError("Unknown feature kind")


def fit_controls(x, examples, relations, *, seed):
    from scipy import sparse
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.linear_model import LogisticRegression
    from threadpoolctl import threadpool_limits

    r, s = len(relations), 2*len(relations)
    width = 4 + s*s + s**3
    if x.shape != (len(examples["labels"]), r*width):
        raise ValueError("Training feature shape differs from model schema")
    rng = np.random.default_rng(seed)
    groups = examples["groups"]
    permutation = np.arange(len(groups))
    for group in np.unique(groups):
        indices = np.flatnonzero(groups == group)
        permutation[indices] = rng.permutation(indices)
    if not np.array_equal(examples["queries"][:, 1], examples["queries"][permutation, 1]):
        raise ValueError("Candidate groups must preserve query relation")
    projection = marginal_projection(s)
    coefficients, audit = {}, {}
    with threadpool_limits(limits=1):
        for kind in ("base", "marginal", "pattern", "permuted"):
            view = sparse.hstack([local_view(x[:, i*width:(i+1)*width], s, kind,
                                             permutation=permutation, projection=projection)
                                  for i in range(r)], format="csr")
            estimator = LogisticRegression(C=10, solver="liblinear", max_iter=2000,
                                           tol=1e-6, random_state=0, fit_intercept=False)
            with warnings.catch_warnings():
                warnings.simplefilter("error", ConvergenceWarning)
                estimator.fit(view, examples["labels"],
                              sample_weight=1 / np.bincount(groups)[groups])
            coefficients[kind] = estimator.coef_[0].reshape(r, -1)
            audit[kind] = {"iterations": int(estimator.n_iter_[0]),
                           "parameters": int(estimator.coef_.size),
                           "coefficient_bytes": int(estimator.coef_.nbytes)}
    model = ExplicitPathModel(coefficients["pattern"], relations=relations)
    return model, coefficients, audit


def rank_target(candidates, scores, target, known, budgets=(16, 64, 256)):
    """Full-denominator average ranks and expected recall under uniform ties."""
    from ._validation import positive_int

    budgets = tuple(budgets)
    for budget in budgets:
        positive_int(budget, "recall budget")
    candidates, scores = np.asarray(candidates), np.asarray(scores)
    if (candidates.ndim != 1 or scores.shape != candidates.shape
            or len(set(candidates.tolist())) != len(candidates) or not np.isfinite(scores).all()):
        raise ValueError("Expected distinct candidates and aligned finite scores")
    position = np.flatnonzero(candidates == target)
    if not len(position):
        return np.inf, np.inf, np.zeros(len(budgets))
    score = scores[position[0]]
    greater, tied = scores > score, scores == score
    raw = 1 + greater.sum() + .5*(tied.sum() - 1)
    keep = np.array([int(c) not in known or c == target for c in candidates], dtype=bool)
    filtered = 1 + (greater & keep).sum() + .5*((tied & keep).sum() - 1)
    recall = np.clip((np.array(budgets) - greater.sum()) / tied.sum(), 0, 1)
    return float(raw), float(filtered), recall
