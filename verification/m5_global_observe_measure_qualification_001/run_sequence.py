"""Run only the two frozen zero-model qualification slots."""

import json
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
import admission
from common import EXTERNAL, ORDER, append


def sequence():
    frozen = admission.verify_freeze()
    directory = EXTERNAL / 'preflight'
    directory.mkdir(parents=True)
    journal = directory / 'SEQUENCE.jsonl'
    with journal.open('x'):
        pass
    for label in ORDER:
        append(journal, {'event': 'start', 'label': label, 'admitted_ns': time.perf_counter_ns(),
                         'freeze_sha256': frozen})
        launched = subprocess.run([sys.executable, '-I', '-B', str(NS / 'harness/run_slot.py'), label])
        path = EXTERNAL / 'slots' / label / 'SLOT_PUBLICATION.json'
        if not path.is_file():
            append(journal, {'event': 'stop_without_slot_publication', 'label': label,
                             'exit_code': launched.returncode, 'closed_ns': time.perf_counter_ns()})
            return 1
        result, receipt = admission.publication(label, frozen)
        safe = admission.can_continue(result, receipt)
        append(journal, {'event': 'publication', 'label': label, 'status': receipt['status'],
                         'exit_code': launched.returncode, 'safe_for_next_slot': safe,
                         'original_slot_result_sha256': receipt['result_sha256'], 'closed_ns': time.perf_counter_ns()})
        if not safe:
            return 1
    return 0


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('pinned_interpreter_I_B_required')
    if sys.argv[1:] == ['--dispatch-smoke']:
        print(json.dumps({'entry': str(Path(__file__).resolve()), 'admission': str(Path(admission.__file__).resolve()),
                          'schema': admission.SCHEMA, 'current_product': admission.registered_product(),
                          'run_root': str(EXTERNAL.resolve()), 'order': list(ORDER),
                          'fresh_process_prepared_only': True}))
        return 0
    if sys.argv[1:]:
        raise ValueError('unregistered_sequence_arguments')
    return sequence()


if __name__ == '__main__':
    raise SystemExit(main())
