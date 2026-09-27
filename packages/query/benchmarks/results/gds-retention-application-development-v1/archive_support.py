"""Retain complete or explicitly interrupted native recommendation runs (stdlib)."""

import argparse
import hashlib
import json
import math
import tarfile
from pathlib import Path, PurePosixPath

DATASETS = ('collaboration', 'friendship', 'communication')
REFERENCES = {'local': 'local', 'manual': 'local', 'native_ra_scalar': 'resource_allocation',
              'native_ra_fused': 'resource_allocation', 'native_aa_fused': 'adamic_adar',
              'gds': 'gds', 'cached_local': 'local', 'cached_gds': 'gds'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text())


def relative(name):
    path = PurePosixPath(name)
    if (not name or not path.parts or path.is_absolute() or '..' in path.parts or '\\' in name
            or path.as_posix() != name or any(':' in part for part in path.parts)):
        raise ValueError('Unsafe archive path')
    return Path(*path.parts)


def validate_manifest(manifest):
    expected_jobs = {(d, t, r) for d in DATASETS for t in (1, 4) for r in range(3)}
    actual_jobs = [(j['dataset'], j['threads'], j['replicate']) for j in manifest['jobs']]
    if (manifest['format'] != 'orbweaver-gds-application-v1'
            or len(actual_jobs) != 18 or set(actual_jobs) != expected_jobs
            or len(manifest['arms']) != len(REFERENCES) or set(manifest['arms']) != set(REFERENCES)
            or (manifest['k'], manifest['samples'], manifest['warmup'], manifest['ranking_precision']) != (16, 3, 1, 12)):
        raise ValueError('Manifest does not describe the declared application protocol')


def validate_worker(manifest, manifest_hash, index, worker):
    if (worker['job'] != manifest['jobs'][index]
            or worker['manifest_sha256'] != manifest_hash
            or worker['all_request_references_match'] is not True):
        raise ValueError('Worker belongs to a different campaign or failed validation')
    arms = [r['arm'] for r in worker['records']]
    if len(arms) != len(manifest['arms']) or set(arms) != set(manifest['arms']):
        raise ValueError('Worker is missing conditions')
    outputs = {}
    for record in worker['records']:
        samples = record['samples_seconds']
        if (record['quality_reference'] != REFERENCES[record['arm']]
                or len(samples) != manifest['samples']
                or any(type(s) not in (int, float) or not math.isfinite(s) or s <= 0 for s in samples)):
            raise ValueError('Invalid measurements or quality reference')
        reference = record['quality_reference']
        if reference in outputs and outputs[reference] != record['output']:
            raise ValueError('Equivalent request alternatives disagree')
        outputs[reference] = record['output']


def validate_records(manifest, results, workers):
    validate_manifest(manifest)
    if (results['format'] != 'orbweaver-gds-application-v1'
            or results['verified_workers'] != len(manifest['jobs'])
            or results['per_arm_reference_match'] is not True
            or len(workers) != len(manifest['jobs'])):
        raise ValueError('Campaign is incomplete or unverified')
    for index, worker in enumerate(workers):
        validate_worker(manifest, results['manifest_sha256'], index, worker)
    expected_outcomes = {(d, t, a) for d in DATASETS for t in (1, 4) for a in REFERENCES}
    actual_outcomes = [(o['dataset'], o['threads'], o['arm']) for o in results['outcomes']]
    if len(actual_outcomes) != len(expected_outcomes) or set(actual_outcomes) != expected_outcomes:
        raise ValueError('Missing or duplicate aggregate conditions')


def validate_interruption(manifest, manifest_hash, cancellation, names, workers, error):
    validate_manifest(manifest)
    stopped = cancellation['interrupted_worker']
    if (type(stopped) is not int or not 0 <= stopped < len(manifest['jobs'])
            or cancellation['completed_workers'] != list(range(stopped))
            or cancellation['unattempted_workers'] != list(range(stopped+1, len(manifest['jobs'])))
            or cancellation['aggregate_timing_claim'] is not False
            or cancellation['manifest_sha256'] != manifest_hash or len(workers) != stopped
            or 'results.json' in names):
        raise ValueError('Invalid interrupted campaign accounting')
    errors = {n for n in names if n.startswith('workers/') and n.endswith('-error.json')}
    if (errors != {f'workers/{stopped:04d}-error.json'} or error['job'] != manifest['jobs'][stopped]
            or error['intentional_interruption'] is not True or error['returncode'] != 130):
        raise ValueError('Missing or inconsistent interruption record')
    for i in cancellation['unattempted_workers']:
        if any(n.startswith(f'workers/{i:04d}') for n in names):
            raise ValueError('An unattempted worker has outputs')
    if f'workers/{stopped:04d}.json' in names:
        raise ValueError('Interrupted worker also has a successful terminal result')
    for i, worker in enumerate(workers):
        validate_worker(manifest, manifest_hash, i, worker)


