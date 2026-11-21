"""Run the previously accepted CLI loop with the single registered P3 cell."""

from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
NS = HERE.parent
HARNESS = NS / 'harness'
PILOT = NS.parent / 'perf050_readonly_product_pilot_001'
PROMPT = PILOT / 'inputs/PROMPT.txt'
PROMPT_SHA = 'ee9e22bfef64fc8799b57f0569a320ebe93a16ff8862c7e3d6ed6236b92be98e'
THIN = HERE / 'thin_stdio.py'

sys.path.insert(0, str(HARNESS))
from common import SLOTS, load, read, save, sha
import bridge


def consumer_adapter():
    paths = sys.path[:]
    try:
        prior = load('_perf050_p3_retained_cli_loop', PILOT / 'consumer/driver.py')
    finally:
        sys.path[:] = paths
    prior.HARNESS, prior.THIN = HARNESS, THIN
    turn, proof, metadata = prior.consumer_adapter()
    source = Path(__file__).resolve()
    proof['execution_sources'].append({'path': str(source), 'bytes': source.stat().st_size, 'sha256': sha(source)})
    proof['schema'] = 'perf050-source-region-final-image-p3-consumer-v1'
    if (Path(bridge.__file__).resolve() != HARNESS / 'bridge.py' or proof['business_tool_attempt_limit'] != 12
            or proof['completed_CLI_tool_limit'] != 12 or
            (proof['CLI_version'], proof['model'], proof['reasoning_effort'], proof['service_tier']) !=
            ('0.152.1', 'gpt-6.1-sol', 'medium', 'default')):
        raise ValueError('retained_consumer_configuration_or_current_tools_changed')
    return turn, proof, metadata


def consume_slot(label, slot_root, endpoint, owner_output, deadline_ns, owned_deadline_ns):
    if (label != 'P3' or SLOTS.get(label) != ('P', 'formal')
            or not time.perf_counter_ns() < deadline_ns < owned_deadline_ns):
        raise ValueError('registered_P3_and_original_absolute_deadlines_required')
    endpoint = Path(endpoint).resolve()
    description = read(endpoint)
    if description['chain_deadline_ns'] != deadline_ns or description['host'] != '127.0.0.1':
        raise ValueError('P3_consumer_requires_owned_loopback_original_deadline')
    prompt = PROMPT.read_bytes()
    if len(prompt) != 387 or sha(PROMPT) != PROMPT_SHA:
        raise ValueError('original_fixed_387_byte_prompt_required')
    turn, proof, metadata = consumer_adapter()
    slot = Path(slot_root).resolve()
    folder, work = slot / 'consumer', slot / 'workspace'
    cell = {'endpoint': str(endpoint), 'group': 'P', 'audit_dir': str(Path(owner_output).resolve())}
    record = turn(episode_id='PERF050-SOURCE-REGION-FINAL-IMAGE-P3', turn_index=1, folder=folder,
                  work=work, cell=cell, install={'python': proof['Python_path']},
                  plan={'model_consumer_enabled': True}, prompt=prompt, episode_deadline_ns=deadline_ns,
                  turn_deadline_ns=deadline_ns, expected_thread_id=None)
    configuration = metadata(folder, proof, record)
    save(folder / 'ACTUAL_CONFIGURATION.json', configuration)
    return {'slot_id': label, 'group': 'P', 'status': record['status'], 'consumer_path': str(folder),
            'consumer_record': str(folder / 'CONSUMER.json'), 'adapter_proof': proof,
            'model_configuration': configuration, 'prompt_sha256': PROMPT_SHA}
