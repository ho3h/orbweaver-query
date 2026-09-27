"""Compact typed graph transport with explicit mass lost to bounded expansion.

This is a conditional Markov/path model, not a new architecture claim. Candidate
mass and truncation bounds refer to its unpruned walk, not factual link truth.
The deployment path uses NumPy only; training uses a separately selected backend.
"""

from dataclasses import dataclass
from collections import defaultdict

import numpy as np


@dataclass
class FlowResult:
    candidates: np.ndarray
    mass: object
    unexplored: object
    excluded: object
    work: dict


class FlowGraph:
    def __init__(self, context, entities, relations, *, mark_seed):
        if (type(entities) is not int or entities < 1 or type(relations) is not int
                or relations < 1 or type(mark_seed) is not int or mark_seed < 0):
            raise ValueError("Positive schema dimensions and nonnegative mark seed required")
        context = np.asarray(context)
        if context.ndim != 2 or context.shape[1] != 3 or not np.issubdtype(context.dtype, np.integer):
            raise ValueError("Expected integer context triples[E,3]")
        adjacency = [defaultdict(set) for _ in range(entities)]
        for h, r, t in context:
            if not (0 <= h < entities and 0 <= t < entities and 0 <= r < relations) or h == t:
                raise ValueError("Context must contain valid non-self triples")
            adjacency[h][t].add(int(r))
            adjacency[t][h].add(int(r + relations))
        self.n, self.r = entities, relations
        self.neighbors = [np.array(sorted(s), np.int64) for s in adjacency]
        self.degree = np.array([len(s) for s in self.neighbors], np.int64)
        self.types, self.type_edges, self.multiplicity = [], [], []
        for node, neighbors in enumerate(self.neighbors):
            types, edges, count = [], [], []
            for edge, dest in enumerate(neighbors):
                symbols = sorted(adjacency[node][int(dest)])
                types.extend(symbols)
                edges.extend([edge] * len(symbols))
                count.append(len(symbols))
            self.types.append(np.array(types, np.int64))
            self.type_edges.append(np.array(edges, np.int64))
            self.multiplicity.append(np.array(count, np.float64))
        # Random marks affect only exact priority ties, not learned features.
        # Permuting a graph and carrying its marks preserves deterministic output;
        # regenerating marks gives equivariance in distribution.
        self.marks = np.random.default_rng(mark_seed).random(entities)

    @property
    def numeric_bytes(self):
        return sum(a.nbytes for arrays in (self.neighbors, self.types, self.type_edges,
                                           self.multiplicity) for a in arrays) + self.degree.nbytes + self.marks.nbytes

    def selected(self, nodes, values, allowance, priority):
        if priority not in ("mass", "density"):
            raise ValueError("Unknown frontier priority")
        if allowance is not None and (type(allowance) is not int or allowance < 0):
            raise ValueError("Allowance must be nonnegative integer or None")
        value = np.asarray(values, dtype=np.float64)
        score = value if priority == "mass" else value / self.degree[nodes].clip(min=1)
        order = np.lexsort((self.marks[nodes], -score))
        chosen, used = [], 0
        for i in order:
            cost = int(self.degree[nodes[i]])
            if cost and (allowance is None or used + cost <= allowance):
                chosen.append(int(i))
                used += cost
        return np.array(chosen, np.int64), used

    def edges(self, nodes, selected):
        destinations, sources, type_edges, types, divisor = [], [], [], [], []
        offset = 0
        for index in selected:
            node = int(nodes[index])
            dest = self.neighbors[node]
            destinations.extend(dest)
            sources.extend([int(index)] * len(dest))
            type_edges.extend(self.type_edges[node] + offset)
            types.extend(self.types[node])
            divisor.extend(self.multiplicity[node][self.type_edges[node]])
            offset += len(dest)
        return (np.array(destinations, np.int64), np.array(sources, np.int64),
                np.array(type_edges, np.int64), np.array(types, np.int64),
                np.array(divisor, np.float64))


