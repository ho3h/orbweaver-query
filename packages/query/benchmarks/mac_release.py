"""Installed-wheel Mac demonstration. See MAC_RELEASE_PROTOCOL.md for boundaries."""

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Only benchmark helpers are imported from this directory; runtime code must
# resolve to the installed distribution, including under Python's isolated mode.
sys.path.insert(0, str(Path(__file__).resolve().parent / 'v1'))
import targeted  # noqa: E402

BASELINES = ('full', 'lru64k', 'lru16m', 'lru_guarded', 'full_guarded')
GRAPHS = ('wordnet', 'movies', 'collaboration')


def write(path, value):
    targeted.write(path, value)


def installed_identity():
    import orbweaver_query

    package = Path(orbweaver_query.__file__).resolve().parent
    distribution = importlib.metadata.distribution('orbweaver-query')
    if package != Path(distribution.locate_file('orbweaver_query')).resolve():
        raise ValueError('Runtime is shadowing the installed distribution')
    files = {str(p.relative_to(package)): targeted.sha(p) for p in sorted(package.rglob('*'))
             if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    return {'version': distribution.version, 'files': files}


def host():
    def command(*args):
        return subprocess.check_output(args, text=True, timeout=10).strip()
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise ValueError('This protocol requires native Apple Silicon Python on macOS')
    return {'system': platform.system(), 'macos': platform.mac_ver()[0],
            'architecture': platform.machine(), 'python': platform.python_version(),
            'numpy': importlib.metadata.version('numpy'),
            'model': command('sysctl', '-n', 'hw.model'),
            'chip': command('sysctl', '-n', 'machdep.cpu.brand_string'),
            'memory_bytes': int(command('sysctl', '-n', 'hw.memsize')),
            'logical_cpus': os.cpu_count()}


def activity():
    # Aggregate telemetry avoids retaining other applications' names/arguments.
    raw = subprocess.check_output(['ps', '-A', '-o', 'pcpu='], text=True, timeout=10)
    return {'utc': datetime.now(timezone.utc).isoformat(), 'load_average': os.getloadavg(),
            'aggregate_process_cpu_percent': sum(float(x) for x in raw.split()),
            'thermal': subprocess.run(['pmset', '-g', 'therm'], capture_output=True,
                                     text=True, timeout=10, check=False).stdout.strip()}


def freeze(run, wheel, host_use):
    import numpy as np
    from orbweaver_query import ExplicitPathModel, GraphSnapshot

    environment = host()
    identity = installed_identity()
    # Confirm the exact wheel supplies every imported package member.
    import zipfile
    with zipfile.ZipFile(wheel) as archive:
        wheel_files = {n.removeprefix('orbweaver_query/'): hashlib.sha256(archive.read(n)).hexdigest()
                       for n in archive.namelist() if n.startswith('orbweaver_query/')
                       and not n.endswith('/')}
    if wheel_files != identity['files']:
        raise ValueError('Installed runtime does not match the supplied wheel')
    run.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).resolve().parent
    shutil.copyfile(__file__, run/'mac_release.py')
    (run/'v1').mkdir()
    shutil.copyfile(here/'v1/targeted.py', run/'v1/targeted.py')
    shutil.copyfile(here/'cache_reference.py', run/'cache_reference.py')
    shutil.copyfile(here/'MAC_RELEASE_PROTOCOL.md', run/'MAC_RELEASE_PROTOCOL.md')
    shutil.copyfile(wheel, run/wheel.name)
    inventory = {}
    for name in GRAPHS:
        for kind in ('graph', 'model'):
            filename = f'{name}-{kind}.npz'
            shutil.copyfile(here/'results/v1-development/inputs'/filename, run/filename)
        queries = here/'results/v1-development/targeted-development-v4'/f'{name}-queries.json.gz'
        (run/f'{name}-queries.json').write_bytes(gzip.decompress(queries.read_bytes()))
        graph = GraphSnapshot.load(run/f'{name}-graph.npz')
        model = ExplicitPathModel.load(run/f'{name}-model.npz')
        inventory[name] = {'nodes': len(graph.node_ids), 'edges': len(graph.triples()),
                           'graph_id': graph.snapshot_id, 'model_id': model.model_id}
    jobs = [{'graph': g, 'workload': w, 'arm': a, 'replicate': i}
            for g in GRAPHS for w in targeted.WORKLOADS for a in targeted.ARMS for i in range(3)]
    random.Random(2026092702).shuffle(jobs)
    write(run/'manifest.json', {'format': 'mac-installed-wheel-v1', 'jobs': jobs,
          'inventory': inventory, 'warmup': 1, 'samples': 3, 'quality_claim': False,
          'files': {str(p.relative_to(run)): targeted.sha(p) for p in sorted(run.rglob('*'))
                    if p.is_file()}, 'installed': identity, 'environment': environment,
          'numpy': np.__version__, 'host_use': host_use, 'wheel': wheel.name,
          'boundary': 'Scoring through to_records and JSON UTF-8 encoding. '
                      'Artifact loading and warm-cache preparation reported separately. '
                      'No database, download, process startup or interpreter import time.',
          'query_source': 'Unchanged targeted-development-v4 inputs; development, not holdout.'})
    return {'workers': len(jobs), 'manifest_sha256': targeted.sha(run/'manifest.json')}


def checked(run):
    manifest = targeted.checked(run)
    if manifest['format'] != 'mac-installed-wheel-v1':
        raise ValueError('Unexpected protocol')
    if installed_identity() != manifest['installed'] or host() != manifest['environment']:
        raise ValueError('Installed runtime, dependencies or host changed after freeze')
    return manifest


