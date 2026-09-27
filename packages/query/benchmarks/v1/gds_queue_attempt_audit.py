"""Replay completed conditions in a failed GDS suite without claiming completeness.

Uses the suite's unchanged frozen source and saved scores. No database, model fit,
confirmation data or fresh timings are involved. Every declared condition must
already have exactly one terminal outcome.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path


def audit(run):
    import numpy as np

    sys.path.insert(0, str(run))
    import gds_queue_diagnostic as diagnostic
    import gds_quality
    import gds_ranking as ranking

    for module in (diagnostic, gds_quality, ranking):
        if Path(module.__file__).resolve().parent != run:
            raise ValueError('Numerical audit requires the unchanged frozen helper modules')
    suite = diagnostic.checked_suite(run)
    sys.path.insert(0, str(run/suite['jobs'][0]['directory']/'source'))
    from orbweaver_query import GraphSnapshot

    completed, failed, audits = [], [], []
    for job in suite['jobs']:
        child = run/job['directory']
        has_result, has_error = ((child/n).exists() for n in ('results.json', 'worker-error.json'))
        if has_result == has_error or not (child/'console.txt').is_file():
            raise ValueError('Every condition must have one terminal outcome and console')
        entry = {'directory': job['directory'], 'status': 'failed' if has_error else 'completed'}
        if has_error:
            error = diagnostic.read(child/'worker-error.json')
            if error['job'] != job or type(error['returncode']) is not int or error['returncode'] == 0:
                raise ValueError('Invalid worker failure record')
            failed.append(job['directory'])
        else:
            if (child/'mismatch.json').exists():
                raise ValueError('A completed condition has a mismatch')
            completed.append(job['directory'])
        if (child/'scores.npz').is_file():
            graph = GraphSnapshot.load(child/'graph.npz')
            with np.load(child/'development.npz', allow_pickle=False) as data:
                sources, positives = data['sources'], data['positives']
            with np.load(child/'scores.npz', allow_pickle=False) as data:
                scores = data['scores']
            mask = ranking.candidate_mask(graph, sources)
            if not np.array_equal(np.isfinite(scores), mask):
                raise ValueError('Raw score domain differs from the complete candidate domain')
            expected = ranking.rank_scores(scores, graph, sources, 16)
            quality = gds_quality.evaluate(scores, mask, sources, positives)
            predicted = {(graph.node_index(row['head']), graph.node_index(r['target']))
                         for row in expected for r in row['recommendations']}
            recall = sum((int(a), int(b)) in predicted for a, b in positives)/len(positives)
            entry.update(full_score_reference_verified=True, score_sha256=diagnostic.sha(child/'scores.npz'),
                         raw_score_quality=quality, deterministic_id_recall16=recall)
        elif has_result:
            raise ValueError('Completed condition has no saved full scores')
        else:
            entry['full_score_reference_verified'] = False
        if has_result:
            result = diagnostic.read(child/'results.json')
            if (result['manifest_sha256'] != job['manifest_sha256']
                    or (result['dataset'], result['threads']) != (job['dataset'], job['threads'])
                    or result['full_scores_sha256'] != entry['score_sha256']
                    or result['all_outputs_match_complete_score_reference'] is not True
                    or result['raw_score_quality'] != quality or result['deterministic_id_recall16'] != recall):
                raise ValueError('Recorded result does not reproduce from full scores')
            records = result['records']
            if len(records) != 2 or {r['arm'] for r in records} != {'global', 'partitioned'}:
                raise ValueError('Missing request arm')
            for record in records:
                samples = record['samples_seconds']
                if (record['output'] != expected or len(samples) != 3 or len(record['counters']) != 3
                        or any(type(s) not in (int, float) or not np.isfinite(s) or s <= 0 for s in samples)):
                    raise ValueError('Recorded outputs or measurements do not validate')
            medians = {r['arm']: float(np.median(r['samples_seconds'])) for r in records}
            entry.update(outputs_recomputed=True, median_seconds=medians,
                         global_over_partitioned=medians['global']/medians['partitioned'])
        audits.append(entry)
    if not failed:
        raise ValueError('Use the frozen summarize-suite command for a fully successful suite')
    return {'format': 'orbweaver-gds-queue-failed-attempt-v1', 'suite_sha256': diagnostic.sha(run/'suite.json'),
            'completed_conditions': completed, 'failed_conditions': failed, 'unattempted_conditions': [],
            'aggregate_timing_claim': False, 'confirmation_contents_read': False, 'case_audits': audits,
            'audit_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'scope': 'full score coverage and completed-output/quality replay; no new model execution or timing'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.run.resolve())
    with args.output.open('x') as output:
        json.dump(report, output, indent=2, sort_keys=True, allow_nan=False)
        output.write('\n')
    print(json.dumps({key: report[key] for key in ('completed_conditions', 'failed_conditions', 'scope')}))
