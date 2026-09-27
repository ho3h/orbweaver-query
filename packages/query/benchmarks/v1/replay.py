"""Restore a frozen development benchmark for exact replay in a fresh directory."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def restore(archive, run):
    manifest = json.loads((archive/'manifest.json').read_text())
    inputs = archive.parent/'inputs'
    run.mkdir(parents=True, exist_ok=False)
    for name, digest in manifest['files'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe manifest path')
        source = archive/relative
        compressed = archive/(str(relative) + '.gz')
        if not source.exists() and relative.suffix == '.npz' and len(relative.parts) == 1:
            source = inputs/relative.name
        payload = source.read_bytes() if source.exists() else gzip.decompress(compressed.read_bytes())
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError(f'Archive checksum mismatch: {name}')
        target = run/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    (run/'manifest.json').write_bytes((archive/'manifest.json').read_bytes())
    return run/'targeted.py'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    print(restore(args.archive.resolve(), args.run.resolve()))
