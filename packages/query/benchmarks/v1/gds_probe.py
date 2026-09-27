"""Exercise the current GDS native training/prediction path before freezing comparisons.

API probe only. Internal GDS metrics on this development fixture are not an
Orbweaver comparison or confirmation result. All database writes are disposable.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from disposable_neo4j import disposable_database


def run(neo4j_home, java, gds_jar, graph_file, output):
    import numpy as np
    from neo4j import GraphDatabase

    from orbweaver_query import GraphSnapshot

    graph = GraphSnapshot.load(graph_file)
    # Use the 300 highest-degree vertices solely as a bounded API fixture.
    chosen = sorted(np.argsort(-graph.degree, kind='stable')[:300].tolist())
    chosen_set = set(chosen)
    pairs = sorted({(min(int(a), int(b)), max(int(a), int(b))) for a, _, b in graph.triples()
                   if int(a) in chosen_set and int(b) in chosen_set})
    stages = []
    with (
        disposable_database(neo4j_home, java, gds_jar=gds_jar, heap_megabytes=1024,
                              entrypoint='org.neo4j.server.Neo4jCommunity', transaction_timeout='120s') as uri,
        GraphDatabase.driver(uri, auth=None) as driver,
    ):
        def query(label, cypher, **params):
            start = time.perf_counter()
            records = [r.data() for r in driver.execute_query(cypher, parameters_=params)[0]]
            stages.append({'stage': label, 'seconds': time.perf_counter()-start, 'records': records})
            print(label, stages[-1]['seconds'], flush=True)
            return records
        query('version', 'RETURN gds.version() AS gds')
        query('nodes', 'UNWIND $nodes AS id CREATE (:Node {externalId:id})', nodes=chosen)
        query('edges', 'UNWIND $pairs AS pair MATCH (a:Node {externalId:pair[0]}), '
                      '(b:Node {externalId:pair[1]}) CREATE (a)-[:LINK]->(b)', pairs=pairs)
        query('projection', "CALL gds.graph.project('probe', 'Node', {LINK:{orientation:'UNDIRECTED'}})")
        query('pipeline', "CALL gds.beta.pipeline.linkPrediction.create('pipe')")
        query('features', "CALL gds.beta.pipeline.linkPrediction.addNodeProperty('pipe', 'fastRP', "
              "{mutateProperty:'embedding', embeddingDimension:64, randomSeed:71, concurrency:1})")
        query('hadamard', "CALL gds.beta.pipeline.linkPrediction.addFeature('pipe', 'hadamard', "
              "{nodeProperties:['embedding']})")
        query('split', "CALL gds.beta.pipeline.linkPrediction.configureSplit('pipe', "
              "{testFraction:0.2,trainFraction:0.3,validationFolds:3,negativeSamplingRatio:1.0})")
        query('logistic', "CALL gds.beta.pipeline.linkPrediction.addLogisticRegression('pipe', "
              "{penalty:0.1, maxEpochs:200})")
        query('forest', "CALL gds.beta.pipeline.linkPrediction.addRandomForest('pipe', "
              "{numberOfDecisionTrees:50,maxDepth:10})")
        query('train', "CALL gds.beta.pipeline.linkPrediction.train('probe', "
              "{pipeline:'pipe', modelName:'model', targetRelationshipType:'LINK', "
              "sourceNodeLabel:'Node',targetNodeLabel:'Node',metrics:['AUCPR'],randomSeed:71,concurrency:1}) "
              "YIELD modelInfo,modelSelectionStats,trainMillis RETURN modelInfo,modelSelectionStats,trainMillis")
        query('predict', "CALL gds.beta.pipeline.linkPrediction.predict.stream('probe', "
              "{modelName:'model',sampleRate:1.0,topN:100,concurrency:1}) "
              "YIELD node1,node2,probability RETURN gds.util.asNode(node1).externalId AS head, "
              "gds.util.asNode(node2).externalId AS target,probability")
    report = {'purpose': 'API development probe, not competitive evidence', 'nodes': len(chosen),
                  'undirected_edges': len(pairs), 'graph_source_id': graph.snapshot_id, 'stages': stages}
    with output.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for arg in ('neo4j-home','java','gds-jar','graph-file','output'):
        p.add_argument('--'+arg, type=Path, required=True)
    a = p.parse_args()
    run(a.neo4j_home,a.java,a.gds_jar,a.graph_file,a.output)
