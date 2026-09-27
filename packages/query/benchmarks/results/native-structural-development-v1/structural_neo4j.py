"""Matched native Neo4j/GDS structural requests and local snapshot inference.

Development only. Freeze first; each worker owns a disposable database. The
confirmation labels are neither required nor opened by this experiment.
"""

import argparse
import hashlib
import json
import math
import os
import platform
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

DATASETS = ('collaboration', 'friendship', 'communication')
WORKLOADS = ('distinct128', 'interleaved256', 'many_targets256', 'hubs128')
METRICS = ('resource_allocation', 'adamic_adar', 'common_neighbors')
ARMS = ('local_cold', 'local_warm', 'gds_native', 'cypher_fused',
        'cypher_selective', 'precomputed')
THREADS = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS',
           'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'BLIS_NUM_THREADS')
CANDIDATES = '''CYPHER runtime=slotted
UNWIND range(0, size($rows)-1) AS input_order
WITH input_order, $rows[input_order] AS row
RETURN row.head AS head, row.relation AS relation, row.target AS target,
       row.ordinal AS ordinal ORDER BY input_order'''
PREFIX = '''CYPHER runtime=slotted
UNWIND range(0, size($rows)-1) AS input_order
WITH input_order, $rows[input_order] AS row
OPTIONAL MATCH (a:Node {id:row.head})
OPTIONAL MATCH (b:Node {id:row.target})
WITH input_order, row, a, b,
 CASE WHEN row.head IS NULL OR row.relation IS NULL OR row.target IS NULL
 THEN 'null_input' WHEN a=b OR EXISTS { (a)-[:LINK]-(b) }
 THEN 'unsupported' ELSE 'scored' END AS status
'''
DEGREE = 'COUNT { (z)-[:LINK]-() }'
CONFIG = "{relationshipQuery:'LINK', direction:'BOTH'}"


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def checked(run):
    manifest = read(run/'manifest.json')
    for name, digest in manifest['files'].items():
        if sha(run/name) != digest:
            raise ValueError(f'Frozen input changed: {name}')
    return manifest


def native_query(arm, filtered):
    """Identical status/filter domain, with distinct physical score strategies."""
    guard = 'WHERE ra >= 0.2\n' if filtered else ''
    if arm == 'gds_native':
        body = f'''WITH *, CASE WHEN status='scored' THEN
 gds.linkprediction.resourceAllocation(a,b,{CONFIG}) END AS ra
{guard}WITH *, CASE WHEN status='scored' THEN
 gds.linkprediction.adamicAdar(a,b,{CONFIG}) END AS aa,
 CASE WHEN status='scored' THEN
 gds.linkprediction.commonNeighbors(a,b,{CONFIG}) END AS cn
'''
    elif arm == 'cypher_fused':
        body = f'''CALL (a,b,status) {{
 OPTIONAL MATCH (a)-[:LINK]-(z)-[:LINK]-(b) WHERE status='scored'
 WITH DISTINCT z
 WITH z, CASE WHEN z IS NOT NULL THEN {DEGREE} END AS degree
 RETURN sum(1.0/degree) AS raw_ra, sum(1.0/log(degree)) AS raw_aa,
 1.0*count(z) AS raw_cn
}}
WITH *, CASE WHEN status='scored' THEN raw_ra END AS ra,
 CASE WHEN status='scored' THEN raw_aa END AS aa,
 CASE WHEN status='scored' THEN raw_cn END AS cn
{guard}'''
    elif arm == 'cypher_selective':
        body = f'''CALL (a,b,status) {{
 OPTIONAL MATCH (a)-[:LINK]-(z)-[:LINK]-(b) WHERE status='scored'
 WITH DISTINCT z
 RETURN collect(CASE WHEN z IS NOT NULL THEN {DEGREE} END) AS degrees
}}
WITH *, CASE WHEN status='scored' THEN reduce(s=0.0,d IN degrees | s+1.0/d) END AS ra
{guard}WITH *, CASE WHEN status='scored' THEN
 reduce(s=0.0,d IN degrees | s+1.0/log(d)) END AS aa,
 CASE WHEN status='scored' THEN 1.0*size(degrees) END AS cn
'''
    else:
        raise ValueError('Unknown native arm')
    return PREFIX + body + 'RETURN row, status, ra, aa, cn ORDER BY input_order'


