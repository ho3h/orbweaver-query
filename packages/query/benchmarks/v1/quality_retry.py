"""Retain a completed GDS time-budget retry without replacing its failed attempt."""

import argparse
import copy
import json
import shutil
from pathlib import Path

import quality_archive


def summarize(previous, retry):
    quality_archive.verify(previous)
    manifest = quality_archive.read(retry/'manifest.json')
    quality_archive.verify_manifest(retry, manifest)
    old = previous/'gds-tuning-negatives16-v1'
    original = quality_archive.read(old/'manifest.json')
    for key in ('gds_config', 'gds_config_name', 'seeds', 'threads', 'gds_version', 'inventory'):
        if manifest[key] != original[key]:
            raise ValueError(f'Retry changes model/data configuration: {key}')
    for dataset in quality_archive.DATASETS:
        for suffix in ('outer.npz', 'evidence.npz', 'fit.npz', 'development.npz', 'confirmation-sealed.npz'):
            name = f'{dataset}-{suffix}'
            if quality_archive.sha(retry/name) != quality_archive.sha(old/name):
                raise ValueError('Retry changes a frozen data split')
    report = quality_archive.read(retry/'friendship-results.json')
    if report['manifest_sha256'] != quality_archive.sha(retry/'manifest.json'):
        raise ValueError('Retry result belongs to another manifest')
    if report['gds_candidate_coverage']['missing']:
        raise ValueError('Retry has incomplete candidate coverage')
    summary = copy.deepcopy(quality_archive.summarize(previous))
    friendship = summary['datasets']['friendship']
    friendship['metrics']['gds_negatives16'] = report['arms']['gds']['metrics']
    friendship['best_completed_gds'] = max((k for k in friendship['metrics'] if k.startswith('gds_')),
                                         key=lambda k: friendship['metrics'][k]['recall16'])
    summary['status'] = 'Four GDS configurations completed on all three development graphs; confirmation sealed; diagnostic timing is not matched application cost'
    summary['retry'] = {'dataset': 'friendship', 'transaction_timeout_seconds': manifest['transaction_timeout_seconds'],
        'coverage': report['gds_candidate_coverage'], 'metrics': report['arms']['gds']['metrics'],
        'original_failed_attempt_retained': True, 'previous_archive_sha256': quality_archive.sha(previous/'ARCHIVE.json'),
        'retry_manifest_sha256': quality_archive.sha(retry/'manifest.json')}
    return summary


def pack(previous, retry, archive):
    summary = summarize(previous, retry)
    archive.mkdir(parents=True, exist_ok=False)
    shutil.copytree(retry, archive/'run', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    quality_archive.write(archive/'summary.json', summary)
    files = {str(p.relative_to(archive)): quality_archive.sha(p) for p in sorted(archive.rglob('*')) if p.is_file()}
    quality_archive.write(archive/'ARCHIVE.json', {'format': 'orbweaver-gds-retry-archive-v1', 'files': files,
        'previous_archive_sha256': quality_archive.sha(previous/'ARCHIVE.json'), 'confirmation_contents_read': False})
    return verify(previous, archive)


def verify(previous, archive):
    receipt = quality_archive.read(archive/'ARCHIVE.json')
    quality_archive.verify_manifest(archive, receipt)
    if quality_archive.sha(previous/'ARCHIVE.json') != receipt['previous_archive_sha256']:
        raise ValueError('Previous campaign archive differs')
    if quality_archive.read(archive/'summary.json') != summarize(previous, archive/'run'):
        raise ValueError('Retry summary differs')
    return {'verified_completed_retry': 'friendship', 'completed_configurations_per_graph': 4,
            'original_failed_attempts_preserved': 1}


def restore(previous, archive, output):
    verify(previous, archive)
    manifest = quality_archive.read(archive/'run/manifest.json')
    output.mkdir(parents=True, exist_ok=False)
    for name in (*manifest['files'], 'manifest.json'):
        target = quality_archive.safe_path(output, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(quality_archive.safe_path(archive/'run', name), target)
    return str(output/'gds_quality.py')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('pack', 'verify', 'restore'))
    parser.add_argument('archive', type=Path)
    parser.add_argument('--previous', type=Path, required=True)
    parser.add_argument('--retry', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'pack':
        result = pack(args.previous, args.retry, args.archive)
    elif args.command == 'verify':
        result = verify(args.previous, args.archive)
    else:
        result = restore(args.previous, args.archive, args.output)
    print(json.dumps(result))
