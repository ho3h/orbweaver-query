"""Verify and restore retained native structural correctness evidence."""

import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path


def safe(root, name):
    path = Path(name)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Unsafe archive path')
    return root/path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(archive):
    receipt = json.loads((archive/'ARCHIVE.json').read_text())
    for name, expected in receipt['files'].items():
        if digest(safe(archive, name).read_bytes()) != expected:
            raise ValueError(f'Archive checksum mismatch: {name}')
    manifest_bytes = (archive/'manifest.json').read_bytes()
    if digest(manifest_bytes) != receipt['runtime_manifest_sha256']:
        raise ValueError('Runtime manifest differs')
    manifest = json.loads(manifest_bytes)
    for name, expected in manifest['files'].items():
        if digest(safe(archive, name).read_bytes()) != expected:
            raise ValueError(f'Frozen source/input differs: {name}')
    raw = gzip.decompress((archive/'verification.json.gz').read_bytes())
    if digest(raw) != receipt['verification_raw_sha256']:
        raise ValueError('Raw verification bytes differ')
    report = json.loads(raw)
    if report['manifest_sha256'] != receipt['runtime_manifest_sha256']:
        raise ValueError('Verification belongs to another run')
    actual = [(r['dataset'], r['workload'], r['filtered'], r['arm']) for r in report['records']]
    expected = {(d, w, f, a) for d in ('collaboration', 'friendship', 'communication')
                for w in manifest['workloads'] for f in (False, True) for a in manifest['arms']}
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError('Missing or repeated verification conditions')
    if report['timing_claim'] or receipt['timing_claim']:
        raise ValueError('This archive contains correctness evidence only')
    if len(actual) != receipt['verified_conditions'] or report['max_absolute_error'] != receipt['max_absolute_error']:
        raise ValueError('Verification summary differs')
    return {'verified_raw_conditions': len(actual), 'max_absolute_error': report['max_absolute_error']}


def restore(archive, output):
    verify(archive)
    manifest = json.loads((archive/'manifest.json').read_text())
    output.mkdir(parents=True, exist_ok=False)
    for name in (*manifest['files'], 'manifest.json'):
        target = safe(output, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe(archive, name), target)
    return str(output/'structural_neo4j.py')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('verify', 'restore'))
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.archive) if args.command == 'verify' else restore(args.archive, args.output)))
