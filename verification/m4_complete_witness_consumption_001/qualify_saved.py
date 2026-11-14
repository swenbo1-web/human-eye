"""Judge the single saved qualification without product or raster execution."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
EXTERNAL = Path('D:/he_complete_witness_001')
PRODUCT_SHA256 = 'd8ad7003397d0c0611f54d128c0d0ad3433865b8d9f69b8b0519123752fe9f02'
INPUT_NAMES = ('scene', 'cameras', 'capture', 'product_binding')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def source_binding(freeze_path):
    frozen = read(freeze_path)
    for path, expected in frozen['files_sha256'].items():
        require(sha(path) == expected, 'frozen_qualification_source_changed:' + path)
    plan = read(HERE / 'PLAN.json')
    manifest_path = Path(plan['inputs']['input_manifest']).resolve()
    manifest = read(manifest_path)
    prompt_path = Path(plan['inputs']['prompt']).resolve()
    require(sha(prompt_path) == plan['expected_prompt_sha256'], 'frozen_prompt_identity')
    inputs = {name: manifest[name]['sha256'] for name in INPUT_NAMES}
    for name in INPUT_NAMES:
        path = Path(manifest[name]['path']).resolve()
        require(sha(path) == inputs[name], 'frozen_input_changed:' + name)
        require(frozen['files_sha256'].get(str(path)) == inputs[name], 'input_missing_from_freeze:' + name)
    truth_path = HERE / 'admin/TRUTH.json'
    truth = read(truth_path)
    require(truth['input_sha256'] == {name: inputs[name] for name in ('scene', 'cameras', 'capture')},
            'truth_source_input_binding')
    for path in (truth_path, HERE / 'PLAN.json', manifest_path, prompt_path,
                 HERE / 'saved_evidence.py', HERE / 'oracle.py', HERE / 'qualify_saved.py'):
        require(frozen['files_sha256'].get(str(path.resolve())) == sha(path),
                'required_judgment_input_not_frozen:' + str(path))
    binding = read(manifest['product_binding']['path'])
    require(binding['source_sha256'] == PRODUCT_SHA256, 'fixed_candidate_source')
    return frozen, plan, manifest, truth, inputs


def validate_entry(run, owner, run_root, frozen, plan, manifest):
    require(run['transport_passed'] is True and run['passed'] is True, 'qualification_transport_failed')
    for name, expected in (('actual_model_calls', 0), ('actual_product_calls', 1),
                           ('actual_business_tools', 1), ('actual_MCP_requests', 3),
                           ('successful_MCP_responses', 3)):
        require(type(run[name]) is int and run[name] == expected, 'qualification_count:' + name)
    require(type(run['actual_rasters']) is int and 1 <= run['actual_rasters'] <= 6,
            'qualification_raster_count')
    pid = run['actor_pid']
    require(type(pid) is int and pid > 0, 'qualification_actor_PID')
    require(Path(run['owner_output']).resolve() == owner, 'qualification_owned_output')
    require(run['source_freeze_sha256'] == sha(HERE / 'FROZEN.json')
            and run['prompt_sha256'] == plan['expected_prompt_sha256'], 'qualification_entry_source_binding')
    for path, expected in run['source_inputs_sha256'].items():
        require(frozen['files_sha256'].get(path) == expected and sha(path) == expected,
                'qualification_execution_source_binding:' + path)
    for path in (Path(plan['inputs']['input_manifest']), Path(plan['inputs']['prompt']),
                 *(Path(manifest[name]['path']) for name in INPUT_NAMES)):
        absolute = str(path.resolve())
        require(run['source_inputs_sha256'].get(absolute) == sha(path),
                'qualification_required_source_binding:' + absolute)

    endpoint = read(run_root / 'ENDPOINT.json')
    config = read(run_root / 'ACTOR_CONFIG.json')
    require(endpoint == run['endpoint'] and endpoint['actor_pid'] == pid
            and endpoint['chain_deadline_ns'] == run['original_deadline_ns'], 'qualification_endpoint_PID_deadline')
    require(config['group'] == 'P' and config['phase'] == 'preparation'
            and config['max_tool_calls'] == 12 and config['max_render_attempts'] == 6
            and config['whole_render_cap'] == 12 and config['phase_render_cap'] == 6
            and config['worker_deadline_ns'] == run['original_deadline_ns']
            and Path(config['output']).resolve() == owner
            and Path(config['budget_root']).resolve() == EXTERNAL / 'raster_budget'
            and Path(config['input_manifest']).resolve() == Path(plan['inputs']['input_manifest']).resolve(),
            'qualification_actual_actor_configuration')

    process = run['process_cleanup']
    close = run['owner_close']
    require(process['pid'] == pid and process['confirmed'] is True and process['reaped'] is True
            and process['process_handle_closed'] is True and process['exit_code'] == 0
            and process['kill_requested'] is False and not process['errors']
            and all(process['pipes_closed'].get(name) is True for name in ('stdin', 'stdout', 'stderr')),
            'qualification_held_process_cleanup')
    require(close == read(owner / 'CLOSE.json') and close['actor_pid'] == pid
            and close['confirmed'] is True and close['server_thread_stopped'] is True
            and not close['errors'], 'qualification_actual_owner_close')
    if 'actual_owner_pid' in run:
        require(run['actual_owner_pid'] == pid, 'qualification_PID_alias')
    if 'cleanup' in run:
        require(run['cleanup'] == {'process': process, 'owner': close}, 'qualification_cleanup_alias')

    observations = read(owner / 'OBSERVATIONS.json')
    metrics = read(owner / 'METRICS.json')
    require(observations['process_id'] == pid
            and metrics['tool_attempts'] == 1
            and metrics['common']['product_observation_calls'] == 1
            and metrics['common']['render_attempts'] == run['actual_rasters']
            and len(observations['render_attempts']) == run['actual_rasters'], 'qualification_owner_PID_counts')
    source = observations['source_inputs']
    for name in INPUT_NAMES:
        require(source[name + '_sha256'] == manifest[name]['sha256']
                and Path(source[name + '_path']).resolve() == Path(manifest[name]['path']).resolve(),
                'qualification_current_owner_source:' + name)
    require(source['manifest_sha256'] == sha(plan['inputs']['input_manifest']), 'qualification_owner_manifest')

    intents = [read(path) for path in sorted((EXTERNAL / 'raster_budget').glob('attempt_*/INTENT.json'))]
    require(len(intents) == run['actual_rasters']
            and [row['global_attempt'] for row in intents] == list(range(1, len(intents) + 1)),
            'qualification_shared_ledger_sequence')
    for intent in intents:
        require(intent['phase'] == 'preparation' and intent['process_id'] == pid
                and Path(intent['owner_output']).resolve() == owner and intent['origin'] == 'product'
                and intent['source_capture_sha256'] == manifest['capture']['sha256']
                and intent['source_scene_sha256'] == manifest['scene']['sha256'],
                'qualification_durable_intent_binding')

    request = read(owner / 'tool_01/REQUEST.json')
    response = read(owner / 'tool_01/RESPONSE.json')
    public = read(run_root / 'MCP_RESPONSE_03.json')
    sent = read(run_root / 'request_03/TCP_TX.bin')
    received = read(run_root / 'request_03/TCP_RX.bin')
    require(sent['args']['message'] == request and received['ok'] is True
            and received['result'] == response == public, 'qualification_public_RPC_receipt')
    require((run_root / 'request_03/TCP_RX.bin').read_bytes()
            == (owner / 'rpc_003/TCP_RX.bin').read_bytes(), 'qualification_actual_socket_bytes')
    transports = read(owner / 'TRANSPORT.json')
    require(len(transports) == 3 and all(row['send_confirmed'] is True for row in transports),
            'qualification_socket_sends_confirmed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run_path = args.runtime_root.resolve() / 'preparation/Q1/QUALIFICATION_RUN.json'
    result = dict(schema='complete-witness-qualification-v1', passed=False, status='evidence_failed',
                  source_freeze_sha256=None, prompt_sha256=None, input_sha256=None,
                  qualification_run=dict(path=str(run_path), sha256=None), truth_sha256=None,
                  actual_model_calls=None, actual_product_calls=None, actual_rasters=None,
                  errors=[], independent_geometry_and_pixels=None)
    try:
        require(args.runtime_root.resolve() == EXTERNAL and args.freeze.resolve() == HERE / 'FROZEN.json',
                'qualification_fixed_runtime_and_freeze')
        frozen, plan, manifest, truth, inputs = source_binding(args.freeze)
        result.update(source_freeze_sha256=sha(args.freeze), prompt_sha256=sha(plan['inputs']['prompt']),
                      input_sha256=inputs, truth_sha256=sha(HERE / 'admin/TRUTH.json'))
        run = read(run_path)
        result['qualification_run']['sha256'] = sha(run_path)
        for name in ('actual_model_calls', 'actual_product_calls', 'actual_rasters'):
            result[name] = run.get(name)
        owner = EXTERNAL / 'preparation/Q1/o'
        validate_entry(run, owner, run_path.parent, frozen, plan, manifest)
        spec = importlib.util.spec_from_file_location('_qualification_saved_evidence', HERE / 'saved_evidence.py')
        saved = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(saved)
        try:
            measured = saved.evaluate(owner, truth)
        except saved.ProductFactError as error:
            result['status'] = 'product_incorrect'
            result['errors'].append(dict(type=type(error).__name__, message=str(error)))
        else:
            require(measured['actual_rasters'] == run['actual_rasters']
                    and measured['actual_product_calls'] == run['actual_product_calls']
                    and measured['actual_owner_pid'] == run['actor_pid'], 'qualification_measured_count_PID_binding')
            result['independent_geometry_and_pixels'] = saved.summary(measured)
            if measured['product_errors']:
                result['status'] = 'product_incorrect'
            elif not measured['realized']:
                result['status'] = 'not_realized'
            else:
                result.update(status='qualified', passed=True)
    except Exception as error:
        result['errors'].append(dict(type=type(error).__name__, message=str(error)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=result['status'], passed=result['passed'], path=str(args.output))))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