def model_plan(graph, filtered):
    from orbweaver_query import NeighborhoodModel, QueryPlan

    models = {name: NeighborhoodModel(relations=graph.relations, metric=name) for name in METRICS}
    plan = QueryPlan(graph)
    for name, model in models.items():
        plan = plan.predict(name, model)
    if filtered:
        plan = plan.where_score('resource_allocation', .2)
    return models, plan.project('head', 'relation', 'target', 'ordinal', *METRICS)


def normalize(records, graph, models):
    result = []
    for record in records:
        row = dict(record['row'])
        for name, column in zip(METRICS, ('ra', 'aa', 'cn')):
            row[name] = {'score': record[column], 'status': record['status'],
                         'snapshot_id': graph.snapshot_id, 'model_id': models[name].model_id,
                         'score_kind': models[name].score_kind}
        result.append(row)
    return result


def oracle(graph, rows, models, filtered):
    """Independent Python-set topology oracle; never uses production expansions."""
    neighbors = [set(map(int, graph.neighbors(i))) for i in range(len(graph.node_ids))]
    records = []
    for row in rows:
        if any(row[name] is None for name in ('head', 'relation', 'target')):
            status, scores = 'null_input', (None,)*3
        else:
            head, target = graph.node_index(row['head']), graph.node_index(row['target'])
            if head == target or target in neighbors[head]:
                status, scores = 'unsupported', (None,)*3
            else:
                common = neighbors[head] & neighbors[target]
                status = 'scored'
                scores = (math.fsum(1/len(neighbors[z]) for z in common),
                          math.fsum(1/math.log(len(neighbors[z])) for z in common), float(len(common)))
        if filtered and (scores[0] is None or scores[0] < .2):
            continue
        records.append({'row': row, 'status': status, **dict(zip(('ra', 'aa', 'cn'), scores))})
    return normalize(records, graph, models)


def assert_equal(actual, expected):
    import numpy as np

    if len(actual) != len(expected):
        raise ValueError('Output row count differs')
    error = 0.
    for a, b in zip(actual, expected):
        if a.keys() != b.keys():
            raise ValueError('Output columns differ')
        for key in a:
            if key not in METRICS:
                if a[key] != b[key]:
                    raise ValueError('Input order/bag/payload differs')
                continue
            x, y = dict(a[key]), dict(b[key])
            xs, ys = x.pop('score'), y.pop('score')
            if x != y:
                raise ValueError('Prediction metadata differs')
            if xs is None or ys is None:
                if xs != ys:
                    raise ValueError('Null/support domain differs')
            else:
                np.testing.assert_allclose(xs, ys, atol=1e-12, rtol=1e-12)
                error = max(error, abs(xs-ys))
    return error


def import_graph(driver, graph):
    """One raw relationship per unordered pair, both assertions when exported."""
    import numpy as np

    triples = graph.triples()
    pairs = np.unique(np.sort(triples[:, (0, 2)], axis=1), axis=0)
    with driver.session() as connection:
        connection.run('CREATE CONSTRAINT external_id FOR (n:Node) REQUIRE n.id IS UNIQUE').consume()
        nodes = [{'id': name, 'ordinal': i} for i, name in enumerate(graph.node_ids)]
        for start in range(0, len(nodes), 1000):
            connection.run('UNWIND $nodes AS row CREATE (:Node {id:row.id, ordinal:row.ordinal})',
                           nodes=nodes[start:start+1000]).consume()
        for start in range(0, len(pairs), 1000):
            batch = [[graph.node_ids[a], graph.node_ids[b]] for a, b in pairs[start:start+1000]]
            connection.run('UNWIND $pairs AS pair MATCH (a:Node {id:pair[0]}),'
                           '(b:Node {id:pair[1]}) CREATE (a)-[:LINK]->(b)', pairs=batch).consume()


