"""Separate profiling harness for the unchanged frozen Quail/vLLM reference.

Requires a completed unprofiled worker on the same host before GPU execution.
The CPU preflight exercises request-runtime wrapping, not CUDA profiler APIs.
"""

import argparse
from contextlib import ExitStack, contextmanager
from functools import wraps
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as file:
        json.dump(value, file, indent=2, sort_keys=True, allow_nan=False)
        file.write('\n')


def load_reference(root):
    sys.path.insert(0, str(root/'source'))
    import orbweaver_query

    if Path(orbweaver_query.__file__).resolve().parent != root/'source/orbweaver_query':
        raise ValueError('Run in a fresh process using the frozen package')
    spec = importlib.util.spec_from_file_location('frozen_reference', root/'reference/quail_execution_reference.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.verify(root/'reference')
    return module


def freeze(root, reference, repository, revision):
    if len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('Supply the full source commit used by the frozen reference')
    root.mkdir(parents=True, exist_ok=False)
    manifest = read(reference/'manifest.json')
    names = ['manifest.json', *manifest['files'], 'DATA_LICENSES.md', 'QWEN_LICENSE.txt']
    for name in names:
        path = Path(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Unsafe reference path')
        destination = root/'reference'/path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(reference/path, destination)
    prefix = 'packages/query/src/'
    files = subprocess.check_output(['git', '-C', str(repository), 'ls-tree', '-r', '--name-only', revision,
                                     '--', prefix+'orbweaver_query'], text=True).splitlines()
    if not files:
        raise ValueError('Package source is absent from the requested commit')
    for name in files:
        destination = root/'source'/name.removeprefix(prefix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(subprocess.check_output(['git', '-C', str(repository), 'show', f'{revision}:{name}']))
    (root/'source/LICENSE').write_bytes(subprocess.check_output(
        ['git', '-C', str(repository), 'show', f'{revision}:LICENSE']))
    for name in ('quail_profile_reference.py', 'quail_trace_audit.py', 'QUAIL_PROFILE_PROTOCOL.md'):
        shutil.copyfile(Path(__file__).with_name(name), root/name)
    load_reference(root)
    write(root/'profile-manifest.json', {'format': 'orbweaver-quail-profile-v1', 'package_revision': revision,
        'reference_manifest_sha256': sha(reference/'manifest.json'), 'timing_claim': False,
        'files': {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*'))
                  if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}})


def verify(root):
    manifest = read(root/'profile-manifest.json')
    if manifest['format'] != 'orbweaver-quail-profile-v1' or manifest['timing_claim'] is not False:
        raise ValueError('Unexpected profiling manifest')
    for name, checksum in manifest['files'].items():
        if sha(root/name) != checksum:
            raise ValueError(f'Frozen profiling input changed: {name}')
    if sha(Path(__file__)) != manifest['files']['quail_profile_reference.py']:
        raise ValueError('Execute the unchanged frozen profiling harness')
    if sha(root/'reference/manifest.json') != manifest['reference_manifest_sha256']:
        raise ValueError('Original reference manifest changed')
    sys.path.insert(0, str(root))
    return load_reference(root)


@contextmanager
def patched(owner, name, replacement):
    original = getattr(owner, name)
    setattr(owner, name, replacement)
    try:
        yield
    finally:
        setattr(owner, name, original)


class ProfileExtension:
    """Annotate the actual configured scheduler in the single-GPU worker."""

    def install_orbweaver_profile_scopes(self):
        import torch

        scheduler = self.vllm_config.scheduler_config.get_scheduler_cls()
        for name in ('schedule', 'update_from_output', 'add_request'):
            original = getattr(scheduler, name)
            if getattr(original, '_orbweaver_profile_scope', False):
                raise ValueError('Scheduler instrumentation already installed')

            @wraps(original)
            def scope(instance, *args, _method=original, _name=name, **kwargs):
                with torch.profiler.record_function('orbweaver.scheduler.'+_name):
                    return _method(instance, *args, **kwargs)

            scope._orbweaver_profile_scope = True
            setattr(scheduler, name, scope)
        return {'pid': os.getpid(), 'scheduler': scheduler.__module__+'.'+scheduler.__name__}


class Capture:
    def __init__(self, arm, output, *, dry=False):
        self.arm, self.output, self.dry = arm, output, dry
        self.calls, self.records, self.profilers = 0, [], []

    def export(self):
        errors = []
        for index, profiler in enumerate(self.profilers):
            path = self.output/('driver.trace.json.gz' if index == 0 else f'driver-{index}.trace.json.gz')
            if path.exists():
                continue
            try:
                profiler.export_chrome_trace(str(path))
            except Exception as error:
                errors.append(f'{type(error).__name__}: {error}')
        return errors

    def wrap(self, original):
        @wraps(original)
        def execute(*args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return original(*args, **kwargs)
            if self.calls != 2:
                raise ValueError('Expected one warmup and one instrumented graph execution')
            if self.dry:
                result = original(*args, **kwargs)
                self.records.append({'kind': 'CPU wrapper preflight; no profiler or inference'})
                return result
            import torch

            llm, workers, before = None, [], set()
            if self.arm == 'vllm':
                llm = args[2]['client'].llm  # execute_request_graph(context, backend, engine_state, boot)
                workers = llm.collective_rpc('install_orbweaver_profile_scopes')
                before = set((self.output/'worker-traces').rglob('*.trace.json*'))
                llm.start_profile(profile_prefix='orbweaver-graph')
            activities = [torch.profiler.ProfilerActivity.CPU]
            if self.arm == 'quail':
                activities.append(torch.profiler.ProfilerActivity.CUDA)
            profiler = torch.profiler.profile(activities=activities, with_stack=False, record_shapes=False)
            try:
                torch.cuda.synchronize()
                with profiler:
                    start_ns, start = time.time_ns(), time.perf_counter()
                    with torch.profiler.record_function('orbweaver.graph'):
                        result = original(*args, **kwargs)
                        torch.cuda.synchronize()
                    end_ns, duration = time.time_ns(), time.perf_counter()-start
            finally:
                self.profilers.append(profiler)
                if llm is not None:
                    llm.stop_profile()
            if abs((end_ns-start_ns)/1e9-duration) > max(.05, duration*.001):
                raise ValueError('Wall and monotonic clocks disagree across the capture')
            produced = sorted(set((self.output/'worker-traces').rglob('*.trace.json*'))-before)
            if llm is not None and (len(produced) != 1 or len(workers) != 1):
                raise ValueError('Expected one vLLM worker trace and one worker identity')
            self.records.append({'start_unix_ns': start_ns, 'end_unix_ns': end_ns,
                'instrumented_graph_seconds': duration, 'driver_pid': os.getpid(), 'workers': workers,
                'worker_traces': [p.relative_to(self.output).as_posix() for p in produced]})
            return result
        return execute


def preflight(root, output):
    reference = verify(root)
    capture = Capture('vllm', output, dry=True)
    original = reference.execute_request_graph
    results = []
    with patched(reference, 'execute_request_graph', capture.wrap(original)):
        for _ in range(2):
            # execute_query installs its explicitly supplied lowered plan on the
            # Query. The preflight inspects an original Quail plan each time.
            with reference.session(reference.tokenizer(root/'reference/tokenizer')) as engine:
                manifest = read(root/'reference/manifest.json')
                bound = reference.QuailPairs(read(root/'reference/inputs.json')).bind(
                    engine, manifest['predicate'], kind='barrier')
                results.append(reference.recording_preflight(bound))
    first, second = results
    if first != second or capture.calls != 2 or len(capture.records) != 1 or reference.execute_request_graph is not original:
        raise ValueError('Instrumentation wrapping changed the actual request-runtime preflight')
    write(output, {'reference': first, 'wrapped_graph_calls': capture.calls, 'instrumented_calls': 1,
                   'original_function_restored': True, 'cuda_profiler_validated': False})


def worker(root, arm, output, baseline):
    reference = verify(root)
    start = read(baseline/'started.json')
    if ((baseline/'failure.json').exists() or start['arm'] != arm
            or start['manifest_sha256'] != sha(root/'reference/manifest.json')
            or read(baseline/'complete.json') != {'arm': arm, 'cold_boot_trials': 1, 'measured_trials': 3}):
        raise ValueError('Require a completed unprofiled worker from the original reference')
    environment = read(baseline/'environment.json')
    expected = [read(baseline/f'trial-{i:02d}.json')['decisions'] for i in range(1, 4)]
    if any(decisions != expected[0] for decisions in expected[1:]):
        raise ValueError('Unprofiled answers are unstable; resolve before spending a profiling run')
    output.mkdir(parents=True, exist_ok=False)
    (output/'worker-traces').mkdir()
    capture = Capture(arm, output)
    try:
        import quail.backends.quail.worker as quail_worker
        import quail.backends.request as request

        with ExitStack() as stack:
            if arm == 'vllm':
                original = reference.PinnedTokenVLLMEngine.llm_kwargs

                def kwargs(engine, spec):
                    return {**original(engine, spec),
                        'worker_extension_cls': 'quail_profile_reference.ProfileExtension',
                        'profiler_config': {'profiler': 'torch', 'torch_profiler_dir': str(output/'worker-traces'),
                            'torch_profiler_with_stack': False, 'torch_profiler_record_shapes': False,
                            'torch_profiler_dump_cuda_time_total': False}}

                stack.enter_context(patched(reference.PinnedTokenVLLMEngine, 'llm_kwargs', kwargs))
                stack.enter_context(patched(request, 'execute_request_graph', capture.wrap(request.execute_request_graph)))
            else:
                stack.enter_context(patched(quail_worker, 'execute_single', capture.wrap(quail_worker.execute_single)))
            reference.worker(root/'reference', arm, output/'execution', repeats=1)
        export_errors = capture.export()
        if export_errors:
            raise RuntimeError(f'Could not export driver trace: {export_errors}')
        if capture.calls != 2 or len(capture.records) != 1:
            raise ValueError('Instrumented graph boundary was not reached exactly once')
        if read(output/'execution/environment.json') != environment:
            raise ValueError('Profiled and unprofiled hardware/dependencies differ')
        profiled = read(output/'execution/trial-01.json')
        if any(profiled['decisions'] != decisions for decisions in expected):
            raise ValueError('Profiling changed answers or unprofiled answers are unstable')
        record = capture.records[0]
        record.update(arm=arm, all_reference_decisions_match=True, timing_claim=False,
            profile_manifest_sha256=sha(root/'profile-manifest.json'),
            baseline_trial_sha256=[sha(baseline/f'trial-{i:02d}.json') for i in range(1, 4)],
            report=profiled['report'], driver_trace='driver.trace.json.gz')
        write(output/'profile.json', record)
        from quail_trace_audit import analyze
        write(output/'trace-analysis.json', analyze(output))
        write(output/'complete.json', {'scope': 'instrumented diagnostic, not comparative timing'})
    except BaseException:
        error = traceback.format_exc()
        write(output/'failure.json', {'traceback': error, 'trace_export_errors': capture.export(),
                                     'completed_graph_captures': capture.records})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    frozen = sub.add_parser('freeze')
    frozen.add_argument('root', type=Path)
    frozen.add_argument('--reference', type=Path, required=True)
    frozen.add_argument('--repository', type=Path, required=True)
    frozen.add_argument('--package-revision', required=True)
    for command in ('preflight', 'worker'):
        task = sub.add_parser(command)
        task.add_argument('root', type=Path)
        task.add_argument('--output', type=Path, required=True)
        if command == 'worker':
            task.add_argument('--arm', choices=('quail', 'vllm'), required=True)
            task.add_argument('--baseline', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'freeze':
        freeze(args.root.resolve(), args.reference.resolve(), args.repository.resolve(), args.package_revision)
    elif args.command == 'preflight':
        preflight(args.root.resolve(), args.output.resolve())
    else:
        worker(args.root.resolve(), args.arm, args.output.resolve(), args.baseline.resolve())
