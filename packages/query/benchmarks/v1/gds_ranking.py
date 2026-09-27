"""Exact per-source ranking boundaries for the native GDS application benchmark.

The public prediction API limits topN globally. The exhaustive reference retains
the full domain; per-source queues adaptively overfetch ties and rank after Bolt
transfer. Both preserve empty sources and use the same score/ID ordering.
"""

import math

PRECISION = 12
HEADS = '''CYPHER runtime=slotted
UNWIND range(0,size($heads)-1) AS ordinal
MATCH (h:Node {id:$heads[ordinal]})
RETURN h.id AS head ORDER BY ordinal'''
GDS_STREAM = '''CALL gds.beta.pipeline.linkPrediction.predict.stream('graph',
{modelName:'model',sourceNodeLabel:'Query',targetNodeLabel:'Node',sampleRate:1.0,
topN:$candidate_count,threshold:0.0,concurrency:$threads})
YIELD node1,node2,probability'''
PARTITIONED = '''CYPHER runtime=slotted
UNWIND $requests AS req
CALL gds.beta.pipeline.linkPrediction.predict.stream('graph',
{modelName:'model',sourceNodeLabel:req.source_label,targetNodeLabel:'Node',sampleRate:1.0,
topN:req.limit,threshold:0.0,concurrency:$threads}) YIELD node1,node2,probability
RETURN req.ordinal AS ordinal,gds.util.asNode(node1).id AS a,
gds.util.asNode(node2).id AS b,probability AS score'''


def prepare_source_specs(query, heads):
    """Prepare singleton labels/counts in an owned simple-graph fixture, no export.

    Include the returned labels in the GDS projection. This is setup, not a timed
    request. The fixture has one undirected LINK edge per unordered node pair.
    """
    if len(set(heads)) != len(heads):
        raise ValueError('Recommendation sources must be distinct')
    rows = query('MATCH (n:Node) WITH count(n) AS total '
        'UNWIND range(0,size($heads)-1) AS ordinal MATCH (h:Node {id:$heads[ordinal]}) '
        'RETURN ordinal,h.id AS head,total-1-COUNT { (h)-[:LINK]-() } AS candidates '
        'ORDER BY ordinal', heads=heads)
    if [r['head'] for r in rows] != heads:
        raise ValueError('Source metadata does not cover requested heads')
    for i, row in enumerate(rows):
        label = f'OrbRankSource_{i}'
        query(f'MATCH (h:Node {{id:$head}}) SET h:{label}', head=row['head'])
        row['source_label'] = label
    return rows


def partitioned_request(source, specs, threads, k=16):
    """Exact per-source top-k with adaptive overfetch of boundary ties.

    GDS breaks equal-probability cutoff ties without the application's ID rule.
    Overfetch until the lowest retained rounded score is below the kth score,
    or the full per-source domain is retained. Thus unreturned rows cannot change
    the answer. Repeated feature preparation is real native cost, not bypassed.
    """
    if type(k) is not int or k < 1:
        raise ValueError('k must be a positive integer')
    if any(type(s['candidates']) is not int or s['candidates'] < 0 for s in specs):
        raise ValueError('Invalid candidate count')
    output = [{'head': s['head'], 'recommendations': []} for s in specs]
    pending = {i: min(2*k, s['candidates']) for i, s in enumerate(specs) if s['candidates']}
    stats = {'rounds': 0, 'procedure_calls': 0, 'returned_pairs': 0, 'max_top_n': 0}
    while pending:
        requests = [{'ordinal': i, 'head': specs[i]['head'],
                     'source_label': specs[i]['source_label'], 'limit': limit}
                    for i, limit in pending.items()]
        values = {i: {} for i in pending}
        stats['rounds'] += 1
        stats['procedure_calls'] += len(requests)
        stats['max_top_n'] = max(stats['max_top_n'], max(pending.values()))
        for row in source.iter_candidates(PARTITIONED, {'requests': requests, 'threads': threads}):
            i = row['ordinal']
            if type(i) is not int or i not in pending:
                raise ValueError('Prediction returned an unexpected source')
            head = specs[i]['head']
            a, b, score = row['a'], row['b'], row['score']
            if head not in (a, b) or a == b:
                raise ValueError('Prediction outside the singleton source domain')
            target = b if a == head else a
            if (type(target) is not str or not math.isfinite(score) or not 0 <= score <= 1
                    or target in values[i]):
                raise ValueError('Invalid or duplicate native prediction')
            values[i][target] = round(float(score), PRECISION)
            stats['returned_pairs'] += 1
        again = {}
        for i, limit in pending.items():
            if len(values[i]) != limit:
                raise ValueError('Incomplete singleton prediction coverage')
            ordered = sorted(values[i].items(), key=lambda item: (-item[1], item[0]))
            if limit < specs[i]['candidates'] and ordered[k-1][1] == ordered[-1][1]:
                again[i] = min(2*limit, specs[i]['candidates'])
            else:
                output[i]['recommendations'] = [{'target': t, 'score': v} for t, v in ordered[:k]]
        pending = again
    return output, stats


