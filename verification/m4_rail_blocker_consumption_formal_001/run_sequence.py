"""Run the six frozen fresh sessions in their registered order."""

from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import DERIVED, can_continue, publication, validate_admission, verify_freeze
from common import EXTERNAL, ORDER, append, sha


def sequence():
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('registered_isolated_interpreter_required')
    frozen_path = NS / 'FROZEN.json'
    freeze = verify_freeze(frozen_path)
    qualification = sha(DERIVED)
    folder = EXTERNAL / 'preflight'
    folder.mkdir(parents=True)
    journal = folder / 'FORMAL_SEQUENCE.jsonl'
    with journal.open('x'):
        pass
    for label in ORDER:
        admitted = validate_admission(label, frozen_path)
        if admitted != {'freeze_sha256': freeze, 'qualification_sha256': qualification}:
            raise ValueError('formal_sealed_admission_changed')
        append(journal, {'event': 'start', 'label': label, 'admitted_ns': time.perf_counter_ns(), **admitted})
        returned = subprocess.run([sys.executable, '-I', '-B', str(NS / 'harness/run_slot.py'), label])
        slot = EXTERNAL / 'slots' / label
        if not (slot / 'SLOT_PUBLICATION.json').is_file():
            append(journal, {'event': 'stop_without_slot_publication', 'label': label,
                             'exit_code': returned.returncode, 'closed_ns': time.perf_counter_ns()})
            return 1
        result, published = publication(label, freeze)
        safe = can_continue(result, published)
        append(journal, {'event': 'publication', 'label': label, 'status': published['status'],
                         'exit_code': returned.returncode, 'safe_for_next_slot': safe,
                         'model_consumer_launched': result['model_consumers'], 'closed_ns': time.perf_counter_ns(),
                         'original_slot_result_sha256': published['result_sha256']})
        if not safe:
            print('Formal schedule closed at', label, 'due to host or unconfirmed state', flush=True)
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(sequence())
