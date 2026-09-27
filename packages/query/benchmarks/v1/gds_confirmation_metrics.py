"""Independent ranking and paired source-block analysis; no file or label access.

These numerical primitives implement GDS_CONFIRMATION_PROTOCOL.md. They do not
fit a model, import the application's ranking code, or decide release readiness.
"""

import numpy as np

DATASETS = ('collaboration', 'friendship', 'communication')
THREADS = (1, 4)
METHODS = ('local', 'gds', 'common_neighbors', 'resource_allocation', 'adamic_adar')
VIEWS = (*DATASETS, 'equal_application', 'positive_weighted')
METRICS = ('recall16', 'recall64', 'reciprocal_rank', 'supported')
COMPARISONS = len(VIEWS)*len(THREADS)*(len(METHODS)-1)
METRIC_EPSILON = 1e-12


def integer_array(value, *, columns=None):
    result = np.asarray(value)
    if (result.dtype.kind not in 'iu' or result.ndim != (1 if columns is None else 2)
            or (columns is not None and result.shape[1] != columns)):
        raise ValueError('Expected an integer vector or pair/triple matrix')
    return result


def graph_domain(node_ids, triples, sources):
    """Recover the simple undirected domain from raw saved triples."""
    node_ids = list(node_ids)
    if (not node_ids or any(not isinstance(v, str) for v in node_ids)
            or len(set(node_ids)) != len(node_ids)):
        raise ValueError('Node IDs must be distinct strings')
    sources = integer_array(sources)
    triples = integer_array(triples, columns=3)
    if (not len(sources) or len(set(sources)) != len(sources)
            or np.any(sources >= len(node_ids)) or np.any(sources < 0)):
        raise ValueError('Invalid or duplicate source indices')
    if (np.any(triples[:, 1] != 0) or np.any(triples[:, (0, 2)] < 0)
            or np.any(triples[:, (0, 2)] >= len(node_ids))
            or np.any(triples[:, 0] == triples[:, 2])):
        raise ValueError('Invalid simple graph edge')
    edges = {(int(h), int(t)) for h, _, t in triples}
    if len(edges) != len(triples) or any((t, h) not in edges for h, t in edges):
        raise ValueError('Graph must have distinct edges in both directions')
    adjacency = [set() for _ in node_ids]
    for h, t in edges:
        adjacency[h].add(t)
    mask = np.ones((len(sources), len(node_ids)), dtype=bool)
    for row, h in enumerate(sources):
        mask[row, [int(h), *adjacency[h]]] = False
    return adjacency, mask


def common_neighbors(adjacency, sources, mask):
    """Count two-hop walks directly, independently of the sparse algebra oracle."""
    scores = np.zeros(mask.shape, dtype=np.float64)
    for row, h in enumerate(sources):
        for middle in adjacency[h]:
            for target in adjacency[middle]:
                scores[row, target] += 1
    scores[~mask] = np.nan
    return scores


def validate_scores(scores, mask, *, complete=False, probability=False):
    if (mask.ndim != 2 or scores.shape != mask.shape or mask.dtype != np.dtype(bool)
            or scores.dtype.kind != 'f' or np.isinf(scores).any()
            or np.any(np.isfinite(scores) & ~mask)):
        raise ValueError('Invalid score matrix or excluded-pair prediction')
    if complete and not np.array_equal(np.isfinite(scores), mask):
        raise ValueError('Incomplete candidate coverage')
    if probability and np.any((scores[mask] < 0) | (scores[mask] > 1)):
        raise ValueError('Native probabilities outside [0, 1]')


def validate_positives(positives, sources, mask):
    positives = integer_array(positives, columns=2)
    sources = integer_array(sources)
    if (len(sources) != mask.shape[0] or len(set(sources)) != len(sources)
            or np.any(sources < 0) or np.any(sources >= mask.shape[1])):
        raise ValueError('Source indices differ from score rows')
    lookup = {int(h): row for row, h in enumerate(sources)}
    pairs = [(int(h), int(t)) for h, t in positives]
    if len(set(pairs)) != len(pairs):
        raise ValueError('Duplicate positive queries')
    if any(h not in lookup or not 0 <= t < mask.shape[1] or not mask[lookup[h], t]
           for h, t in pairs):
        raise ValueError('Positive query outside the common candidate domain')
    return pairs, lookup


