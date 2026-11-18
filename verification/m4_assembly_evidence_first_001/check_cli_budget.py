"""Replay the previously verified Codex 0.152.1 text presentation budget."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[2]
PRIOR = ROOT / 'verification/m1_source_region_facts_first_001/checks'
PINS = {
    'client_budget_replay.py': '8a59abf2ccdaba3013c7ef3e8180265a3311ca3d5039f8af86b679252be08f4a',
    'CLIENT_BUDGET_REVIEW.json': '0e90ad3df1f74a1977d96b212bd7592e11cdbc4e285a80213a25745fedc57ae8',
}
BODY_TARGET = 10_000


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def audit(replay_root):
    for name, digest in PINS.items():
        if sha((PRIOR / name).read_bytes()) != digest:
            raise ValueError('prior CLI budget reference changed: ' + name)
    policy = json.loads((PRIOR / 'CLIENT_BUDGET_REVIEW.json').read_bytes())['policy']
    helpers = runpy.run_path(str(PRIOR / 'client_budget_replay.py'))
    variants = {}
    for name in ('A', 'first', 'optimized'):
        variants[name] = results = {}
        for case in ('second_assembly', 'assembly001'):
            results[case] = modes = {}
            for mode in ('default', 'full', 'brief'):
                path = replay_root / name / case / mode
                raw = (path / 'PUBLIC.json').read_bytes()
                text = raw.decode('utf8')
                json.loads(text)
                schema = (path / 'TOOL_SCHEMA.json').read_bytes()
                if json.loads(schema)['name'] != 'human_eye_scene_observe':
                    raise ValueError('unexpected public tool schema')
                # Use the original replay's assumed header format. It is a
                # separate text item and consumes budget before the body.
                items = helpers['model_items']({'content': [{'type': 'text', 'text': text}]}, '1.0000')
                first = helpers['truncate_items'](items, policy['MCP_bytes'])
                second = helpers['truncate_items'](first, policy['history_approximate_tokens'], token_mode=True)
                modes[mode] = {'body_bytes': len(raw), 'body_sha256': sha(raw), 'body_target_pass': len(raw) <= BODY_TARGET,
                               'tool_schema_bytes': len(schema), 'tool_schema_sha256': sha(schema),
                               'replay_header_bytes': len(items[0]['text'].encode('utf8')),
                               'MCP_text_preserved': first == items, 'history_text_preserved': second == items}
    return {'scope': 'Offline presentation replay. No model call or provider usage.',
            'previous_replay_sha256': PINS, 'policy': policy, 'target_body_bytes': BODY_TARGET,
            'variants': variants}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('replay', type=Path)
    parser.add_argument('output', type=Path)
    options = parser.parse_args()
    with options.output.open('x', encoding='utf8', newline='\n') as output:
        output.write(json.dumps(audit(options.replay), indent=2, sort_keys=True) + '\n')
