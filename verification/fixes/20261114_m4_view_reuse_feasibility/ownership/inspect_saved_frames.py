"""Offline inspection only: no product imports, rendering, model or Blender calls."""
from pathlib import Path
import hashlib
import json
import numpy as np

OUT = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
PRODUCT = Path('D:/he_consume_001/product')
ROOT = Path('D:/he_consume_001/formal/P1/o')
manifest = []

def read_file(path):
    path = Path(path)
    data = path.read_bytes()
    manifest.append(dict(path=path.as_posix(), bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    return data

for relative in ('human_eye_plugin/attention_raster.py', 'human_eye_plugin/active_observation_images.py',
                 'verification/m4_consumable_observation_001/native_tools.py',
                 'verification/m4_consumable_observation_001/bridge.py'):
    read_file(AUTHOR / relative)
for relative in ('human_eye_plugin/attention_raster.py', 'human_eye_plugin/active_observation_images.py'):
    if (PRODUCT / relative).is_file():
        read_file(PRODUCT / relative)
obs = json.loads(read_file(ROOT / 'OBSERVATIONS.json'))
frames = obs['frames']
prod = next(f for f in frames if f['view_name'] == 'SCENE' and f['origin'] == 'product')
native = next(f for f in frames if f['view_name'] == 'SCENE' and f['origin'] == 'native')
read_file(prod['NPZ']); read_file(native['NPZ'])
read_file(prod['PNG']); read_file(native['PNG'])

with np.load(prod['NPZ'], allow_pickle=False) as p, np.load(native['NPZ'], allow_pickle=False) as n:
    raw = n['triangle_ids']
    mapping = p['face_patch_ids']
    foreground = n['owners'] >= 0
    derived = np.full(raw.shape, -1, dtype=np.int32)
    derived[foreground] = mapping[raw[foreground]]
    roi72 = p['patch_owners'] == 72
    summary = dict(
        method='Offline saved NPZ comparison; numpy only; no product imports or renderer executions',
        new_product_calls=0, new_model_calls=0, new_Blender_calls=0, new_raster_calls=0,
        product_source_digest=obs['active'][0]['product_source_sha256'],
        product_keys=p.files, native_keys=n.files,
        same_pose=prod['pose'] == native['pose'],
        same_PNG_sha=prod['PNG_sha256'] == native['PNG_sha256'],
        equal_arrays={key: bool(np.array_equal(p[key], n[key])) for key in ('color', 'depth', 'owners')},
        raw_triangle_background_values=np.unique(raw[~foreground]).tolist(),
        raw_triangle_foreground_range=[int(raw[foreground].min()), int(raw[foreground].max())],
        product_face_offsets=p['face_patch_offsets'].tolist(),
        source_triangle_count=len(mapping), mapping_payload_bytes=sum(p[k].nbytes for k in p.files if k not in ('color','depth','owners','patch_owners')),
        full_frame_raw_to_patch_lookup_equal=bool(np.array_equal(derived,p['patch_owners'])),
        visible_region72_source_triangle_ids=np.unique(raw[roi72]).tolist(),
        region72_mapped_source_triangles=np.flatnonzero(mapping==72).tolist(),
        query_pixel=dict(x=109,y=247,object_owner=int(p['owners'][247,109]), patch_owner=int(p['patch_owners'][247,109]),raw_triangle=int(raw[247,109])),
        saved_product_buffers_bytes=sum(p[k].nbytes for k in ('color','depth','owners','patch_owners')),
        added_raw_int32_bytes=int(raw.nbytes), added_three_frame_bytes=int(raw.nbytes*3),
    )
OUT.joinpath('INPUT_HASHES.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
OUT.joinpath('SAVED_FRAME_FINDINGS.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
