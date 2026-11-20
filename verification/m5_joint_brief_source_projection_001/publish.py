"""Seal the offline and sole real joint-brief result with original denominator."""

import argparse
from pathlib import Path
import subprocess
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import publication, registered_product, verify_freeze
from common import EXTERNAL, ROOT, asset_identity, load, read, save, sha


HISTORY = '6562ba5ef6569512465adad2725f2bfa50748423'


def archive():
    verify_freeze(NS / 'FROZEN.json')
    retained = load('_m5_joint_projection_archive', NS.parent / 'm4_cross_scale_live_task_formal_001/publish.py')
    retained.NS, retained.EXTERNAL = NS, EXTERNAL
    retained.archive()


def seal():
    freeze_path = NS / 'FROZEN.json'
    freeze = verify_freeze(freeze_path) if freeze_path.is_file() else None
    asset_identity()
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    paths = subprocess.check_output(['git', 'diff', '--name-only', HISTORY], cwd=ROOT).decode().splitlines()
    if any(not path.startswith(prefix) for path in paths):
        raise ValueError('unrelated_product_or_evidence_change')
    offline_path = NS / 'checks/OFFLINE_CONTROLS.json'
    live_path = NS / 'checks/LIVE_REVIEW.json'
    offline = read(offline_path) if offline_path.is_file() else {}
    live = read(live_path) if live_path.is_file() else {}
    if live and live['freeze_sha256'] != freeze:
        raise ValueError('live_review_not_from_the_same_frozen_operation')
    slots = EXTERNAL / 'slots'
    started = {p.name for p in slots.iterdir()} if slots.is_dir() else set()
    if started not in (set(), {'B'}):
        raise ValueError('unregistered_real_slot_or_replacement')
    slot = slots / 'B'
    published = slot / 'SLOT_PUBLICATION.json'
    status = 'unconfirmed' if started else 'unrun'
    counts, identity = None, None
    if published.is_file():
        raw, receipt = publication('B', freeze)
        status = receipt['status']
        counts = (raw.get('budget') or {}).get('counts')
        identity = {'result_sha256': receipt['result_sha256'], 'publication_sha256': sha(published)}
        if raw['model_consumers'] != 0 or raw['paid_API_calls'] != 0:
            raise ValueError('external_activity_not_in_this_qualification')
    bounds = {'Blender_start_attempts': 1, 'business_admissions': 1, 'all_raster_upper': 3, 'consumer_admissions': 0}
    if counts and any(counts[key] > value for key, value in bounds.items()):
        raise ValueError('qualification_budget_exceeded')
    actual_counts_valid = (bool(counts and all(counts[key] == value for key, value in bounds.items()))
                           and counts['all_raster_actual'] == 3)
    gates = {'archived_assembly_and_dense_offline_projection': offline.get('passed') is True,
             'actual_source_and_CLI': live.get('passed') is True, 'actual_closed_counts': status == 'completed' and actual_counts_valid}
    names = ('REPORT.md', 'checks/OFFLINE_CONTROLS.json', 'checks/LIVE_PREFLIGHT.json', 'checks/LIVE_REVIEW.json',
             'harness/DISPATCH_PREFLIGHT.json', 'install/BUILD_INSTALL.json', 'RUNTIME_INDEX.json')
    save(NS / 'DECISION.json', {'task': 'M5-JOINT-BRIEF-SOURCE-PROJECTION-001', 'passed': all(gates.values()),
        'freeze_sha256': freeze, 'product': registered_product(), 'product_changed_files': 1,
        'gates': gates, 'registered_live_slots': 1, 'actual_slot_status': status, 'original_slot_identity': identity,
        'actual_ledger_counts': counts, 'asset_rebuilds': 0, 'additional_qualifications': 0,
        'models': 0, 'replacements': 0, 'paid_API_calls': 0, 'single_slot_timing_is_diagnostic': True,
        'evidence_sha256': {name: sha(NS / name) for name in names if (NS / name).is_file()}})
    manifest = NS / 'CONTENT_MANIFEST.json'
    rows = [{'path': item.relative_to(NS).as_posix(), 'bytes': item.stat().st_size, 'sha256': sha(item)}
            for item in sorted(NS.rglob('*')) if item.is_file() and item != manifest]
    if any(item['path'].endswith(('.pyc', '.bak')) for item in rows):
        raise ValueError('unexpected_generated_file_in_evidence')
    save(manifest, {'count': len(rows), 'files': rows, 'self_excluded': True})
    print('Evidence sealed', len(rows), sha(manifest), gates, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('archive', 'seal'))
    globals()[parser.parse_args().action]()