def export_graph(source):
    return source.snapshot(nodes='MATCH (n:Node) RETURN n.id AS id ORDER BY n.ordinal',
        edges="MATCH (a:Node)-[:LINK]-(b:Node) RETURN a.id AS head,'LINK' AS relation,b.id AS target",
        relations=('LINK',))


def precompute(plan, rows):
    result = plan.run(rows).to_records()
    return {(row['head'], row['relation'], row['target']): {name: row[name] for name in METRICS}
            for row in result}


def request(arm, source, plan, models, rows, filtered, cache, table):
    if arm.startswith('local_'):
        if arm == 'local_cold':
            cache.clear()
        return source.run_plan(plan, CANDIDATES, {'rows': rows}, cache=cache).to_records()
    if arm == 'precomputed':
        output = []
        for row in source.iter_candidates(CANDIDATES, {'rows': rows}):
            values = table[row['head'], row['relation'], row['target']]
            score = values['resource_allocation']['score']
            if not filtered or (score is not None and score >= .2):
                output.append({**row, **values})
        return output
    return normalize(source.iter_candidates(native_query(arm, filtered), {'rows': rows}),
                     plan.graph, models)


def runtime_identity(neo4j_home, java, gds_jar):
    return {'gds_sha256': sha(gds_jar), 'java_binary_sha256': sha(java),
            'java_release': (java.parent.parent/'release').read_text(),
            'neo4j_libraries': {p.name: sha(p) for p in sorted((neo4j_home/'lib').glob('*.jar'))}}


def freeze(run, plan_run, neo4j_home, java, gds_jar):
    checked(plan_run)
    run.mkdir(parents=True, exist_ok=False)
    package = Path(__file__).resolve().parents[2]
    shutil.copytree(package/'src/orbweaver_query', run/'source/orbweaver_query',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('structural_neo4j.py', 'STRUCTURAL_NEO4J_PROTOCOL.md'):
        shutil.copyfile(Path(__file__).with_name(name), run/name)
    shutil.copyfile(package/'tools/disposable_neo4j.py', run/'disposable_neo4j.py')
    for dataset in DATASETS:
        for suffix in ('outer.npz', 'queries.json'):
            shutil.copyfile(plan_run/f'{dataset}-{suffix}', run/f'{dataset}-{suffix}')
    jobs = [{'dataset': d, 'replicate': r} for d in DATASETS for r in range(3)]
    random.Random(8201).shuffle(jobs)
    files = {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob('*')) if p.is_file()}
    write(run/'manifest.json', {'format': 'orbweaver-native-structural-v1', 'files': files,
        'jobs': jobs, 'arms': list(ARMS), 'workloads': list(WORKLOADS), 'warmup': 2, 'samples': 5,
        'runtime_identity': runtime_identity(neo4j_home, java, gds_jar),
        'gds_version': '2026.09.0', 'neo4j_version': '2026.09.0',
        'java_major': 21, 'heap_megabytes': 2048, 'page_cache_megabytes': 64,
        'query_runtime': 'slotted', 'fetch_size': 1000, 'transaction_timeout_seconds': 120,
        'input_plan_manifest_sha256': sha(plan_run/'manifest.json'), 'confirmation_contents_read': False})
    return {'workers': len(jobs), 'request_conditions': len(jobs)*len(WORKLOADS)*2*len(ARMS),
            'manifest_sha256': sha(run/'manifest.json')}


