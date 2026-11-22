"""Run the existing cold CLI loop with the same new prompt in both arms."""

from hashlib import sha256
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
NS = HERE.parent
HARNESS = NS / 'harness'
PILOT = NS.parent / 'perf050_readonly_product_pilot_001'
PROMPT = NS / 'inputs/PROMPT.txt'
PROMPT_SHA = '254f79b43eaf77a305a2372a77f26454a3aac75882591b845533ca6c805ce771'
THIN = HERE / 'thin_stdio.py'


sys.path.insert(0, str(HARNESS))
from common import FORMAL_LABELS, SLOTS, load, read, save, sha

LABELS = {label: SLOTS[label][0] for label in FORMAL_LABELS}
import bridge


def consumer_adapter():
    paths = sys.path[:]
    try:
        prior = load('_perf050_transfer_retained_cli_loop', PILOT / 'consumer/driver.py')
    finally:
        sys.path[:] = paths
    prior.HARNESS, prior.THIN = HARNESS, THIN
    turn, proof, metadata = prior.consumer_adapter()
    own = Path(__file__).resolve()
    proof['execution_sources'].append({'path': str(own), 'bytes': own.stat().st_size, 'sha256': sha(own)})
    proof['schema'] = 'm4-dense-sweep-integrated-native-pilot-001-consumer-v1'
    if (Path(bridge.__file__).resolve() != HARNESS / 'bridge.py' or proof['business_tool_attempt_limit'] != 12
            or proof['completed_CLI_tool_limit'] != 12 or
            (proof['CLI_version'], proof['model'], proof['reasoning_effort'], proof['service_tier']) !=
            ('0.152.1', 'gpt-6.1-sol', 'medium', 'default')):
        raise ValueError('retained_transfer_CLI_or_tool_limits_changed')
    return turn, proof, metadata


def consume_slot(label, slot_root, endpoint, owner_output, deadline_ns, owned_deadline_ns):
    group = LABELS.get(label)
    if (group is None or SLOTS.get(label) != (group, 'formal')
            or not time.perf_counter_ns() < deadline_ns < owned_deadline_ns):
        raise ValueError('registered_transfer_arm_and_absolute_deadlines_required')
    endpoint = Path(endpoint).resolve()
    description = read(endpoint)
    if description['chain_deadline_ns'] != deadline_ns or description['host'] != '127.0.0.1':
        raise ValueError('transfer_consumer_requires_owned_loopback_original_deadline')
    prompt = PROMPT.read_bytes()
    if sha256(prompt).hexdigest() != PROMPT_SHA or not prompt.decode('utf-8').strip():
        raise ValueError('original_shared_transfer_prompt_required')
    turn, proof, metadata = consumer_adapter()
    slot = Path(slot_root).resolve()
    folder, work = slot / 'consumer', slot / 'workspace'
    cell = {'endpoint': str(endpoint), 'group': group, 'audit_dir': str(Path(owner_output).resolve())}
    record = turn(episode_id='M4-DENSE-SWEEP-INTEGRATED-NATIVE-PILOT-001-' + label, turn_index=1, folder=folder,
                  work=work, cell=cell, install={'python': proof['Python_path']},
                  plan={'model_consumer_enabled': True}, prompt=prompt, episode_deadline_ns=deadline_ns,
                  turn_deadline_ns=deadline_ns, expected_thread_id=None)
    configuration = metadata(folder, proof, record)
    save(folder / 'ACTUAL_CONFIGURATION.json', configuration)
    return {'slot_id': label, 'group': group, 'status': record['status'], 'consumer_path': str(folder),
            'consumer_record': str(folder / 'CONSUMER.json'), 'adapter_proof': proof,
            'model_configuration': configuration, 'prompt_sha256': PROMPT_SHA}