def transport(graph, head, logits, *, budget=1024, priority="density", backend="numpy"):
    """Three-step positive transport; score is (mass_at_2 + .5*mass_at_3)/1.5.

    logits[3,2R] parameterize relation weights at each step. Each observed
    neighbor receives the mean weight of its relation symbols, normalized over
    all neighbors of the selected node. Whole adjacency lists are expanded.
    At most floor(budget/3) neighbor entries are visited per step. Pruned mass
    is never renormalized. Isolated heads are absorbing and excluded.

    Torch gradients pass through retained transitions, not the discrete frontier
    selection. Training must describe this surrogate rather than claiming an
    unbiased gradient of the search policy. No targets/labels enter this API.
    """
    if (type(head) is not int or not 0 <= head < graph.n
            or (budget is not None and (type(budget) is not int or budget < 3))
            or backend not in ("numpy", "torch")):
        raise ValueError("Invalid head, budget or backend")
    torch = None
    if backend == "torch":
        import torch

        if not isinstance(logits, torch.Tensor) or logits.dtype != torch.float64 or logits.device.type != "cpu":
            raise ValueError("Training requires CPU float64 logits")
        detached = logits.detach().numpy()
    else:
        logits = np.asarray(logits, dtype=np.float64)
        detached = logits
    if logits.shape != (3, 2 * graph.r) or not np.isfinite(detached).all():
        raise ValueError("Expected finite logits[3,2R]")
    if priority not in ("mass", "density"):
        raise ValueError("Unknown frontier priority")

    def array(value):
        return torch.as_tensor(value, dtype=torch.float64) if torch else np.asarray(value, dtype=np.float64)

    def zeros(n):
        return torch.zeros(n, dtype=torch.float64) if torch else np.zeros(n, np.float64)

    def scatter(size, index, values):
        if torch:
            return zeros(size).index_add(0, torch.as_tensor(index), values)
        return np.bincount(index, weights=values, minlength=size)

    def numeric(value):
        return value.detach().numpy() if torch else value

    excluded_nodes = set(graph.neighbors[head].tolist()) | {head}
    work = {"adjacency_entries": 0, "type_entries": 0, "frontier_items_scored": 0,
            "expanded_nodes": 0, "steps": []}
    if not graph.degree[head]:
        return FlowResult(np.empty(0, np.int64), zeros(0), array(0.), array(1.), work)
    nodes, mass = np.array([head], np.int64), array([1.])
    candidates, combined = np.empty(0, np.int64), zeros(0)
    unexplored, excluded = array(0.), array(0.)
    for step in range(3):
        selected, visited = graph.selected(nodes, numeric(mass), None if budget is None else budget // 3, priority)
        destination, source, edge, types, divisor = graph.edges(nodes, selected)
        work["adjacency_entries"] += visited
        work["type_entries"] += len(types)
        work["frontier_items_scored"] += len(nodes)
        work["expanded_nodes"] += len(selected)
        work["steps"].append({"frontier": len(nodes), "selected_nodes": len(selected),
                              "adjacency_entries": visited, "type_entries": len(types)})
        if len(destination):
            # A detached shift preserves derivatives of the normalized ratio and
            # prevents overflow without clipping meaningful relative weights.
            weights = (logits[step] - float(detached[step].max())).exp() if torch else np.exp(
                logits[step] - detached[step].max())
            edge_weight = scatter(len(destination), edge, weights[types] / array(divisor))
            total = scatter(len(nodes), source, edge_weight)
            transmitted = mass[source] * edge_weight / total[source]
            next_nodes, inverse = np.unique(destination, return_inverse=True)
            next_mass = scatter(len(next_nodes), inverse, transmitted)
        else:
            next_nodes, next_mass = np.empty(0, np.int64), zeros(0)
        nodes, mass = next_nodes, next_mass
        if step >= 1:
            weight = (1. if step == 1 else .5) / 1.5
            allowed = np.array([int(n) not in excluded_nodes for n in nodes], bool)
            new_nodes = nodes[allowed]
            union = np.union1d(candidates, new_nodes)
            combined = scatter(len(union), np.searchsorted(union, candidates), combined) + scatter(
                len(union), np.searchsorted(union, new_nodes), mass[allowed] * weight)
            candidates = union
            unexplored = unexplored + weight * (1 - mass.sum())
            excluded = excluded + weight * mass[~allowed].sum()
    return FlowResult(candidates, combined, unexplored, excluded, work)


def witness_logits(graph, fit_triples, *, shared=False):
    """Conventional positive-path count initializer/control, not an exact MLE.

    Weight witnessed paths by the uniform walk probability and length discount.
    Normalize each query's total witness contribution before accumulating edge
    symbol marginals. Add one pseudocount per relation/step/symbol. Only fitting
    targets guide counts; no development labels or unobserved target edges enter.
    """
    counts = np.ones((1 if shared else graph.r, 3, 2 * graph.r), np.float64)
    neighbors = [set(a.tolist()) for a in graph.neighbors]
    lookup = []
    for node in range(graph.n):
        lookup.append({int(dest): graph.types[node][graph.type_edges[node] == edge]
                       for edge, dest in enumerate(graph.neighbors[node])})
    usable = 0
    for h, relation, target in fit_triples:
        witnesses, total = [], 0.
        for middle in sorted(neighbors[h] & neighbors[target]):
            probability = 1 / graph.degree[h] / graph.degree[middle]
            witnesses.append(((int(h), middle, int(target)), probability))
            total += probability
        for first in graph.neighbors[h]:
            for second in sorted(neighbors[first] & neighbors[target]):
                probability = .5 / graph.degree[h] / graph.degree[first] / graph.degree[second]
                witnesses.append(((int(h), int(first), second, int(target)), probability))
                total += probability
        if not total:
            continue
        usable += 1
        row = 0 if shared else int(relation)
        for path, probability in witnesses:
            for step, (u, v) in enumerate(zip(path[:-1], path[1:])):
                types = lookup[u][v]
                counts[row, step, types] += probability / total / len(types)
    logits = np.log(counts / counts.sum(-1, keepdims=True))
    return logits, {"fit_triples": len(fit_triples), "with_witness": usable,
                    "initializer": "uniform-walk witnessed symbol marginal counts + 1 pseudocount"}