def worker(run, index, neo4j_home, java, gds_jar):
    sys.path.insert(0, str(run/'source'))
    sys.path.insert(0, str(run))
    import numpy as np
    from disposable_neo4j import disposable_database
    from neo4j import GraphDatabase

    from orbweaver_query import BindingCache, GraphSnapshot
    from orbweaver_query.neo4j import Neo4jSource

    manifest = checked(run)
    if runtime_identity(neo4j_home, java, gds_jar) != manifest['runtime_identity']:
        raise ValueError('Runtime artifacts differ from the frozen runtime')
    job = manifest['jobs'][index]
    graph = GraphSnapshot.load(run/f'{job["dataset"]}-outer.npz')
    queries = read(run/f'{job["dataset"]}-queries.json')
    conditions = [(w, f, a) for w in WORKLOADS for f in (False, True) for a in ARMS]
    random.Random(8202+index).shuffle(conditions)
    setup, records, max_error = {}, [], 0.
    begin = time.perf_counter()
    with (disposable_database(neo4j_home, java, gds_jar=gds_jar,
            heap_megabytes=manifest['heap_megabytes'], entrypoint='org.neo4j.server.Neo4jCommunity',
            transaction_timeout=f'{manifest["transaction_timeout_seconds"]}s') as uri,
          GraphDatabase.driver(uri, auth=None) as driver):
        setup['database_start_seconds'] = time.perf_counter()-begin
        with driver.session() as connection:
            version = connection.run('RETURN gds.version() AS version').single()['version']
            server = connection.run('CALL dbms.components() YIELD versions RETURN versions[0] AS version').single()['version']
            if version != manifest['gds_version'] or server != manifest['neo4j_version']:
                raise ValueError('Database/plugin version differs from frozen protocol')
            functions = [dict(r) for r in connection.run("SHOW FUNCTIONS YIELD name, signature "
                "WHERE name STARTS WITH 'gds.linkprediction.' RETURN name,signature ORDER BY name")]
        begin = time.perf_counter()
        import_graph(driver, graph)
        setup['import_seconds'] = time.perf_counter()-begin
        source = Neo4jSource(driver, fetch_size=manifest['fetch_size'])
        begin = time.perf_counter()
        exported = export_graph(source)
        setup['evidence_export_seconds'] = time.perf_counter()-begin
        if exported.snapshot_id != graph.snapshot_id:
            raise ValueError('Exported evidence differs from the frozen graph')
        for workload, filtered, arm in conditions:
            rows = queries[workload]
            models, plan = model_plan(exported, filtered)
            expected = oracle(graph, rows, models, filtered)
            cache, table = BindingCache(max_entries=6*len(rows)), None
            begin = time.perf_counter()
            if arm == 'local_warm':
                plan.run(rows, cache=cache)
            elif arm == 'precomputed':
                _, unfiltered = model_plan(exported, False)
                table = precompute(unfiltered, rows)
            preparation = time.perf_counter()-begin if arm in ('local_warm', 'precomputed') else 0.
            samples, digest = [], None
            for repeat in range(manifest['warmup']+manifest['samples']):
                begin = time.perf_counter()
                output = request(arm, source, plan, models, rows, filtered, cache, table)
                encoded = json.dumps(output, sort_keys=True, allow_nan=False).encode()
                elapsed = time.perf_counter()-begin
                # Validation is outside the measured request boundary.
                max_error = max(max_error, assert_equal(output, expected))
                current = hashlib.sha256(encoded).hexdigest()
                if digest is not None and current != digest:
                    raise ValueError('Repeated requests changed outputs')
                digest = current
                if repeat >= manifest['warmup']:
                    samples.append(elapsed)
            inference_only = []
            if arm.startswith('local_'):
                for _ in range(manifest['samples']):
                    if arm == 'local_cold':
                        cache.clear()
                    begin = time.perf_counter()
                    local_output = plan.run(rows, cache=cache).to_records()
                    json.dumps(local_output, sort_keys=True, allow_nan=False)
                    inference_only.append(time.perf_counter()-begin)
                    max_error = max(max_error, assert_equal(local_output, expected))
            records.append({'workload': workload, 'filtered': filtered, 'arm': arm,
                'samples_seconds': samples, 'median_seconds': float(np.median(samples)),
                'preparation_seconds': preparation, 'local_inference_seconds': inference_only,
                'pair_cache': cache.info().__dict__,
                'precomputed_pairs': None if table is None else len(table),
                'precomputed_serialized_bytes': None if table is None else len(json.dumps(list(table.items())).encode()),
                'output': output, 'output_sha256': digest})
            print(f'{job["dataset"]}/{job["replicate"]}: {workload}/{filtered}/{arm}',
                  file=sys.stderr, flush=True)
    try:
        import resource
        scale = 1 if sys.platform == 'darwin' else 1024
        python_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*scale
        java_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*scale
    except ImportError:
        python_rss = java_rss = None
    return {'job': job, 'setup': setup, 'max_absolute_error': max_error, 'records': records,
        'manifest_sha256': sha(run/'manifest.json'), 'native_functions': functions,
        'peak_python_rss_bytes': python_rss, 'peak_java_rss_bytes': java_rss,
        'memory_scope': 'whole worker/DB across all arms; not per-arm attribution',
        'environment': {'python': sys.version, 'platform': platform.platform(),
                        'gds': version, 'neo4j': server}}


