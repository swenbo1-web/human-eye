"""Bind the old immutable qualification evidence to this formal pair only."""

from pathlib import Path
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from common import EXTERNAL, SOURCE_SHA, asset_identity, read, save, sha


PAST = NS.parent / 'm4_cross_scale_live_task_recovery_001'
PAST_RUN = Path('D:/he_m4_cross_scale_live_task_recovery_001')


def bind():
    if (EXTERNAL / 'slots').exists():
        raise ValueError('formal slots already initialized')
    frozen = NS / 'FROZEN.json'
    original_qualification = PAST / 'QUALIFICATION.json'
    original_freeze = PAST / 'FROZEN.json'
    offline = NS / 'checks/OFFLINE_EVIDENCE.json'
    evidence = read(offline)
    if (evidence['original_freeze_sha256'] != sha(original_freeze) or
            evidence['original_qualification_sha256'] != sha(original_qualification)):
        raise ValueError('derived evidence is detached from the original qualification')
    expected = {Path(row['path']).resolve(): row for row in read(frozen)['direct_inputs']}
    for path in (offline, original_qualification, original_freeze):
        pin = expected[path.resolve()]
        if pin['sha256'] != sha(path) or pin['bytes'] != path.stat().st_size:
            raise ValueError('gate source changed/' + str(path))
    old = read(original_qualification)
    if (old['passed'] is not False or old['freeze_sha256'] != sha(original_freeze)
            or [(slot['label'], slot['passed']) for slot in old['slots']] != [('QN', False), ('QP', True)]):
        raise ValueError('previous qualification status or original freeze mismatch')
    seals = []
    for label in ('QN', 'QP'):
        root = PAST_RUN / 'slots' / label
        original = root / 'SLOT_RESULT.json'
        original_rx = root / 'client/call_01/RESPONSE.json'
        for path in (original, original_rx):
            if expected[path.resolve()]['sha256'] != sha(path):
                raise ValueError('old original bytes changed/' + str(path))
        seals.append({'label': label, 'result_sha256': sha(original), 'response_sha256': sha(original_rx)})
    _, asset_sha = asset_identity()
    passed = bool(evidence.get('passed'))
    if passed:
        if any(evidence[field] is not True for field in ('geometry_arms_passed', 'CLI_preservation_passed', 'negative_controls_passed')):
            raise ValueError('derived qualification success without required independent checks')
        by_label = {row['label']: row for row in evidence['slots']}
        if set(by_label) != {'QN', 'QP'} or any(any(by_label[row['label']][k] != v for k, v in row.items()) for row in seals):
            raise ValueError('derived evidence does not use the old actual slot results and replies')
    admission = {'passed': passed, 'freeze_sha256': sha(frozen), 'asset_sha256': asset_sha,
        'product_source_sha256': SOURCE_SHA, 'slots': ['N1', 'P1'], 'qualification_seals': seals,
        'previous_freeze_sha256': sha(original_freeze), 'previous_qualification_sha256': sha(original_qualification),
        'evidence': {'path': str(offline.resolve()), 'sha256': sha(offline), 'bytes': offline.stat().st_size},
        'scope': 'One new formal N/P pair only; original qualification statuses are retained.',
        'additional_qualification': 0, 'asset_builds': 0, 'admission_ns': time.perf_counter_ns()}
    save(NS / 'ADMISSION.json', admission)
    print('Formal admission', passed, sha(NS / 'ADMISSION.json'))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(bind())
