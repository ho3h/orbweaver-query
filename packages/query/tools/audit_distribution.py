"""Inspect a built wheel/sdist before publication; writes an optional JSON receipt."""

import argparse
import hashlib
import json
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath


def audit(directory):
    wheels, sources = sorted(directory.glob('*.whl')), sorted(directory.glob('*.tar.gz'))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError('Use a directory containing exactly one wheel and one source archive')
    wheel, source = wheels[0], sources[0]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_name, = [n for n in names if n.endswith('.dist-info/METADATA')]
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
        if metadata['Name'] != 'orbweaver-query':
            raise ValueError('Unexpected package name')
        required = ('orbweaver_query/__init__.py', 'orbweaver_query/assets/wn18rr-path71.npz',
                    'orbweaver_query/assets/THIRD_PARTY_NOTICES.md')
        if not all(n in names for n in required) or not any(n.endswith('/LICENSE') for n in names):
            raise ValueError('Missing runtime, model or license notices')
        if any(not n.startswith(('orbweaver_query/', 'orbweaver_query-')) for n in names):
            raise ValueError('Unexpected files outside runtime and wheel metadata')
        core = [r for r in metadata.get_all('Requires-Dist', []) if 'extra ==' not in r]
        if core != ['numpy>=1.26']:
            raise ValueError(f'Unexpected core dependencies: {core}')
    with tarfile.open(source) as archive:
        members = archive.getmembers()
        relative = []
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not member.isfile():
                raise ValueError(f'Unexpected archive member: {member.name}')
            relative.append(str(PurePosixPath(*path.parts[1:])))
        forbidden = {'__pycache__', '.venv', 'runs', 'dist', '.pytest_cache', '.ruff_cache'}
        if any(forbidden.intersection(PurePosixPath(n).parts) or n.endswith('.pyc') for n in relative):
            raise ValueError('Development environment or bytecode leaked into sdist')
        inputs = [n for n in relative if n.startswith('benchmarks/results/')]
        if len(inputs) != 9 or any(not n.endswith(('.npz', '-queries.json.gz')) for n in inputs):
            raise ValueError('Expected only the nine small demonstration inputs in sdist results')
        for required in ('LICENSE', 'pyproject.toml', 'tests/test_target_execution.py',
                         'benchmarks/mac_release.py', 'benchmarks/MAC_RELEASE_PROTOCOL.md',
                         'benchmarks/v1/targeted.py', 'benchmarks/cache_reference.py'):
            if required not in relative:
                raise ValueError(f'Missing reproduction member: {required}')
        for required in ('examples/movie_recommendations.py', 'examples/score_csv.py',
                         'BRING_YOUR_OWN_GRAPH.md', 'benchmarks/movie_workflow.py'):
            if required not in relative:
                raise ValueError(f'Missing public-preview example: {required}')
    return {'package': metadata['Name'], 'version': metadata['Version'],
            'core_dependencies': core, 'wheel_members': len(names), 'sdist_members': len(members),
            'artifacts': {p.name: {'bytes': p.stat().st_size,
                                  'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                          for p in (wheel, source)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = json.dumps(audit(args.directory), indent=2, sort_keys=True)+'\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(report)
    print(report, end='')


if __name__ == '__main__':
    main()
