"""Real Quail planning/Foreign/projection, with a Boolean decision oracle.

No model forward pass, CUDA timing, or model-quality result is supplied here.
Tested with upstream commit 41b883b838687cfbf018080f068f3e81bf2f8e64.
"""

# Optional dependencies must be checked before importing their submodules.
# ruff: noqa: E402

import pytest

quail = pytest.importorskip("quail")
pa = pytest.importorskip("pyarrow")

from quail.backends.quail.graph import partner_list_builder, partner_maps, stage_partner_lists
from quail.execution.execute import execute_query
from quail.execution.result import answer_table, document_index_table
from quail.execution.runner import ExecutionContext, ForeignRuntime, SurvivorStream
from quail.execution.types import PhysicalResponse
from quail.physical import AiFilter, AiJoin, Foreign, PortRef, decode_graph

from orbweaver_query.quail import QuailPairs


@pytest.fixture
def session():
    # Byte tokens validate the plan wiring, not model tokenization or costs.
    with quail.Session(quail.EngineConfig(model="qwen3-4b-fp8", device="h100-sxm"),
                       tokenizer=lambda text: list(text.encode())) as value:
        yield value


def rows(long_side="head"):
    return [dict(head=head, target=target, head_text=head*(200 if long_side == "head" else 5),
                 target_text=target*(200 if long_side == "target" else 5), ordinal=i)
            for i, (head, target) in enumerate([
                ("c2", "d3"), ("c0", "d2"), ("c1", "d1"),
                ("c2", "d2"), ("c2", "d3"), ("c1", "d0")])]


def foreign_result(bound, session, survivors=None):
    plan = bound.query.plan()
    foreign, = plan.graph.nodes_by_type(Foreign.type_name)
    request = bound.query._prepare_physical()
    tables = request.column_tables()
    ids = survivors or {alias: list(reversed(range(table.num_rows)))
                        for alias, table in tables.items()}
    inputs = {port.name: ids[port.source.port.split(":")[1]] for port in foreign.inputs}
    context = ExecutionContext(runtimes=session.registry.runtimes,
        sources=request.relations, functions=session.registry.functions)
    return plan, foreign, tables, ForeignRuntime().execute(foreign, inputs, context)


@pytest.mark.parametrize("kind", ["per_batch", "barrier"])
@pytest.mark.parametrize("long_side", ["head", "target"])
def test_actual_plan_pair_domain_and_projection(session, monkeypatch, kind, long_side):
    original = rows(long_side)
    candidates = QuailPairs(original)
    bound = candidates.bind(session, "Does {1} support {0}?", kind=kind)
    plan, foreign, tables, result = foreign_result(bound, session)
    plan.graph.validate(runtime_keys=set(session.registry.runtimes))
    plan.graph.validate_backend(plan.backend)
    decoded = decode_graph(plan.to_envelope(session.registry.codecs)["graph"],
                           session.registry.codecs)
    assert decoded == plan.graph
    join, = plan.graph.nodes_by_type(AiJoin.type_name)
    stage, = join.stages
    assert stage.pairs_from == foreign.node_id
    assert PortRef(foreign.node_id, f"pairs:{foreign.written_pos}") in {
        port.source for port in join.inputs}
    pair_table = result.outputs[f"pairs:{foreign.written_pos}"]
    actual = [(tables["l"]["id"][left].as_py(), tables["r"]["id"][right].as_py())
              for left, right in zip(pair_table["l"].to_pylist(), pair_table["r"].to_pylist())]
    assert set(actual) == set(candidates.candidate_pairs)
    assert len(actual) == len(candidates.candidate_pairs) == 5  # Not the 3x4 cross product.

    # Exercise Quail's actual per-anchor partner restriction for either orientation.
    for anchor, partner in (("l", "r"), ("r", "l")):
        spec = [dict(pairs_from=True, written_pos=0, anchor=anchor, partners=[partner])]
        members = [(i,) for i in reversed(range(tables[partner].num_rows))]
        anchors = list(reversed(range(tables[anchor].num_rows)))
        lists_for = partner_list_builder(spec, [members], partner_maps(spec, {0: pair_table}))
        allowed, = stage_partner_lists(spec, lists_for, anchors)
        visited = {(anchors[local], members[member][0])
                   for local, indices in allowed.items() for member in indices}
        assert visited == set(zip(pair_table[anchor].to_pylist(), pair_table[partner].to_pylist()))

    # Replay a fixed truth assignment through Quail's real projection/finish path.
    # It validates row reconstruction; these bits are NOT model predictions.
    positive = {("c2", "d3"), ("c1", "d0")}
    answers = [pair in positive for pair in actual]
    answer = answer_table({alias: pair_table[alias].to_pylist() for alias in ("l", "r")},
        answers, "join_answers", {"written_pos": stage.written_pos, "anchor": stage.anchor,
                                   "partners": ",".join(stage.partners), "semantics": "full"})
    outputs = {PortRef(foreign.node_id, key): value for key, value in result.outputs.items()}
    outputs[PortRef(join.node_id, f"join_answers:{stage.written_pos}")] = answer
    outputs[PortRef(join.node_id, f"ids:{join.anchor}")] = document_index_table(
        {join.anchor: list(range(tables[join.anchor].num_rows))}, "document_ids")
    monkeypatch.setattr(bound.query, "run", lambda: execute_query(bound.query,
        physical_executor=lambda request: PhysicalResponse(outputs,
            {"wall_s": 0.0, "fresh_tokens": 0, "backend": "decision-oracle-NOT-inference"})))
    collected = bound.run()
    assert collected.rows == tuple(row for row in original if (row["head"], row["target"]) in positive)
    assert collected.backend_result.answer_tables["joins"]
    assert collected.candidate_identity == candidates.identity
    with pytest.raises(ValueError, match="namespace"):
        candidates.bind(session, "{0} {1}")


