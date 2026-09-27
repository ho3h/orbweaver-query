"""Stdlib audit of archived outputs, identities, samples and aggregate calculation."""
import hashlib
import json
import math
import statistics
import tarfile
from pathlib import Path

folder=Path(__file__).resolve().parent
receipt=json.loads((folder/'ARCHIVE.json').read_text())
archive=folder/'evidence.tar.gz'
assert hashlib.sha256(archive.read_bytes()).hexdigest()==receipt['archive_sha256']
assert hashlib.sha256((folder/'results.json').read_bytes()).hexdigest()==receipt['results_sha256']
summary=json.loads((folder/'results.json').read_text())
with tarfile.open(archive) as tar:
    assert len(tar.getmembers())==receipt['files']
    manifest=json.load(tar.extractfile('manifest.json'))
    assert hashlib.sha256(tar.extractfile('manifest.json').read()).hexdigest()==receipt['manifest_sha256']
    for name, digest in manifest['files'].items():
        assert hashlib.sha256(tar.extractfile(name).read()).hexdigest()==digest, name
    records=[]
    for index, job in enumerate(manifest['jobs']):
        name=f'workers/{index:04d}.json'
        raw=tar.extractfile(name).read()
        assert hashlib.sha256(raw).hexdigest()==summary['workers_sha256'][f'{index:04d}.json']
        record=json.loads(raw)
        assert record['job']==job and record['serialization_included'] is True
        samples=record['samples_seconds']
        assert len(samples)==3 and all(math.isfinite(x) and x>0 for x in samples)
        assert statistics.median(samples)==record['median_seconds']
        assert hashlib.sha256(json.dumps(record['output'],sort_keys=True,allow_nan=False).encode()).hexdigest()==record['output_sha256']
        records.append(record)
ratios=[]
max_error=0.0
for condition in summary['outcomes']:
    selected=[r for r in records if all(r['job'][k]==condition[k] for k in ('graph','workload'))]
    assert len(selected)==27
    reference=next(r['output'] for r in selected if r['job']['arm']=='full')
    for record in selected:
        assert len(record['output'])==len(reference)
        for x,y in zip(reference,record['output']):
            a,b=dict(x),dict(y)
            pa,pb=dict(a.pop('prediction')),dict(b.pop('prediction'))
            va,vb=pa.pop('score'),pb.pop('score')
            assert a==b and pa==pb
            if va is None or vb is None:
                assert va==vb
            else:
                assert math.isclose(va,vb,rel_tol=1e-12,abs_tol=1e-12)
                max_error=max(max_error,abs(va-vb))
    medians={}
    for arm in condition['arms']:
        rows=[r for r in selected if r['job']['arm']==arm]
        assert {r['job']['replicate'] for r in rows}=={0,1,2}
        medians[arm]=statistics.median(r['median_seconds'] for r in rows)*1000
        assert medians[arm]==condition['arms'][arm]['ms']
    fastest=min(medians[a] for a in ('full','lru64k','lru16m','lru_guarded','full_guarded'))
    ratio=fastest/medians['targeted']; ratios.append(ratio)
    assert ratio==condition['strongest_ondemand_speedup']
assert len(records)==648 and len(ratios)==24
aggregate=math.exp(statistics.mean(math.log(v) for v in ratios))
assert math.isclose(aggregate,summary['geometric_mean_ondemand_speedup'],rel_tol=1e-15)
assert max_error==summary['max_absolute_error']
print(json.dumps({'verified':True,'workers':len(records),'conditions':len(ratios),
                  'max_absolute_error':max_error,'geometric_mean_ondemand_speedup':aggregate},indent=2))