def pack(run, archive, *, interrupted=False):
    manifest = read(run/'manifest.json')
    for name, checksum in manifest['files'].items():
        if digest((run/relative(name)).read_bytes()) != checksum:
            raise ValueError(f'Frozen input changed: {name}')
    if interrupted:
        cancellation = read(run/'CANCELLATION.json')
        stopped = cancellation['interrupted_worker']
        workers = [read(run/'workers'/f'{i:04d}.json') for i in cancellation['completed_workers']]
        validate_interruption(manifest, digest((run/'manifest.json').read_bytes()), cancellation,
            {p.relative_to(run).as_posix() for p in run.rglob('*') if p.is_file()}, workers,
            read(run/'workers'/f'{stopped:04d}-error.json'))
    else:
        results = read(run/'results.json')
        if results['manifest_sha256'] != digest((run/'manifest.json').read_bytes()):
            raise ValueError('Summary belongs to a different manifest')
        workers = [read(run/'workers'/f'{i:04d}.json') for i in range(len(manifest['jobs']))]
        validate_records(manifest, results, workers)
        if list((run/'workers').glob('*-error.json')):
            raise ValueError('A successful campaign cannot contain failed workers')
    for index, worker in enumerate(workers):
        if digest((run/'workers'/f'{index:04d}-scores.npz').read_bytes()) != worker['full_scores_sha256']:
            raise ValueError('Raw scores changed')
    paths = sorted(p for p in run.rglob('*') if p.is_file()
                   and '__pycache__' not in p.parts and p.suffix != '.pyc'
                   and p != run/'recorded-results.json')
    if any(p.is_symlink() for p in paths):
        raise ValueError('Cannot archive symlinks')
    archive.mkdir(parents=True, exist_ok=False)
    files = {p.relative_to(run).as_posix(): digest(p.read_bytes()) for p in paths}
    with tarfile.open(archive/'evidence.tar.gz', 'w:gz') as tar:
        for path in paths:
            tar.add(path, arcname=path.relative_to(run).as_posix(), recursive=False)
    receipt = {'format': ('orbweaver-gds-application-interrupted-archive-v1' if interrupted
                         else 'orbweaver-gds-application-archive-v1'), 'files': files,
               'archive_sha256': digest((archive/'evidence.tar.gz').read_bytes()),
               'verified_workers': len(workers), 'confirmation_contents_read': False}
    (archive/'ARCHIVE.json').write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n')
    return verify(archive)


def members(archive):
    receipt = read(archive/'ARCHIVE.json')
    if 'recorded-results.json' in receipt['files']:
        raise ValueError('Archive uses the reserved replay-summary path')
    if digest((archive/'evidence.tar.gz').read_bytes()) != receipt['archive_sha256']:
        raise ValueError('Compressed evidence checksum differs')
    seen, size = set(), 0
    with tarfile.open(archive/'evidence.tar.gz', 'r:gz') as tar:
        for member in tar:
            relative(member.name)
            size += member.size
            if (not member.isfile() or member.name in seen or member.size < 0
                    or size > 2*1024**3 or member.name not in receipt['files']):
                raise ValueError('Unexpected or unsafe archive member')
            data = tar.extractfile(member).read()
            if digest(data) != receipt['files'][member.name]:
                raise ValueError(f'Archive member checksum differs: {member.name}')
            seen.add(member.name)
            yield member.name, data
    if seen != set(receipt['files']):
        raise ValueError('Archive is missing indexed files')


def verify(archive):
    receipt = read(archive/'ARCHIVE.json')
    interrupted = receipt['format'] == 'orbweaver-gds-application-interrupted-archive-v1'
    count = receipt['verified_workers']
    if (type(count) is not int or not 0 <= count <= 18
            or (interrupted and count == 18)
            or (not interrupted and (receipt['format'] != 'orbweaver-gds-application-archive-v1'
                                     or count != 18))):
        raise ValueError('Unexpected archive format or worker count')
    # Keep only small JSON records in memory; raw score/graph arrays are hashed.
    retained = {name: data for name, data in members(archive)
                if name in ('manifest.json', 'results.json', 'CANCELLATION.json') or
                (name.startswith('workers/') and Path(name).name[:4].isdigit()
                 and name.endswith('.json'))}
    manifest = json.loads(retained['manifest.json'])
    for name, checksum in manifest['files'].items():
        if receipt['files'].get(name) != checksum:
            raise ValueError('Archived frozen input checksum mismatch')
    workers = [json.loads(retained[f'workers/{i:04d}.json']) for i in range(receipt['verified_workers'])]
    if interrupted:
        cancellation = json.loads(retained['CANCELLATION.json'])
        stopped = cancellation['interrupted_worker']
        validate_interruption(manifest, digest(retained['manifest.json']), cancellation,
            set(receipt['files']), workers, json.loads(retained[f'workers/{stopped:04d}-error.json']))
    else:
        results = json.loads(retained['results.json'])
        if results['manifest_sha256'] != digest(retained['manifest.json']):
            raise ValueError('Archived summary/manifest mismatch')
        validate_records(manifest, results, workers)
    for index, worker in enumerate(workers):
        if receipt['files'].get(f'workers/{index:04d}-scores.npz') != worker['full_scores_sha256']:
            raise ValueError('Archived raw score checksum mismatch')
    return {'verified_workers': len(workers), 'verified_files': len(receipt['files']),
            'status': 'interrupted; no aggregate timing claim' if interrupted else 'complete'}


def restore(archive, output):
    verify(archive)
    output.mkdir(parents=True, exist_ok=False)
    for name, data in members(archive):
        # Keep the original under a distinct name so summarize can rebuild it.
        target = output/relative('recorded-results.json' if name == 'results.json' else name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return str(output/'gds_application.py')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('pack', 'verify', 'restore'))
    parser.add_argument('archive', type=Path)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--interrupted', action='store_true')
    args = parser.parse_args()
    if args.command == 'pack':
        result = pack(args.run, args.archive, interrupted=args.interrupted)
    elif args.command == 'restore':
        result = restore(args.archive, args.output)
    else:
        result = verify(args.archive)
    print(json.dumps(result))
