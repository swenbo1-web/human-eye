"""Seal original responses, runtime receipts and the fixed product comparison."""

import argparse
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import PRODUCT_GIT, publication, verify_freeze
from common import EXTERNAL, ROOT, SLOTS, SOURCE_SHA, load, read, save, sha


BASE = '069a7b5d96f4f0f38d6340b2d041088ed6174bc8'
FORMAL = NS.parent / 'm4_cross_scale_live_task_formal_001'


def answers():
    frozen = verify_freeze(NS / 'FROZEN.json')
    records = []
    for label in ('N1', 'P1'):
        slot = EXTERNAL / 'slots' / label
        row = {'slot': label, 'status': 'unrun', 'slot_result_sha256': None, 'published_ns': None,
               'path': None, 'original_path': None, 'sha256': None, 'bytes': None}
        if not slot.exists():
            records.append(row)
            continue
        result, published = publication(label, frozen)
        row.update(status=published['status'], slot_result_sha256=published['result_sha256'],
                   published_ns=published['published_ns'])
        if result.get('answer') is not None:
            source = slot / 'consumer/PUBLIC_FINAL.txt'
            raw = source.read_bytes()
            if sha(source) != result['answer']['sha256'] or len(raw) != result['answer']['bytes']:
                raise ValueError('original_formal_public_answer_changed/' + label)
            target = NS / 'answers' / (label + '.txt')
            target.parent.mkdir(exist_ok=True)
            with target.open('xb') as stream:
                stream.write(raw)
            row.update(path=str(target), original_path=str(source), sha256=sha(target), bytes=len(raw))
        records.append(row)
    save(NS / 'ANSWERS_SEALED.json', {'answers': records, 'sealed_ns': time.perf_counter_ns(),
                                   'replacement_consumers': 0})


def costs():
    frozen = verify_freeze(NS / 'FROZEN.json')
    helper = load('_assembly_transfer_retained_costs', FORMAL / 'costs.py')
    helper.NS, helper.EXTERNAL = NS, EXTERNAL
    rows = []
    for label in SLOTS:
        summary = helper.slot_summary(label)
        if summary['status'] != 'unrun':
            original, published = publication(label, frozen)
            summary['status'] = published['status']
            summary['phase'] = original['phase']
            summary['asset_sha256'] = original['asset_sha256']
            summary['diagnostic_close'] = original.get('diagnostic_close')
        rows.append(summary)
    gate_path = NS / 'QUALIFICATION.json'
    save(NS / 'RUNTIME_REVIEW.json', {'slots': rows, 'new_asset_builds': 0, 'external_paid_API': 0,
         'cash_fees': None, 'provider_identity': None, 'actual_internal_provider_input': None,
         'qualification_sha256': sha(gate_path) if gate_path.exists() else None})


def archive():
    verify_freeze(NS / 'FROZEN.json')
    helper = load('_assembly_transfer_retained_archive', FORMAL / 'publish.py')
    helper.NS, helper.EXTERNAL = NS, EXTERNAL
    helper.archive()


def finalize():
    frozen = verify_freeze(NS / 'FROZEN.json')
    namespace = NS.relative_to(ROOT).as_posix() + '/'
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT).decode().splitlines()
    if any(not path.startswith(namespace) for path in changed):
        raise ValueError('product_or_other_evidence_changed_outside_this_test')
    gate_path = NS / 'QUALIFICATION.json'
    gate = read(gate_path) if gate_path.exists() else {'passed': False}
    qualification_sha = sha(gate_path) if gate_path.exists() else None
    slots, ledger = [], None
    for label in SLOTS:
        slot = EXTERNAL / 'slots' / label
        row = {'label': label, 'phase': SLOTS[label][1], 'status': 'unrun', 'model_consumers': 0}
        if slot.exists():
            original, pub = publication(label, frozen)
            if (original['phase'] == 'formal' and (gate['passed'] is not True
                    or original['qualification_sha256'] != qualification_sha)):
                raise ValueError('formal_original_not_bound_to_the_actual_qualification/' + label)
            ledger = original.get('budget') or ledger
            row.update(status=pub['status'], model_consumers=original['model_consumers'],
                       result_sha256=pub['result_sha256'])
        slots.append(row)
    shown = ('REPORT.md', 'ANSWERS_SEALED.json', 'RUNTIME_REVIEW.json', 'RUNTIME_INDEX.json')
    optional = ('QUALIFICATION.json', 'scoring/QUALITY.json', 'checks/TOOL_EVIDENCE.json')
    names = (*shown, *(name for name in optional if (NS / name).exists()))
    save(NS / 'DECISION.json', {'task': 'M4-CROSS-SCALE-ASSEMBLY-TRANSFER-001',
         'freeze_sha256': frozen, 'qualification_passed': gate['passed'],
         'qualification_sha256': qualification_sha, 'slots': slots,
         'qualification_denominator': 2, 'formal_denominator': 2, 'replacements': 0,
         'product_git': PRODUCT_GIT, 'product_source_sha256': SOURCE_SHA, 'product_diff_files': 0,
         'actual_ledger_counts': (ledger or {}).get('counts'),
         'evidence_sha256': {name: sha(NS / name) for name in names}})
    path = NS / 'CONTENT_MANIFEST.json'
    files = [p for p in sorted(NS.rglob('*')) if p.is_file() and p != path]
    if any(p.suffix == '.pyc' for p in files):
        raise ValueError('unexpected_bytecode_in_evidence_folder')
    rows = [{'path': p.relative_to(NS).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in files]
    save(path, {'files': rows, 'count': len(rows), 'self_excluded': True})
    print('Sealed', len(files) + 1, sha(path))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('answers', 'costs', 'archive', 'finalize'))
    globals()[parser.parse_args().action]()
