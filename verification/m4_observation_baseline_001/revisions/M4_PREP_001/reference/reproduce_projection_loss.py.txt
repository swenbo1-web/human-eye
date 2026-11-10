from pathlib import Path
import hashlib
import importlib.util
import json

BASE = Path('D:/hefe/verification/fixes/20261111_m4_observation_prep_review')
SCRIPT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_observation_baseline_001/quality_handoff/pack_quality.py')
raw_script = SCRIPT.read_bytes()
assert hashlib.sha256(raw_script).hexdigest() == '34a0480c318408826404ea76197ac22bfe1083c977fd9a83959de3ac3e10fe33'
spec = importlib.util.spec_from_file_location('_root_m4_projection_audit', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
payload = {'condition': {'lower_band': True, 'behind_front_beam': True, 'within_pipe_radius': True},
           'profile': 'rectangular frame with through hole', 'gap_m': 0.00010000728070735931}
text = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
response = {'jsonrpc': '2.0', 'id': 42,
            'result': {'content': [{'type': 'text', 'text': text}], 'isError': False}}
raw = json.dumps(response, ensure_ascii=False).encode()
removals = []
projected = module.audit_projection(module.without_rpc_envelope(response, raw, removals), raw, removals)
after = json.loads(projected['result']['content'][0]['text'])
assert 'condition' not in after and 'profile' not in after and after['gap_m'] == payload['gap_m']
record = {'kind': 'root actual pure-function replay, no model/product/Blender execution',
          'script_sha256': hashlib.sha256(raw_script).hexdigest(), 'input': response,
          'projection': projected, 'removals': removals,
          'reproduced': True, 'impact': 'valid native semantic evidence omitted from quality packet'}
(BASE/'ROOT_PROJECTION_REPRODUCTION.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'reproduced': True, 'removed_semantic_keys': ['condition','profile'], 'remaining': after}))
