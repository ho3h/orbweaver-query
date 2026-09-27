"""Retain GDS queue diagnostics, including fully attempted failed suites."""

import argparse
import json
import math
import statistics
import tarfile
from pathlib import Path

from gds_application_archive import digest, members, read, relative


def validate_case(files, retained):
    if {'worker-error.json', 'mismatch.json'} & files.keys():
        raise ValueError('A successful condition cannot contain a failure record')
    manifest, result = (json.loads(retained[name]) for name in ('manifest.json', 'results.json'))
    if (manifest['format'] not in ('orbweaver-gds-queue-diagnostic-v1', 'orbweaver-gds-queue-diagnostic-v2')
            or result['format'] != manifest['format']
            or result['manifest_sha256'] != digest(retained['manifest.json'])
            or result['full_scores_sha256'] != files.get('scores.npz')
            or result['all_outputs_match_complete_score_reference'] is not True
            or result['single_process_diagnostic'] is not True
            or result['confirmation_contents_read'] is not False
            or type(manifest['threads']) is not int or manifest['threads'] not in (1, 4)
            or (manifest['k'], manifest['warmup'], manifest['samples']) != (16, 1, 3)):
        raise ValueError('Result does not match the bounded protocol')
    if manifest['format'].endswith('-v1') and manifest['threads'] != 1:
        raise ValueError('Original diagnostic requires one thread')
    if manifest['format'].endswith('-v2') and (
            manifest['dataset'] not in ('collaboration', 'friendship', 'communication')
            or (result['dataset'], result['threads']) != (manifest['dataset'], manifest['threads'])):
        raise ValueError('Result graph/thread identity differs')
    for name, checksum in manifest['files'].items():
        if files.get(name) != checksum:
            raise ValueError('Frozen input changed')
    records = result['records']
    if (len(records) != 2 or {r['arm'] for r in records} != {'global', 'partitioned'}
            or records[0]['output'] != records[1]['output']):
        raise ValueError('Missing request control or inconsistent outputs')
    for record in records:
        samples = record['samples_seconds']
        if (len(samples) != 3 or len(record['counters']) != 3
                or any(type(s) not in (int, float) or not math.isfinite(s) or s <= 0 for s in samples)):
            raise ValueError('Invalid measurements')
    medians = {r['arm']: statistics.median(r['samples_seconds']) for r in records}
    return {'verified_files': len(files), 'median_seconds': medians,
            'global_over_partitioned': medians['global']/medians['partitioned'],
            'scope': 'byte integrity and result envelope; no database or score recomputation'}


def validate_suite_inputs(files, retained):
    suite = json.loads(retained['suite.json'])
    expected = {(d, t) for d in ('collaboration', 'friendship', 'communication') for t in (1, 4)}
    if (suite['format'] != 'orbweaver-gds-queue-suite-v1'
            or suite['confirmation_contents_read'] is not False
            or suite['one_process_per_condition'] is not True
            or len(suite['jobs']) != 6
            or {(j['dataset'], j['threads']) for j in suite['jobs']} != expected
            or any(type(j['threads']) is not int for j in suite['jobs'])
            or 'recorded-summary.json' in files):
        raise ValueError('Invalid six-condition suite')
    for name, checksum in suite['files'].items():
        if files.get(name) != checksum:
            raise ValueError('Frozen suite source changed')
    for job in suite['jobs']:
        prefix = f"{job['dataset']}-t{job['threads']}/"
        if job['directory']+'/' != prefix:
            raise ValueError('Invalid condition directory')
        manifest = json.loads(retained[prefix+'manifest.json'])
        if (digest(retained[prefix+'manifest.json']) != job['manifest_sha256']
                or manifest['format'] != 'orbweaver-gds-queue-diagnostic-v2'
                or (manifest['dataset'], manifest['threads']) != (job['dataset'], job['threads'])):
            raise ValueError('Condition identity differs')
        for name, checksum in manifest['files'].items():
            if files.get(prefix+name) != checksum:
                raise ValueError('Frozen condition input changed')
    return suite


def validate_suite(files, retained):
    suite = validate_suite_inputs(files, retained)
    summary = json.loads(retained['summary.json'])
    expected = {(j['dataset'], j['threads']) for j in suite['jobs']}
    if (summary['format'] != suite['format'] or summary['verified_conditions'] != 6
            or summary['suite_sha256'] != digest(retained['suite.json'])
            or summary['confirmation_contents_read'] is not False
            or len(summary['conditions']) != 6
            or {(c['dataset'], c['threads']) for c in summary['conditions']} != expected
            or 'ATTEMPT.json' in files
            or any(n.endswith(('/worker-error.json', '/mismatch.json')) for n in files)):
        raise ValueError('Incomplete, failed or invalid six-condition suite')
    for job in suite['jobs']:
        prefix = job['directory']+'/'
        payload = {n: retained[prefix+n] for n in ('manifest.json', 'results.json')}
        result = json.loads(payload['results.json'])
        checked = validate_case({n[len(prefix):]: h for n, h in files.items() if n.startswith(prefix)}, payload)
        case, = [c for c in summary['conditions']
                 if (c['dataset'], c['threads']) == (job['dataset'], job['threads'])]
        for key in ('median_seconds', 'global_over_partitioned'):
            if case[key] != checked[key]:
                raise ValueError('Summary timing does not match raw samples')
        if (case['raw_score_quality'] != result['raw_score_quality']['metrics']
                or case['deterministic_id_recall16'] != result['deterministic_id_recall16']
                or case['setup_seconds'] != result['setup_seconds']
                or case['selected_classifier'] != result['model_training'][0]['modelInfo']['bestParameters']
                or case['partitioned_counters'] != next(
                    r['counters'] for r in result['records'] if r['arm'] == 'partitioned')):
            raise ValueError('Summary quality, model, setup or counters differ')
    return {'verified_files': len(files), 'verified_conditions': 6,
            'scope': 'byte integrity and result envelopes; numerical replay remains separate'}


