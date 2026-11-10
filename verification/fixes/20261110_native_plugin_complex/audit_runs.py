"""Recompute trial metrics from public events and owned raw transport records."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

SOURCE = {'A': 'e224f445a310c8b799b49d6f3f30184fa9b76b569cfa9ff1e79707c0291115b0',
          'B': 'a50e34c9169e9384047b29fa8bda8a072f96681f64610334ccec367d8597589b'}

def read(p):
    return json.loads(Path(p).read_bytes())

def rows(p):
    return [json.loads(s) for s in Path(p).read_text(encoding='utf8').splitlines() if s.strip()]

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = args.evidence
    plan = read(root / 'PLAN.json')
    freeze = read(root / 'FREEZE.json')
    freeze_passed = all(sha(root / name) == digest for name, digest in freeze.items())
    results, native_schemas, common_configs = [], [], []
    for slot in plan['sequence']:
        folder = root / 'cells' / slot['cell']
        data = read(folder / 'CONSUMER.json')
        events = rows(folder / 'events.jsonl')
        completed = [x for x in events if x['event']['type'] == 'turn.completed']
        raw_usage = completed[-1]['event'].get('usage') if completed else None
        observed_calls = [x for x in events if x['event']['type'] == 'item.completed'
                          and x['event'].get('item', {}).get('type') == 'mcp_tool_call']
        tools = Counter(x['event']['item']['tool'] for x in observed_calls)
        final_messages = [x for x in events if x['event']['type'] == 'item.completed'
                          and x['event'].get('item', {}).get('type') == 'agent_message']
        final = data['final']
        final_present_in_events = any(x['event']['item'].get('text') == final for x in final_messages)
        public_usage_matches = raw_usage is not None and all(data['usage'].get(k) == v for k, v in raw_usage.items())
        tool_catalog = None
        wire_tx = wire_rx = catalog_bytes = tool_rx_bytes = 0
        requests = Counter()
        for tx in sorted((folder / 'attachments').glob('*/*/TX.bin')):
            req = read(tx)
            method = req.get('method')
            requests[method] += 1
            wire_tx += tx.stat().st_size
            rx = tx.parent / 'RX.bin'
            if not rx.exists():
                continue
            wire_rx += rx.stat().st_size
            response = read(rx)
            if method == 'tools/list':
                tool_catalog = response['result']['tools']
                catalog_bytes += rx.stat().st_size
            if method == 'tools/call':
                tool_rx_bytes += rx.stat().st_size
        assert tool_catalog is not None, ('missing_public_catalog', slot['cell'])
        native_schema = next(t for t in tool_catalog if t['name'] == 'execute_blender_code')
        native_schemas.append(canonical(native_schema))
        configs = {}
        for i, value in enumerate(data['argv']):
            if value == '-c':
                key, setting = data['argv'][i + 1].split('=', 1)
                if not key.startswith('mcp_servers.'):
                    configs[key] = setting
        common_configs.append(configs)
        identity = read(folder / 'owner' / 'IDENTITY.json')
        identity_ok = identity['runtime_identity'] is None if slot['group'] == 'N' else (
            identity['runtime_identity']['source_sha256'] == SOURCE[slot['group']]
            and identity['runtime_identity']['source_kind'] == 'installed_distribution')
        closed = read(folder / 'OWNER_FINISH.json')
        worker_closed = read(folder / 'owner/native/WORKER_CLOSED.json')
        worker_events = rows(folder / 'owner/native/WORKER_EVENTS.jsonl')
        current_geometry_unchanged = (worker_closed['initial_geometry_fingerprint'] == worker_closed['final_geometry_fingerprint']
                                      and read(folder / 'owner/INITIAL.json') == read(folder / 'owner/FINAL.json'))
        owner_tools = read(folder / 'owner/TOOLS.json')
        last_tool_ns = max((x['perf_ns'] for x in observed_calls), default=None)
        full_s = data['total_task_wall_ns'] / 1e9
        prompt_s = data['prompt_to_final_ns'] / 1e9 if data['prompt_to_final_ns'] is not None else None
        raw_tools = [x['event']['item'] for x in observed_calls]
        native_code = '\n'.join(x.get('arguments', {}).get('code', '') for x in raw_tools if x['tool'] == 'execute_blender_code')
        results.append({**slot, 'status': data['status'], 'valid_completion': data['valid_completion'],
            'full_task_seconds': full_s, 'prompt_to_final_seconds': prompt_s,
            'pre_consumer_setup_seconds': data['pre_consumer_setup_ns'] / 1e9,
            'owner_finish_seconds': closed['finish_elapsed_ns'] / 1e9,
            'after_last_tool_to_final_seconds': None if last_tool_ns is None or data['final_received_ns'] is None else (data['final_received_ns']-last_tool_ns)/1e9,
            'tool_counts': dict(tools), 'tool_count': len(observed_calls),
            'tool_seconds_sum': sum(t['elapsed_ns'] for t in owner_tools['tools']) / 1e9,
            'raw_usage': raw_usage, 'usage_matches_raw': public_usage_matches,
            'model_total_input_output_tokens': None if raw_usage is None else raw_usage['input_tokens']+raw_usage['output_tokens'],
            'catalog_bytes': catalog_bytes, 'tool_response_wire_bytes': tool_rx_bytes,
            'all_mcp_request_wire_bytes': wire_tx, 'all_mcp_response_wire_bytes': wire_rx,
            'mcp_methods': dict(requests),
            'worker_execute_code_rpc_count_including_initial_final': sum('script_sha256' in x for x in worker_events),
            'worker_rpc_count_including_initial_final_close': len(worker_events),
            'worker_non_script_events': [x for x in worker_events if 'script_sha256' not in x],
            'worker_execution_seconds_including_initial_final': sum(x['elapsed_ns'] for x in worker_events if 'script_sha256' in x) / 1e9,
            'native_calls_in_events_match_owner': tools['execute_blender_code'] == sum(t['name'] == 'execute_blender_code' for t in owner_tools['tools']),
            'public_tools': [t['name'] for t in tool_catalog],
            'runtime_identity_passed': identity_ok, 'prompt_sha256': data['input_sha256'],
            'final_sha256': hashlib.sha256(final.encode('utf8')).hexdigest() if final is not None else None,
            'final_present_in_public_events': final_present_in_events,
            'cli_final_matches': data['cli_output_matches_public_final'],
            'full_geometry_unchanged': current_geometry_unchanged,
            'owner_cleanup_confirmed': closed['confirmed'], 'consumer_reaped': data['process_reaped'],
            'original_blend_unchanged': closed['close']['asset_unchanged'],
            'errors': data['errors'], 'unexpected_tools': data['unexpected_tool_deviations'],
            'provider_retry_observations': data['provider_retry_observations'],
            'consumer_pid': data['consumer_pid'], 'actor_pid': closed['actor_pid'], 'blender_pid': worker_closed['pid'],
            'native_code_mentions_plugin': 'human_eye' in native_code.lower(),
            'fees': data['fees'], 'provider_requests': data['provider_requests'], 'resolved_effort': data['resolved_effort']})
    summaries = {}
    for group in ('N', 'A', 'B'):
        group_rows = [x for x in results if x['group'] == group]
        summary = {'n': len(group_rows)}
        for key in ('full_task_seconds', 'prompt_to_final_seconds', 'tool_count', 'model_total_input_output_tokens'):
            values = [x[key] for x in group_rows if x[key] is not None]
            summary[key] = {'median': statistics.median(values), 'min': min(values), 'max': max(values), 'sum': sum(values)} if values else None
        usage_keys = set().union(*(x['raw_usage'] for x in group_rows if x['raw_usage']))
        summary['usage_sums'] = {k: sum(x['raw_usage'].get(k, 0) or 0 for x in group_rows if x['raw_usage']) for k in sorted(usage_keys)}
        summary['tool_counts'] = dict(sum((Counter(x['tool_counts']) for x in group_rows), Counter()))
        for key in ('catalog_bytes', 'tool_response_wire_bytes', 'all_mcp_request_wire_bytes', 'all_mcp_response_wire_bytes', 'worker_execute_code_rpc_count_including_initial_final', 'worker_rpc_count_including_initial_final_close'):
            summary[key + '_sum'] = sum(x[key] for x in group_rows)
        summaries[group] = summary
    artifact = {'cycle': plan['cycle_id'], 'method': 'independent recomputation from raw events, transport RX/TX and owned worker records; no author grader or summary imported',
                'freeze_passed': freeze_passed, 'denominator': plan['denominator'], 'observed_cells': len(results),
                'native_schemas_equal': len(set(native_schemas)) == 1,
                'common_cli_configs_equal': all(x == common_configs[0] for x in common_configs),
                'prompt_hashes_equal_to_plan': all(x['prompt_sha256'] == plan['prompt_sha256'] for x in results),
                'same_requested_model_and_effort': all(json.loads(x['model']) == plan['model'] and json.loads(x['model_reasoning_effort']) == plan['requested_effort'] for x in common_configs),
                'common_cli_config': common_configs[0], 'groups': summaries, 'cells': results,
                'cost_scope': 'consumer usage is actual reported usage; setup/review/judge token usage, provider request counts and billed dollars are unmeasured; after-last-tool includes transport/orchestration and is not identified as pure reasoning'}
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: artifact[k] for k in ('freeze_passed', 'denominator', 'observed_cells', 'native_schemas_equal', 'common_cli_configs_equal', 'prompt_hashes_equal_to_plan', 'groups')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
