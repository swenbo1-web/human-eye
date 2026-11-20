"""Seal the one recovery result and retain its original runtime evidence."""

import argparse
from pathlib import Path
import subprocess
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import publication, registered_product, verify_freeze
from common import EXTERNAL, ROOT, asset_identity, load, read, save, sha
from freeze import FAILED_ARCHIVE, FAILED_FREEZE, FAILED_RESULT, HISTORY


def archive():
    verify_freeze(NS / 'FROZEN.json')
    retained = load('_m5_joint_projection_recovery_archive', NS.parent / 'm4_cross_scale_live_task_formal_001/publish.py')
    retained.NS, retained.EXTERNAL = NS, EXTERNAL
    retained.archive()


def seal():
    freeze_path = NS / 'FROZEN.json'
    freeze = verify_freeze(freeze_path) if freeze_path.is_file() else None
    asset_identity()
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    paths = subprocess.check_output(['git', 'diff', '--name-only', HISTORY], cwd=ROOT).decode().splitlines()
    if any(not path.startswith(prefix) for path in paths):
        raise ValueError('changes_outside_recovery_evidence_namespace')
    live_path = NS / 'checks/LIVE_REVIEW.json'
    live = read(live_path) if live_path.is_file() else {}
    if live and live['freeze_sha256'] != freeze:
        raise ValueError('live_review_uses_another_freeze')

    slots = EXTERNAL / 'slots'
    started = {p.name for p in slots.iterdir()} if slots.is_dir() else set()
    if started not in (set(), {'B'}):
        raise ValueError('unexpected_real_slot_or_replacement')
    result_status = 'unconfirmed' if started else 'unrun'
    counts, identity = None, None
    if (slots / 'B/SLOT_PUBLICATION.json').is_file():
        raw, receipt = publication('B', freeze)
        result_status = receipt['status']
        counts = (raw.get('budget') or {}).get('counts')
        identity = {'result_sha256': receipt['result_sha256'], 'publication_sha256': sha(slots / 'B/SLOT_PUBLICATION.json')}
        if raw['model_consumers'] != 0 or raw['paid_API_calls'] != 0:
            raise ValueError('unexpected_external_activity')
    bounds = {'Blender_start_attempts': 1, 'business_admissions': 1, 'all_raster_upper': 3, 'consumer_admissions': 0}
    if counts and (any(counts[key] > value for key, value in bounds.items()) or counts['all_raster_actual'] > 3):
        raise ValueError('qualification_budget_exceeded')
    denominations = live.get('denominators', {})
    count_pass = bool(counts and all(counts[key] == value for key, value in bounds.items())
                      and counts['Blender_spawned_confirmed'] == 1 and counts['all_raster_actual'] == 3
                      and counts['pending_raster_reservations'] == 0
                      and all(denominations.get(key) == value for key, value in {
                          'registered_owned': 1, 'actual_owned_slot_directories': 1, 'observed_public_requests': 1,
                          'observed_outer_batches': 1, 'proven_actual_frames': 3, 'model_consumers': 0}.items()))
    gates = {'recovery_offline_gate': freeze is not None, 'actual_source_and_CLI': live.get('passed') is True,
             'actual_closed_counts': result_status == 'completed' and count_pass}

    names = ('REPORT.md', 'checks/LIVE_PREFLIGHT.json', 'checks/LIVE_REVIEW.json',
             'harness/DISPATCH_PREFLIGHT.json', 'RUNTIME_INDEX.json')
    save(NS / 'DECISION.json', {'task': 'M5-JOINT-BRIEF-SOURCE-PROJECTION-RECOVERY-001', 'passed': all(gates.values()),
         'freeze_sha256': freeze, 'product': registered_product(), 'product_changed_files': 0, 'product_builds': 0,
         'original_failure': {'status': 'failed', 'registered_owned': 1, 'business_admissions': 0,
                              'freeze_sha256': FAILED_FREEZE, 'result_sha256': FAILED_RESULT, 'archive_sha256': FAILED_ARCHIVE},
         'gates': gates, 'registered_live_slots': 1, 'actual_slot_status': result_status,
         'slot_identity': identity, 'actual_ledger_counts': counts, 'observed_denominators': denominations,
         'asset_rebuilds': 0, 'additional_qualifications': 0, 'models': 0, 'replacements': 0, 'paid_API_calls': 0,
         'single_slot_timing_is_diagnostic': True,
         'evidence_sha256': {name: sha(NS / name) for name in names if (NS / name).is_file()}})
    manifest = NS / 'CONTENT_MANIFEST.json'
    rows = [{'path': path.relative_to(NS).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
            for path in sorted(NS.rglob('*')) if path.is_file() and path != manifest]
    if any(item['path'].endswith(('.pyc', '.bak')) for item in rows):
        raise ValueError('unexpected_generated_file_in_evidence')
    save(manifest, {'count': len(rows), 'files': rows, 'self_excluded': True})
    print('Recovery evidence sealed', len(rows), sha(manifest), gates, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('archive', 'seal'))
    globals()[parser.parse_args().action]()
