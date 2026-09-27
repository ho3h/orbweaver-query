"""Native graph + materialized semantic-filter correctness, with fixed decisions.

This executes no model. It verifies dependencies through actual Quail/Neo4j
operators; neither oracle counts nor byte-token plans establish performance.
"""

import argparse
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
from unittest.mock import patch

from neo4j import GraphDatabase
import quail
from quail.execution.execute import execute_query
from quail.physical import AiFilter, Foreign

import quail_bridge_check as base
from quail_reference_oracle import DecisionOracle
from disposable_neo4j import disposable_database, native_runtime_identity
from orbweaver_query.neo4j import Neo4jSource
from orbweaver_query.quail import QuailPairs


def verify(driver, rows):
    previous = base.verify(driver, rows)  # Creates only this disposable fixture.
    source = Neo4jSource(driver, fetch_size=7)
    captured = QuailPairs.from_neo4j(source, base.EXPORT)
    pair_truth = {p: int(base.digest(p)[:8], 16) % 3 == 0 for p in captured.candidate_pairs}
    reports = []
    for filtered in (('l',), ('r',), ('l', 'r')):
        for empty in (False, True):
            truth = {a: {p[i]: int(base.digest(['eligible', p[i]])[:8], 16) % 3 != 0
                         for p in captured.candidate_pairs} for i, a in enumerate(('l', 'r'))}
            if empty:
                truth[filtered[0]] = dict.fromkeys(truth[filtered[0]], False)
            options = {('head_predicate' if a == 'l' else 'target_predicate'): 'Eligible: {0}'
                       for a in filtered}
            expected = tuple(source.iter_candidates(base.POSITIVE.replace('ORDER BY',
                'AND (NOT $filter_head OR c.id IN $eligible_heads) '
                'AND (NOT $filter_target OR d.id IN $eligible_targets) ORDER BY'),
                {'filter_head': 'l' in filtered, 'filter_target': 'r' in filtered,
                 'eligible_heads': [k for k, keep in truth['l'].items() if keep],
                 'eligible_targets': [k for k, keep in truth['r'].items() if keep]}))
            with quail.Session(quail.EngineConfig(model='qwen3-4b-fp8', device='h100-sxm'),
                               tokenizer=lambda text: list(text.encode())) as session:
                bound = captured.bind(session, 'Does {1} support {0}?', **options)
                plan = bound.query.plan()
                filters = plan.graph.nodes_by_type(AiFilter.type_name)
                assert {n.alias for n in filters} == set(filtered)
                assert all(not n.pin_survivors for n in filters)
                foreign, = plan.graph.nodes_by_type(Foreign.type_name)
                assert foreign.kind == 'barrier'
                oracle = DecisionOracle(session, truth, pair_truth)
                with patch.object(bound.query, 'run', lambda: execute_query(
                        bound.query, physical_executor=oracle)):
                    actual = bound.run().rows
                assert actual == expected
                pair_trace, = [t for t in oracle.trace if t['kind'] == 'pair']
                wanted = {p for p in captured.candidate_pairs
                          if all(truth[a][p[0 if a == 'l' else 1]] for a in filtered)}
                assert set(pair_trace['evaluated']) == wanted
                assert len(pair_trace['evaluated']) == len(wanted)
                reports.append({'filtered_aliases': list(filtered), 'all_rejected': empty,
                    'native_rows_equal': True, 'oracle_trace': oracle.trace,
                    'pair_domain_sha256': base.digest(sorted(wanted)),
                    'output_bindings': len(actual), 'output_sha256': base.digest(actual),
                    'plan': plan.graph.explain()})
    return {'base_check': previous, 'dependent_conditions': reports,
            'kind': 'CPU correctness; fixed oracle, no inference, quality or timing result'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--neo4j-home', type=Path, required=True)
    parser.add_argument('--java', type=Path, required=True)
    parser.add_argument('--inputs', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Use a new output path')
    upstream = Path(quail.__file__).resolve().parents[1]
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upstream, text=True).strip()
    if commit != base.PIN or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=upstream, text=True).strip():
        raise ValueError('Requires clean pinned Quail source')
    native = native_runtime_identity(args.java)
    with disposable_database(args.neo4j_home, args.java,
            entrypoint='org.neo4j.server.Neo4jCommunity') as uri:
        with GraphDatabase.driver(uri, auth=None) as driver:
            result = verify(driver, base.fixture(args.inputs))
            result['neo4j_version'] = driver.execute_query(
                'CALL dbms.components() YIELD versions RETURN versions[0] AS version')[0][0]['version']
    package = Path(__file__).resolve().parents[2]
    files = [Path(__file__), Path(base.__file__), Path(__file__).with_name('quail_reference_oracle.py'),
             package/'src/orbweaver_query/quail.py', package/'src/orbweaver_query/neo4j.py',
             package/'tools/disposable_neo4j.py']
    result.update(quail_commit=commit, python=platform.python_version(), native_runtime=native,
        dependencies={n: version(n) for n in ('quail-engine', 'pyarrow', 'neo4j', 'numpy')},
        source_sha256={str(p.relative_to(package)): sha256(p.read_bytes()).hexdigest() for p in files},
        input_sha256=sha256(args.inputs.read_bytes()).hexdigest() if args.inputs else None,
        oracle='Pair: sha256([head,target]) modulo 3 equals 0; document: '
               'sha256([eligible,id]) modulo 3 differs from 0. First 32 bits. Not model decisions.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'passed': True,
                      'dependent_conditions': len(result['dependent_conditions'])}))


if __name__ == '__main__':
    main()
