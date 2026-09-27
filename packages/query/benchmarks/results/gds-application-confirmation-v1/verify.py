"""Verify confirmation archive bytes; optionally restore without evaluating labels."""

import argparse
import json
from pathlib import Path

from archive_support import digest, members, read, relative


def verify(root, output=None):
    receipt = read(root/'ARCHIVE.json')
    if receipt['format'] != 'orbweaver-gds-confirmation-archive-v1':
        raise ValueError('Unexpected archive format')
    files = dict(members(root))
    manifest = json.loads(files['manifest.json'])
    for name, expected in manifest['files'].items():
        if digest(files[name]) != expected:
            raise ValueError('Retained confirmation input checksum differs')
    result = json.loads(files['results.json'])
    started = json.loads(files['EVALUATION_STARTED.json'])
    identity = digest(files['manifest.json'])
    if (result['manifest_sha256'] != identity or started['manifest_sha256'] != identity
            or result['confirmation_labels_parsed'] is not True
            or len(result['workers']) != 18 or 'error.json' in files):
        raise ValueError('Confirmation is incomplete or belongs to different inputs')
    for index, worker in enumerate(result['workers']):
        if (json.loads(files[f'workers/{index:04d}.json']) != worker
                or worker['frozen_prediction_identity'] != manifest['workers'][index]):
            raise ValueError('Retained worker or frozen prediction identity differs')
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
        for name, data in files.items():
            target = output/relative(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return {'verified_files': len(files), 'manifest_sha256': identity,
            'results_sha256': digest(files['results.json']), 'retained_workers': 18,
            'scope': 'Byte integrity and complete records; frozen numerical replay is separate'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(Path(__file__).resolve().parent, args.output), indent=2))
