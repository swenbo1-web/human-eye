"""Root-only postprocessing of frozen raw receipts; never launches consumers."""
import hashlib
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/native_plugin_complex_005')

def read(path):
    return json.loads(path.read_bytes())

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def union_ns(intervals):
    total = 0
    end = -1
    for start, stop in sorted(intervals):
        total += max(0, stop - max(start, end))
        end = max(end, stop)
    return total

def main():
    seal = read(HERE / 'BLIND_QUALITY_SEAL.json')
    for name, expected in seal['files'].items():
        assert digest(HERE / name) == expected, name
    mapping = read(RUN / 'private/BLIND_MAP.json')
    plan = read(RUN / 'PLAN.json')
    run_rows = {r['cell']: r for r in read(RUN / 'RUN_RESULT.json')['cells']}
    grades = {}
    for name in ('BLIND_ASSEMBLY_REVIEW.json', 'BLIND_DISCOVERY_REVIEW.json'):
        for row in read(HERE / name)['answers']:
            grades[row['answer_id']] = row['full_pass']
    answers = {x['answer_id']: x for x in read(RUN / 'blind/ANSWERS.json')['answers']}
    assert len(mapping['answers']) == len(grades) == len(answers) == 18
    rows = []
    sources = {}
    for aid, link in mapping['answers'].items():
        folder = RUN / 'cells' / link['cell']
        consumer_path = folder / 'CONSUMER.json'
        c = read(consumer_path)
        assert digest(consumer_path) == link['consumer_sha256']
        assert hashlib.sha256(answers[aid]['text'].encode()).hexdigest() == link['public_final_sha256']
        assert answers[aid]['text'] == c['final']
        assert c['input_sha256'] == plan['tasks'][link['task']]['model_input_sha256']
        events = [json.loads(line) for line in (folder / 'events.jsonl').read_bytes().splitlines()]
        usages = [x['event']['usage'] for x in events if x['event']['type'] == 'turn.completed']
        finals = [x for x in events if x['event']['type'] == 'item.completed' and x['event'].get('item', {}).get('type') == 'agent_message']
        assert len(usages) == 1 and usages[0] == c['usage']
        assert finals[-1]['event']['item']['text'] == c['final']
        assert finals[-1]['perf_ns'] == c['final_received_ns']
        assert c['prompt_to_final_ns'] == c['final_received_ns'] - c['prompt_submitted_ns']
        assert run_rows[link['cell']]['total_task_wall_ns'] == c['total_task_wall_ns']
        tools_path = folder / 'owner/TOOLS.json'
        ledger = read(tools_path)
        calls = ledger['tools']
        assert len(calls) == ledger['attempts'] == len(c['tool_calls'])
        tool_intervals = [(x['started_ns'], x['started_ns'] + x['elapsed_ns']) for x in calls]
        public = {'tx_bytes': 0, 'rx_bytes': 0, 'requests_with_id': 0, 'notifications': 0,
                  'tool_calls': 0, 'tool_rx_bytes': 0, 'control_rx_bytes': 0,
                  'delivered_tool_text_utf8_bytes': 0}
        for tx in sorted((folder / 'attachments').glob('bridge_*/*/TX.bin')):
            raw = tx.read_bytes()
            req = json.loads(raw)
            public['tx_bytes'] += len(raw)
            if 'id' not in req:
                public['notifications'] += 1
                continue
            public['requests_with_id'] += 1
            rx = tx.with_name('RX.bin')
            response = json.loads(rx.read_bytes())
            assert response.get('id') == req['id']
            n = rx.stat().st_size
            public['rx_bytes'] += n
            if req['method'] == 'tools/call':
                public['tool_calls'] += 1
                public['tool_rx_bytes'] += n
                for item in response.get('result', {}).get('content', []):
                    if item.get('type') == 'text':
                        public['delivered_tool_text_utf8_bytes'] += len(item['text'].encode('utf-8'))
            else:
                public['control_rx_bytes'] += n
        assert public['tool_calls'] == len(calls)
        u = c['usage']
        finish = c['owner_finish']['finish_elapsed_ns']
        residual = c['total_task_wall_ns'] - c['wall_ns'] - c['pre_consumer_setup_ns'] - finish
        assert residual >= 0
        row = {'cell': link['cell'], 'answer_id': aid, 'task': link['task'], 'group': link['group'],
               'full_pass': grades[aid], 'status': c['status'],
               'whole_s': c['total_task_wall_ns'] / 1e9,
               'prompt_to_final_s': c['prompt_to_final_ns'] / 1e9,
               'tool_union_s': union_ns(tool_intervals) / 1e9,
               'tool_elapsed_sum_s': sum(x['elapsed_ns'] for x in calls) / 1e9,
               'setup_s': c['pre_consumer_setup_ns'] / 1e9,
               'after_final_consumer_s': (c['cleanup_end_ns'] - c['final_received_ns']) / 1e9,
               'owner_finish_s': finish / 1e9,
               'driver_gap_s': residual / 1e9,
               'tool_calls': len(calls), 'tool_errors': sum(bool(x['is_error']) for x in calls),
               'native_calls': sum(x['name'] == 'execute_blender_code' for x in calls),
               'plugin_calls': sum(x['name'] == 'human_eye_scene_observe' for x in calls),
               'plugin_successes': sum(x['name'] == 'human_eye_scene_observe' and not x['is_error'] for x in calls),
               'usage': u, 'inclusive_total_tokens': u['input_tokens'] + u['output_tokens'],
               'uncached_input_tokens': u['input_tokens'] - u['cached_input_tokens'],
               'public_wire': public, 'owner_intended_tool_wire_bytes': ledger['wire_tool_bytes'],
               'reported_provider_requests': c['provider_requests'], 'fees': c['fees'],
               'requested_effort': c['requested_effort'], 'resolved_effort': c['resolved_effort']}
        rows.append(row)
        for path in (consumer_path, folder / 'events.jsonl', tools_path):
            sources[str(path)] = digest(path)
    rows.sort(key=lambda x: x['cell'])
    groups = []
    for task in ('assembly', 'discovery'):
        for group in ('N', 'H', 'C'):
            selected = [r for r in rows if r['task'] == task and r['group'] == group]
            result = {'task': task, 'group': group, 'n': len(selected), 'passes': sum(r['full_pass'] for r in selected)}
            for field in ('whole_s', 'prompt_to_final_s', 'tool_union_s', 'setup_s', 'after_final_consumer_s',
                          'owner_finish_s', 'tool_calls', 'inclusive_total_tokens', 'uncached_input_tokens', 'tool_elapsed_sum_s', 'driver_gap_s'):
                values = [r[field] for r in selected]
                result[field] = {'median': statistics.median(values), 'min': min(values), 'max': max(values), 'sum': sum(values)}
            result['tool_errors'] = sum(r['tool_errors'] for r in selected)
            result['native_calls'] = sum(r['native_calls'] for r in selected)
            result['plugin_calls'] = sum(r['plugin_calls'] for r in selected)
            result['plugin_successes'] = sum(r['plugin_successes'] for r in selected)
            result['usage_sum'] = {key: sum(r['usage'][key] for r in selected) for key in selected[0]['usage']}
            result['public_wire_sum'] = {key: sum(r['public_wire'][key] for r in selected) for key in selected[0]['public_wire']}
            groups.append(result)
    result = {'schema': 'complex005.root.raw-recompute.v1', 'scope': 'Independent raw JSON/event/frame postprocessing; no new consumers, Blender or product invocation.',
              'denominator': 18, 'quality_passes': sum(r['full_pass'] for r in rows),
              'usage_note': 'Input includes cached input; output includes reported reasoning subset. Do not add these subsets again. Exact provider requests/fees unexposed.',
              'timing_note': 'Whole lifecycle is driver measurement. Tool union lies inside consumer wall and is not additive to it. Preparation/review outside each cell is separate, not zero.',
              'groups': groups, 'rows': rows, 'raw_file_sha256': sources, 'blind_quality_seal_sha256': digest(HERE / 'BLIND_QUALITY_SEAL.json')}
    (HERE / 'ROOT_RECOMPUTED_RESULTS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(groups, ensure_ascii=False))

if __name__ == '__main__':
    main()
