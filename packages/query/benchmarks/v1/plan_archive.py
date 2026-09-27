"""Retain exact composed-plan worker bytes in a compact, replayable archive."""

import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path

AUXILIARY = ('analysis-plan.json', 'plan_comparison.py', 'comparison.json', 'analysis.json',
             'ANALYSIS_RECEIPT.json', 'structural_analysis.py', 'graph_pipeline_analysis.py')


def read(path):
    return json.loads(path.read_text())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def target(root, name):
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Unsafe archive path')
    return root/relative


def verify_inputs(root):
    manifest = read(root/'manifest.json')
    for name, digest in manifest['files'].items():
        if sha(target(root,name).read_bytes()) != digest:
            raise ValueError(f'Frozen input changed: {name}')
    return manifest


def pack(run, archive):
    manifest = verify_inputs(run)
    report = read(run/'results.json')
    failures = report.get('failed_workers', 0)
    if (not report['numerical_parity']
            or report['verified_workers'] + failures != len(manifest['jobs'])
            or (failures and report.get('parity_scope') != 'completed workers only')):
        raise ValueError('Campaign is not verified and complete')
    if report['manifest_sha256'] != sha((run/'manifest.json').read_bytes()):
        raise ValueError('Summary belongs to another frozen campaign')
    if len(list((run/'workers').glob('*-error.json'))) != failures:
        raise ValueError('Failed worker count differs from the report')
    archive.mkdir(parents=True,exist_ok=False)
    extras = tuple(name for name in AUXILIARY if (run/name).exists())
    for name in (*manifest['files'],'manifest.json','results.json',*extras):
        path = target(archive,name)
        path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(target(run,name),path)
    with gzip.open(archive/'workers.jsonl.gz','wt',encoding='utf-8') as stream:
        for index, job in enumerate(manifest['jobs']):
            candidates = (f'{index:04d}.json', f'{index:04d}-error.json')
            found = [n for n in candidates if (run/'workers'/n).exists()]
            if len(found) != 1:
                raise ValueError('Expected exactly one terminal worker record')
            name = found[0]
            raw = (run/'workers'/name).read_text()
            if json.loads(raw)['job'] != job:
                raise ValueError('Worker does not match its frozen job')
            stream.write(json.dumps({'name':name,'sha256':sha(raw.encode()),'raw':raw})+'\n')
    files = {str(p.relative_to(archive)):sha(p.read_bytes()) for p in sorted(archive.rglob('*')) if p.is_file()}
    with (archive/'ARCHIVE.json').open('x') as stream:
        json.dump({'format':'orbweaver-plan-archive-v1','workers':len(manifest['jobs']),'files':files},
                   stream,indent=2,sort_keys=True)
        stream.write('\n')
    return verify(archive)


def worker_records(archive):
    manifest = read(archive/'manifest.json')
    count = 0
    with gzip.open(archive/'workers.jsonl.gz','rt',encoding='utf-8') as stream:
        for index,line in enumerate(stream):
            value = json.loads(line)
            if (value['name'] not in (f'{index:04d}.json', f'{index:04d}-error.json')
                    or sha(value['raw'].encode()) != value['sha256']):
                raise ValueError('Corrupt archived worker')
            if json.loads(value['raw'])['job'] != manifest['jobs'][index]:
                raise ValueError('Archived worker differs from its job')
            count += 1
            yield value
    if count != len(manifest['jobs']):
        raise ValueError('Incomplete worker archive')


def verify(archive):
    metadata = read(archive/'ARCHIVE.json')
    for name,digest in metadata['files'].items():
        if sha(target(archive,name).read_bytes()) != digest:
            raise ValueError(f'Archive checksum mismatch: {name}')
    manifest = verify_inputs(archive)
    report = read(archive/'results.json')
    if (report['manifest_sha256'] != sha((archive/'manifest.json').read_bytes())
            or report['verified_workers'] + report.get('failed_workers', 0) != len(manifest['jobs'])
            or not report['numerical_parity']
            or (report.get('failed_workers', 0) and report.get('parity_scope') != 'completed workers only')):
        raise ValueError('Archive summary does not describe this verified campaign')
    if (archive/'analysis-plan.json').exists():
        declaration = read(archive/'analysis-plan.json')
        if (declaration['runtime_manifest_sha256'] != sha((archive/'manifest.json').read_bytes())
                or declaration['script_sha256'] != sha(target(archive,declaration['script']).read_bytes())):
            raise ValueError('Analysis declaration differs from retained inputs/script')
    if (archive/'ANALYSIS_RECEIPT.json').exists():
        analysis = read(archive/'ANALYSIS_RECEIPT.json')
        if analysis['runtime_manifest_sha256'] != sha((archive/'manifest.json').read_bytes()):
            raise ValueError('Analysis belongs to another runtime campaign')
        for name,digest in analysis['files'].items():
            if sha(target(archive,name).read_bytes()) != digest:
                raise ValueError('Post-collection analysis checksum differs')
    count = failures = 0
    for record in worker_records(archive):
        count += 1
        failures += record['name'].endswith('-error.json')
    if failures != report.get('failed_workers', 0):
        raise ValueError('Archived failure count differs from the summary')
    if count != metadata['workers']:
        raise ValueError('Worker count differs from archive metadata')
    return {'verified_worker_bytes':count, 'successful_workers':count-failures,
            'failed_workers':failures}


def restore(archive, output, with_workers=False):
    verify(archive)
    manifest = read(archive/'manifest.json')
    output.mkdir(parents=True,exist_ok=False)
    indexed = read(archive/'ARCHIVE.json')['files']
    if (archive/'ANALYSIS_RECEIPT.json').exists():
        indexed = {**indexed, **read(archive/'ANALYSIS_RECEIPT.json')['files'], 'ANALYSIS_RECEIPT.json': None}
    extras = tuple(name for name in AUXILIARY if name in indexed)
    for name in (*manifest['files'],'manifest.json',*extras):
        path = target(output,name)
        path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(target(archive,name),path)
    if with_workers:
        (output/'workers').mkdir()
        for record in worker_records(archive):
            target(output/'workers',record['name']).write_text(record['raw'])
    runner = next(name for name in ('plan_runtime.py', 'structural_neo4j.py', 'graph_pipeline.py')
                  if (output/name).exists())
    return str(output/runner)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('pack','verify','restore'))
    parser.add_argument('archive',type=Path)
    parser.add_argument('--run',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--with-workers',action='store_true')
    args = parser.parse_args()
    if args.command=='pack':
        result = pack(args.run,args.archive)
    elif args.command=='verify':
        result = verify(args.archive)
    else:
        result = restore(args.archive,args.output,args.with_workers)
    print(json.dumps(result))
