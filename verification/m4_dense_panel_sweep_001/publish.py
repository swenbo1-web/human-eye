"""Seal original qualification and formal artifacts with the full denominator."""

import argparse
from pathlib import Path
import subprocess
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import PRODUCT, verify_freeze
from common import ASSET_SHA256, EXTERNAL, FORMAL, ORDER, PRODUCT_BINDING, ROOT, asset_identity, load, read, save, sha


BASE = '17bce4aa30f8cf9a3d044c0eb856935a8dccf9d9'


def archive():
    verify_freeze()
    original = load('_dense_panel_original_archive', FORMAL / 'publish.py')
    original.NS, original.EXTERNAL = NS, EXTERNAL
    original.archive()


def finalize():
    frozen = verify_freeze()
    asset_identity()
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    changes = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT).decode().splitlines()
    if any(not path.startswith(prefix) for path in changes):
        raise ValueError('product_or_evidence_delta_outside_registered_namespace')
    product_gate_path = NS / 'checks/QUALIFICATION_QP.json'
    product_gate = read(product_gate_path)
    slot_dirs = EXTERNAL / 'slots'
    actual_order = [label for label in ORDER if (slot_dirs / label).is_dir()]
    if (actual_order != list(ORDER[:len(actual_order)])
            or set(actual_order) != {path.name for path in slot_dirs.iterdir()}
            or not actual_order or actual_order[0] != 'QP'):
        raise ValueError('registered_slot_order_or_no_replacement_rule_violated')
    raw_statuses = []
    ledger_counts = None
    for label in ORDER:
        slot = slot_dirs / label
        path, publication_path = (slot / name for name in ('SLOT_RESULT.json', 'SLOT_PUBLICATION.json'))
        row = {'label': label, 'status': 'incomplete' if slot.exists() else 'unrun'}
        if path.is_file() and publication_path.is_file():
            result, publication = read(path), read(publication_path)
            digest = sha(path)
            if (result['label'] != label or publication['label'] != label or publication['result_sha256'] != digest
                    or result['freeze_sha256'] != frozen or result['asset_sha256'] != ASSET_SHA256
                    or result.get('paid_API_calls', 0) != 0):
                raise ValueError('actual_publication_does_not_match_frozen_run/' + label)
            if label in ('QP', 'QN') and result['model_consumers'] != 0:
                raise ValueError('model_in_zero_model_qualification/' + label)
            if label == 'QP' and (result['product_source_sha256'] != PRODUCT['source_sha256']
                    or result['product_binding_sha256'] != sha(PRODUCT_BINDING)):
                raise ValueError('actual_qualification_product_does_not_match_frozen_install')
            row.update(status=publication['status'], result_sha256=digest, publication_sha256=sha(publication_path),
                       model_consumers=result['model_consumers'])
            ledger_counts = (result.get('budget') or {}).get('counts') or ledger_counts
        raw_statuses.append(row)
    if product_gate.get('passed') is not True and actual_order != ['QP']:
        raise ValueError('downstream_slot_opened_without_passing_first_qualification')
    final_path = NS / 'checks/FORMAL_REVIEW.json'
    final = read(final_path) if final_path.is_file() else {}
    model_slots = [row for row in raw_statuses if row['label'] not in ('QP', 'QN')]
    files = ('FROZEN.json', 'truth/CURRENT_TRUTH.json', 'checks/QUALIFICATION_QP.json',
             'checks/QUALIFICATION_QN.json', 'checks/FORMAL_REVIEW.json', 'REPORT.md', 'RUNTIME_INDEX.json')
    save(NS / 'DECISION.json', {
        'task': 'M4-DENSE-PANEL-SWEEP-001', 'freeze_sha256': frozen, 'product': PRODUCT,
        'passed': final.get('passed') is True, 'product_diff_files': 0, 'product_qualification_passed': product_gate['passed'],
        'product_qualification_reason': product_gate.get('reason'),
        'qualification_denominator': 2, 'formal_model_slots_denominator': 6,
        'actual_qualification_slots': len(actual_order) - sum(row['status'] != 'unrun' for row in model_slots),
        'actual_formal_model_slots': sum(row.get('model_consumers', 0) for row in model_slots),
        'actual_ledger_counts': ledger_counts, 'slots': raw_statuses, 'api_calls': 0, 'replacements': 0,
        'asset_rebuilds': 0, 'evidence_sha256': {name: sha(NS / name) for name in files if (NS / name).is_file()},
    })
    manifest = NS / 'CONTENT_MANIFEST.json'
    rows = [{'path': item.relative_to(NS).as_posix(), 'bytes': item.stat().st_size, 'sha256': sha(item)}
            for item in sorted(NS.rglob('*')) if item.is_file() and item != manifest]
    if any(row['path'].endswith('.pyc') for row in rows):
        raise ValueError('generated_bytecode_in_evidence_folder')
    save(manifest, {'count': len(rows), 'files': rows, 'self_excluded': True})
    print('Sealed', len(rows) + 1, sha(manifest), 'product_qualification', product_gate['passed'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('archive', 'finalize'))
    globals()[parser.parse_args().action]()
