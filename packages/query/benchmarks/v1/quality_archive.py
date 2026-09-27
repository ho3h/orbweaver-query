"""Archive, verify and restore the four frozen GDS development configurations."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

RUNS = ('gds-quality-development-v1', 'gds-tuning-wide-v1',
        'gds-tuning-rich-v1', 'gds-tuning-negatives16-v1')
DATASETS = ('collaboration', 'friendship', 'communication')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def safe_path(root, name):
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Unsafe manifest path')
    return root/relative


def verify_manifest(root, manifest):
    for name, expected in manifest['files'].items():
        if sha(safe_path(root, name)) != expected:
            raise ValueError(f'Checksum mismatch: {name}')


def summarize(root):
    output = {}
    for dataset in DATASETS:
        table, failures = {}, {}
        for run_name in RUNS:
            run = root/run_name
            manifest = read(run/'manifest.json')
            if not (run/f'{dataset}-results.json').exists():
                error = run/f'{dataset}-error.json'
                if not error.exists():
                    raise ValueError(f'Attempt is not terminal: {run_name}/{dataset}')
                failures['gds_'+manifest.get('gds_config_name','baseline')] = {
                    'error_sha256':sha(error),'run':run_name}
                continue
            report = read(run/f'{dataset}-results.json')
            if report['manifest_sha256'] != sha(run/'manifest.json'):
                raise ValueError('Result belongs to another frozen input')
            if report['gds_candidate_coverage']['missing'] != 0:
                raise ValueError('Incomplete candidate coverage')
            if run_name == RUNS[0]:
                table.update({k:v['metrics'] for k,v in report['arms'].items() if k != 'gds'})
            table['gds_'+manifest.get('gds_config_name','baseline')] = report['arms']['gds']['metrics']
        output[dataset] = {'positive_queries':read(root/RUNS[0]/f'{dataset}-results.json')['arms']['path']['positive_queries'],
            'metrics':table, 'failed_attempts':failures,
            'best_completed_gds':max((k for k in table if k.startswith('gds_')), key=lambda k:table[k]['recall16']),
            'best_orbweaver':max((k for k in table if not k.startswith('gds_')), key=lambda k:table[k]['recall16'])}
    return {'status':'development only; confirmation sealed; diagnostic costs not matched',
            'datasets':output}


def pack(runs, archive):
    # Verify completeness before creating the archive, including any failed files.
    for name in RUNS:
        verify_manifest(runs/name, read(runs/name/'manifest.json'))
    summary = summarize(runs)
    archive.mkdir(parents=True, exist_ok=False)
    for name in RUNS:
        shutil.copytree(runs/name, archive/name, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    write(archive/'summary.json', summary)
    files = {str(p.relative_to(archive)):sha(p) for p in sorted(archive.rglob('*')) if p.is_file()}
    write(archive/'ARCHIVE.json', {'format':'orbweaver-gds-development-archive-v1','files':files,
        'confirmation_contents_read':False, 'configurations':list(RUNS)})
    return summary


def verify(archive):
    verify_manifest(archive, read(archive/'ARCHIVE.json'))
    for name in RUNS:
        verify_manifest(archive/name, read(archive/name/'manifest.json'))
    assert read(archive/'summary.json') == summarize(archive)
    failures = sum(len(d['failed_attempts']) for d in summarize(archive)['datasets'].values())
    return {'verified_configurations':len(RUNS),'verified_results':len(RUNS)*len(DATASETS)-failures,
            'verified_failed_attempts':failures}


def restore(archive, configuration, output):
    verify(archive)
    run = archive/configuration
    manifest = read(run/'manifest.json')
    output.mkdir(parents=True, exist_ok=False)
    for name in manifest['files']:
        target = safe_path(output, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe_path(run, name), target)
    shutil.copyfile(run/'manifest.json', output/'manifest.json')
    verify_manifest(output, manifest)
    return str(output/'gds_quality.py')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('pack','verify','restore'))
    parser.add_argument('archive', type=Path)
    parser.add_argument('--runs', type=Path)
    parser.add_argument('--configuration', choices=RUNS, default=RUNS[0])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'pack':
        result = pack(args.runs, args.archive)
    elif args.command == 'verify':
        result = verify(args.archive)
    else:
        result = restore(args.archive, args.configuration, args.output)
    print(json.dumps(result, sort_keys=True))
