"""Independent saved-array / source-delta checks; no product import or raster."""
import ast
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe')
BASE = ROOT / 'verification/m4_view_reuse_001'
OUT = Path(__file__).resolve().parent
checks, inputs, cases = [], [], []

def read(path):
    raw = Path(path).read_bytes()
    inputs.append(dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    return raw

def check(name, yes):
    checks.append(dict(name=name, passed=bool(yes)))

def fp(value):
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True, separators=(',', ':')).encode('utf8')).hexdigest()

for path in sorted((BASE / 'product_checks_01/cases').glob('*_FRAME.json')):
    frame = json.loads(read(path))
    raw = read(Path(frame['arrays_path']))
    check(path.stem + ': NPZ bytes', hashlib.sha256(raw).hexdigest() == frame['arrays_sha256'])
    check(path.stem + ': PNG bytes', hashlib.sha256(read(Path(frame['image_path']))).hexdigest() == frame['image_sha256'])
    with np.load(frame['arrays_path'], allow_pickle=False) as archive:
        a = {key: archive[key] for key in archive.files}
    raw_ids, owners, patches = a['triangle_ids'], a['owners'], a['patch_owners']
    fg = owners >= 0
    offsets = a['face_patch_offsets']
    check(path.stem + ': shared shapes', raw_ids.shape == owners.shape == patches.shape == a['depth'].shape)
    check(path.stem + ': raw dtype', raw_ids.dtype == np.int32)
    check(path.stem + ': foreground exact', np.array_equal(raw_ids >= 0, fg))
    check(path.stem + ': background ids', np.all(raw_ids[~fg] == -1) and np.all(patches[~fg] == -1))
    check(path.stem + ': background depth', np.isposinf(a['depth'][~fg]).all())
    check(path.stem + ': foreground depth', np.all(np.isfinite(a['depth'][fg]) & (a['depth'][fg] > 0)))
    winner, object_ids = raw_ids[fg], owners[fg]
    check(path.stem + ': source range', np.all((winner >= 0) & (winner < offsets[-1])))
    check(path.stem + ': object offset', np.all((winner >= offsets[object_ids]) & (winner < offsets[object_ids + 1])))
    check(path.stem + ': patch lookup', np.array_equal(patches[fg], a['face_patch_ids'][winner]))
    for key in ('owner_schema', 'owner_mapping_identity', 'triangle_id_scope'):
        check(path.stem + ': ' + key, a[key].item() == frame[key])
    if path.name == 'subdivided_patch_FRAME.json':
        check('one patch retains eight raw IDs', len(np.unique(winner)) == 8 and np.unique(patches[fg]).tolist() == [0])
    if path.name == 'multi_object_near_far_unsupported_FRAME.json':
        check('unsupported preserves raw two', np.all(raw_ids[owners == 1] == 2) and np.all(patches[owners == 1] == -1))
    if path.name in ('equal_depth_first_winner_FRAME.json', 'clipped_triangle_fan_FRAME.json'):
        check(path.stem + ': source zero wins', fg.any() and set(np.unique(winner)) == {0})
    cases.append(dict(case=path.stem, shape=list(raw_ids.shape), foreground=int(fg.sum()), raw_ids=np.unique(winner).tolist()))

source_path = ROOT / 'human_eye_plugin/active_observation_images.py'
source_bytes = read(source_path)
source = source_bytes.decode('utf-8').replace('\r\n', '\n')
new_block = """        image_ref = frame.get('image_ref')
        if not image_ref:
            reference_binding = (self._binding, self._patch_mapping_identity, name, frame['image_sha256'])
            if has_raw:
                reference_binding += (OWNER_SCHEMA, self._patch_mapping['owner_identity'], frame.get('frame_identity'))
            image_ref = 'active-image:' + fingerprint(reference_binding)
"""
check('final missing-ref patch exact block once', source.count(new_block) == 1)
old = source.replace(new_block, '').replace("            'image_ref': image_ref,\n", """            'image_ref': frame.get('image_ref') or 'active-image:' + fingerprint(
                (self._binding, self._patch_mapping_identity, name, frame['image_sha256']),
            ),
""")
first = json.loads(read(BASE / 'product_checks_01/RESULT.json'))
prior_sha = first['source_pins'][0]['sha256']
check('reverting only fallback restores first matrix bytes', any(hashlib.sha256(b).hexdigest() == prior_sha
      for b in (old.encode('utf-8'), old.replace('\n', '\r\n').encode('utf-8'))))
after = json.loads(read(BASE / 'no_ref_after_02/RESULT.json'))
check('final saved-byte fallback tested current source', after['source_sha256'] == hashlib.sha256(source_bytes).hexdigest())
check('fallback checks passed zero raster', after['passed'] and after['actual_product_raster_calls'] == after['actual_direct_raster_calls'] == 0)
frame = json.loads(read(BASE / 'product_checks_01/cases/subdivided_patch_FRAME.json'))
binding = ((frame['scene_identity'], frame['candidate_identity']), frame['patch_mapping_identity'], frame['view_name'], frame['image_sha256'])
check('legacy fallback formula retained', after['actual_legacy_ref'] == 'active-image:' + fp(binding))
check('new fallback owner and frame bound', after['actual_dual_ref'] == 'active-image:' + fp(binding + (
    frame['owner_schema'], frame['owner_mapping_identity'], frame['frame_identity'])))
check('fallback schemes cannot collide in saved case', after['actual_legacy_ref'] != after['actual_dual_ref'])

for relative in ('human_eye_plugin/active_observation_host.py','human_eye_plugin/live_spatial_mcp.py',
                 'human_eye_plugin/attention_raster.py','human_eye_plugin/active_observation.py',
                 'verification/m4_view_reuse_001/native_tools.py','verification/m4_view_reuse_001/bridge.py',
                 'verification/m4_view_reuse_001/case_worker.py','verification/m4_view_reuse_001/product_checks.py',
                 'verification/m4_view_reuse_001/fallback_checks.py'):
    read(ROOT / relative)
result = dict(method='Independent NumPy saved-byte checks and source-only fallback reversal; no product/scorer imports',
              new_product_model_Blender_raster_calls=0, checks=len(checks), passed=sum(x['passed'] for x in checks),
              failures=[x for x in checks if not x['passed']], details=checks, saved_cases=cases,
              limit='Does not independently rerun the first matrix or all native integration branches.')
(OUT / 'RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(OUT / 'INPUTS.json').write_text(json.dumps(inputs, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: result[k] for k in ('checks','passed','failures')}))
raise SystemExit(bool(result['failures']))
