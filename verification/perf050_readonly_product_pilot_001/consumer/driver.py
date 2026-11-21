"""Use the retained fresh ChatGPT CLI loop for one natural prompt per arm."""

from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
NS = HERE.parent
HARNESS = NS / 'harness'
sys.path.insert(0, str(HARNESS))
from common import SLOTS, load, read, save, sha
import bridge


PRIOR = NS.parent / 'm4_live_source_region_task_003'
DENSE = NS.parent / 'm4_dense_panel_sweep_formal_001'
THIN = HERE / 'thin_stdio.py'
PROMPT = NS / 'inputs/PROMPT.txt'
LABELS = {'N1': 'N', 'P1': 'P'}


def consumer_adapter():
    if Path(bridge.__file__).resolve() != HARNESS / 'bridge.py':
        raise ValueError('pilot_consumer_must_share_the_actual_pilot_bridge')
    dense = load('_perf050_dense_adapter', DENSE / 'harness/consumer.py')
    adapter_path = PRIOR / 'consumer_adapter.py'
    adapter = load('_perf050_existing_chatgpt_consumer', adapter_path)
    adapter.THIN = THIN
    contract = adapter.consumer_contract
    contract.archive_turn = dense.reused_function(PRIOR / 'consumer_contract.py', 'archive_turn',
                                                  dict(vars(contract)), dense.remove_old_task_condition)
    retained, proof = adapter.consumer_adapter()
    turn = dense.reused_function(adapter.LOOP, 'consume_turn', dict(retained.__globals__), dense.count_business_calls)
    paths = {Path(row['path']).resolve() for row in proof['execution_sources']}
    paths.update((Path(__file__).resolve(), HARNESS / 'bridge.py', THIN, adapter_path,
                  DENSE / 'harness/consumer.py', PRIOR / 'consumer_contract.py', DENSE / 'thin_stdio.py',
                  PRIOR / 'thin_stdio.py'))
    proof.update(schema='perf050-readonly-product-pilot-consumer-v1',
                 actual_tools_by_group={key: sorted(value) for key, value in bridge.TOOL_NAMES.items()},
                 business_tool_attempt_limit=bridge.TOOL_LIMIT, completed_CLI_tool_limit=bridge.TOOL_LIMIT,
                 natural_prompt_no_product_first_call_constraint=True,
                 execution_sources=[{'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
                                    for path in sorted(paths)])
    return turn, proof, adapter.metadata


def consume_slot(label, slot_root, endpoint, owner_output, deadline_ns, owned_deadline_ns):
    group = LABELS.get(label)
    if (group is None or SLOTS.get(label) != (group, 'formal')
            or not time.perf_counter_ns() < deadline_ns < owned_deadline_ns):
        raise ValueError('registered_pilot_formal_slot_and_absolute_deadlines_required')
    endpoint = Path(endpoint).resolve()
    description = read(endpoint)
    if description['chain_deadline_ns'] != deadline_ns or description['host'] != '127.0.0.1':
        raise ValueError('pilot_consumer_requires_owned_loopback_original_deadline')
    turn, proof, metadata = consumer_adapter()
    slot = Path(slot_root).resolve()
    folder, work = slot / 'consumer', slot / 'workspace'
    prompt = PROMPT.read_bytes()
    if not prompt.decode('utf-8').strip() or prompt.startswith(b'\xef\xbb\xbf'):
        raise ValueError('nonempty_original_UTF8_natural_prompt_required')
    cell = {'endpoint': str(endpoint), 'group': group, 'audit_dir': str(Path(owner_output).resolve())}
    record = turn(episode_id='PERF050-READONLY-PRODUCT-PILOT-001-' + label, turn_index=1, folder=folder,
                  work=work, cell=cell, install={'python': proof['Python_path']},
                  plan={'model_consumer_enabled': True}, prompt=prompt, episode_deadline_ns=deadline_ns,
                  turn_deadline_ns=deadline_ns, expected_thread_id=None)
    configuration = metadata(folder, proof, record)
    save(folder / 'ACTUAL_CONFIGURATION.json', configuration)
    return {'slot_id': label, 'group': group, 'status': record['status'], 'consumer_path': str(folder),
            'consumer_record': str(folder / 'CONSUMER.json'), 'adapter_proof': proof,
            'model_configuration': configuration, 'prompt_sha256': sha(PROMPT)}
