"""Run the already authorized frozen six-slot sequence exactly once."""

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import time
import traceback


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent


def main():
    assert not (BATCH / 'FORMAL_PROCESS.json').exists()
    assert not (BATCH / 'STARTED.json').exists()
    started = time.perf_counter_ns()
    launch = {'started_ns': started, 'started_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'authorized six-slot driver, no retry or replacement', 'status': 'running'}
    with (BATCH / 'FORMAL_PROCESS.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(launch, stream, indent=2)
        stream.write('\n')
    spec = importlib.util.spec_from_file_location('_spatial_fact_formal_driver', HERE / 'driver.py')
    driver = importlib.util.module_from_spec(spec)
    result = None
    error = None
    try:
        spec.loader.exec_module(driver)
        result = driver.run_models()
    except BaseException as exception:
        error = {'type': type(exception).__name__, 'message': str(exception),
                 'traceback': traceback.format_exc()}
        with (BATCH / 'FORMAL_ERROR.json').open('x', encoding='utf8', newline='\n') as stream:
            json.dump(error, stream, indent=2)
            stream.write('\n')
        # The driver's completed-prefix records remain authoritative. A failure
        # before its first cell can still deliver all six not-run slots.
        path = BATCH / 'RUN_RESULT.json'
        if path.exists():
            result = json.loads(path.read_bytes())
        elif (BATCH / 'STARTED.json').exists():
            result = {'records': [], 'stop': 'controller_failure_before_first_cell',
                      'started_cells': 0, 'maximum_consumers': 6,
                      'all_planned_dispatched': False, 'no_replacements': True}
        if result is not None:
            result['stop'] = result.get('stop') or 'controller_exception_requires_review'
            result.setdefault('batch_started_ns', started)
            result['batch_ended_ns'] = time.perf_counter_ns()
            result['batch_wall_ns'] = result['batch_ended_ns'] - result['batch_started_ns']
            driver.save(path, result)
    terminal = {'started_ns': started, 'ended_ns': time.perf_counter_ns(),
                'ended_utc': datetime.now(timezone.utc).isoformat(),
                'status': 'terminal', 'controller_error': error,
                'started_cells': None if result is None else result['started_cells'],
                'stop': None if result is None else result['stop']}
    driver.save(BATCH / 'FORMAL_PROCESS.json', terminal)
    print(json.dumps({'terminal': True, 'started_cells': terminal['started_cells'],
                      'execution_exception': error is not None}))
    return 0 if result is not None and error is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