def quality(scores, mask, sources, positives):
    """Uniform-tie recall and reciprocal average tie rank, including misses."""
    validate_scores(scores, mask)
    pairs, lookup = validate_positives(positives, sources, mask)
    ordered = [np.sort(row[np.isfinite(row)]) for row in scores]
    outcomes = []
    for head, target in pairs:
        row = lookup[head]
        score = float(scores[row, target])
        supported = bool(np.isfinite(score))
        if supported:
            values = ordered[row]
            left, right = np.searchsorted(values, score, side='left'), np.searchsorted(
                values, score, side='right')
            tied, greater = int(right-left), len(values)-int(right)
            rank = 1+greater+(tied-1)/2
            r16 = min(1., max(0., (16-greater)/tied))
            r64 = min(1., max(0., (64-greater)/tied))
        else:
            rank, r16, r64 = None, 0., 0.
        outcomes.append({'head': head, 'target': target, 'supported': supported,
                         'rank': rank, 'recall16': r16, 'recall64': r64,
                         'reciprocal_rank': 0. if rank is None else 1/rank})
    return {'positive_queries': len(pairs), 'outcomes': outcomes,
            'metrics': {key: float(np.mean([r[key] for r in outcomes])) if outcomes else None
                        for key in METRICS}, 'evaluable': bool(pairs)}


def assess(scores, mask, sources, positives, node_ids):
    """Keep raw, rounded and actual returned-answer quality distinct."""
    validate_scores(scores, mask)
    pairs, lookup = validate_positives(positives, sources, mask)
    rounded = np.full(scores.shape, np.nan)
    finite = np.isfinite(scores)
    # Python round matches the declared HALF_EVEN application rule, not np.round.
    rounded[finite] = [round(float(v), 12) for v in scores[finite]]
    output = []
    selected = set()
    for row, head in enumerate(sources):
        targets = sorted(np.flatnonzero(np.isfinite(rounded[row])),
                         key=lambda t: (-rounded[row, t], node_ids[t]))[:16]
        selected.update((int(head), int(t)) for t in targets)
        output.append({'head': str(node_ids[head]), 'recommendations': [
            {'target': str(node_ids[t]), 'score': float(rounded[row, t])} for t in targets]})
    hits = [{'head': h, 'target': t, 'hit': (h, t) in selected} for h, t in pairs]
    counts = np.zeros(len(sources), dtype=np.int64)
    for head, _ in pairs:
        counts[lookup[head]] += 1
    return {'raw': quality(scores, mask, sources, positives),
            'rounded': quality(rounded, mask, sources, positives),
            'deterministic_id_recall16': sum(r['hit'] for r in hits)/len(hits) if hits else None,
            'deterministic_outcomes': hits, 'output': output,
            'source_positive_counts': counts.tolist()}


def source_totals(assessment, sources):
    """Contributions, not per-source means: positive queries define the metric."""
    lookup = {int(h): row for row, h in enumerate(sources)}
    totals = np.zeros(len(sources), dtype=np.float64)
    for outcome in assessment['raw']['outcomes']:
        totals[lookup[outcome['head']]] += outcome['recall16']
    return totals