def validate_failed_suite(files, retained):
    suite = validate_suite_inputs(files, retained)
    attempt = json.loads(retained['ATTEMPT.json'])
    if (attempt['format'] != 'orbweaver-gds-queue-failed-attempt-v1'
            or attempt['suite_sha256'] != digest(retained['suite.json'])
            or attempt['aggregate_timing_claim'] is not False
            or attempt['confirmation_contents_read'] is not False
            or 'summary.json' in files):
        raise ValueError('Failed attempt cannot supply a successful suite summary')
    completed, failed = [], []
    for job in suite['jobs']:
        prefix = job['directory']+'/'
        has_result, has_error = (prefix+n in files for n in ('results.json', 'worker-error.json'))
        if has_result == has_error or prefix+'console.txt' not in files:
            raise ValueError('Every condition requires one terminal outcome and its console')
        if has_error:
            error = json.loads(retained[prefix+'worker-error.json'])
            if (error['job'] != job or type(error['returncode']) is not int or error['returncode'] == 0):
                raise ValueError('Invalid failed worker record')
            failed.append(job['directory'])
        else:
            if prefix+'mismatch.json' in files:
                raise ValueError('Successful condition contains a mismatch')
            validate_case({n[len(prefix):]: h for n, h in files.items() if n.startswith(prefix)},
                          {n: retained[prefix+n] for n in ('manifest.json', 'results.json')})
            completed.append(job['directory'])
    if (not failed or attempt['completed_conditions'] != completed
            or attempt['failed_conditions'] != failed or attempt['unattempted_conditions'] != []):
        raise ValueError('Incomplete or inconsistent terminal accounting')
    return {'verified_files': len(files), 'completed_conditions': completed, 'failed_conditions': failed,
            'status': 'failed suite; no aggregate timing claim',
            'scope': 'byte integrity and terminal envelopes; numerical replay remains separate'}


VALIDATORS = {
    'orbweaver-gds-queue-archive-v1': validate_case,
    'orbweaver-gds-queue-suite-archive-v1': validate_suite,
    'orbweaver-gds-queue-failed-suite-archive-v1': validate_failed_suite,
}
RECORD_NAMES = {'manifest.json', 'results.json', 'suite.json', 'summary.json', 'ATTEMPT.json', 'worker-error.json'}


def verify(archive):
    receipt = read(archive/'ARCHIVE.json')
    if receipt['format'] not in VALIDATORS:
        raise ValueError('Unexpected archive format')
    retained = {name: data for name, data in members(archive)
                if Path(name).name in RECORD_NAMES}
    return VALIDATORS[receipt['format']](receipt['files'], retained)


def pack(run, archive, *, suite=False, failed=False):
    if failed and not suite:
        raise ValueError('Failed accounting applies only to a fully attempted suite')
    format_name = ('orbweaver-gds-queue-failed-suite-archive-v1' if failed else
                   'orbweaver-gds-queue-suite-archive-v1' if suite else 'orbweaver-gds-queue-archive-v1')
    paths = sorted(p for p in run.rglob('*') if p.is_file()
                   and '__pycache__' not in p.parts and p.suffix != '.pyc')
    if any(p.is_symlink() for p in paths):
        raise ValueError('Cannot archive symlinks')
    files = {p.relative_to(run).as_posix(): digest(p.read_bytes()) for p in paths}
    retained = {p.relative_to(run).as_posix(): p.read_bytes() for p in paths
                if p.name in RECORD_NAMES}
    VALIDATORS[format_name](files, retained)
    archive.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive/'evidence.tar.gz', 'w:gz') as tar:
        for path in paths:
            tar.add(path, arcname=path.relative_to(run).as_posix(), recursive=False)
    receipt = {'format': format_name, 'files': files,
               'archive_sha256': digest((archive/'evidence.tar.gz').read_bytes())}
    (archive/'ARCHIVE.json').write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n')
    return verify(archive)


def restore(archive, output):
    result = verify(archive)
    suite = read(archive/'ARCHIVE.json')['format'] == 'orbweaver-gds-queue-suite-archive-v1'
    output.mkdir(parents=True, exist_ok=False)
    for name, data in members(archive):
        target = output/relative('recorded-summary.json' if suite and name == 'summary.json' else name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('pack', 'verify', 'restore'))
    parser.add_argument('archive', type=Path)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--suite', action='store_true')
    parser.add_argument('--failed', action='store_true')
    args = parser.parse_args()
    if args.command == 'pack':
        result = pack(args.run, args.archive, suite=args.suite, failed=args.failed)
    elif args.command == 'restore':
        result = restore(args.archive, args.output)
    else:
        result = verify(args.archive)
    print(json.dumps(result))