def gds_query(*, full=False):
    prefix = 'CYPHER runtime=slotted\n'
    pairs = GDS_STREAM + '''
UNWIND [[node1,node2],[node2,node1]] AS pair
WITH gds.util.asNode(pair[0]) AS h,gds.util.asNode(pair[1]) AS t,probability
WHERE h:Query
'''
    if full:
        return prefix + pairs + '''RETURN h.ordinal AS head,t.ordinal AS target,
probability AS score ORDER BY head,target'''
    return prefix + '''CALL () {
''' + pairs + '''WITH h.id AS head,t.id AS target,round(probability,12,'HALF_EVEN') AS score
ORDER BY head,score DESC,target
WITH head,collect({target:target,score:score})[..$k] AS recommendations
RETURN collect({head:head,recommendations:recommendations}) AS ranked
}
UNWIND range(0,size($heads)-1) AS ordinal
WITH ordinal,$heads[ordinal] AS head,ranked
RETURN head,coalesce([r IN ranked WHERE r.head=head | r.recommendations][0],[])
AS recommendations ORDER BY ordinal'''


def structural_query(metric, *, scalar=False):
    if metric not in ('resource_allocation', 'adamic_adar'):
        raise ValueError('Unknown structural metric')
    prefix = '''CYPHER runtime=slotted
UNWIND range(0,size($heads)-1) AS ordinal
MATCH (h:Node {id:$heads[ordinal]})
CALL (h) {
'''
    if scalar:
        function = 'resourceAllocation' if metric == 'resource_allocation' else 'adamicAdar'
        return prefix + f'''MATCH (t:Node) WHERE t<>h AND NOT EXISTS {{ (h)-[:LINK]-(t) }}
WITH t,round(gds.linkprediction.{function}(h,t,
{{relationshipQuery:'LINK',direction:'BOTH'}}),12,'HALF_EVEN') AS score
ORDER BY score DESC,t.id LIMIT $k
RETURN collect({{target:t.id,score:score}}) AS recommendations
}}
RETURN h.id AS head,recommendations ORDER BY ordinal'''
    weight = '1.0/z.degree' if metric == 'resource_allocation' else '1.0/log(z.degree)'
    # Degree is prepared once on the immutable fixture and charged separately.
    # Positive two-hop paths avoid an all-pairs cross product. Zero-score fill
    # is necessary for low-degree/isolated sources and uses the same ID tie rule.
    return prefix + f'''MATCH (h)-[:LINK]-(z)-[:LINK]-(t)
WHERE t<>h AND NOT EXISTS {{ (h)-[:LINK]-(t) }}
WITH t,round(sum({weight}),12,'HALF_EVEN') AS score
ORDER BY score DESC,t.id LIMIT $k
RETURN collect({{target:t.id,score:score}}) AS positive
}}
CALL (h,positive) {{
MATCH (t:Node) WHERE size(positive)<$k AND t<>h
AND NOT EXISTS {{ (h)-[:LINK]-(t) }}
AND NOT any(p IN positive WHERE p.target=t.id)
WITH t ORDER BY t.id LIMIT $k
RETURN collect({{target:t.id,score:0.0}}) AS zeros
}}
RETURN h.id AS head,(positive+zeros)[..$k] AS recommendations ORDER BY ordinal'''


def candidate_mask(graph, sources):
    import numpy as np

    mask = np.ones((len(sources), len(graph.node_ids)), dtype=bool)
    for i, h in enumerate(sources):
        mask[i, h] = False
        mask[i, graph.neighbors(int(h))] = False
    return mask


def from_stream(records, graph, sources):
    """Reject missing, duplicate, non-finite or out-of-domain native predictions."""
    import numpy as np

    candidates = candidate_mask(graph, sources)
    scores = np.full(candidates.shape, np.nan)
    lookup = {int(h): i for i, h in enumerate(sources)}
    for row in records:
        h, t, value = row['head'], row['target'], row['score']
        if (type(h) is not int or type(t) is not int or h not in lookup
                or not 0 <= t < len(graph.node_ids) or not candidates[lookup[h], t]):
            raise ValueError('Native prediction outside the candidate domain')
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('Invalid native probability')
        i = lookup[h]
        if math.isfinite(scores[i, t]):
            raise ValueError('Duplicate native prediction')
        scores[i, t] = value
    if np.any(candidates & ~np.isfinite(scores)):
        raise ValueError('Incomplete native candidate coverage')
    return scores


