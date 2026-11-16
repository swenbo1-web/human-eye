"""Retain the frozen audit and adapt its one saved PID field lookup."""

import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
BASE = HERE / 'runtime_lifecycle.py'
EXPECTED = 'a10f11008f89674c09e9f39039c309e6670b7f20a257fb74a409e7181b67e347'
raw = BASE.read_bytes()
if hashlib.sha256(raw).hexdigest() != EXPECTED:
    raise ValueError('frozen_runtime_audit_source_changed')
source = raw.decode('utf8')
old = "data['source']['pid'] == native_config['pid']"
new = "data['source']['pid'] == processes['native']['spawn']['pid']"
if source.count(old) != 1:
    raise ValueError('saved_pid_adapter_expected_one_lookup')
source = source.replace(old, new)
metadata_site = 'new_product_calls=0, new_Blender_starts=0, new_rasters=0)'
if source.count(metadata_site) != 1:
    raise ValueError('saved_pid_adapter_expected_one_metadata_site')
source = source.replace(metadata_site, metadata_site[:-1] + ', saved_schema_adapter=ADAPTATION)')
namespace = dict(__file__=str(BASE), __name__='_m4_global_local_saved_pid_adaptation')
exec(compile(source, str(BASE), 'exec'), namespace)
adapter_pin = namespace['pin'](__file__)
namespace['ADAPTATION'] = dict(
    schema='m4-global-local-saved-pid-adaptation-v1', adapter=adapter_pin,
    frozen_source=namespace['pin'](BASE), initial_failure_run=namespace['pin'](HERE.parent / 'RUNTIME_REVIEW_RUN.json'),
    initial_failure_stderr=namespace['pin'](HERE.parent / 'RUNTIME_REVIEW.stderr.bin'),
    reason='CONFIG.json is persisted before spawn and has no pid. The actual SPAWN pid is bound to the retained process proof and independently checked against READY.',
    semantic_change=dict(before=old, after=new), execution_source_or_original_changes=0,
    new_Blender_starts=0, new_product_calls=0, new_rasters=0)
for label in namespace['LABELS']:
    folder = namespace['RUNTIME'] / 'sessions' / label
    ready = namespace['read'](folder / 'native/READY.json')
    spawn = namespace['read'](folder / 'native/SPAWN.json')
    namespace['check'](label + '/saved_adapter_READY_matches_SPAWN', ready['pid'] == spawn['pid'])
namespace['main']()