def execute(run, neo4j_home, java, gds_jar):
    manifest = checked(run)
    folder = run/'workers'
    folder.mkdir(exist_ok=True)
    for index, job in enumerate(manifest['jobs']):
        output, error = folder/f'{index:04d}.json', folder/f'{index:04d}-error.json'
        if output.exists():
            continue
        if error.exists():
            raise ValueError('Preserve the failed attempt and freeze a new campaign')
        command = [sys.executable, str(run/'structural_neo4j.py'), 'worker', str(run),
                   '--index', str(index), '--neo4j-home', str(neo4j_home), '--java', str(java),
                   '--gds-jar', str(gds_jar)]
        with (folder/f'{index:04d}-console.txt').open('x') as log:
            result = subprocess.run(command, env={**os.environ, **{k: '1' for k in THREADS}},
                                    stdout=subprocess.PIPE, stderr=log, text=True, check=False)
        if result.returncode:
            write(error, {'job': job, 'stdout': result.stdout, 'returncode': result.returncode})
            raise RuntimeError(f'Worker {index} failed; retained its console/error files')
        write(output, json.loads(result.stdout))
        print(f'{index+1}/{len(manifest["jobs"])} database workers', flush=True)
    return {'workers': len(manifest['jobs'])}


def verify(run, neo4j_home, java, gds_jar):
    """Full-fixture correctness only; may run while unrelated fitting is active."""
    sys.path.insert(0, str(run/'source'))
    sys.path.insert(0, str(run))
    from disposable_neo4j import disposable_database
    from neo4j import GraphDatabase

    from orbweaver_query import BindingCache, GraphSnapshot
    from orbweaver_query.neo4j import Neo4jSource

    manifest = checked(run)
    if runtime_identity(neo4j_home, java, gds_jar) != manifest['runtime_identity']:
        raise ValueError('Runtime artifacts differ from the frozen runtime')
    records, max_error = [], 0.
    for dataset in DATASETS:
        graph = GraphSnapshot.load(run/f'{dataset}-outer.npz')
        queries = read(run/f'{dataset}-queries.json')
        with (disposable_database(neo4j_home, java, gds_jar=gds_jar,
                heap_megabytes=manifest['heap_megabytes'], entrypoint='org.neo4j.server.Neo4jCommunity',
                transaction_timeout=f'{manifest["transaction_timeout_seconds"]}s') as uri,
              GraphDatabase.driver(uri, auth=None) as driver):
            import_graph(driver, graph)
            source = Neo4jSource(driver, fetch_size=manifest['fetch_size'])
            exported = export_graph(source)
            if exported.snapshot_id != graph.snapshot_id:
                raise ValueError('Exported snapshot differs')
            for workload in WORKLOADS:
                rows = queries[workload]
                for filtered in (False, True):
                    models, plan = model_plan(exported, filtered)
                    expected = oracle(graph, rows, models, filtered)
                    _, unfiltered = model_plan(exported, False)
                    table = precompute(unfiltered, rows)
                    cache = BindingCache(max_entries=6*len(rows))
                    for arm in ARMS:
                        output = request(arm, source, plan, models, rows, filtered, cache, table)
                        max_error = max(max_error, assert_equal(output, expected))
                        records.append({'dataset': dataset, 'workload': workload,
                                        'filtered': filtered, 'arm': arm, 'output': output})
        print(f'{dataset}: all native/local arms verified', file=sys.stderr, flush=True)
    report = {'manifest_sha256': sha(run/'manifest.json'), 'timing_claim': False,
              'max_absolute_error': max_error, 'records': records}
    write(run/'verification.json', report)
    return {'verified_conditions': len(records), 'max_absolute_error': max_error}


