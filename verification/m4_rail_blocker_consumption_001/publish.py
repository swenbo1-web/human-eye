"""Seal the exact failed gate, the original owned archive and the offline review."""

import argparse
from pathlib import Path
import subprocess
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import publication, verify_freeze
from common import ARMS, EXTERNAL, ORDER, ROOT, SLOTS, asset_identity, load, read, save, sha


def archive():
    verify_freeze(NS / 'FROZEN.json')
    script = NS.parent / 'm4_cross_scale_live_task_formal_001/publish.py'
    retained = load('_rail_original_runtime_archive', script)
    retained.NS, retained.EXTERNAL = NS, EXTERNAL
    retained.archive()


def seal():
    freeze = verify_freeze(NS / 'FROZEN.json')
    asset_identity()
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    diff = subprocess.check_output(['git', 'diff', '--name-only', 'a3277cd78'], cwd=ROOT).decode().splitlines()
    if any(not path.startswith(prefix) for path in diff):
        raise ValueError('unexpected_change_outside_rail_batch_evidence')
    gate_path = NS / 'QUALIFICATION.json'
    gate = read(gate_path)
    replay = read(NS / 'qualification/OFFLINE_RECHECK.json')
    second_review = read(NS / 'truth/QUALIFICATION_ORIGINALS_REVIEW.json')
    if (gate['passed'] is not False or gate['freeze_sha256'] != freeze or replay['passed_offline'] is not True
            or replay['qualification_gate_sha256'] != sha(gate_path)
            or sorted(path.name for path in (EXTERNAL / 'slots').iterdir()) != ['QA', 'QB']):
        raise ValueError('original_failure_or_replacement_denominator_changed')
    cost = read(NS / 'RUNTIME_REVIEW.json')
    if cost['freeze_sha256'] != freeze or cost['qualification_sha256'] != sha(gate_path):
        raise ValueError('runtime_spans_not_bound_to_original_observation')
    slots, counts = [], None
    for label in ORDER:
        row = {'label': label, 'phase': SLOTS[label][1], 'arm': ARMS[label], 'host_status': 'unrun',
               'formal_quality': None, 'model_consumers': 0}
        if label in ('QA', 'QB'):
            result, pub = publication(label, freeze)
            review = next(item for item in gate['slots'] if item['label'] == label)
            supplemental = next(item for item in replay['slots'] if item['label'] == label)
            if (review['passed'] is not False or supplemental['passed'] is not True or
                    result['model_consumers'] != 0 or result['paid_API_calls'] != 0 or
                    pub['result_sha256'] != review['result_sha256'] or sha(NS / 'qualification' /
                    f'{label}_REVIEW.json') != review['review_sha256']):
                raise ValueError('original_and_supplemental_slot_certificates_disagree')
            counts = result['budget']['counts']
            row.update(host_status=pub['status'], original_qualification_passed=False, offline_recheck_passed=True,
                       result_sha256=pub['result_sha256'], publication_sha256=review['publication_sha256'])
        slots.append(row)
    if (counts['Blender_start_attempts'], counts['all_raster_actual'], counts['business_admissions'],
            counts['consumer_admissions']) != (2, 6, 4, 0):
        raise ValueError('unexpected_actual_denominator')
    inputs = ('REPORT.md', 'QUALIFICATION.json', 'truth/CURRENT_TRUTH.json',
              'truth/QUALIFICATION_ORIGINALS_REVIEW.json', 'qualification/OFFLINE_RECHECK.json',
              'RUNTIME_REVIEW.json', 'RUNTIME_INDEX.json')
    save(NS / 'DECISION.json', {'task': 'M4-RAIL-BLOCKER-CONSUMPTION-001', 'passed': False,
        'freeze_sha256': freeze, 'original_qualification_passed': False, 'offline_recheck_passed': True,
        'independent_additional_review_present': isinstance(second_review, dict), 'slots': slots,
        'formal_planned': 6, 'formal_started': 0, 'formal_unrun': 6, 'formal_model_quality': None,
        'B_first_packet_adoption': None, 'blocker_followup_reduction': None, 'full_time_gate': None,
        'raw_cli_usage_gate': None, 'actual_ledger_counts': counts, 'product_diff_files': 0,
        'asset_rebuilds': 0, 'replacements': 0, 'paid_API_calls': 0, 'Google_calls': 0,
        'evidence_sha256': {name: sha(NS / name) for name in inputs}})
    manifest = NS / 'CONTENT_MANIFEST.json'
    files = [{'path': path.relative_to(NS).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
             for path in sorted(NS.rglob('*')) if path.is_file() and path != manifest]
    if any(row['path'].endswith(('.pyc', '.bak')) for row in files):
        raise ValueError('unexpected_generated_file_in_batch_evidence')
    save(manifest, {'count': len(files), 'files': files, 'self_excluded': True})
    print('Evidence sealed', len(files), sha(manifest))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('archive', 'seal'))
    globals()[parser.parse_args().action]()
