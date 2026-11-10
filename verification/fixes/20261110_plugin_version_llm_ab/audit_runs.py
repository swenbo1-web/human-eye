"""Independent recomputation of actual A/B records, identity and paired costs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import tomllib

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
DATA = ROOT / 'verification/plugin_version_llm_ab_001'
HERE = Path(__file__).parent
SOURCES = {'A': 'e224f445a310c8b799b49d6f3f30184fa9b76b569cfa9ff1e79707c0291115b0',
           'B': 'a50e34c9169e9384047b29fa8bda8a072f96681f64610334ccec367d8597589b'}


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    spec = importlib.util.spec_from_file_location('root_ab_geometry', HERE / 'audit_geometry.py')
    geometry_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geometry_module)
    geometry = geometry_module.audit
    plan, installs = read(DATA / 'PLAN.json'), read(DATA / 'INSTALL_RESULT.json')
    checks, rows, blind, geometry_rows = [], [], [], []
    def need(condition, name):
        checks.append({'check': name, 'passed': bool(condition)})
    for name, digest in read(DATA / 'PLAN_FREEZE.json').items():
        need(sha(DATA / name) == digest, 'frozen plan ' + name)
    freeze = read(DATA / 'RUNNER_FREEZE.json')
    for field, name in [('runner_sha256', 'run_consumers.py'), ('bridge_sha256', 'bridge.py'),
                        ('initializer_sha256', 'initializer.py'), ('plan_sha256', 'PLAN.json')]:
        need(freeze[field] == sha(DATA / name), 'frozen execution ' + name)
    for index, slot in enumerate(plan['sequence'], 1):
        cell = DATA / 'formal_cells' / slot['cell']
        c = read(cell / 'CONSUMER.json')
        prefix = 'cell ' + slot['cell'] + ': '
        need(all(c[k] == slot[k] for k in ('cell', 'task', 'pair', 'version')), prefix + 'fixed slot')
        b = read(cell / 'bridge_native/BRIDGE_RESULT.json')
        child = read(cell / 'bridge_native/CHILD_INSTALL_IDENTITY.json')
        case_files = list((cell / 'bridge_native').glob('case_*.json'))
        need(len(case_files) == 1, prefix + 'one actual native case')
        raw = read(case_files[0])
        geom = geometry(case_files[0]); geometry_rows.append(geom)
        need(geom['passed'], prefix + 'independent native geometry')
        receipt = raw['receipt']
        need(c['valid_completion'] and c['safe_to_continue'], prefix + 'complete and cleaned session')
        need(not c['errors'] and not c['unexpected_tool_deviations'], prefix + 'no execution or tool deviations')
        need(c['model'] == plan['model'] and c['requested_effort'] == plan['requested_effort'], prefix + 'same requested model setting')
        need(c['input_sha256'] == plan['prompt_sha256'] == sha(DATA / 'PROMPT.txt'), prefix + 'identical prompt')
        install = installs['versions'][slot['version']]
        mcp_argument = next(x for x in c['argv'] if x.startswith('mcp_servers.arm_engine='))
        mcp_config = tomllib.loads(mcp_argument)['mcp_servers']['arm_engine']
        need(Path(mcp_config['command']).resolve() == Path(install['python']).resolve(), prefix + 'selected installed interpreter in actual argv')
        need(Path(b['installed_import_root']) == Path(install['installed_root']), prefix + 'actual imports in selected install')
        need(b['source_before'] == b['source_after'] and b['source_unchanged'], prefix + 'unchanged runtime source')
        need(b['source_before']['source_sha256'] == SOURCES[slot['version']], prefix + 'controller canonical source')
        need(child['runtime_identity']['source_sha256'] == SOURCES[slot['version']], prefix + 'worker canonical source')
        need(child['runtime_identity']['source_kind'] == 'installed_distribution', prefix + 'worker installed source')
        need(b['bridge_sha256'] == freeze['bridge_sha256'] and b['initializer_sha256'] == freeze['initializer_sha256'], prefix + 'common bridge and observer bytes')
        need(b['process_exit']['closed'] and b['process_exit']['returncode'] == 0, prefix + 'owned process closed')
        need(b['blend_sha256_before'] == b['blend_sha256_after'], prefix + 'original fixture file unchanged')
        need(read(cell / 'bridge_native/INITIAL_NATIVE.json') == raw['native_before'], prefix + 'initial state binding')
        need(read(cell / 'bridge_native/FINAL_NATIVE.json') == raw['native_after'], prefix + 'terminal state binding')
        need(len(b['calls']) == 1 and b['calls'][0]['result']['status'] == receipt['status'], prefix + 'one model-requested product call')
        need(sum(r['command'] == 'correct_arm_axial' for r in b['rpc']) == 1, prefix + 'one mutation RPC')
        need(b['cost_counts']['arm_ledger_validation'] == (2 if slot['version'] == 'A' else 1), prefix + 'changed validation path exercised')
        need(receipt['work']['source']['preparations'] == (1 if slot['version'] == 'A' else 0), prefix + 'changed preparation path exercised')
        tool_names = [x['item']['tool'] for x in c['tool_calls']]
        need(tool_names == ['describe_task', 'run_arm_goal'], prefix + 'actual model tool sequence')
        events = [json.loads(line) for line in (cell / 'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        raw_usage = [e['event']['usage'] for e in events if e['event'].get('type') == 'turn.completed']
        need(len(raw_usage) == 1 and all(raw_usage[0].get(k) == v for k, v in c['usage'].items()), prefix + 'actual public usage')
        message_events = [e for e in events if e['event'].get('type') == 'item.completed' and e['event'].get('item', {}).get('type') == 'agent_message']
        need(message_events[-1]['event']['item']['text'] == c['final'], prefix + 'actual final answer binding')
        need(message_events[-1]['perf_ns'] == c['final_received_ns'], prefix + 'actual final timestamp')
        times = [c[k] for k in ('started_ns', 'prompt_submitted_ns', 'final_received_ns', 'turn_completed_ns', 'process_exit_ns', 'cleanup_end_ns')]
        need(times == sorted(times), prefix + 'monotonic lifecycle timestamps')
        need(c['prompt_to_final_ns'] == c['final_received_ns'] - c['prompt_submitted_ns'], prefix + 'prompt through final duration')
        need(c['wall_ns'] == c['cleanup_end_ns'] - c['started_ns'], prefix + 'complete lifecycle duration')
        result = {'cell': slot['cell'], 'task': slot['task'], 'pair': slot['pair'], 'version': slot['version'],
                  'status': receipt['status'], 'geometry_passed': geom['passed'],
                  'prompt_to_final_s': c['prompt_to_final_ns'] / 1e9, 'whole_s': c['wall_ns'] / 1e9,
                  'adapter_call_with_close_ms': b['calls'][0]['elapsed_ns'] / 1e6,
                  'engine_entry_ms': b['calls'][0]['scheduler_entry_ns'] / 1e6,
                  'worker_product_ms': raw['pure_product_method_ns'] / 1e6,
                  'input_tokens': c['usage'].get('input_tokens'), 'cached_input_tokens': c['usage'].get('cached_input_tokens'),
                  'output_tokens': c['usage'].get('output_tokens'), 'tool_calls': len(tool_names),
                  'bridge_text_bytes': b['public_text_bytes'], 'answer_bytes': len(c['final'].encode()),
                  'provider_retry_observations': c['provider_retry_observations'], 'fees': c['fees']}
        rows.append(result)
        blind.append({'review_id': 'answer_' + str((index * 7) % 13).zfill(2),
                      'answer': c['final'], 'actual_tool_names': tool_names,
                      'actual_status': receipt['status'], 'actual_task_succeeded': receipt['task_succeeded'],
                      'actual_setter_attempts': receipt['setter_attempts'], 'actual_setter_returns': receipt['setter_returns'],
                      'independent_before_j': geom['before_j'], 'independent_after_j': geom['after_j'],
                      'geometry_passed': geom['passed'],
                      'product_receipt': {k: v for k, v in b['calls'][0]['result'].items()
                                          if k in ('status', 'task_succeeded', 'setter_attempts', 'setter_returns',
                                                   'executed', 'reason', 'feedback', 'preview')}})
    pairs = []
    metrics = ('prompt_to_final_s', 'whole_s', 'engine_entry_ms', 'worker_product_ms', 'input_tokens', 'output_tokens')
    for task in dict.fromkeys(r['task'] for r in rows):
        for pair in (1, 2):
            group = {r['version']: r for r in rows if r['task'] == task and r['pair'] == pair}
            pairs.append({'task': task, 'pair': pair, 'A_cell': group['A']['cell'], 'B_cell': group['B']['cell'],
                          'B_change_percent': {m: (group['B'][m] / group['A'][m] - 1) * 100 for m in metrics}})
    summary = {}
    for label in ('A', 'B'):
        values = [r for r in rows if r['version'] == label]
        summary[label] = {m: {'median': statistics.median(r[m] for r in values),
                             'minimum': min(r[m] for r in values), 'maximum': max(r[m] for r in values),
                             'sum': sum(r[m] for r in values)} for m in metrics}
    out = {'schema': 'root-plugin-ab-run-review-v1', 'passed': all(x['passed'] for x in checks),
           'checks': checks, 'rows': rows, 'paired_changes': pairs, 'summary': summary,
           'denominator': 12, 'geometry': geometry_rows}
    (HERE / 'RUN_REVIEW.json').write_text(json.dumps(out, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    # Versions and timing omitted from the independent semantic scoring packet.
    (HERE / 'BLIND_ANSWERS.json').write_text(json.dumps(sorted(blind, key=lambda x: x['review_id']), indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'passed': out['passed'], 'checks': len(checks), 'rows': len(rows), 'summary': summary}))
    raise SystemExit(0 if out['passed'] else 1)


if __name__ == '__main__':
    main()
