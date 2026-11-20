"""Seal real answers, formal footage, and the frozen comparison verdict."""

import argparse
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import publication, verify_freeze
from common import ARMS, EXTERNAL, ORDER, ROOT, asset_identity, load, read, save, sha


BASE = '69c48d35f581b72ef8762ccf5cdae545adaaf882'


def answers():
    freeze = verify_freeze(NS / 'FROZEN.json')
    records = []
    for label in ORDER:
        slot = EXTERNAL / 'slots' / label
        row = {'slot': label, 'status': 'unconfirmed' if slot.exists() else 'unrun',
               'slot_result_sha256': None, 'published_ns': None, 'path': None, 'original_path': None,
               'sha256': None, 'bytes': None}
        if (slot / 'SLOT_PUBLICATION.json').is_file():
            result, published = publication(label, freeze)
            row.update(status=published['status'], slot_result_sha256=published['result_sha256'],
                       published_ns=published['published_ns'])
            if result.get('answer') is not None:
                source = slot / 'consumer/PUBLIC_FINAL.txt'
                original = result['answer']
                raw = source.read_bytes()
                if Path(original['path']).resolve() != source.resolve() or sha(source) != original['sha256'] or len(raw) != original['bytes']:
                    raise ValueError('actual_answer_not_bound_to_published_slot/' + label)
                target = NS / 'answers' / f'{label}.txt'
                target.parent.mkdir(exist_ok=True)
                with target.open('xb') as out:
                    out.write(raw)
                row.update(path=str(target), original_path=str(source), sha256=sha(target), bytes=len(raw))
        records.append(row)
    save(NS / 'ANSWERS_SEALED.json', {'answers': records, 'sealed_ns': time.perf_counter_ns(),
                                    'freeze_sha256': freeze, 'replacement_consumers': 0})


def archive():
    verify_freeze(NS / 'FROZEN.json')
    script = NS.parent / 'm4_cross_scale_live_task_formal_001/publish.py'
    prior = load('_rail_formal_original_archive', script)
    prior.NS, prior.EXTERNAL = NS, EXTERNAL
    prior.archive()


def seal():
    frozen_path = NS / 'FROZEN.json'
    freeze = verify_freeze(frozen_path)
    qualification = read(frozen_path)['derived_qualification_sha256']
    asset_identity()
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT).decode().splitlines()
    if any(not name.startswith(prefix) for name in changed):
        raise ValueError('change_outside_formal_verification_scope')
    cost = read(NS / 'RUNTIME_REVIEW.json')
    if (cost['freeze_sha256'], cost['qualification_sha256']) != (freeze, qualification):
        raise ValueError('formal_cost_timing_bound_to_different_trial')
    quality = read(NS / 'scoring/QUALITY.json')
    followups = read(NS / 'scoring/FOLLOWUPS.json')
    if [row['slot'] for row in quality['slots']] != list(ORDER) or [row['label'] for row in cost['slots']] != list(ORDER):
        raise ValueError('registered_slot_denominator_unavailable')
    recorder = EXTERNAL / 'slots'
    actual_dirs = {path.name for path in recorder.iterdir()} if recorder.exists() else set()
    if actual_dirs != set(ORDER[:len(actual_dirs)]):
        raise ValueError('out_of_order_formal_slot_or_replacement')
    counts = {}
    rows = []
    for label in ORDER:
        slot = recorder / label
        row = {'label': label, 'arm': ARMS[label], 'status': 'unrun', 'model_consumers': 0}
        if (slot / 'SLOT_PUBLICATION.json').is_file():
            result, pub = publication(label, freeze)
            if result['qualification_sha256'] != qualification or result['phase'] != 'formal' or result['paid_API_calls'] != 0:
                raise ValueError('actual_formal_slot_outside_approved_scope/' + label)
            row.update(status=pub['status'], model_consumers=result['model_consumers'], result_sha256=pub['result_sha256'],
                       publication_sha256=sha(slot / 'SLOT_PUBLICATION.json'))
            counts = (result.get('budget') or {}).get('counts') or counts
        elif label in actual_dirs:
            row.update(status='unconfirmed', model_consumers=None)
        rows.append(row)
    models = sum(row['model_consumers'] or 0 for row in rows)
    if (models > 6 or any(counts.get(field, 0) > max_count for field, max_count in (
            ('Blender_start_attempts', 6), ('consumer_admissions', 6), ('all_raster_upper', 72)))):
        raise ValueError('actual_ledger_over_frozen_formal_budget')
    perf = cost['formal_comparison']
    quality_counts = quality['complete_counts']
    conditions = {'prior_qualifications_used_via_derived_gate': True,
        'complete_quality_both_arms': quality_counts == {'A': 3, 'B': 3},
        'B_first_packet_blocker_evidence_adopted_in_each_slot': quality['blocker_adoption_count'] == 3,
        'fewer_blocker_followups': followups['followup_gate_passed'],
        'complete_time': perf['time_gate_passed'], 'raw_CLI_usage': perf['CLI_usage_gate_passed'],
        'six_fresh_consumers': models == len(perf['actual_fresh_thread_ids']) == 6 and perf['unique_fresh_threads']}
    summaries = ('REPORT.md', 'ANSWERS_SEALED.json', 'qualification/DERIVED.json', 'RUNTIME_REVIEW.json',
                 'RUNTIME_INDEX.json', 'scoring/QUALITY.json', 'scoring/FORMAL_EVIDENCE.json',
                 'scoring/CLAIMS.json', 'scoring/FOLLOWUPS.json', 'scoring/FOLLOWUP_NOTES.json')
    save(NS / 'DECISION.json', {'task': 'M4-RAIL-BLOCKER-CONSUMPTION-FORMAL-001', 'passed': all(conditions.values()),
        'freeze_sha256': freeze, 'qualification_sha256': qualification, 'old_qualification_original_passed': False,
        'gates': conditions, 'slots': rows, 'new_qualifications': 0, 'formal_slots_planned': len(ORDER),
        'formal_slots_started': len(actual_dirs), 'formal_models_observed': models,
        'quality_complete_by_arm': quality_counts, 'B_slots_adopting_both_first_packet_blockers': quality['blocker_adoption_count'],
        'paired_B_followup_reduction_count': followups['B_fewer_blocker_followup_pairs'],
        'new_run_budget_counts': counts, 'replacements': 0, 'asset_rebuilds': 0, 'paid_API_calls': 0,
        'Google_calls': 0, 'product_diff_files': 0, 'evidence_sha256': {name: sha(NS / name) for name in summaries}})
    manifest = NS / 'CONTENT_MANIFEST.json'
    files = [{'path': f.relative_to(NS).as_posix(), 'bytes': f.stat().st_size, 'sha256': sha(f)}
             for f in sorted(NS.rglob('*')) if f.is_file() and f != manifest]
    if any(row['path'].endswith(('.pyc', '.bak')) for row in files):
        raise ValueError('unexpected_generated_file_in_formal_evidence')
    save(manifest, {'count': len(files), 'files': files, 'self_excluded': True})
    print('Formal evidence sealed', len(files), sha(manifest), conditions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('answers', 'archive', 'seal'))
    globals()[parser.parse_args().action]()
