"""Root-window lifetimes for reusable, model-internal source preparation."""

from collections import Counter, OrderedDict


class PreparationScope:
    """Internal numeric-byte-bounded LRU; never retains final prediction scores."""

    def __init__(self, max_bytes):
        self.max_bytes = max_bytes
        self.entries = OrderedDict()
        self.eligible = set()
        self.bytes = self.peak_bytes = self.builds = self.hits = self.evictions = 0

    @staticmethod
    def key(model, graph, head):
        return (graph.snapshot_id, getattr(model, "preparation_id", model.model_id),
                getattr(model, "feature_id", model.model_id),
                getattr(model, "candidate_support", "backend_defined"), head)

    def hint(self, graph, rows, groups, window_size):
        """Enable preparation for sources present in more than one scoring batch."""
        if not self.max_bytes or len(rows) <= window_size:
            return
        for group in groups:
            model = group[0].model
            if not callable(getattr(model, "prepare_source", None)):
                continue
            batches = Counter()
            for offset in range(0, len(rows), window_size):
                heads = {graph.node_index(row[p.head])
                         for row in rows[offset:offset + window_size] for p in group
                         if all(row[c] is not None for c in (p.head, p.relation, p.target))}
                batches.update(heads)
            self.eligible.update(self.key(model, graph, h) for h, count in batches.items() if count > 1)

    def expand(self, model, graph, head, targets, limits):
        key = self.key(model, graph, head)
        preparation_visits = 0
        if key in self.entries:
            prepared = self.entries[key]
            self.entries.move_to_end(key)
            self.hits += 1
        elif key in self.eligible and self.max_bytes:
            prepared = model.prepare_source(graph, head, limits)
            self.builds += 1
            preparation_visits = prepared.type_visits
            size = prepared.numeric_bytes
            if type(size) is not int or size < 0:
                raise ValueError("Prepared source must report nonnegative integer numeric bytes")
            if size <= self.max_bytes:
                while self.bytes + size > self.max_bytes:
                    _, old = self.entries.popitem(last=False)
                    self.bytes -= old.numeric_bytes
                    self.evictions += 1
                self.entries[key] = prepared
                self.bytes += size
                self.peak_bytes = max(self.peak_bytes, self.bytes)
            else:
                # Use the already-built state once; do not repeatedly rebuild an
                # oversized prefix when bounded-target execution is available.
                self.eligible.discard(key)
        else:
            targeted = getattr(model, "expand_targets", None)
            return (targeted(graph, head, targets, limits) if callable(targeted)
                    else model.expand(graph, head, limits)), 0
        return prepared.expand_targets(targets, limits), preparation_visits
