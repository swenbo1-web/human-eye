"""Single authorized invocation of the frozen formal function."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import time
import traceback

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
process_file = HERE / 'PROCESS.json'
assert not (BATCH / 'STARTED.json').exists(), 'existing STARTED; no repeat'
assert not (BATCH / 'RUN_RESULT.json').exists(), 'existing RUN_RESULT; no repeat'
assert sha(BATCH / 'PLAN.json') == 'bd8af1e9619ccf9dad8c43a3ecf17eb240843f5b76f4ca9390b8a283ecc00096'
assert sha(BATCH / 'GO.json') == 'd962e9ee0e1ad8cdce22683b2bc38b9558efe3a96f146f525ea9d5e5cb3f458c'
assert sha(BATCH / 'runtime/driver.py') == '8ac3d68fcc6d36005cea661e0c621c3bd3526765d5462c76b158ffe94590c230'
receipt = {'controller_pid': os.getpid(), 'controller_parent_pid': os.getppid(),
           'started_ns': time.perf_counter_ns(), 'phase': 'calling_frozen_run_models_once',
           'PLAN_sha256': sha(BATCH / 'PLAN.json'), 'GO_sha256': sha(BATCH / 'GO.json'),
           'driver_sha256': sha(BATCH / 'runtime/driver.py')}
with process_file.open('x', encoding='utf8') as stream:
    json.dump(receipt, stream, indent=2)
try:
    namespace = runpy.run_path(str(BATCH / 'runtime/driver.py'), run_name='_sgc_formal_control')
    result = namespace['run_models']()
    records = result['records']
    summary = {'terminal': True, 'started_cells': result['started_cells'], 'stop': result['stop'],
               'owner_cleanup_confirmed_records': sum(bool(row.get('finish') and row['finish'].get('confirmed')) for row in records),
               'consumer_launcher_reaped_records': sum(bool(row.get('consumer') and row['consumer'].get('process_reaped')) for row in records),
               'cleanup_scope': 'existing receipts only; unexposed runtime EXIT remains unknown'}
    receipt.update(phase='terminal_function_return', wrapper_exit_code=0, summary=summary)
    print(json.dumps(summary))
except BaseException as exc:
    receipt.update(phase='controller_exception', wrapper_exit_code=1,
                   exception={'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()})
    raise
finally:
    receipt['ended_ns'] = time.perf_counter_ns()
    process_file.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8', newline='\n')
