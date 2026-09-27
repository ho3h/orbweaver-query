"""Verify retained resource evidence; optionally restore without running it."""

import argparse
import json
from pathlib import Path

from archive_support import digest, members, read, relative


def verify(root, output=None):
    receipt = read(root/'ARCHIVE.json')
    if receipt['format'] != 'orbweaver-gds-memory-diagnostic-archive-v1':
        raise ValueError('Unexpected archive format')
    files = dict(members(root))
    manifest = json.loads(files['manifest.json'])
    for name, expected in manifest['files'].items():
        if digest(files[name]) != expected:
            raise ValueError('Retained evidence checksum differs')
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
        for name, data in files.items():
            target = output/relative(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return {'verified_files': len(files), 'manifest_sha256': digest(files['manifest.json']),
            'scope': 'byte integrity; resource/output audit is a separate command'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(Path(__file__).resolve().parent, args.output), indent=2))
