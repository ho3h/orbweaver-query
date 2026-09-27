"""NumPy-only explicit path baseline over the same graph storage as compact state.

Stores one head's sparse path proportions as coordinate arrays. This avoids a
SciPy dependency without changing the fitted explicit model. It still enumerates
typed prefixes. No targets or labels enter inference.
"""

from collections import defaultdict

import numpy as np

from .bounded_flow import FlowGraph


class ExplicitRuntime:
    def __init__(self, graph: FlowGraph, coefficient):
        self.graph = graph
        s = 2 * graph.r
        coefficient = np.asarray(coefficient, dtype=np.float64)
        if coefficient.size != graph.r * (4+s*s+s**3) or not np.isfinite(coefficient).all():
            raise ValueError('Invalid explicit path coefficients')
        self.coefficient = coefficient.reshape(graph.r, -1).copy()
        self.coefficient.flags.writeable = False
        self.cached_head, self.cached = None, None

    def clear_cache(self):
        self.cached_head, self.cached = None, None

    @property
    def parameter_bytes(self):
        return self.coefficient.nbytes

    def expand(self, head):
        g, s = self.graph, self.graph.r * 2
        if type(head) is not int or not 0 <= head < g.n:
            raise ValueError('Invalid graph head')
        if head == self.cached_head:
            return self.cached
        excluded = {head} | set(g.neighbors[head].tolist())
        state, terminal = {(head, 0): 1.}, defaultdict(float)
        for step in range(3):
            following = defaultdict(float)
            for (node, prefix), value in sorted(state.items()):
                offset = 0
                for dest, count in zip(g.neighbors[node], g.multiplicity[node]):
                    count = int(count)
                    increment = value / g.degree[node] / count
                    for symbol in g.types[node][offset:offset+count]:
                        following[int(dest), prefix*s+int(symbol)] += increment
                    offset += count
            state = following
            if step >= 1:
                weight, offset = (2/3, 0) if step == 1 else (1/3, s*s)
                for (node, code), value in sorted(state.items()):
                    if node not in excluded:
                        terminal[node, offset+code] += weight*value
        nodes = np.array(sorted({n for n, _ in terminal}), np.int64)
        positions = {int(n): i for i, n in enumerate(nodes)}
        entries = sorted(terminal.items())
        row = np.array([positions[n] for (n, _), _ in entries], np.int64)
        col = np.array([c for (_, c), _ in entries], np.int64)
        values = np.array([v for _, v in entries], np.float64)
        mass = np.bincount(row, weights=values, minlength=len(nodes))
        if np.any(mass <= 0):
            raise ValueError('Invalid candidate mass')
        proportions = values / mass[row]
        length2 = np.bincount(row[col < s*s], weights=proportions[col < s*s], minlength=len(nodes))
        base = np.column_stack((np.ones(len(nodes)), np.log(mass), np.log1p(g.degree[nodes]), length2))
        self.cached_head, self.cached = head, (nodes, base, row, col, proportions)
        return self.cached

    def score(self, head, relation):
        if type(relation) is not int or not 0 <= relation < self.graph.r:
            raise ValueError('Invalid query relation')
        nodes, base, row, col, proportions = self.expand(head)
        weight = self.coefficient[relation]
        scores = base @ weight[:4] + np.bincount(row, weights=proportions*weight[col+4], minlength=len(nodes))
        if not np.isfinite(scores).all():
            raise ValueError('Nonfinite explicit scores')
        return nodes, scores
