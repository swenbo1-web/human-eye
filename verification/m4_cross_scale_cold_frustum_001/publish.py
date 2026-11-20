"""Seal the actual paired results, original runtime and repository scope."""

import argparse
from pathlib import Path
import subprocess
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import PRODUCTS, verify_freeze
from common import BINDINGS, EXTERNAL, FORMAL, ORDER, ROOT, load, read, save, sha


BASE = 'a04838bef854e9ba7441e0374e96fea0e8aa080b'
RECEIPTS = EXTERNAL / 'preflight/pair_checks'


def archive():
    verify_freeze()
    helper = load('_cold_frustum_exact_runtime_archive', FORMAL / 'publish.py')
    helper.NS, helper.EXTERNAL = NS, EXTERNAL
    helper.archive()


def finalize():
    frozen = verify_freeze()
    namespace = NS.relative_to(ROOT).as_posix() + '/'
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT).decode().splitlines()
    if any(not path.startswith(namespace) for path in changed):
        raise ValueError('changes_outside_registered_evidence_namespace')
    review_path = NS / 'checks/PAIR_REVIEW.json'
    review = read(review_path)
    if review['cold_global_index_percent_reduction_threshold'] != 20:
        raise ValueError('registered_twenty_percent_gate_changed')
    slots, ledger = [], None
    for label in ORDER:
        slot = EXTERNAL / 'slots' / label
        row = {'label': label, 'arm': label[0], 'status': 'unrun'}
        if slot.exists():
            result = slot / 'SLOT_RESULT.json'
            publication = slot / 'SLOT_PUBLICATION.json'
            raw = read(result)
            pub = read(publication)
            if (pub['result_sha256'] != sha(result) or pub['label'] != label or raw['label'] != label
                    or raw['freeze_sha256'] != frozen or raw['model_consumers'] != 0 or raw['paid_API_calls'] != 0
                    or raw['product_source_sha256'] != PRODUCTS[label[0]]['source_sha256']
                    or raw['product_binding_sha256'] != sha(BINDINGS[label[0]])):
                raise ValueError('actual_slot_not_bound_to_registered_arm/' + label)
            ledger = raw.get('budget') or ledger
            row.update(status=pub['status'], result_sha256=sha(result), publication_sha256=sha(publication))
        slots.append(row)
    receipts = {p.name: sha(p) for p in sorted(RECEIPTS.glob('AFTER_PAIR_*.json'))}
    passed = bool(review['passed'] and review['reviewed_pair_count'] == review['reviewed_passing_pairs'] == 3
                  and all(row['status'] == 'completed' for row in slots) and len(receipts) == 3)
    if passed and sha(review_path) != receipts['AFTER_PAIR_03.json']:
        raise ValueError('final_pair_review_does_not_match_original_quality_gate')
    counts = (ledger or {}).get('counts')
    if passed and (counts['all_raster_actual'], counts['all_raster_upper'], counts['business_admissions'],
                   counts['Blender_start_attempts'], counts['consumer_admissions']) != (18, 18, 12, 6, 0):
        raise ValueError('actual_complete_experiment_denominators_disagree')
    save(NS / 'DECISION.json', {'passed': passed, 'freeze_sha256': frozen, 'slots': slots,
         'task': 'M4-CROSS-SCALE-COLD-FRUSTUM-001', 'products': PRODUCTS,
         'baseline_candidate_product_diff_files': 2, 'tested_pair_denominator': 3,
         'quality_passed': review['quality_passed'],
         'median_cold_index_and_RPC_gates_passed': review['median_cold_index_and_RPC_gates_passed'],
         'median_cold_global_index_percent_reduction': review['median_cold_global_index_percent_reduction'],
         'zero_model_and_replacements': True, 'actual_ledger_counts': counts,
         'original_quality_receipts': receipts,
         'final_evidence_sha256': {name: sha(NS / name) for name in
                                  ('checks/PAIR_REVIEW.json', 'checks/FRUSTUM_CONTROLS.json',
                                   'checks/FRUSTUM_HOT_REPLAY.json', 'REPORT.md', 'RUNTIME_INDEX.json')}})
    path = NS / 'CONTENT_MANIFEST.json'
    files = [p for p in sorted(NS.rglob('*')) if p.is_file() and p != path]
    if any(p.suffix == '.pyc' for p in files):
        raise ValueError('unexpected_generated_bytecode_in_evidence_folder')
    rows = [{'path': p.relative_to(NS).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in files]
    save(path, {'files': rows, 'count': len(rows), 'self_excluded': True})
    print('Sealed', len(files) + 1, sha(path), 'quality_passed', passed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('archive', 'finalize'))
    globals()[parser.parse_args().action]()