def rank_scores(scores, graph, sources, k):
    """All arms use rounded scores and application-string IDs for ranking ties."""
    import numpy as np

    if type(k) is not int or k < 1:
        raise ValueError('k must be a positive integer')
    candidates = candidate_mask(graph, sources)
    if scores.shape != candidates.shape:
        raise ValueError('Score matrix does not match candidate domain')
    if np.any(np.isfinite(scores) & ~candidates):
        raise ValueError('Scores include excluded pairs')
    output = []
    for i, h in enumerate(sources):
        # Missing model support is not a zero-valued score; it cannot be returned.
        entries = [(graph.node_ids[t], round(float(scores[i, t]), PRECISION))
                   for t in np.flatnonzero(candidates[i] & np.isfinite(scores[i]))]
        entries.sort(key=lambda item: (-item[1], item[0]))
        output.append({'head': graph.node_ids[h], 'recommendations':
                       [{'target': t, 'score': v} for t, v in entries[:k]]})
    return output


def structural_scores(graph, sources, metric):
    """Independent sparse-algebra oracle, also a strong manual execution control."""
    import numpy as np
    from scipy import sparse

    if metric == 'resource_allocation':
        weights = 1/np.maximum(graph.degree, 1)
    elif metric == 'adamic_adar':
        weights = 1/np.log(np.maximum(graph.degree, 2))
    else:
        raise ValueError('Unknown structural metric')
    n = len(graph.node_ids)
    adjacency = sparse.csr_matrix((np.ones(len(graph.indices)), graph.indices,
                                   graph.indptr), shape=(n, n))
    scores = (adjacency[sources].multiply(weights) @ adjacency).toarray()
    scores[~candidate_mask(graph, sources)] = np.nan
    return scores


def local_scores(graph, sources, model):
    import numpy as np
    from orbweaver_query import LinkQuery, Session

    scores = np.full((len(sources), len(graph.node_ids)), np.nan)
    result = Session(graph, model).run([LinkQuery(graph.node_ids[h], 'LINK') for h in sources])
    for i, row in enumerate(result.rows):
        scores[i, [graph.node_index(t) for t in row.candidate_ids]] = row.scores
    return scores


def fit_gds(query, config, threads):
    """Same selected pipeline/classifier budget as development, explicit threads."""
    query("CALL gds.beta.pipeline.linkPrediction.create('pipe')")
    query("CALL gds.beta.pipeline.linkPrediction.addNodeProperty('pipe','fastRP',"
          "{mutateProperty:'embedding',embeddingDimension:$dimension,randomSeed:71,"
          "concurrency:$threads})", dimension=config['dimension'], threads=threads)
    query("CALL gds.beta.pipeline.linkPrediction.addFeature('pipe','hadamard',"
          "{nodeProperties:['embedding']})")
    if config['rich']:
        query("CALL gds.beta.pipeline.linkPrediction.addNodeProperty('pipe','degree',"
              "{mutateProperty:'degree',concurrency:$threads})", threads=threads)
        query("CALL gds.beta.pipeline.linkPrediction.addFeature('pipe','hadamard',"
              "{nodeProperties:['degree']})")
        query("CALL gds.beta.pipeline.linkPrediction.addFeature('pipe','cosine',"
              "{nodeProperties:['embedding']})")
    query("CALL gds.beta.pipeline.linkPrediction.configureSplit('pipe',"
          "{testFraction:0.2,trainFraction:0.3,validationFolds:3,negativeSamplingRatio:$ratio})",
          ratio=config['negative_ratio'])
    query("CALL gds.beta.pipeline.linkPrediction.addLogisticRegression('pipe',"
          "{penalty:0.1,maxEpochs:200})")
    query("CALL gds.beta.pipeline.linkPrediction.addRandomForest('pipe',"
          "{numberOfDecisionTrees:50,maxDepth:10})")
    return query("CALL gds.beta.pipeline.linkPrediction.train('graph',"
          "{pipeline:'pipe',modelName:'model',targetRelationshipType:'LINK',"
          "sourceNodeLabel:'Node',targetNodeLabel:'Node',metrics:['AUCPR'],randomSeed:71,"
          "concurrency:$threads}) YIELD modelInfo,modelSelectionStats,trainMillis,configuration "
          "RETURN modelInfo,modelSelectionStats,trainMillis,configuration", threads=threads)
