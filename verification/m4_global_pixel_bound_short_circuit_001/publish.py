"""Archive original paired runtime and seal the candidate's evidence-only decision."""

import argparse
from pathlib import Path
import subprocess
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import publication, registered_products, verify_freeze
from common import EXTERNAL, ORDER, ROOT, asset_identity, load, read, save, sha


BASE_EVIDENCE = 'a17083c0dff7d4e90daae59406b4a19960583df4'


def archive():
    verify_freeze(NS / 'FROZEN.json')
    script = NS.parent / 'm4_cross_scale_live_task_formal_001/publish.py'
    original = load('_pixel_bound_original_archive', script)
    original.NS, original.EXTERNAL = NS, EXTERNAL
    original.archive()


def seal():
    freeze_path = NS / 'FROZEN.json'
    freeze = verify_freeze(freeze_path) if freeze_path.is_file() else None
    asset_identity()
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    diffs = subprocess.check_output(['git', 'diff', '--name-only', BASE_EVIDENCE], cwd=ROOT).decode().splitlines()
    if any(not name.startswith(prefix) for name in diffs):
        raise ValueError('unexpected_product_or_evidence_scope_changed')
    offline_path = NS / 'checks/OFFLINE_CONTROLS.json'
    offline = read(offline_path) if offline_path.is_file() else {}
    live_path = NS / 'checks/LIVE_REVIEW.json'
    review = read(live_path) if live_path.is_file() else {}
    states, budget = [], None
    slot_dir = EXTERNAL / 'slots'
    present = set(path.name for path in slot_dir.iterdir()) if slot_dir.is_dir() else set()
    if present != set(ORDER[:len(present)]):
        raise ValueError('out_of_order_slot_or_replacement')
    for label in ORDER:
        folder = slot_dir / label
        receipt_path = folder / 'SLOT_PUBLICATION.json'
        row = {'label': label, 'arm': label[0], 'status': 'unconfirmed' if label in present else 'unrun'}
        if receipt_path.is_file():
            result, receipt = publication(label, freeze)
            if result['model_consumers'] != 0 or result['paid_API_calls'] != 0:
                raise ValueError('engineering_slot_outside_approved_zero_model_scope/' + label)
            budget = (result.get('budget') or {}).get('counts') or budget
            row.update(status=receipt['status'], result_sha256=receipt['result_sha256'],
                       publication_sha256=sha(receipt_path))
        states.append(row)

    if review and review['freeze_sha256'] != freeze:
        raise ValueError('paired_analysis_not_bound_to_this_freeze')
    quality = review.get('quality_passed') is True
    perf = review.get('performance_passed') is True
    conditions = {'offline_three_sources_and_boundaries': offline.get('passed') is True,
                  'three_equivalent_real_pairs': quality and all(row['status'] == 'completed' for row in states),
                  'stage_and_cold_RPC': perf}
    passed = all(conditions.values())
    if budget and any(budget[key] > max_count for key, max_count in (('Blender_start_attempts', 6),
                ('business_admissions', 6), ('all_raster_upper', 12), ('consumer_admissions', 0))):
        raise ValueError('actual_owned_budget_above_frozen_limits')
    if passed and (budget['Blender_start_attempts'], budget['business_admissions'],
                   budget['all_raster_actual'], budget['consumer_admissions']) != (6, 6, 12, 0):
        raise ValueError('complete_three_pair_denominators_disagree')
    deliverables = ('checks/OFFLINE_CONTROLS.json', 'checks/REGRESSION.json', 'checks/LIVE_REVIEW.json',
                    'harness/DISPATCH_PREFLIGHT_RECOVERY.json', 'prelaunch/FAILURE.json',
                    'RUNTIME_INDEX.json', 'REPORT.md', 'install/BUILD_INSTALL.json')
    save(NS / 'DECISION.json', {'task': 'M4-GLOBAL-PIXEL-BOUND-SHORT-CIRCUIT-001', 'passed': passed,
          'freeze_sha256': freeze, 'products': registered_products(), 'gates': conditions, 'slots': states,
          'planned_pairs': 3, 'actual_ledger_counts': budget, 'product_diff_files': 1, 'replacements': 0,
          'model_consumers': 0, 'additional_qualifications': 0, 'asset_rebuilds': 0, 'paid_API_calls': 0,
          'prelaunch_process_failures': 1, 'owned_slots_consumed_by_prelaunch_failure': 0,
          'evidence_sha256': {name: sha(NS / name) for name in deliverables if (NS / name).is_file()}})
    manifest = NS / 'CONTENT_MANIFEST.json'
    files = [{'path': path.relative_to(NS).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
             for path in sorted(NS.rglob('*')) if path.is_file() and path != manifest]
    if any(row['path'].endswith(('.pyc', '.bak')) for row in files):
        raise ValueError('unexpected_generated_file_in_evidence')
    save(manifest, {'count': len(files), 'files': files, 'self_excluded': True})
    print('Sealed', len(files), sha(manifest), conditions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('archive', 'seal'))
    globals()[parser.parse_args().action]()
