"""Run each pre-registered owned slot once, with a closed qualification gate."""

from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path[:0] = [str(NS / 'harness'), str(NS / 'qualification')]
from admission import (GATE_SCHEMA, can_continue, clean_qualification, publication, qualification_rows,
                       validate_admission, verify_freeze)
from common import EXTERNAL, ORDER, append, save, sha
from qualify import qualify


def sequence():
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('registered_isolated_interpreter_required')
    frozen_path = NS / 'FROZEN.json'
    freeze = verify_freeze(frozen_path)
    folder = EXTERNAL / 'preflight'
    folder.mkdir(parents=True)
    journal = folder / 'SEQUENCE.jsonl'
    with journal.open('x'):
        pass

    def execute(label, gate_sha=None):
        validate_admission(label, frozen_path)
        append(journal, {'event': 'start', 'label': label, 'admitted_ns': time.perf_counter_ns(),
                         'freeze_sha256': freeze, 'qualification_sha256': gate_sha})
        returned = subprocess.run([sys.executable, '-I', '-B', str(NS / 'harness/run_slot.py'), label])
        slot = EXTERNAL / 'slots' / label
        if not (slot / 'SLOT_PUBLICATION.json').is_file():
            append(journal, {'event': 'stop_without_slot_publication', 'label': label,
                             'exit_code': returned.returncode, 'closed_ns': time.perf_counter_ns()})
            return False
        result, published = publication(label, freeze)
        safe = clean_qualification(result, published) if gate_sha is None else can_continue(result, published)
        append(journal, {'event': 'publication', 'label': label, 'status': published['status'],
                         'exit_code': returned.returncode, 'safe_for_next_slot': safe,
                         'model_consumer_launched': result['model_consumers'], 'closed_ns': time.perf_counter_ns(),
                         'original_slot_result_sha256': published['result_sha256']})
        return safe

    reviews = []
    for label in ORDER[:2]:
        safe = execute(label)
        if (EXTERNAL / 'slots' / label / 'SLOT_PUBLICATION.json').is_file():
            reviews.append(qualify(label, freeze))
        if not safe:
            break
    passed = len(reviews) == 2 and all(review['passed'] is True for review in reviews)
    if passed:
        gate_rows = qualification_rows(freeze)
    else:
        by_label = {row['label']: row for row in reviews}
        gate_rows = []
        for label in ORDER[:2]:
            row = by_label.get(label)
            if row is None:
                gate_rows.append({'label': label, 'passed': False, 'status': 'unrun_or_no_publication'})
            else:
                gate_rows.append({'label': label, 'passed': row['passed'], 'result_sha256': row['slot_result_sha256'],
                                  'publication_sha256': row['publication_sha256'],
                                  'review_sha256': sha(NS / 'qualification' / f'{label}_REVIEW.json')})
    gate = NS / 'QUALIFICATION.json'
    save(gate, {'schema': GATE_SCHEMA, 'passed': passed, 'freeze_sha256': freeze, 'slots': gate_rows})
    if not passed:
        print('Zero-model qualification failed. All formal slots remain unrun.', flush=True)
        return 1
    gate_sha = sha(gate)
    for label in ORDER[2:]:
        if not execute(label, gate_sha):
            print('Formal schedule stopped at', label, 'because the host or original result could not be confirmed.',
                  flush=True)
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(sequence())
