"""Seal the one candidate slot, installed identity and original runtime archive."""

import argparse
from pathlib import Path
import subprocess
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import PRODUCTS, verify_freeze
from common import BINDINGS, EXTERNAL, FORMAL, ROOT, load, read, save, sha


BASE = '39fd39cdad162bbe7e5eb68243881d39bb67d285'


def archive():
    verify_freeze()
    helper = load('_pixel_evidence_exact_runtime_archive', FORMAL / 'publish.py')
    helper.NS, helper.EXTERNAL = NS, EXTERNAL
    helper.archive()


def finalize():
    frozen = verify_freeze()
    namespace = NS.relative_to(ROOT).as_posix() + '/'
    changes = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT).decode().splitlines()
    if any(not name.startswith(namespace) for name in changes):
        raise ValueError('unexpected_change_outside_pixel_evidence_archive')
    slots = EXTERNAL / 'slots'
    if {path.name for path in slots.iterdir()} != {'P1'}:
        raise ValueError('exactly_one_original_candidate_slot_required')
    slot = slots / 'P1'
    path = slot / 'SLOT_RESULT.json'
    result = read(path)
    receipt = read(slot / 'SLOT_PUBLICATION.json')
    if (receipt['result_sha256'] != sha(path) or receipt['label'] != 'P1' or result['label'] != 'P1'
            or result['freeze_sha256'] != frozen or result['model_consumers'] != 0 or result['paid_API_calls'] != 0
            or result['product_source_sha256'] != PRODUCTS['P']['source_sha256']
            or result['product_binding_sha256'] != sha(BINDINGS['P'])):
        raise ValueError('original_candidate_publication_or_product_changed')
    review = read(NS / 'checks/LIVE_REVIEW.json')
    passed = receipt['status'] == 'completed' and review['passed'] is True
    counts = (result.get('budget') or {}).get('counts')
    if passed and (counts['all_raster_actual'], counts['all_raster_upper'], counts['business_admissions'],
                   counts['Blender_start_attempts'], counts['consumer_admissions']) != (3, 3, 2, 1, 0):
        raise ValueError('actual_test_denominator_outside_registered_candidate')
    save(NS / 'DECISION.json', {'passed': passed, 'freeze_sha256': frozen, 'slot': 'P1',
         'task': 'M4-CROSS-SCALE-PIXEL-EVIDENCE-001', 'product': PRODUCTS['P'], 'product_diff_files': 1,
         'runtime_status': receipt['status'], 'slot_result_sha256': sha(path), 'owned_denominator': 1,
         'model_consumers': 0, 'replacements': 0, 'actual_ledger_counts': counts,
         'evidence_sha256': {name: sha(NS / name) for name in
                             ('checks/PIXEL_CONTROLS.json', 'checks/LIVE_REVIEW.json', 'RUNTIME_INDEX.json', 'REPORT.md')}})
    manifest = NS / 'CONTENT_MANIFEST.json'
    files = [p for p in sorted(NS.rglob('*')) if p.is_file() and p != manifest]
    if any(p.suffix == '.pyc' for p in files):
        raise ValueError('unexpected_generated_bytecode_in_evidence_folder')
    rows = [{'path': p.relative_to(NS).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in files]
    save(manifest, {'files': rows, 'count': len(rows), 'self_excluded': True})
    print('Sealed', len(files) + 1, sha(manifest), 'passed', passed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('archive', 'finalize'))
    globals()[parser.parse_args().action]()