def test_surviving_noncontiguous_ids_and_empty_domain(session):
    bound = QuailPairs(rows()).bind(session, "{0} {1}")
    for survivors, expected in [({"l": [2, 0], "r": [3, 0]}, {(2, 3), (0, 0)}),
                                 ({"l": [], "r": [1]}, set())]:
        _, foreign, _, result = foreign_result(bound, session, survivors)
        table = result.outputs[f"pairs:{foreign.written_pos}"]
        assert set(zip(table["l"].to_pylist(), table["r"].to_pylist())) == expected
        assert table.schema.types == [pa.int32(), pa.int32()]


@pytest.mark.parametrize("anchor", ["l", pytest.param("r", marks=pytest.mark.xfail(
    strict=True, reason="Pinned Quail transposes right-stream Foreign pairs on finalization"))])
def test_actual_streamed_foreign_pairs(session, anchor):
    bound = QuailPairs(rows()).bind(session, "{0} {1}")
    plan = bound.query.plan()
    foreign, = plan.graph.nodes_by_type(Foreign.type_name)
    request = bound.query._prepare_physical()
    tables = request.column_tables()
    partner = "r" if anchor == "l" else "l"
    ids = {anchor: SurvivorStream(foreign, range(tables[anchor].num_rows)),
           partner: list(range(tables[partner].num_rows))}
    _, _, _, result = foreign_result(bound, session, ids)
    streamed = result.outputs[f"pairs:{foreign.written_pos}"]
    batches = [list(reversed(range(tables[anchor].num_rows)))[:1],
               list(reversed(range(tables[anchor].num_rows)))[1:]]
    visited = set()
    for batch in batches:
        allowed = streamed.batch(batch)
        visited.update((a, b) if anchor == "l" else (b, a)
                       for a, partners in allowed.items() for b in partners)
    expected = {(0, 0), (1, 1), (2, 2), (0, 1), (2, 3)}
    assert visited == expected
    # Both finalization orientations must preserve alias column meaning as well.
    final = result.finalize().outputs[f"pairs:{foreign.written_pos}"]
    assert set(zip(final["l"].to_pylist(), final["r"].to_pylist())) == expected


@pytest.mark.parametrize("long_side", ["head", "target"])
@pytest.mark.parametrize("filtered", [("l",), ("r",), ("l", "r")])
@pytest.mark.parametrize("empty", [False, True])
def test_document_survivors_drive_actual_graph_pair_selection(
        session, monkeypatch, long_side, filtered, empty):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parents[1]/'benchmarks/v1/quail_reference_oracle.py'
    spec = importlib.util.spec_from_file_location('quail_reference_oracle', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = rows(long_side)
    original.append({**original[0], 'head_text': None})
    captured = QuailPairs(original)
    options = {('head_predicate' if a == 'l' else 'target_predicate'): 'Eligible: {0}'
               for a in filtered}
    bound = captured.bind(session, '{0} supported by {1}', **options)
    plan = bound.query.plan()
    filters = plan.graph.nodes_by_type(AiFilter.type_name)
    assert {f.alias for f in filters} == set(filtered)
    assert all(not f.pin_survivors for f in filters)
    foreign, = plan.graph.nodes_by_type(Foreign.type_name)
    assert foreign.kind == 'barrier'
    for f in filters:
        assert PortRef(f.node_id, f'ids:{f.alias}') in {p.source for p in foreign.inputs}
    truth = {'l': {'c2': True, 'c0': False, 'c1': True},
             'r': {'d3': True, 'd2': False, 'd1': False, 'd0': True}}
    if empty:
        truth[filtered[0]] = dict.fromkeys(truth[filtered[0]], False)
    positives = {('c2', 'd3'), ('c0', 'd2'), ('c1', 'd0')}
    pair_truth = {pair: pair in positives for pair in captured.candidate_pairs}
    oracle = module.DecisionOracle(session, truth, pair_truth)
    monkeypatch.setattr(bound.query, 'run', lambda: execute_query(
        bound.query, physical_executor=oracle))
    expected_pairs = {pair for pair in captured.candidate_pairs
                      if all(truth[a][pair[0 if a == 'l' else 1]] for a in filtered)}
    result = bound.run()
    assert result.rows == tuple(row for row in original
        if row['head_text'] is not None and (row['head'], row['target']) in expected_pairs & positives)
    pair_trace, = [r for r in oracle.trace if r['kind'] == 'pair']
    assert set(pair_trace['evaluated']) == expected_pairs
    assert len(pair_trace['evaluated']) == len(expected_pairs)
    for a in filtered:
        document_trace, = [r for r in oracle.trace if r.get('alias') == a]
        assert set(document_trace['evaluated']) == set(truth[a])
        assert len(document_trace['evaluated']) == len(truth[a])
    assert result.backend_result.answer_tables['filters']
