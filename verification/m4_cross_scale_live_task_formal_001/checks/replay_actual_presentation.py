"""Replay the already pinned CLI presentation policy on actual P1 product replies."""

import hashlib
import json
from pathlib import Path
import runpy


NS = Path(__file__).resolve().parents[1]
ROOT = NS.parents[1]
REPLAY = ROOT / 'verification/m1_source_region_facts_first_001/checks'
RUN = Path('D:/he_m4_cross_scale_live_task_formal_001/slots/P1')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    helper = runpy.run_path(str(REPLAY / 'client_budget_replay.py'))
    policy = json.loads((REPLAY / 'CLIENT_BUDGET_REVIEW.json').read_bytes())['policy']
    sources = {Path(row['path']).resolve(): row['sha256'] for row in json.loads((NS / 'FROZEN.json').read_bytes())['direct_inputs']}
    for name in ('client_budget_replay.py', 'CLIENT_BUDGET_REVIEW.json'):
        path = (REPLAY / name).resolve()
        assert sha(path.read_bytes()) == sources[path]
    results = []
    for folder in sorted((RUN / 'owner').glob('tool_*')):
        req = json.loads((folder / 'REQUEST.json').read_bytes())
        if req['params']['name'] != 'human_eye_scene_observe':
            continue
        wire = (folder / 'RESPONSE.json').read_bytes()
        result = json.loads(wire)['result']
        if result['isError'] or [row['type'] for row in result['content']].count('text') != 1:
            continue
        text = next(row['text'] for row in result['content'] if row['type'] == 'text')
        task = json.loads(text)
        facts = {k: task[k] for k in ('binding', 'region_task', 'images', 'witness_pixels') if k in task}
        if 'region_task' not in facts and 'region_task' in (task.get('facts') or {}):
            facts['region_task'] = task['facts']['region_task']
        serialized = {k: json.dumps(v, ensure_ascii=False, separators=(',', ':')) for k, v in facts.items()}
        assert all(s in text for s in serialized.values())
        versions = []
        for duration in ('0.0000', '10.0000', '100.0000'):
            emitted = helper['model_items'](result, duration)
            mcp = helper['truncate_items'](emitted, policy['MCP_bytes'])
            final = helper['truncate_items'](mcp, policy['history_approximate_tokens'], token_mode=True)
            retained = [row['text'] for row in final if row['type'] == 'input_text'][1:]
            versions.append({'header_bytes': len(emitted[0]['text'].encode()), 'all_items_unchanged': emitted == final,
                'retained_body_bytes': sum(len(s.encode()) for s in retained),
                'complete_field_retained': {k: any(fragment in s for s in retained) for k, fragment in serialized.items()},
                'all_images_unchanged': [r for r in emitted if r['type'] == 'input_image'] ==
                                        [r for r in final if r['type'] == 'input_image']})
        results.append({'attempt': int(folder.name.rsplit('_', 1)[1]), 'response_sha256': sha(wire),
                        'response_detail': req['params']['arguments'].get('response_detail', 'default'),
                        'body_bytes': len(text.encode()), 'offline_presentation': versions})
    out = {'slot': 'P1', 'scope': 'Offline fallback CLI presentation policy replay on real emitted results. '
           'Actual CLI public event equality is recorded separately. Supplier model input is unobserved.', 'calls': results}
    with (NS / 'checks/ACTUAL_CLI_PRESENTATION.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(out, stream, indent=2, sort_keys=True)
        stream.write('\n')


if __name__ == '__main__':
    main()
