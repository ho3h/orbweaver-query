"""Exercise semantic audit rejection on a disposable restored evidence directory."""

import argparse
import importlib.util
import json
from pathlib import Path


def check(root):
    spec = importlib.util.spec_from_file_location('retention_audit', root/'gds_retention_application_audit.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    expected = audit.read(root/'summary.json')
    if audit.summarize(root) != expected:
        raise ValueError('Restored numerical audit differs')
    cases = []

    def reject(name, relative, mutate):
        path = root/relative
        saved = path.read_bytes()
        try:
            data = json.loads(saved)
            changed = mutate(data)
            if changed is None:
                path.unlink()
            else:
                path.write_text(json.dumps(changed))
            try:
                audit.summarize(root)
            except (ValueError, FileNotFoundError) as error:
                cases.append({'case': name, 'rejected': True, 'error_type': type(error).__name__})
            else:
                raise AssertionError(f'Audit accepted {name}')
        finally:
            path.write_bytes(saved)

    child = 'collaboration-t1/grouped/'
    reject('missing terminal outcomes', 'terminal.json', lambda data: None)
    reject('failed terminal process', 'terminal.json', lambda data: [dict(data[0], returncode=1), data[1]])
    reject('missing repeated output', child+'request-05.json', lambda data: None)
    reject('changed returned answer', child+'request-01.json', lambda data: dict(data, output=[]))
    reject('unreleased reservation', child+'checkpoint-07.json', lambda data: dict(
        data, summary=[dict(data['summary'][0], totalTasksMemory=1)]))
    reject('unexpired task records', child+'checkpoint-08.json', lambda data: dict(data, completed_task_count=1))
    reject('changed recorded quality', child+'full-score-reference.json', lambda data: dict(data, raw_quality={}))
    if audit.summarize(root) != expected:
        raise ValueError('Mutation guards did not restore the original evidence')
    return {'restored_summary_matches': True, 'semantic_rejections': cases,
            'scope': 'saved-evidence audit guards; no new database or model execution'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('restored', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.restored), indent=2, sort_keys=True))
