"""Frozen, non-timing diagnostic of GDS prediction reservation lifetimes."""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path


def probe(run, mode, neo4j_home, java, gds_jar):
    import gds_ranking as ranking
    from disposable_neo4j import disposable_database, native_runtime_identity
    from neo4j import GraphDatabase

    sys.path.insert(0, str(run/'source'))
    from orbweaver_query.neo4j import Neo4jSource

    manifest = json.loads((run/'manifest.json').read_text())
    application = manifest.get('dataset') == 'collaboration'
    threads = manifest.get('threads', 1)
    if type(threads) is not int or threads not in (1, 4):
        raise ValueError('Probe requires one or four configured threads')
    for name, expected in manifest['files'].items():
        if hashlib.sha256((run/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen probe source changed')
    if native_runtime_identity(java) != manifest['native_runtime']:
        raise ValueError('Native runtime differs')
    if hashlib.sha256(gds_jar.read_bytes()).hexdigest() != manifest['gds_jar_sha256']:
        raise ValueError('GDS jar differs')
    if any(os.environ.get(key) != str(threads) for key in manifest['thread_environment']):
        raise ValueError('Numeric thread ceilings differ')
    if application:
        import numpy as np

        import gds_quality
        from structural_neo4j import import_graph, runtime_identity
        from orbweaver_query import GraphSnapshot

        if runtime_identity(neo4j_home, java, gds_jar) != manifest['runtime_identity']:
            raise ValueError('Pinned application runtime differs')
        graph = GraphSnapshot.load(run/'graph.npz')
        with np.load(run/'development.npz', allow_pickle=False) as data:
            sources, positives = data['sources'], data['positives']
    output = run/mode
    output.mkdir(exist_ok=False)

    def save(name, value):
        with (output/name).open('x') as file:
            json.dump(value, file, indent=2, sort_keys=True, allow_nan=False, default=str)
            file.write('\n')

    with (disposable_database(neo4j_home, java, gds_jar=gds_jar, heap_megabytes=8192,
            entrypoint='org.neo4j.server.Neo4jCommunity', transaction_timeout='900s',
            gds_progress_retention_seconds=manifest.get('gds_progress_retention_seconds', 0)) as uri,
            GraphDatabase.driver(uri, auth=None) as driver):
        def query(cypher, **parameters):
            return [r.data() for r in driver.execute_query(cypher, parameters_=parameters)[0]]

        versions = query('CALL dbms.components() YIELD versions '
                         'RETURN versions[0] AS neo4j,gds.version() AS gds')[0]
        if versions != {'neo4j': '2026.09.0', 'gds': '2026.09.0'}:
            raise ValueError('Native database versions differ')
        procedures = query("SHOW PROCEDURES YIELD name,signature WHERE name STARTS WITH 'gds.memory' "
                           "OR name IN ['gds.listProgress','dbms.queryJmx','dbms.listPools'] RETURN name,signature")
        save('procedures.json', procedures)
        save('settings.json', query("SHOW SETTINGS YIELD name,value WHERE name IN "
             "['gds.progress_tracking_enabled','gds.progress_tracking_retention_period'] RETURN name,value"))
        names = {row['name'] for row in procedures}
        checkpoints = []

        def checkpoint(stage):
            record = {'stage': stage, 'memory': query('CALL gds.memory.list()'),
                      'summary': query('CALL gds.memory.summary()'),
                      'progress': query('CALL gds.listProgress()')}
            if 'dbms.queryJmx' in names:
                record['jvm_heap'] = query("CALL dbms.queryJmx('java.lang:type=Memory') YIELD attributes "
                                           'RETURN attributes.HeapMemoryUsage AS heap')
            else:
                record['jvm_heap'] = {'available': False}
            checkpoints.append(record)
            if application:
                record['completed_task_count'] = len(query("CALL gds.listProgress('',true)"))
            save(f'checkpoint-{len(checkpoints)-1:02d}.json', record)
            print(mode, stage, record['summary'], flush=True)
            if application and (record['progress'] or any(r['totalTasksMemory'] for r in record['summary'])):
                raise ValueError('Completed application work still has active tasks or reservations')

        if application:
            heads = [graph.node_ids[i] for i in sources]
            if len(heads) != 64:
                raise ValueError('Application probe must retain all 64 development sources')
            import_graph(driver, graph)
        else:
            n = manifest['nodes']
            heads = [f'n{i:03}' for i in range(manifest['heads'])]
            edges = sorted({tuple(sorted((i, (i+step) % n))) for i in range(n) for step in (1, 7)})
            query('UNWIND range(0,$n-1) AS i CREATE (:Node {id:$ids[i],ordinal:i})',
                  n=n, ids=[f'n{i:03}' for i in range(n)])
            query('UNWIND $edges AS edge MATCH (a:Node {ordinal:edge[0]}),(b:Node {ordinal:edge[1]}) '
                  'CREATE (a)-[:LINK]->(b)', edges=edges)
        query('UNWIND $heads AS id MATCH (n:Node {id:id}) SET n:Query', heads=heads)
        specs = ranking.prepare_source_specs(query, heads)
        query("CALL gds.graph.project('graph',$labels,{LINK:{orientation:'UNDIRECTED'}})",
              labels=['Node', 'Query', *[s['source_label'] for s in specs]])
        checkpoint('projected')
        for i in range(0 if application else manifest['requests']):
            query("CALL gds.fastRP.mutate('graph',{mutateProperty:'probeEmbedding',"
                  "embeddingDimension:256,randomSeed:71,concurrency:1})")
            query("CALL gds.graph.nodeProperties.drop('graph',['probeEmbedding'])")
            checkpoint(f'standalone-{i+1}')
        trained = ranking.fit_gds(query, manifest['gds_config'], threads)
        save('model-training.json', trained)
        checkpoint('fitted')
        source = Neo4jSource(driver, fetch_size=1000)
        reference = None
        if application:
            mask = ranking.candidate_mask(graph, sources)
            params = {'heads': heads, 'k': 16, 'threads': threads, 'candidate_count': int(mask.sum())}
            scores = ranking.from_stream(source.iter_candidates(ranking.gds_query(full=True), params), graph, sources)
            np.savez_compressed(output/'scores.npz', scores=scores)
            reference = ranking.rank_scores(scores, graph, sources, 16)
            with np.load(run/'previous-scores.npz', allow_pickle=False) as data:
                previous = data['scores']
            if not np.array_equal(np.isfinite(previous), mask):
                raise ValueError('Previous raw scores cover a different candidate domain')
            save('full-score-reference.json', {'output': reference, 'candidate_count': int(mask.sum()),
                 'raw_quality': gds_quality.evaluate(scores, mask, sources, positives),
                 'prior_max_absolute_score_difference': float(np.max(np.abs(scores[mask]-previous[mask])))})
            checkpoint('full-score-reference')

        class SeparateTransactions:
            def iter_candidates(self, cypher, parameters):
                for request in parameters['requests']:
                    yield from source.iter_candidates(cypher, {**parameters, 'requests': [request]})

        request_source = source if mode == 'grouped' else SeparateTransactions()
        requests = []
        try:
            for i in range(manifest['requests']):
                rows, counters = ranking.partitioned_request(request_source, specs, threads, 16)
                if reference is None:
                    reference = rows
                elif rows != reference:
                    raise ValueError('Prediction differs from its complete-score or repeated reference')
                request = {'output': rows, 'counters': counters}
                requests.append(request)
                save(f'request-{i+1:02d}.json', request)
                checkpoint(f'prediction-{i+1}')
        except Exception as error:
            save('failure.json', {'type': type(error).__name__, 'message': str(error)})
            checkpoint('after-failure')
            raise
        if application:
            remaining = manifest['cleanup_wait_seconds']
            while remaining:
                wait = min(30, remaining)
                print(mode, 'waiting for task-record cleanup', remaining, flush=True)
                time.sleep(wait)
                remaining -= wait
            checkpoint('after-retention-expiry')
            if checkpoints[-1]['completed_task_count']:
                raise ValueError('Completed task records remain after the declared retention wait')
        save('result.json', {'mode': mode, 'versions': versions, 'requests': len(requests),
                            'threads': threads, 'repeated_outputs_equal': True,
                            'full_score_reference_checked': application,
                            'scope': 'resource diagnostic, not comparative timing or model-quality selection'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--mode', choices=('grouped', 'separate'), required=True)
    for name in ('neo4j-home', 'java', 'gds-jar'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    probe(args.run.resolve(), args.mode, args.neo4j_home, args.java, args.gds_jar)
