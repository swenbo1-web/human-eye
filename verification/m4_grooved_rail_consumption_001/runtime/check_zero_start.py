"""Exercise consumer startup failure without launching a process or a model."""

import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
OUT = HERE / 'zero_start_checks_01'


def main():
    OUT.mkdir(exist_ok=False)
    spec = importlib.util.spec_from_file_location('_grooved_rail_zero_start_transport', HERE / 'consumer_transport.py')
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    results = []
    prompt = (HERE.parent / 'input/PROMPT.txt').read_bytes()
    for group in ('N', 'P'):
        temporary = OUT / 'tmp' / group
        folder = temporary / 'cells/synthetic_zero_start'
        folder.mkdir(parents=True)
        cell = {'group': group, 'endpoint': str(folder / 'synthetic_endpoint.json'), 'audit_dir': str(folder / 'owner')}
        (folder / 'cell.json').write_text(json.dumps(cell), encoding='utf8')
        with patch.object(transport, 'HERE', temporary), patch.object(transport, 'ROOT', temporary), \
                patch.object(transport.subprocess, 'Popen', side_effect=OSError('synthetic launch failure before any process')) as launched:
            record = transport.consume({'cell': 'synthetic_zero_start', 'group': group, 'task': 'T1', 'round': 1},
                {'python': 'synthetic-python'}, {'max_session_seconds': 450, 'image_count': 0, 'new_images': 0, 'inputs': {}},
                prompt)
        assert launched.call_count == 1
        assert record['status'] == 'failed' and not record['valid_completion'] and not record['safe_to_continue']
        assert record['consumer_pid'] is None and record['thread_id'] is None and record['final'] is None
        assert not record['process_reaped'] and not record['readers_stopped'] is False
        assert record['input_image_count'] == record['input_image_bytes'] == 0
        assert not record['image_delivery']['CLI_process_launched']
        assert len(record['errors']) == 1 and record['errors'][0]['type'] == 'OSError'
        assert record['input_sha256'] == hashlib.sha256(prompt).hexdigest()
        assert record['input_text_bytes'] == len(prompt)
        assert (folder / 'CONSUMER.json').is_file()
        results.append({'group': group, 'recorded_failed_before_process': True, 'model_started': False,
                        'record_path': str(folder / 'CONSUMER.json')})
    value = {'passed': True, 'checks': 2, 'records': results, 'real_process_launches': 0,
             'Blender_sessions': 0, 'model_consumers': 0,
             'transport_sha256': hashlib.sha256((HERE / 'consumer_transport.py').read_bytes()).hexdigest(),
             'common_prompt_sha256': hashlib.sha256(prompt).hexdigest(),
             'common_prompt_bytes': len(prompt),
             'scope': 'startup failure creates a deliverable failed consumer record; driver not_run tail is checked separately'}
    (OUT / 'RESULTS.json').write_text(json.dumps(value, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps(value))


if __name__ == '__main__':
    main()
