"""Seal original answers, raw owned artifacts and the fixed comparison verdict."""

import argparse
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path[:0] = [str(NS / 'harness'), str(NS)]
from admission import publication, verify_freeze
from common import EXTERNAL, ORDER, ROOT, SLOTS, asset_identity, load, read, save, sha
from qualification_gate import external_qp


BASE = 'ea74b940dd78f3e467856659b197acdbe9710f6d'
FORMAL = NS.parent / 'm4_cross_scale_live_task_formal_001'


def answers():
    frozen = verify_freeze(NS / 'FROZEN.json')
    records = []
    for label in ORDER[1:]:
        slot = EXTERNAL / 'slots' / label
        row = {'slot': label, 'status': 'unrun', 'slot_result_sha256': None, 'published_ns': None,
               'path': None, 'original_path': None, 'sha256': None, 'bytes': None}
        if slot.exists():
            result, published = publication(label, frozen)
            row.update(status=published['status'], slot_result_sha256=published['result_sha256'],
                       published_ns=published['published_ns'])
            if result.get('answer') is not None:
                source = slot / 'consumer/PUBLIC_FINAL.txt'
                raw = source.read_bytes()
                if sha(source) != result['answer']['sha256'] or len(raw) != result['answer']['bytes']:
                    raise ValueError('original_model_final_text_changed/' + label)
                target = NS / 'answers' / (label + '.txt')
                target.parent.mkdir(exist_ok=True)
                with target.open('xb') as stream:
                    stream.write(raw)
                row.update(path=str(target), original_path=str(source), sha256=sha(target), bytes=len(raw))
        records.append(row)
    save(NS / 'ANSWERS_SEALED.json', {'answers': records, 'sealed_ns': time.perf_counter_ns(),
                                   'freeze_sha256': frozen, 'replacement_consumers': 0})


def archive():
    verify_freeze(NS / 'FROZEN.json')
    original = load('_dense_formal_original_runtime_archive', FORMAL / 'publish.py')
    original.NS, original.EXTERNAL = NS, EXTERNAL
    original.archive()


def finalize():
    frozen = verify_freeze(NS / 'FROZEN.json')
    asset_identity()
    qp, _ = external_qp()
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    changes = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT).decode().splitlines()
    if any(not path.startswith(prefix) for path in changes):
        raise ValueError('unregistered_product_or_evidence_scope_changed')
    gate_path = NS / 'QUALIFICATION.json'
    gate = read(gate_path) if gate_path.is_file() else {}
    gate_sha = sha(gate_path) if gate else None
    if gate and (gate['freeze_sha256'] != frozen or gate['external_QP_reused'] is not True
                 or gate['slots'][1] != {key: qp[key] for key in gate['slots'][1]}):
        raise ValueError('original_qualification_pair_changed')
    slot_dirs = EXTERNAL / 'slots'
    actual = [label for label in ORDER if (slot_dirs / label).is_dir()]
    if actual != list(ORDER[:len(actual)]) or slot_dirs.exists() and set(actual) != {p.name for p in slot_dirs.iterdir()}:
        raise ValueError('out_of_order_or_unregistered_slot_original')
    rows, counts = [], None
    for label in ORDER:
        row = {'label': label, 'group': SLOTS[label][0], 'phase': SLOTS[label][1], 'status': 'unrun', 'model_consumers': 0}
        if label in actual:
            original, pub = publication(label, frozen)
            if (original['paid_API_calls'] != 0 or original['model_consumers'] not in (0, 1)
                    or label == 'QN' and original['model_consumers'] != 0
                    or label != 'QN' and (gate.get('passed') is not True or original['qualification_sha256'] != gate_sha)):
                raise ValueError('actual_slot_outside_frozen_model_or_admission_scope/' + label)
            counts = (original.get('budget') or {}).get('counts') or counts
            row.update(status=pub['status'], model_consumers=original['model_consumers'],
                       result_sha256=pub['result_sha256'], publication_sha256=sha(EXTERNAL / 'slots' / label / 'SLOT_PUBLICATION.json'))
        rows.append(row)
    compare = read(NS / 'RUNTIME_REVIEW.json')
    if compare['freeze_sha256'] != frozen or compare['qualification_sha256'] != gate_sha:
        raise ValueError('cost_record_not_tied_to_the_same_experiment')
    quality_path = NS / 'scoring/QUALITY.json'
    quality = read(quality_path) if quality_path.is_file() else {}
    if quality and [item['slot'] for item in quality['slots']] != list(ORDER[1:]):
        raise ValueError('quality_missing_registered_formal_denominator')
    correct = quality.get('complete_counts', {'N': 0, 'P': 0})
    adoptions = quality.get('product_adoption_count', 0)
    perf = compare['formal_comparison']
    observed_models = sum(item['model_consumers'] for item in rows[1:])
    pass_gate = gate.get('passed') is True
    conditions = {'qualification': pass_gate, 'complete_quality_both_arms': correct == {'N': 3, 'P': 3},
                  'actual_adoption_each_plugin_slot': adoptions == 3, 'complete_time': perf['time_gate_passed'],
                  'raw_CLI_usage': perf['CLI_usage_gate_passed'],
                  'fresh_consumers': observed_models == len(perf['actual_fresh_thread_ids']) == 6 and perf['unique_fresh_threads']}
    passed = all(conditions.values())
    if observed_models > 6 or counts and (counts['Blender_start_attempts'] > 7
                                          or counts['all_raster_upper'] > 78
                                          or counts['consumer_admissions'] > 6):
        raise ValueError('observed_ledger_exceeded_frozen_limits')
    deliverables = ('REPORT.md', 'ANSWERS_SEALED.json', 'RUNTIME_REVIEW.json', 'RUNTIME_INDEX.json',
                    'QUALIFICATION.json', 'qualification/NATIVE_REVIEW.json', 'scoring/QUALITY.json',
                    'scoring/FORMAL_EVIDENCE.json', 'scoring/CLAIMS.json', 'checks/TOOL_REVIEW.json')
    save(NS / 'DECISION.json', {'task': 'M4-DENSE-PANEL-SWEEP-FORMAL-001', 'passed': passed,
        'freeze_sha256': frozen, 'qualification_sha256': gate_sha, 'gates': conditions, 'qualified_external_QP': qp,
        'new_native_qualifications_planned': 1, 'new_formal_slots_planned': 6, 'new_formal_model_slots_run': observed_models,
        'slots': rows, 'complete_correct_by_arm': correct, 'plugin_slots_with_actual_adoption': adoptions,
        'product_git': qp['product_git'], 'product_source_sha256': qp['product_source_sha256'], 'product_diff_files': 0,
        'actual_ledger_counts': counts, 'replacements': 0, 'asset_rebuilds': 0, 'paid_API_calls': 0,
        'evidence_sha256': {name: sha(NS / name) for name in deliverables if (NS / name).is_file()}})
    manifest = NS / 'CONTENT_MANIFEST.json'
    files = [{'path': path.relative_to(NS).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
             for path in sorted(NS.rglob('*')) if path.is_file() and path != manifest]
    if any(row['path'].endswith('.pyc') for row in files):
        raise ValueError('generated_bytecode_in_frozen_evidence')
    save(manifest, {'files': files, 'count': len(files), 'self_excluded': True})
    print('Sealed', len(files) + 1, sha(manifest), 'passed', passed, conditions)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('answers', 'archive', 'finalize'))
    globals()[parser.parse_args().action]()