def paired_bootstrap(totals, counts, *, draws=100_000, seed=20260928):
    """Pair methods within sources and average repetitions before resampling.

    Each dataset supplies totals shaped (two thread settings, three process
    repetitions, 64 sources, five methods), in the constant orders above.
    Counts are the 64 source positive denominators. No labels are loaded here.
    """
    if set(totals) != set(DATASETS) or set(counts) != set(DATASETS):
        raise ValueError('All three graph families are required')
    if type(draws) is not int or draws < 1 or type(seed) is not int:
        raise ValueError('Invalid bootstrap configuration')
    differences, denominators = [], []
    for name in DATASETS:
        values = np.asarray(totals[name])
        denominator = integer_array(counts[name])
        if (values.shape != (2, 3, 64, 5) or denominator.shape != (64,)
                or np.any(denominator < 0) or not np.isfinite(values).all()
                or np.any(values < 0) or np.any(values > denominator[None, None, :, None])):
            raise ValueError('Invalid per-source contributions or denominators')
        means = values.mean(axis=1)
        differences.append(means[:, :, 0, None]-means[:, :, 1:])
        denominators.append(denominator)
    denominator_sums = np.array([d.sum() for d in denominators])
    configuration = {'draws': draws, 'seed': seed, 'resampling_unit': 'source',
                     'process_repetitions_are_not_label_samples': True,
                     'simultaneous_comparisons': COMPARISONS,
                     'simultaneous_tail_probability': .05/(2*COMPARISONS),
                     'decision_absolute_tolerance': METRIC_EPSILON,
                     'percentile_method': 'linear', 'numpy_version': np.__version__}
    empty = [name for name, size in zip(DATASETS, denominator_sums) if not size]
    if empty:
        return {'status': 'unevaluable', 'empty_positive_applications': empty,
                'configuration': configuration, 'comparisons': [], 'quality_rule': None}

    rng = np.random.default_rng(seed)
    numerators = np.empty((3, draws, 2, 4))
    sampled_denominators = np.empty((3, draws), dtype=np.int64)
    for dataset, (difference, denominator) in enumerate(zip(differences, denominators)):
        for start in range(0, draws, 1000):
            end = min(draws, start+1000)
            indices = rng.integers(0, 64, size=(end-start, 64))
            sampled_denominators[dataset, start:end] = denominator[indices].sum(axis=1)
            numerators[dataset, start:end] = difference[:, indices, :].sum(axis=2).transpose(1, 0, 2)
    valid = np.all(sampled_denominators > 0, axis=0)
    exclusions = {'by_application': {name: int(np.sum(sampled_denominators[i] == 0))
                                    for i, name in enumerate(DATASETS)},
                  'any_application': int(np.sum(~valid)), 'retained_draws': int(np.sum(valid))}
    if not valid.any():
        return {'status': 'unevaluable', 'configuration': configuration,
                'exclusions': exclusions, 'comparisons': [], 'quality_rule': None}
    d = sampled_denominators[:, valid]
    n = numerators[:, valid]
    per_application = n/d[:, :, None, None]
    samples = [*per_application, per_application.mean(axis=0),
               n.sum(axis=0)/d.sum(axis=0)[:, None, None]]
    point_numerators = np.array([v.sum(axis=1) for v in differences])
    per_application_points = point_numerators/denominator_sums[:, None, None]
    estimates = [*per_application_points, per_application_points.mean(axis=0),
                 point_numerators.sum(axis=0)/denominator_sums.sum()]
    tail = configuration['simultaneous_tail_probability']
    comparisons = []
    for name, sample, estimate in zip(VIEWS, samples, estimates):
        for t, threads in enumerate(THREADS):
            for c, control in enumerate(METHODS[1:]):
                lo, hi = np.quantile(sample[:, t, c], [tail, 1-tail], method='linear')
                comparisons.append({'view': name, 'threads': threads, 'control': control,
                    'difference': float(estimate[t, c]),
                    'percentile_95': np.quantile(sample[:, t, c], [.025, .975], method='linear').tolist(),
                    'simultaneous_95': [float(lo), float(hi)],
                    'supported_loss': bool(hi < -METRIC_EPSILON),
                    'supported_improvement': bool(lo > METRIC_EPSILON),
                    'one_point_noninferiority': bool(lo > -.01+METRIC_EPSILON)})
    rules = {}
    for threads in THREADS:
        relevant = [r for r in comparisons if r['threads'] == threads]
        within = all(r['difference'] >= -.01-METRIC_EPSILON
                     for r in relevant if r['view'] in DATASETS)
        pooled_loss = any(r['supported_loss'] for r in relevant if r['view'] not in DATASETS)
        rules[str(threads)] = {'point_estimates_within_one_point_on_every_application': within,
                              'statistically_supported_pooled_loss': pooled_loss,
                              'original_quality_conditions_met': within and not pooled_loss,
                              'one_point_noninferiority_all_views':
                                  all(r['one_point_noninferiority'] for r in relevant)}
    return {'status': 'evaluated', 'configuration': configuration, 'exclusions': exclusions,
            'comparisons': comparisons, 'quality_rule': rules,
            'interpretation': 'Conditional on three fixed graphs; connected sources need not be independent. Quality conditions alone do not close gate B or any release gate.'}