def summarize(run):
    import numpy as np

    manifest = checked(run)
    workers = [read(run/'workers'/f'{i:04d}.json') for i in range(len(manifest['jobs']))]
    outcomes = []
    for index, worker_result in enumerate(workers):
        if worker_result['job'] != manifest['jobs'][index] or worker_result['manifest_sha256'] != sha(run/'manifest.json'):
            raise ValueError('Worker belongs to a different frozen campaign')
    for dataset in DATASETS:
        for workload in WORKLOADS:
            for filtered in (False, True):
                arms, reference = {}, None
                for arm in ARMS:
                    records = [record for w in workers if w['job']['dataset'] == dataset
                        for record in w['records'] if (record['workload'], record['filtered'], record['arm'])
                        == (workload, filtered, arm)]
                    if len(records) != 3:
                        raise ValueError('Missing or duplicate condition')
                    for record in records:
                        if reference is None:
                            reference = record['output']
                        assert_equal(record['output'], reference)
                    latency = float(np.median([r['median_seconds'] for r in records]))
                    setup = float(np.median([r['preparation_seconds'] for r in records]))
                    export = float(np.median([w['setup']['evidence_export_seconds'] for w in workers
                                             if w['job']['dataset'] == dataset])) if arm in ('local_cold', 'local_warm', 'precomputed') else 0.
                    arms[arm] = {'ms': 1000*latency, 'preparation_ms': 1000*setup,
                        'evidence_export_ms': 1000*export,
                        'amortized_ms': {str(n): 1000*(latency+(setup+export)/n) for n in (1, 10, 100, 1000)}}
                outcomes.append({'dataset': dataset, 'workload': workload, 'filtered': filtered,
                                 'output_rows': len(reference), 'arms': arms})
    report = {'numerical_parity': True, 'verified_workers': len(workers),
        'max_absolute_error': max(w['max_absolute_error'] for w in workers), 'outcomes': outcomes,
        'manifest_sha256': sha(run/'manifest.json'), 'development_only': True}
    write(run/'results.json', report)
    return {k: v for k, v in report.items() if k != 'outcomes'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('freeze', 'verify', 'worker', 'execute', 'summarize'))
    parser.add_argument('run', type=Path)
    parser.add_argument('--plan-run', type=Path)
    parser.add_argument('--neo4j-home', type=Path)
    parser.add_argument('--java', type=Path)
    parser.add_argument('--gds-jar', type=Path)
    parser.add_argument('--index', type=int)
    args = parser.parse_args()
    root = args.run.resolve()
    if args.command == 'freeze':
        report = freeze(root, args.plan_run, args.neo4j_home, args.java, args.gds_jar)
    elif args.command == 'worker':
        report = worker(root, args.index, args.neo4j_home, args.java, args.gds_jar)
    elif args.command == 'execute':
        report = execute(root, args.neo4j_home, args.java, args.gds_jar)
    elif args.command == 'verify':
        report = verify(root, args.neo4j_home, args.java, args.gds_jar)
    else:
        report = summarize(root)
    print(json.dumps(report, allow_nan=False))
