"""Seal original transport, source and fixed-budget qualification evidence."""

import argparse
from pathlib import Path
import subprocess
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import publication, registered_product, verify_freeze
from common import EXTERNAL, ORDER, ROOT, asset_identity, load, read, save, sha


BASE = '42e72c2611b99a477e88a5fb26ead0cbad5e71b1'


def archive():
    verify_freeze(NS / 'FROZEN.json')
    prior = load('_m5_global_original_archive',
                 NS.parent / 'm4_cross_scale_live_task_formal_001/publish.py')
    prior.NS, prior.EXTERNAL = NS, EXTERNAL
    prior.archive()


def seal():
    freeze = verify_freeze(NS / 'FROZEN.json')
    asset_identity()
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT).decode().splitlines()
    if any(not name.startswith(prefix) for name in changed):
        raise ValueError('unexpected_product_or_evidence_scope_changed')
    live_path = NS / 'checks/LIVE_REVIEW.json'
    cost_path = NS / 'RESOURCE_REVIEW.json'
    live, resources = read(live_path), read(cost_path)
    if live['freeze_sha256'] != freeze or resources['freeze_sha256'] != freeze:
        raise ValueError('review_not_bound_to_one_frozen_trial')
    slots = EXTERNAL / 'slots'
    actual = set(path.name for path in slots.iterdir()) if slots.is_dir() else set()
    if actual != set(ORDER[:len(actual)]):
        raise ValueError('unregistered_slot_or_replacement')
    rows, counts = [], None
    for label in ORDER:
        root = slots / label
        rel = root / 'SLOT_PUBLICATION.json'
        entry = {'label': label, 'status': 'unconfirmed' if label in actual else 'unrun'}
        if rel.is_file():
            result, receipt = publication(label, freeze)
            if result['model_consumers'] != 0 or result['paid_API_calls'] != 0:
                raise ValueError('actual_external_consumer_outside_qualified_scope')
            entry.update(status=receipt['status'], result_sha256=receipt['result_sha256'], publication_sha256=sha(rel))
            counts = (result.get('budget') or {}).get('counts') or counts
        rows.append(entry)
    bounded = {'Blender_start_attempts': 2, 'business_admissions': 3, 'all_raster_upper': 6, 'consumer_admissions': 0}
    if counts and any(counts[key] > cap for key, cap in bounded.items()):
        raise ValueError('observed_budget_outside_frozen_scope')

    resource_rows = resources['rows']
    count_ok = bool(counts and all(counts[key] == cap for key, cap in bounded.items()))
    actual_user_cost_shapes = count_ok and counts['all_raster_actual'] == 6 and all(
        row['status'] == 'completed' and not row['cost_issues'] and len(row['outer_batches']) == 1 and
        len(row['public_packets']) == (2 if row['label'] == 'A' else 1) and
        row['independently_recorded_kernel_solves'] == 1 for row in resource_rows)
    gates = {'actual_public_result_source_and_CLI_quality': live['passed'] is True,
             'two_readonly_slots_completed': all(row['status'] == 'completed' for row in rows),
             'actual_cost_denominator_observed': actual_user_cost_shapes}
    keys = ('REPORT.md', 'checks/LIVE_REVIEW.json', 'checks/LIVE_PREFLIGHT.json', 'truth/MEASUREMENT_TRUTH.json',
            'RESOURCE_REVIEW.json', 'RUNTIME_INDEX.json', 'harness/DISPATCH_PREFLIGHT.json')
    save(NS / 'DECISION.json', {'task': 'M5-GLOBAL-OBSERVE-MEASURE-QUALIFICATION-001',
        'passed': all(gates.values()), 'freeze_sha256': freeze, 'product': registered_product(), 'gates': gates,
        'slots': rows, 'actual_ledger_counts': counts, 'product_diff_files': 0, 'product_rebuilds': 0, 'asset_rebuilds': 0,
        'additional_qualifications': 0, 'replacements': 0, 'model_consumers': 0,
        'external_paid_API_calls': 0, 'single_pair_timing_is_diagnostic': True,
        'evidence_sha256': {path: sha(NS / path) for path in keys if (NS / path).is_file()}})
    manifest = NS / 'CONTENT_MANIFEST.json'
    files = [{'path': path.relative_to(NS).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
             for path in sorted(NS.rglob('*')) if path.is_file() and path != manifest]
    if any(row['path'].endswith(('.pyc', '.bak')) for row in files):
        raise ValueError('unexpected_generated_file_in_qualification_evidence')
    save(manifest, {'count': len(files), 'files': files, 'self_excluded': True})
    print('Sealed', len(files), sha(manifest), gates, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('archive', 'seal'))
    globals()[parser.parse_args().action]()
