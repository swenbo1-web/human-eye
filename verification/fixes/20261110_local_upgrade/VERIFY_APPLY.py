"""Independently compare the exact four files around activation."""
from pathlib import Path
import base64
import hashlib
import json
import tomllib

OUT = Path(__file__).resolve().parent
before, after = OUT / 'BEFORE', OUT / 'AFTER_APPLY'
old = '9.7.2+20261103.scene.trace.r1'
new = '9.7.2+20261110.scale.opt.r1'
load = lambda base, name: json.loads((base / name).read_bytes())
checks = {}
a = tomllib.loads((before / '.codex/config.toml').read_text('utf8'))
b = tomllib.loads((after / '.codex/config.toml').read_text('utf8'))
old_live = dict(a['mcp_servers']['human_eye_live'])
new_live = dict(b['mcp_servers']['human_eye_live'])
for key in ('command', 'args', 'cwd'):
    a['mcp_servers']['human_eye_live'].pop(key)
    b['mcp_servers']['human_eye_live'].pop(key)
assert a == b
assert old_live['command'] == new_live['command'] and old_live['cwd'] == new_live['cwd']
assert [v.replace(old, new) for v in old_live['args']] == new_live['args']
checks['all_other_mcp_servers_and_settings_unchanged'] = True

a = load(before, '.codex/hooks.json')
b = load(after, '.codex/hooks.json')
changed = 0
for event, groups in a['hooks'].items():
    for i, group in enumerate(groups):
        for j, hook in enumerate(group['hooks']):
            target = b['hooks'][event][i]['hooks'][j]
            old_command, new_command = hook['command'], target['command']
            prefix_a, encoded_a = old_command.rsplit(' ', 1)
            prefix_b, encoded_b = new_command.rsplit(' ', 1)
            assert prefix_a == prefix_b
            decoded_a = base64.b64decode(encoded_a).decode('utf-16le')
            decoded_b = base64.b64decode(encoded_b).decode('utf-16le')
            assert decoded_a.replace(old, new) == decoded_b
            changed += old_command != new_command
            hook['command'] = target['command']
assert a == b and changed == 5
checks['five_hook_commands_only_version_path_changed'] = True

a = load(before, '.human-eye/live-connector.routing-spatial.json')
b = load(after, '.human-eye/live-connector.routing-spatial.json')
for key in ('project_root', 'expected_identity'):
    a.pop(key)
    b.pop(key)
assert a == b
checks['connector_only_root_and_identity_changed'] = True

rel = '.human-eye/live-state.routing-spatial.json'
raw_a, raw_b = (before / rel).read_bytes(), (after / rel).read_bytes()
a, b = json.loads(raw_a), json.loads(raw_b)
fp_a, fp_b = a.pop('config_fingerprint'), b.pop('config_fingerprint')
assert a == b
assert raw_a.count(fp_a.encode()) == 1
assert raw_a.replace(fp_a.encode(), fp_b.encode(), 1) == raw_b
checks['runtime_and_all_journals_byte_preserved'] = True
checks['state_sessions_preserved'] = len(a.get('runtime', {}).get('sessions', {}))
checks['state_goal_segments_preserved'] = len(a.get('goal_segments', {}))
checks['inflight'] = b.get('inflight')
checks['quarantine'] = b.get('runtime', {}).get('quarantine')
checks['old_config_fingerprint'] = fp_a
checks['new_config_fingerprint'] = fp_b
checks['state_sha256_after_apply'] = hashlib.sha256(raw_b).hexdigest()
(OUT / 'APPLY_DIFF_REVIEW.json').write_text(json.dumps(checks, indent=2), encoding='utf8')
print(json.dumps(checks))
