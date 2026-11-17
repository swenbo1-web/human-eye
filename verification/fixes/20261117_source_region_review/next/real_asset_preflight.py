"""Bind saved native/evaluated source evidence to the unchanged user asset."""
from pathlib import Path
import hashlib
import json

OUT = Path(__file__).resolve().parent
BASE = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_real_data_001')
ASSET = Path('D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend')


def read(path):
    return json.loads(path.read_bytes())


def identity(path):
    payload = path.read_bytes()
    return dict(path=str(path), bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())


inventory_path = BASE / 'INVENTORY.json'
region_path = BASE / 'private/ARM_REGION.json'
raw_path = BASE / 'private/capture_02/raw_selected.json'
evaluated_path = BASE / 'private/capture_02/evaluated_selected.json'
inventory, region = read(inventory_path), read(region_path)
raw, evaluated = read(raw_path), read(evaluated_path)
asset = identity(ASSET)
assert asset['sha256'] == inventory['source_sha256'] == region['source_sha256']
assert asset['sha256'] == '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
native = inventory['native']
target = next(row for row in native['objects'] if row['name'] == region['object_name'])
cube = next(row for row in native['objects'] if row['name'] == 'Cube')
assert target['modifiers'] == []
assert not [row for row in native['objects'] if row['type'] == 'ARMATURE']
assert native['armature_datablocks'] == []
assert target['mesh']['vertices'] == len(raw['vertices_object']) == 27304
assert target['mesh']['polygons'] == 29073
assert target['mesh']['triangles'] == len(raw['triangles']) == 53264
for field in ('object_name', 'matrix_world', 'vertex_ids', 'vertices_object',
              'vertices_world', 'triangles', 'polygon_ids_by_triangle'):
    assert raw[field] == evaluated[field], field
assert len(region['source_vertex_ids']) == 410
assert len(region['source_triangle_ids']) == 748
assert len(set(region['source_triangle_ids'])) == 748
for ordinal, source in enumerate(region['source_vertex_ids']):
    assert region['vertices_world'][ordinal] == raw['vertices_world'][source]
    assert region['vertices_object'][ordinal] == raw['vertices_object'][source]
for ordinal, source in enumerate(region['source_triangle_ids']):
    mapped = [region['source_vertex_ids'][index] for index in region['triangles_local'][ordinal]]
    assert mapped == raw['triangles'][source]
    assert region['source_polygon_ids'][ordinal] == raw['polygon_ids_by_triangle'][source]
assert cube['mesh']['triangles'] == 12
result = dict(
    status='saved_source_correspondence_verified_current_asset_sha_matches',
    scope='Root reads saved M6 exports and hashes original file; no new Blender read.',
    asset=asset,
    source_inputs=[identity(path) for path in (inventory_path, region_path, raw_path, evaluated_path)],
    object_name=region['object_name'], native_vertices=27304, native_polygons=29073,
    evaluated_triangles=53264, modifiers=target['modifiers'], armature_objects=0,
    source_region_vertices=410, source_region_triangles=748,
    selected_and_reference_triangle_total=748 + cube['mesh']['triangles'],
    reference_object=dict(name='Cube', type=cube['type'], hide_render=cube['hide_render'],
                          matrix_world=cube['matrix_world'], triangles=cube['mesh']['triangles']),
    original_native_to_evaluated='same-index identical vertices, triangles, polygon IDs in saved export',
    real_rig_or_pose_validation='unavailable_in_this_asset',
    actual_current_product_entry='not_run', fresh_asset_read='not_run',
    actual_scene_visibility='not_run; hidden reference-object participation requires explicit observation',
    model_benefit='unmeasured', new_live_Blender=0, new_raster=0, new_model=0)
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'REAL_ASSET_PREFLIGHT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(json.dumps({key: result[key] for key in ('status', 'native_vertices', 'evaluated_triangles',
      'source_region_triangles', 'selected_and_reference_triangle_total', 'real_rig_or_pose_validation')}, ensure_ascii=False))
