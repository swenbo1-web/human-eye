"""Seal unchanged run originals and the decision against the frozen pair order."""

import argparse
from pathlib import Path
import subprocess
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import registered_products, verify_freeze
from common import BINDINGS, EXTERNAL, FORMAL, ORDER, ROOT, load, read, save, sha


BASE = '58920560404544bfc973463761bcd2db55acc5ff'


def archive():
    if (NS / 'FROZEN.json').is_file():
        verify_freeze()
    original = load('_projected_bounds_runtime_archive', FORMAL / 'publish.py')
    original.NS, original.EXTERNAL = NS, EXTERNAL
    original.archive()


def finalize():
    frozen = verify_freeze() if (NS / 'FROZEN.json').is_file() else None
    namespace = NS.relative_to(ROOT).as_posix() + '/'
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT).decode().splitlines()
    if any(not path.startswith(namespace) for path in changed):
        raise ValueError('unexpected_product_or_evidence_change_outside_this_namespace')

    products = registered_products()
    review_path = NS / 'checks/LIVE_REVIEW.json'
    review = read(review_path) if review_path.is_file() else {}
    controls_path = NS / 'checks/PROJECTED_BOUNDS_CONTROLS.json'
    controls = read(controls_path) if controls_path.is_file() else {}
    receipts = {}
    slot_results = {}
    slots, counts = [], None
    for label in ORDER:
        folder = EXTERNAL / 'slots' / label
        result_path, publication = (folder / name for name in ('SLOT_RESULT.json', 'SLOT_PUBLICATION.json'))
        row = {'label': label, 'status': 'incomplete' if folder.exists() else 'unrun'}
        if result_path.is_file():
            result = read(result_path)
            checksum = sha(result_path)
            if (not frozen or result['label'] != label or result['arm'] != label[0]
                    or result['freeze_sha256'] != frozen or result['model_consumers'] != 0
                    or result['paid_API_calls'] != 0
                    or result['product_source_sha256'] != products[label[0]]['source_sha256']
                    or result['product_binding_sha256'] != sha(BINDINGS[label[0]])):
                raise ValueError('slot_result_lost_its_registered_product_or_freeze/' + label)
            slot_results[label] = checksum
            row['result_sha256'] = checksum
            counts = (result.get('budget') or {}).get('counts') or counts
            if publication.is_file():
                receipt = read(publication)
                if receipt['label'] != label or receipt['result_sha256'] != checksum:
                    raise ValueError('slot_publication_mismatch/' + label)
                row.update(status=receipt['status'], publication_sha256=sha(publication))
        slots.append(row)
    for number in (1, 2, 3):
        path = EXTERNAL / 'preflight/pair_checks' / f'AFTER_PAIR_{number:02d}.json'
        if not path.is_file():
            continue
        receipt = read(path)
        pair = ORDER[(number - 1) * 2:number * 2]
        if receipt['passed'] and (receipt['freeze_sha256'] != frozen
                or receipt['slot_result_sha256'] != {label: slot_results[label] for label in pair}):
            raise ValueError('quality_receipt_not_bound_to_actual_pair/' + str(number))
        receipts[path.name] = {'sha256': sha(path), 'passed': receipt['passed']}

    passed = (controls.get('passed') is True and review.get('passed') is True
              and review['freeze_sha256'] == frozen and review['passed_slot_count'] == 6
              and review['cold_index_threshold_percent'] == 20 and review['cold_RPC_improved_pairs_required'] == 2
              and review['median_cold_index_reduction_percent'] >= 20 and review['cold_RPC_improved_pairs'] >= 2
              and review['median_cold_RPC_delta_ms'] < 0
              and all(row['status'] == 'completed' for row in slots)
              and len(receipts) == 3 and all(row['passed'] for row in receipts.values()))
    if passed and (counts['Blender_start_attempts'], counts['business_admissions'],
                   counts['all_raster_upper'], counts['all_raster_actual'], counts['consumer_admissions']) != (
                       6, 12, 18, 18, 0):
        raise ValueError('actual_complete_experiment_denominators_disagree')
    names = ('checks/PROJECTED_BOUNDS_CONTROLS.json', 'checks/LIVE_REVIEW.json',
             'REPORT.md', 'RUNTIME_INDEX.json', 'install/BUILD_INSTALL.json')
    save(NS / 'DECISION.json', {
        'task': 'M4-CROSS-SCALE-PROJECTED-BOUNDS-001', 'passed': bool(passed),
        'offline_passed': controls.get('passed', False), 'freeze_sha256': frozen, 'products': products,
        'product_diff_files': 1, 'slots': slots, 'planned_pairs': 3, 'actual_ledger_counts': counts,
        'quality_passed': review.get('quality_passed', False),
        'performance_passed': review.get('performance_passed', False),
        'replacements': 0, 'asset_rebuilds': 0, 'model_consumers': 0, 'paid_API_calls': 0,
        'original_quality_receipts': receipts,
        'evidence_sha256': {name: sha(NS / name) for name in names if (NS / name).is_file()},
    })
    path = NS / 'CONTENT_MANIFEST.json'
    rows = [{'path': item.relative_to(NS).as_posix(), 'sha256': sha(item), 'bytes': item.stat().st_size}
            for item in sorted(NS.rglob('*')) if item.is_file() and item != path]
    if any(row['path'].endswith('.pyc') for row in rows):
        raise ValueError('generated_bytecode_must_stay_outside_evidence')
    save(path, {'count': len(rows), 'files': rows, 'self_excluded': True})
    print('Sealed', len(rows) + 1, sha(path), 'passed', bool(passed))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('archive', 'finalize'))
    globals()[parser.parse_args().action]()
