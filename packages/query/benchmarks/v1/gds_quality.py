"""Frozen outer-held-out link ranking comparison with native GDS and structural controls."""

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

DATA = {
    'collaboration': ('ca-GrQc.txt.gz', 'a254442cdf5d684712578b630c2e0d7543518ab154ef2341cabb607572ce7230'),
    'friendship': ('facebook_combined.txt.gz', '125e84db872eeba443d270c70315c256b0af43a502fcfe51f50621166ad035d7'),
    'communication': ('email-Eu-core.txt.gz', '4b47acdb80197b085fe63c819c357ae488131ee904ed93d1b219a68b0f9e245f'),
}
GDS_CONFIGS = {
    'baseline': {'dimension':64,'rich':False,'negative_ratio':1.0},
    'wide': {'dimension':256,'rich':False,'negative_ratio':1.0},
    'rich': {'dimension':256,'rich':True,'negative_ratio':1.0},
    'negatives16': {'dimension':256,'rich':True,'negative_ratio':16.0},
}
THREADS = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS',
           'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'BLIS_NUM_THREADS')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def freeze(run, data_dir, gds_config='baseline', reuse=None, transaction_timeout_seconds=900):
    import numpy as np

    from orbweaver_query import GraphSnapshot

    run.mkdir(parents=True, exist_ok=False)
    package = Path(__file__).resolve().parents[2]
    shutil.copytree(package/'src/orbweaver_query', run/'source/orbweaver_query',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copyfile(package/'tools/disposable_neo4j.py', run/'disposable_neo4j.py')
    shutil.copyfile(__file__, run/'gds_quality.py')
    shutil.copyfile(Path(__file__).with_name('GDS_COMPARISON_PROTOCOL.md'), run/'PROTOCOL.md')
    inventory = {}
    for name, (filename, checksum) in DATA.items():
        path = data_dir/filename
        if sha(path) != checksum:
            raise ValueError(f'Unexpected source bytes for {name}')
        original = [tuple(map(int, line.split())) for line in gzip.decompress(path.read_bytes()).decode().splitlines()
                    if line and not line.startswith('#')]
        nodes = sorted({n for pair in original for n in pair})
        index = {n: i for i, n in enumerate(nodes)}
        pairs = np.array(sorted({(index[min(a,b)],index[max(a,b)]) for a,b in original if a != b}),np.int64)
        roles = np.searchsorted([.8,.9],np.random.default_rng(20260926).random(len(pairs)))
        outer, dev, confirmation = [pairs[roles==r] for r in range(3)]
        inner = np.searchsorted([.56,.8],np.random.default_rng(71).random(len(outer)))
        evidence, fitting = outer[inner==0], outer[inner==1]
        def undirected(selected):
            return np.vstack((np.column_stack((selected[:,0],np.zeros(len(selected),np.int64),selected[:,1])),
                              np.column_stack((selected[:,1],np.zeros(len(selected),np.int64),selected[:,0]))))
        for suffix, selected in (('outer',outer),('evidence',evidence)):
            graph = GraphSnapshot(undirected(selected), node_ids=list(map(str,nodes)),relations=('LINK',))
            graph.save(run/f'{name}-{suffix}.npz')
        np.savez_compressed(run/f'{name}-fit.npz', triples=undirected(fitting))
        sources = np.sort(np.random.default_rng(20260927).choice(len(nodes),64,replace=False))
        positives = np.array([(int(h),int(t)) for a,b in dev for h,t in ((a,b),(b,a)) if h in set(sources.tolist())],np.int64)
        np.savez_compressed(run/f'{name}-development.npz', sources=sources, positives=positives)
        np.savez_compressed(run/f'{name}-confirmation-sealed.npz', pairs=confirmation)
        inventory[name] = {'source':filename,'source_sha256':checksum,'nodes':len(nodes),'pairs':len(pairs),
            'outer_train':len(outer),'development':len(dev),'confirmation':len(confirmation),
            'inner_evidence':len(evidence),'inner_fitting':len(fitting),'inner_unused':int((inner==2).sum()),
            'evaluation_sources':len(sources),'evaluation_positive_queries':len(positives),
            'removed_self_rows':sum(a==b for a,b in original)}
    if reuse is not None:
        checked(reuse)
        for name in DATA:
            if sha(run/f'{name}-outer.npz') != sha(reuse/f'{name}-outer.npz') or sha(run/f'{name}-development.npz') != sha(reuse/f'{name}-development.npz'):
                raise ValueError('Reused baseline has different evidence or evaluation queries')
            shutil.copyfile(reuse/f'{name}-results.json',run/f'{name}-reused-baseline.json')
    files = {str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()}
    write(run/'manifest.json', {'format':'gds-link-ranking-development-v1','files':files,'inventory':inventory,
        'seeds':{'outer':20260926,'sources':20260927,'fit':71},'gds_version':'2026.09.0',
        'confirmation_evaluation_permitted':False,'primary_metric':'recall16','threads':1,
        'gds_config':GDS_CONFIGS[gds_config],'gds_config_name':gds_config,'reused_baselines':reuse is not None,
        'transaction_timeout_seconds':transaction_timeout_seconds})
    return inventory


def checked(run):
    manifest=read(run/'manifest.json')
    for name, expected in manifest['files'].items():
        if sha(run/name)!=expected:
            raise ValueError(f'Frozen file changed: {name}')
    return manifest


def evaluate(scores, candidates, sources, positives):
    import numpy as np
    lookup={int(h):i for i,h in enumerate(sources)}
    rows=[]
    for h,t in positives:
        h,t=int(h),int(t)
        i=lookup[h]
        assert candidates[i,t]
        score=scores[i,t]
        values=scores[i,candidates[i]]
        finite=np.isfinite(values)
        if not np.isfinite(score):
            rank, recall16, recall64 = None, 0., 0.
        else:
            greater=int(np.sum(values[finite]>score))
            tied=int(np.sum(values[finite]==score))
            rank=1+greater+.5*(tied-1)
            recall16=float(np.clip((16-greater)/tied,0,1))
            recall64=float(np.clip((64-greater)/tied,0,1))
        rows.append({'head':h,'target':t,'supported':bool(np.isfinite(score)),
                     'rank':rank,'recall16':recall16,'recall64':recall64,
                     'reciprocal_rank':0. if rank is None else 1/rank})
    metrics={key:float(np.mean([r[key] for r in rows]))
             for key in ('recall16','recall64','reciprocal_rank','supported')}
    return {'metrics':metrics,'positive_queries':len(rows),'outcomes':rows}


def worker(run, dataset, neo4j_home, java, gds_jar):
    sys.path.insert(0,str(run/'source'))
    sys.path.insert(0,str(run))
    import numpy as np
    from disposable_neo4j import disposable_database, native_runtime_identity
    from neo4j import GraphDatabase
    from scipy import sparse
    from sklearn.linear_model import LogisticRegression
    from threadpoolctl import threadpool_limits

    from orbweaver_query import ExplicitPathModel, GraphSnapshot, LinkQuery, Session
    from orbweaver_query.datasets import positives_by_query
    from orbweaver_query.training import prepare_examples

    manifest=checked(run)
    runtime_architecture=native_runtime_identity(java)
    graph=GraphSnapshot.load(run/f'{dataset}-outer.npz')
    evidence=GraphSnapshot.load(run/f'{dataset}-evidence.npz')
    with np.load(run/f'{dataset}-development.npz',allow_pickle=False) as file:
        sources,positives=file['sources'],file['positives']
    with np.load(run/f'{dataset}-fit.npz',allow_pickle=False) as file:
        fitting=file['triples']
    # Confirmation is intentionally never loaded by this evaluator.
    n=len(graph.node_ids)
    candidates=np.ones((len(sources),n),dtype=bool)
    for i,h in enumerate(sources):
        candidates[i,int(h)]=False
        candidates[i,graph.neighbors(int(h))]=False
    report={'manifest_sha256':sha(run/'manifest.json'),'dataset':dataset,
            'runtime_architecture':runtime_architecture,
            'candidate_count':int(candidates.sum()),'arms':{},'stages':[]}
    def log(stage, seconds):
        report['stages'].append({'stage':stage,'seconds':seconds})
        print(stage,round(seconds,3),flush=True)

    if manifest.get('reused_baselines'):
        prior=read(run/f'{dataset}-reused-baseline.json')
        report['arms']={k:v for k,v in prior['arms'].items() if k!='gds'}
        report['reused_baseline_sha256']=sha(run/f'{dataset}-reused-baseline.json')
    else:
        began=time.perf_counter()
        examples,x,audit=prepare_examples(evidence,fitting,positives_by_query(graph.triples()),seed=71)
        with threadpool_limits(limits=1):
            estimator=LogisticRegression(C=10,solver='liblinear',max_iter=2000,tol=1e-6,random_state=0,fit_intercept=False)
            estimator.fit(x,examples['labels'],sample_weight=1/np.bincount(examples['groups'])[examples['groups']])
        model=ExplicitPathModel(estimator.coef_,relations=graph.relations)
        model.save(run/f'{dataset}-path-model.npz')
        log('orbweaver_fit',time.perf_counter()-began)
        began=time.perf_counter()
        scores=np.full(candidates.shape,np.nan)
        results=Session(graph,model).run([LinkQuery(graph.node_ids[int(h)],'LINK') for h in sources])
        for i,row in enumerate(results.rows):
            scores[i,[graph.node_index(t) for t in row.candidate_ids]]=row.scores
        log('orbweaver_predict',time.perf_counter()-began)
        report['arms']['path']={**evaluate(scores,candidates,sources,positives),'fit_audit':audit,
                                'model_id':model.model_id,'training_parameters':estimator.get_params()}
        np.savez_compressed(run/f'{dataset}-path-scores.npz',scores=scores)

        adjacency=sparse.csr_matrix((np.ones(len(graph.indices)),graph.indices,graph.indptr),shape=(n,n))
        for name,weights in (('common_neighbors',np.ones(n)),
                             ('adamic_adar',1/np.log(np.maximum(graph.degree,2))),
                             ('resource_allocation',1/np.maximum(graph.degree,1))):
            began=time.perf_counter()
            scores=(adjacency[sources].multiply(weights)@adjacency).toarray()
            log(name+'_predict',time.perf_counter()-began)
            report['arms'][name]=evaluate(scores,candidates,sources,positives)
            np.savez_compressed(run/f'{dataset}-{name}-scores.npz',scores=scores)

    gds_config=manifest.get('gds_config',GDS_CONFIGS['baseline'])
    report['gds_config']=gds_config
    begin_database=time.perf_counter()
    with (disposable_database(neo4j_home,java,gds_jar=gds_jar,heap_megabytes=8192,
                              entrypoint='org.neo4j.server.Neo4jCommunity',
                              transaction_timeout=f"{manifest.get('transaction_timeout_seconds',900)}s") as uri,
          GraphDatabase.driver(uri,auth=None) as driver):
        def query(cypher,**params):
            return [r.data() for r in driver.execute_query(cypher,parameters_=params)[0]]
        version=query('RETURN gds.version() AS version')[0]['version']
        if version!=manifest['gds_version']:
            raise ValueError('GDS version differs from protocol')
        log('database_start',time.perf_counter()-begin_database)
        begin=time.perf_counter()
        query('CREATE CONSTRAINT external_id FOR (n:Node) REQUIRE n.externalId IS UNIQUE')
        query('UNWIND range(0,$last) AS id CREATE (:Node {externalId:id})',last=n-1)
        query('UNWIND $ids AS id MATCH (n:Node {externalId:id}) SET n:Query',ids=sources.tolist())
        triples=graph.triples()
        pairs=triples[triples[:,0]<triples[:,2]][:,(0,2)]
        for offset in range(0,len(pairs),1000):
            query('UNWIND $pairs AS pair MATCH (a:Node {externalId:pair[0]}),'
                  '(b:Node {externalId:pair[1]}) CREATE (a)-[:LINK]->(b)',pairs=pairs[offset:offset+1000].tolist())
        query("CALL gds.graph.project('graph', ['Node','Query'], {LINK:{orientation:'UNDIRECTED'}})")
        log('gds_import_projection',time.perf_counter()-begin)
        query("CALL gds.beta.pipeline.linkPrediction.create('pipe')")
        query("CALL gds.beta.pipeline.linkPrediction.addNodeProperty('pipe','fastRP',"
              "{mutateProperty:'embedding',embeddingDimension:$dimension,randomSeed:71,concurrency:1})",dimension=gds_config['dimension'])
        query("CALL gds.beta.pipeline.linkPrediction.addFeature('pipe','hadamard',{nodeProperties:['embedding']})")
        if gds_config['rich']:
            query("CALL gds.beta.pipeline.linkPrediction.addNodeProperty('pipe','degree',{mutateProperty:'degree',concurrency:1})")
            query("CALL gds.beta.pipeline.linkPrediction.addFeature('pipe','hadamard',{nodeProperties:['degree']})")
            query("CALL gds.beta.pipeline.linkPrediction.addFeature('pipe','cosine',{nodeProperties:['embedding']})")
        query("CALL gds.beta.pipeline.linkPrediction.configureSplit('pipe',"
              "{testFraction:0.2,trainFraction:0.3,validationFolds:3,negativeSamplingRatio:$ratio})",ratio=gds_config['negative_ratio'])
        query("CALL gds.beta.pipeline.linkPrediction.addLogisticRegression('pipe',{penalty:0.1,maxEpochs:200})")
        query("CALL gds.beta.pipeline.linkPrediction.addRandomForest('pipe',{numberOfDecisionTrees:50,maxDepth:10})")
        begin=time.perf_counter()
        fitted=query("CALL gds.beta.pipeline.linkPrediction.train('graph',"
              "{pipeline:'pipe',modelName:'model',targetRelationshipType:'LINK',sourceNodeLabel:'Node',"
              "targetNodeLabel:'Node',metrics:['AUCPR'],randomSeed:71,concurrency:1}) "
              "YIELD modelInfo,modelSelectionStats,trainMillis RETURN modelInfo,modelSelectionStats,trainMillis")
        log('gds_fit',time.perf_counter()-begin)
        scores=np.full(candidates.shape,np.nan)
        lookup={int(h):i for i,h in enumerate(sources)}
        begin=time.perf_counter()
        count=0
        with driver.session() as connection:
            cursor=connection.run("CALL gds.beta.pipeline.linkPrediction.predict.stream('graph',"
                "{modelName:'model',sourceNodeLabel:'Query',targetNodeLabel:'Node',sampleRate:1.0,"
                "topN:$top,threshold:0.0,concurrency:1}) YIELD node1,node2,probability "
                "RETURN gds.util.asNode(node1).externalId AS head,gds.util.asNode(node2).externalId AS target,probability",
                top=int(candidates.sum()))
            for row in cursor:
                h,t,value=int(row['head']),int(row['target']),float(row['probability'])
                for a,b in ((h,t),(t,h)):
                    if a in lookup:
                        i=lookup[a]
                        if not candidates[i,b]:
                            raise ValueError('GDS predicted outside the declared candidate domain')
                        if np.isfinite(scores[i,b]) and scores[i,b]!=value:
                            raise ValueError('Conflicting symmetric predictions')
                        scores[i,b]=value
                count+=1
        log('gds_predict_stream_all_scores',time.perf_counter()-begin)
        missing=int(np.sum(candidates & ~np.isfinite(scores)))
        report['gds_candidate_coverage']={'requested':int(candidates.sum()),'streamed_pairs':count,'missing':missing}
        if missing:
            write(run/f'{dataset}-coverage-failure.json',report)
            raise ValueError(f'GDS did not return {missing} declared candidates')
        report['arms']['gds']={**evaluate(scores,candidates,sources,positives),'native_training':fitted}
        np.savez_compressed(run/f'{dataset}-gds-scores.npz',scores=scores)
    write(run/f'{dataset}-results.json',report)
    return {name:arm['metrics'] for name,arm in report['arms'].items()}


def execute(run,dataset,neo4j_home,java,gds_jar):
    checked(run)
    write(run/f'{dataset}-started.json',{'started':time.time(),'manifest_sha256':sha(run/'manifest.json'),
        'gds_jar_sha256':sha(gds_jar),'java':str(java),'neo4j_home':str(neo4j_home)})
    env={**os.environ,**{k:'1' for k in THREADS}}
    with (run/f'{dataset}-console.txt').open('x') as log:
        result=subprocess.run([sys.executable,str(run/'gds_quality.py'),'worker',str(run),'--dataset',dataset,
            '--neo4j-home',str(neo4j_home),'--java',str(java),'--gds-jar',str(gds_jar)],
            env=env,stdout=log,stderr=subprocess.STDOUT,check=False)
    if result.returncode:
        raise RuntimeError(f'Failed with {result.returncode}; see {run}/{dataset}-console.txt')
    return {k:v['metrics'] for k,v in read(run/f'{dataset}-results.json')['arms'].items()}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('freeze','execute','worker'))
    parser.add_argument('run',type=Path)
    parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--gds-config',choices=tuple(GDS_CONFIGS),default='baseline')
    parser.add_argument('--reuse-results',type=Path)
    parser.add_argument('--transaction-timeout-seconds',type=int,default=900)
    parser.add_argument('--dataset',choices=tuple(DATA),default='collaboration')
    for name in ('neo4j-home','java','gds-jar'):
        parser.add_argument('--'+name,type=Path)
    args=parser.parse_args()
    run=args.run.resolve()
    try:
        if args.command=='freeze':
            result=freeze(run,args.data_dir,args.gds_config,args.reuse_results,args.transaction_timeout_seconds)
        elif args.command=='execute':
            result=execute(run,args.dataset,args.neo4j_home,args.java,args.gds_jar)
        else:
            result=worker(run,args.dataset,args.neo4j_home,args.java,args.gds_jar)
        print(json.dumps(result,allow_nan=False),flush=True)
    except Exception:
        if args.command=='worker':
            write(run/f'{args.dataset}-error.json',{'traceback':traceback.format_exc()})
        raise