def worker(run, index):
    checked(run)
    start = activity()
    result = targeted.worker(run, index, installed=True, serialize=True)
    return {**result, 'activity_before': start, 'activity_after': activity()}


def execute(run):
    manifest = checked(run)
    folder = run/'workers'
    folder.mkdir(exist_ok=False)  # Failed/incomplete runs are retained, never silently resumed.
    began = time.monotonic()
    for index, job in enumerate(manifest['jobs']):
        env = {**os.environ, **{key: '1' for key in targeted.THREADS}}
        process = subprocess.run([sys.executable, '-I', str(run/'mac_release.py'),
                                  'worker', str(run), '--index', str(index)],
                                 env=env, capture_output=True, text=True, check=False, timeout=180)
        if process.returncode:
            write(folder/f'{index:04d}-error.json', {'job': job, 'stdout': process.stdout,
                                                  'stderr': process.stderr})
            raise RuntimeError(f'Worker {index} failed; see retained error record')
        write(folder/f'{index:04d}.json', json.loads(process.stdout))
        if index % 54 == 0:
            print(f'{index + 1}/{len(manifest["jobs"])} workers; '
                  f'{time.monotonic()-began:.0f}s elapsed', flush=True)
    return {'workers': len(manifest['jobs']), 'wall_seconds': time.monotonic()-began}


def verify(run):
    import numpy as np

    # Verification can run on another platform: no fresh timing or host equality required.
    manifest = targeted.checked(run)
    records = [targeted.read(run/'workers'/f'{i:04d}.json')
               for i in range(len(manifest['jobs']))]
    for job, record in zip(manifest['jobs'], records):
        if record['job'] != job or record['serialization_included'] is not True:
            raise ValueError('Mismatched job or request boundary')
        encoded = json.dumps(record['output'], sort_keys=True, allow_nan=False).encode()
        if hashlib.sha256(encoded).hexdigest() != record['output_sha256']:
            raise ValueError('Output digest mismatch')
        values = [*record['samples_seconds'], record['median_seconds'],
                  record['load_seconds'], record['first_request_seconds']]
        if len(record['samples_seconds']) != 3 or not all(np.isfinite(v) and v > 0 for v in values):
            raise ValueError('Invalid measurement')
    # Existing evaluator checks every score, status, metadata, bag and position
    # against the full-expansion arm. Existing random-walk-oracle tests are separate.
    targeted.summarize(run)
    result = targeted.read(run/'results.json')
    per_condition = []
    for condition in result['outcomes']:
        selected = [r for r in records if r['job']['graph'] == condition['graph']
                    and r['job']['workload'] == condition['workload']]
        medians = {}
        for arm, summary in condition['arms'].items():
            rs = [r for r in selected if r['job']['arm'] == arm]
            medians[arm] = [r['median_seconds'] for r in rs]
            summary['load_ms'] = float(np.median([r['load_seconds'] for r in rs]))*1000
            summary['first_request_ms'] = float(np.median([r['first_request_seconds'] for r in rs]))*1000
            summary['loaded_first_use_ms'] = float(np.median([
                r['load_seconds']+r['preparation_seconds']+r['first_request_seconds'] for r in rs]))*1000
            summary['process_medians_ms'] = [v*1000 for v in medians[arm]]
        condition['strongest_ondemand_arm'] = min(BASELINES, key=lambda a: condition['arms'][a]['ms'])
        per_condition.append(medians)
    rng = np.random.default_rng(2026092703)
    ratios = []
    for condition in per_condition:
        sampled = {arm: np.median(rng.choice(values, size=(10000, 3)), axis=1)
                   for arm, values in condition.items()}
        ratios.append(np.minimum.reduce([sampled[a] for a in BASELINES])/sampled['targeted'])
    interval = np.quantile(np.exp(np.mean(np.log(ratios), axis=0)), [.025, .975]).tolist()
    result.update({'format': 'mac-installed-wheel-v1', 'environment': manifest['environment'],
        'wheel_sha256': manifest['files'][manifest['wheel']], 'host_use': manifest['host_use'],
        'boundary': manifest['boundary'], 'bootstrap_95_percent_interval': interval,
        'interval_scope': 'Process resampling conditional on these 24 reused conditions; '
                          'does not measure contention bias, workload or hardware generalization.',
        'quality_claim': False, 'gate_A_complete': False,
        'reason': 'Installed-distribution demonstration; reused development inputs, '
                  'warm lookup and composed/native workloads remain separate controls.',
        'workers_sha256': {f'{i:04d}.json': targeted.sha(run/'workers'/f'{i:04d}.json')
                           for i in range(len(records))}})
    write(run/'mac-results.json', result)
    return {k: v for k, v in result.items() if k not in ('outcomes', 'workers_sha256')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('freeze', 'execute', 'worker', 'verify'))
    parser.add_argument('run', type=Path)
    parser.add_argument('--wheel', type=Path)
    parser.add_argument('--host-use', choices=('quiet-requested', 'normal-mixed-use'),
                        default='normal-mixed-use')
    parser.add_argument('--index', type=int)
    args = parser.parse_args()
    run = args.run.resolve()
    if args.command == 'freeze':
        if args.wheel is None:
            parser.error('--wheel is required for freeze')
        result = freeze(run, args.wheel.resolve(), args.host_use)
    elif args.command == 'execute':
        result = execute(run)
    elif args.command == 'worker':
        if args.index is None:
            parser.error('--index is required for worker')
        result = worker(run, args.index)
    else:
        result = verify(run)
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
