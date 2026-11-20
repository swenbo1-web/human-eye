"""Run the six fixed engineering slots serially and preserve the observed denominator."""

from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import can_continue, publication, verify_freeze
from common import EXTERNAL, ORDER, append


def sequence():
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('registered_isolated_interpreter_required')
    freeze = verify_freeze()
    directory = EXTERNAL / 'preflight'
    directory.mkdir(parents=True)
    journal = directory / 'SEQUENCE.jsonl'
    with journal.open('x'):
        pass
    for label in ORDER:
        append(journal, {'event': 'start', 'label': label, 'admitted_ns': time.perf_counter_ns(),
                         'freeze_sha256': freeze})
        launched = subprocess.run([sys.executable, '-I', '-B', str(NS / 'harness/run_slot.py'), label])
        if not (EXTERNAL / 'slots' / label / 'SLOT_PUBLICATION.json').is_file():
            append(journal, {'event': 'stop_without_slot_publication', 'label': label,
                             'exit_code': launched.returncode, 'closed_ns': time.perf_counter_ns()})
            return 1
        result, receipt = publication(label, freeze)
        safe = can_continue(result, receipt)
        append(journal, {'event': 'publication', 'label': label, 'status': receipt['status'],
                         'exit_code': launched.returncode, 'safe_for_next_slot': safe,
                         'original_slot_result_sha256': receipt['result_sha256'], 'closed_ns': time.perf_counter_ns()})
        if not safe:
            print('Unconfirmed host or original result at', label, flush=True)
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(sequence())
