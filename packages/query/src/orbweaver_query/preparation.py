"""Root-window lifetimes for reusable, model-internal source preparation."""

from collections import Counter, OrderedDict
from dataclasses import dataclass


@dataclass(frozen=True)
class PreparedEntry:
    state: object
    domain: frozenset | None = None

    @property
    def numeric_bytes(self):
        return self.state.numeric_bytes


class PreparationScope:
    """Internal numeric-byte-bounded LRU; never retains final prediction scores."""

    def __init__(self, max_bytes, *, coalesce_targets=True):
        self.max_bytes = max_bytes
        self.coalesce_targets = coalesce_targets
        self.entries = OrderedDict()
        self.eligible = set()
        self.targets = {}
        self.bytes = self.peak_bytes = self.builds = self.hits = self.evictions = 0
        self.target_builds = self.target_hits = 0

    @staticmethod
    def key(model, graph, head):
        return (graph.snapshot_id, getattr(model, "preparation_id", model.model_id),
                getattr(model, "feature_id", model.model_id),
                getattr(model, "candidate_support", "backend_defined"), head)

    def hint(self, graph, rows, groups, window_size, *, cache=None, pending=None):
        """Enable preparation for sources present in more than one scoring batch."""
        self.targets = {}
        if not self.max_bytes or len(rows) <= window_size:
            return
        pending = {} if pending is None else pending
        for group in groups:
            model = group[0].model
            coalesce = self.coalesce_targets and callable(getattr(model, "prepare_targets", None))
            if not coalesce and not callable(getattr(model, "prepare_source", None)):
                continue
            batches, targets = Counter(), {}
            for offset in range(0, len(rows), window_size):
                heads = set()
                for row in rows[offset:offset + window_size]:
                    for p in group:
                        if any(row[c] is None for c in (p.head, p.relation, p.target)):
                            continue
                        head = graph.node_index(row[p.head])
                        if coalesce:
                            target = graph.node_index(row[p.target])
                            if cache is not None:
                                key = (graph.snapshot_id, p.model.model_id, head,
                                       graph.relation_index(row[p.relation]), target)
                                if key in pending or cache._contains(key):
                                    continue
                            targets.setdefault(head, set()).add(target)
                        heads.add(head)
                batches.update(heads)
            for head, count in batches.items():
                if count > 1:
                    key = self.key(model, graph, head)
                    self.eligible.add(key)
                    if coalesce:
                        self.targets.setdefault(key, set()).update(targets[head])

    def expand(self, model, graph, head, targets, limits):
        targets = tuple(targets)
        key = self.key(model, graph, head)
        preparation_visits = 0
        prepare_targets = getattr(model, "prepare_targets", None)
        domain = self.targets.get(key) if callable(prepare_targets) else None
        if key in self.entries:
            entry = self.entries[key]
            if ((entry.domain is not None and not entry.domain.issuperset(targets)) or
                    (entry.domain is None and domain is not None)):
                del self.entries[key]
                self.bytes -= entry.numeric_bytes
                self.evictions += 1
        if key in self.entries:
            entry = self.entries[key]
            prepared = entry.state
            self.entries.move_to_end(key)
            self.hits += 1
            self.target_hits += entry.domain is not None
        elif key in self.eligible and self.max_bytes:
            if domain is not None:
                domain = frozenset(domain) | frozenset(targets)
                prepared = prepare_targets(graph, head, tuple(sorted(domain)), limits)
                self.target_builds += 1
            elif callable(getattr(model, "prepare_source", None)):
                prepared = model.prepare_source(graph, head, limits)
            else:
                targeted = getattr(model, "expand_targets", None)
                return (targeted(graph, head, targets, limits) if callable(targeted)
                        else model.expand(graph, head, limits)), 0
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
                self.entries[key] = PreparedEntry(prepared, domain)
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
