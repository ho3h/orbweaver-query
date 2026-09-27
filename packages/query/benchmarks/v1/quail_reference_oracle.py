"""Fixed Boolean decisions for CPU wiring checks, never model or timing evidence.

Only AiFilter/AiJoin decisions are supplied. Quail's real dependency runner,
scans, Foreign callback, physical output conversion and final projection execute.
This helper is outside the shipped package and cannot serve as an inference arm.
"""

from quail.execution.result import answer_table
from quail.execution.runner import ExecutionContext, GenericRunner, NodeResult, compute_subgraph
from quail.execution.types import PhysicalResponse, export_physical_outputs
from quail.physical import AiFilter, AiJoin, Scan, decode_graph, validate_streams


class DecisionOracle:
    def __init__(self, session, document_truth, pair_truth):
        self.session = session
        self.document_truth = document_truth
        self.pair_truth = pair_truth
        self.trace = []

    def __call__(self, request):
        registry = self.session.registry
        graph = decode_graph(request.plan['graph'], registry.codecs)
        validate_streams(graph)
        graph = compute_subgraph(graph)
        tables = request.column_tables()
        oracle = self

        def application_id(alias, index):
            return tables[alias]['id'][index].as_py()

        class Decisions:
            def execute(self, node, inputs, context):
                if isinstance(node, AiFilter):
                    if node.pin_survivors or len(node.stages) != 1:
                        raise ValueError('Oracle requires one materialized filter per alias')
                    ids, = inputs.values()
                    rows = {i: [oracle.document_truth[node.alias][application_id(node.alias, i)]]
                            for i in ids}
                    oracle.trace.append({'kind': 'document', 'alias': node.alias,
                                         'evaluated': [application_id(node.alias, i) for i in ids]})
                    return NodeResult({f'ids:{node.alias}': [i for i in ids if rows[i][0]],
                                       f'filter_answers:{node.alias}': rows})
                if not isinstance(node, AiJoin) or len(node.stages) != 1:
                    raise ValueError('Oracle requires one candidate-restricted full join')
                stage, = node.stages
                if stage.semantics != 'full':
                    raise ValueError('Oracle does not simulate existence early termination')
                pairs, = [inputs[p.name] for p in node.inputs
                           if p.source.port.startswith('pairs:')]
                indices = list(zip(pairs['l'].to_pylist(), pairs['r'].to_pylist()))
                evaluated = [(application_id('l', a), application_id('r', b)) for a, b in indices]
                bits = [oracle.pair_truth[pair] for pair in evaluated]
                oracle.trace.append({'kind': 'pair', 'evaluated': evaluated})
                answer = answer_table({a: pairs[a].to_pylist() for a in ('l', 'r')}, bits,
                    'join_answers', {'written_pos': stage.written_pos, 'anchor': stage.anchor,
                                     'partners': ','.join(stage.partners), 'semantics': 'full'})
                accepted = [i for i, keep in zip(pairs[node.anchor].to_pylist(), bits) if keep]
                return NodeResult({f'ids:{node.anchor}': sorted(set(accepted)),
                                   f'join_answers:{stage.written_pos}': answer})

        runtimes = dict(registry.runtimes)
        runtimes.update({AiFilter.runtime_key: Decisions(), AiJoin.runtime_key: Decisions()})
        sources = dict(request.relations)
        sources.update({n.input_id: list(reversed(range(len(request.inputs[n.input_id]))))
                        for n in graph.nodes if isinstance(n, Scan)})
        run = GenericRunner().run(graph, ExecutionContext(
            runtimes=runtimes, sources=sources, functions=registry.functions))
        return PhysicalResponse(export_physical_outputs(graph, run),
            {'wall_s': 0.0, 'fresh_tokens': 0, 'backend': 'decision-oracle-NOT-inference'})
