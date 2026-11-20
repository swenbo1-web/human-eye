"""Use the frozen Codex CLI loop without the prior task's product-call gate."""

import ast
from pathlib import Path
import sys
import time

from common import HERE, NS, PRIOR, SLOTS, load, read, save, sha


def reused_function(path, name, scope, transform):
    tree = ast.parse(path.read_bytes(), filename=str(path))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    transform(function)
    repaired = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    exec(compile(repaired, str(path), 'exec'), scope)
    return scope[name]


def remove_old_task_condition(function):
    condition = ast.parse("cell['group'] == 'P'", mode='eval').body
    candidates = [node for node in function.body if isinstance(node, ast.If) and
                  ast.dump(node.test) == ast.dump(condition)]
    if len(candidates) != 1 or not any(isinstance(node, ast.Constant) and
            node.value == 'initial_P_query_is_not_standard_source_region' for node in ast.walk(candidates[0])):
        raise ValueError('prior_source_region_call_gate_changed')
    function.body.remove(candidates[0])


def count_business_calls(function):
    original = ast.parse("len(record['tool_calls']) > 4", mode='eval').body
    matches = [node for node in ast.walk(function) if isinstance(node, ast.If) and
               ast.dump(node.test) == ast.dump(original)]
    if len(matches) != 1 or len(matches[0].body) != 1:
        raise ValueError('prior_cli_budget_guard_changed')
    matches[0].test = ast.parse("len(record.get('business_tool_calls', [])) > TOOL_LIMIT", mode='eval').body
    matches[0].body = ast.parse("raise ValueError('original_business_tool_attempt_limit')").body


def consumer_adapter():
    # Bind the new bridge before importing the retained loop and wire contract.
    sys.path.insert(0, str(NS))
    import bridge
    adapter_path = PRIOR / 'consumer_adapter.py'
    adapter = load('_cross_task_prior_consumer_adapter', adapter_path)
    adapter.THIN = NS / 'thin_stdio.py'
    contract = adapter.consumer_contract
    contract.archive_turn = reused_function(PRIOR / 'consumer_contract.py', 'archive_turn',
                                             dict(vars(contract)), remove_old_task_condition)
    retained, proof = adapter.consumer_adapter()
    turn = reused_function(adapter.LOOP, 'consume_turn', dict(retained.__globals__), count_business_calls)
    executed = {Path(row['path']).resolve() for row in proof['execution_sources']}
    executed.update((Path(__file__).resolve(), NS / 'bridge.py', NS / 'thin_stdio.py', adapter_path,
                     PRIOR / 'consumer_contract.py'))
    proof['schema'] = 'm4-cross-scale-live-task-formal-consumer-adapter-v1'
    proof['loop_change'] = 'Only business MCP results count toward the twelve-attempt CLI bound. The bridge and ledger independently count raw attempts.'
    proof['actual_tools_by_group'] = {k: sorted(v) for k, v in bridge.TOOL_NAMES.items()}
    proof['execution_sources'] = [{'path': str(f), 'sha256': sha(f), 'bytes': f.stat().st_size}
                                  for f in sorted(executed)]
    return turn, proof, adapter.metadata


def consume_slot(label, slot_root, endpoint, owner_output, deadline_ns, owned_deadline_ns):
    group, phase = SLOTS[label]
    if (phase != 'formal' or not time.perf_counter_ns() < deadline_ns < owned_deadline_ns or
            read(endpoint)['chain_deadline_ns'] != deadline_ns):
        raise ValueError('registered_formal_slot_and_absolute_deadlines_required')
    turn, proof, metadata = consumer_adapter()
    slot = Path(slot_root).resolve()
    prompt_path = NS / 'inputs' / f'PROMPT_{group}.txt'
    cell = {'endpoint': str(Path(endpoint).resolve()), 'group': group, 'audit_dir': str(Path(owner_output).resolve())}
    folder = slot / 'consumer'
    original = turn(episode_id='M4-CROSS-SCALE-LIVE-TASK-FORMAL-001-' + label, turn_index=1, folder=folder,
        work=slot / 'workspace', cell=cell, install={'python': proof['Python_path']},
        plan={'model_consumer_enabled': True}, prompt=prompt_path.read_bytes(),
        episode_deadline_ns=deadline_ns, turn_deadline_ns=deadline_ns, expected_thread_id=None)
    configuration = metadata(folder, proof, original)
    save(folder / 'ACTUAL_CONFIGURATION.json', configuration)
    return {'slot_id': label, 'group': group, 'status': original['status'], 'consumer_path': str(folder),
            'consumer_record': str(folder / 'CONSUMER.json'), 'adapter_proof': proof,
            'model_configuration': configuration, 'prompt_sha256': sha(prompt_path)}
