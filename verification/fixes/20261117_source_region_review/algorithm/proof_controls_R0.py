"""Independent synthetic controls for producer-owned NPZ byte proof.

Runs installed R1, plus the preserved early candidate for the historical
publication counterexample. Production raster is replaced with fixed buffers.
"""
import copy
import hashlib
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

OUT = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
INSTALL = Path('D:/he_m4_m5_source_region_001/R1/product')
sys.path[:0] = [str(INSTALL), 'D:/he_anchor_001/venv/Lib/site-packages']
import numpy as np
from PIL import Image
from human_eye_plugin import active_observation_images as module

cases = []
counts = dict(production_raster_calls=0, synthetic_frame_buffers=0,
              PNG_encodings=0, NPZ_encodings=0, NPZ_decodes=0)
native_savez = np.savez_compressed
native_load = np.load
native_image_save = Image.Image.save


def check(value, label):
    if not value:
        raise AssertionError(label)


def count_savez(*args, **kwargs):
    counts['NPZ_encodings'] += 1
    return native_savez(*args, **kwargs)


def count_image_save(*args, **kwargs):
    counts['PNG_encodings'] += 1
    return native_image_save(*args, **kwargs)


def count_load(*args, **kwargs):
    counts['NPZ_decodes'] += 1
    return native_load(*args, **kwargs)


def no_real_raster(*args, **kwargs):
    counts['production_raster_calls'] += 1
    raise AssertionError('production_raster_forbidden')


def input_objects():
    vertices = ((0., 0., 0.), (1., 0., 0.), (0., 1., 0.))
    objects = ((vertices, ((0, 1, 2),), 'independent-source', 'one-triangle'),)
    ident = [[float(i == j) for j in range(4)] for i in range(4)]
    pose = dict(name='SCENE', size_px=[64,64], projection='orthographic',
                view_matrix=ident, projection_matrix=ident)
    return objects, dict(views=[pose])


def buffers():
    counts['synthetic_frame_buffers'] += 1
    color = np.full((64,64,3), 12, np.uint8)
    depth = np.full((64,64), np.inf, np.float64)
    owners = np.full((64,64), -1, np.int32)
    triangles = np.full((64,64), -1, np.int32)
    color[10:14,10:14] = (100,150,200)
    depth[10:14,10:14] = 1
    owners[10:14,10:14] = 0
    triangles[10:14,10:14] = 0
    return color,depth,owners,triangles


def build(path, enabled=True, target=module):
    objects,cameras = input_objects()
    adapter = target.SceneObservationImages(objects, cameras, path,
        scene_identity='current-geometry', candidate_identity='current-cameras',
        _reuse_published_payload=enabled, _measure_stages=True)
    with patch.object(target, 'rasterize_attention', return_value=buffers()):
        frame = adapter.render_view('SCENE')
    return adapter,frame


def validate(name, adapter, frame, *, accepted, decodes, reuses=None):
    before = counts['NPZ_decodes']
    diagnostics = {}
    try:
        result = adapter.validate_frame(frame, _diagnostics=diagnostics)
        outcome,error = True,None
    except (ValueError,KeyError) as exc:
        result,outcome,error = None,False,str(exc)
    observed = counts['NPZ_decodes']-before
    check(outcome == accepted and observed == decodes,
          f'{name}/expected_accept={accepted},decode={decodes}/actual={outcome},{observed},{error}')
    if reuses is not None:
        check(diagnostics.get('fresh_payload_reuses') == reuses, name+'/reuse_count')
    cases.append(dict(case=name, accepted=outcome, error=error,
                      NPZ_decodes=observed, diagnostics=diagnostics))
    return result


def controls(directory):
    adapter,frame = build(directory/'producer')
    validate('fresh_same_producer',adapter,frame,accepted=True,decodes=0,reuses=1)
    validate('same_frame_revalidated',adapter,frame,accepted=True,decodes=0,reuses=1)
    validate('shallow_copy_of_frame',adapter,dict(frame),accepted=True,decodes=1,reuses=0)
    validate('deep_copy_of_frame',adapter,copy.deepcopy(frame),accepted=True,decodes=1,reuses=0)
    validate('saved_frame_without_buffers',adapter,{k:v for k,v in frame.items() if k!='buffers'},
             accepted=True,decodes=1,reuses=0)
    foreign,other = build(directory/'foreign')
    validate('foreign_adapter_same_geometry',foreign,frame,accepted=True,decodes=1,reuses=0)
    old,oldframe = build(directory/'old_default',enabled=False)
    validate('default_decoder_retained',old,oldframe,accepted=True,decodes=1,reuses=0)
    for key in ('arrays_path','image_path'):
        oldpath = frame[key]
        alias = directory/('path-alias-'+Path(oldpath).name)
        alias.write_bytes(Path(oldpath).read_bytes())
        frame[key] = str(alias)
        validate('changed_'+key+'_same_bytes',adapter,frame,accepted=True,decodes=1,reuses=0)
        frame[key] = oldpath
    for key in ('frame_identity','PNG_bytes'):
        original = frame[key]
        frame[key] = 'changed' if isinstance(original,str) else original+1
        validate('metadata_changed_'+key,adapter,frame,accepted=True,decodes=1,reuses=0)
        frame[key] = original
    original = frame['arrays']['color']['sha256']
    frame['arrays']['color']['sha256'] = '0'*64
    validate('array_metadata_mutation',adapter,frame,accepted=True,decodes=1,reuses=0)
    frame['arrays']['color']['sha256'] = original
    # A shallow buffer alias shares the underlying current bytes. Mutation
    # through this alias must be caught even with write=False restored.
    for key in ('color','depth','owners','triangle_ids','patch_owners'):
        original = frame['buffers'][key]
        alias = original.view()
        original.setflags(write=True)
        alias.setflags(write=True)
        location = (10,10,0) if key=='color' else (10,10)
        oldvalue = alias[location].copy()
        alias[location] = 99 if key=='color' else 2
        alias.setflags(write=False)
        original.setflags(write=False)
        validate('mutated_via_alias_'+key,adapter,frame,accepted=False,decodes=1,reuses=0)
        original.setflags(write=True)
        original[location] = oldvalue
        original.setflags(write=False)
    for changed in (frame['buffers']['depth'].astype(np.float32),frame['buffers']['depth'][:32]):
        original = frame['buffers']['depth']
        frame['buffers']['depth'] = changed
        validate('depth_dtype_or_shape_changed',adapter,frame,accepted=False,decodes=1,reuses=0)
        frame['buffers']['depth'] = original
    for group in ('arrays','owner_arrays'):
        for key,original in list(adapter._patch_mapping[group].items()):
            if not original.size:
                continue
            changed = original.copy()
            changed.flat[0] = 7 if changed.dtype.kind in 'iu' else 'foreign'
            adapter._patch_mapping[group][key] = changed
            validate('current_mapping_changed_'+key,adapter,frame,accepted=False,decodes=1,reuses=0)
            adapter._patch_mapping[group][key] = original
    for key in ('candidate_identity','mesh_order_identity','owner_mapping_identity'):
        original = frame[key]
        frame[key] = 'foreign'
        validate('binding_changed_'+key,adapter,frame,accepted=False,decodes=0,reuses=0)
        frame[key] = original
    for key in ('arrays_path','image_path'):
        path = Path(frame[key])
        original = path.read_bytes()
        path.write_bytes(original+b'added bytes')
        validate('persisted_bytes_mutated_'+key,adapter,frame,accepted=False,decodes=0,
                 reuses=0 if key=='arrays_path' else 1)
        path.write_bytes(original)
    # Coherent mutation has the old full-decoder contract. It cannot reuse the
    # proof even when caller updates every public hash to match new bytes.
    archive = Path(frame['arrays_path'])
    original_bytes,original_sha = archive.read_bytes(),frame['arrays_sha256']
    with native_load(BytesIO(original_bytes),allow_pickle=False) as source:
        changed = {key:source[key] for key in source.files}
    changed['depth'][10,10] = 2
    with BytesIO() as stream:
        np.savez_compressed(stream,**changed)
        encoded = stream.getvalue()
    archive.write_bytes(encoded)
    frame['arrays_sha256'] = hashlib.sha256(encoded).hexdigest()
    validate('updated_disk_hash_still_decodes_and_rejects_old_buffer',adapter,frame,
             accepted=False,decodes=1,reuses=0)
    original_buffer = frame['buffers']['depth']
    original_metadata = copy.deepcopy(frame['arrays']['depth'])
    frame['buffers']['depth'] = changed['depth']
    frame['arrays']['depth'] = module._array_metadata(changed['depth'])
    validate('coherent_saved_replacement_uses_full_decoder',adapter,frame,
             accepted=True,decodes=1,reuses=0)
    frame['buffers']['depth'] = original_buffer
    frame['arrays']['depth'] = original_metadata
    frame['arrays_sha256'] = original_sha
    archive.write_bytes(original_bytes)
    validate('restored_original_proof',adapter,frame,accepted=True,decodes=0,reuses=1)


def publication_counterexamples(directory):
    initial_path = AUTHOR/'verification/m4_m5_source_region_001/core_tests/opt_initial_source/active_observation_images.py'
    spec = importlib.util.spec_from_file_location('human_eye_plugin._independent_initial_image_adapter',initial_path)
    initial = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(initial)
    outcomes = []
    native_read = Path.read_bytes
    for name,target,reuse in (('old_default',module,False),('early_candidate',initial,True),('fixed_R1',module,True)):
        replacements = []
        def intercepted(path):
            if path.suffix=='.npz' and not replacements:
                with native_load(BytesIO(native_read(path)),allow_pickle=False) as source:
                    changed = {key:source[key] for key in source.files}
                changed['color'][0,0,0] ^= 1
                with BytesIO() as stream:
                    np.savez_compressed(stream,**changed)
                    path.write_bytes(stream.getvalue())
                replacements.append(str(path))
            return native_read(path)
        frame=None
        try:
            with patch.object(Path,'read_bytes',intercepted):
                adapter,frame = build(directory/name,enabled=reuse,target=target)
            adapter.validate_frame(frame)
            accepted,error = True,None
        except ValueError as exc:
            accepted,error = False,str(exc)
        check(len(replacements)==1, name+'/first_read_replacement_injected')
        check(accepted == (name=='early_candidate'), name+'/historical_publication_outcome')
        outcomes.append(dict(variant=name,accepted=accepted,error=error,NPZ_replacements=1,
                             rejected_before_frame_return=frame is None))
    return outcomes


def main():
    with tempfile.TemporaryDirectory(dir=OUT,prefix='synthetic-') as temporary:
        with patch.object(module,'rasterize_attention',side_effect=no_real_raster), \
                patch.object(np,'savez_compressed',side_effect=count_savez), \
                patch.object(np,'load',side_effect=count_load), \
                patch.object(Image.Image,'save',new=count_image_save):
            controls(Path(temporary))
            publication = publication_counterexamples(Path(temporary)/'publication')
    check(counts['production_raster_calls']==0,'zero_production_raster')
    result = dict(status='passed',cases=cases,publication=publication,counts=counts,
        installed_module_path=str(Path(module.__file__).resolve()),
        product_source_sha256=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
        new_live_operations=dict(Blender=0,MCP=0,raster=0,model=0,paid_API=0))
    (OUT/'PROOF_RESULT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=result['status'],cases=len(cases),publication=publication,counts=counts)))


if __name__=='__main__':
    try:
        main()
    except BaseException:
        import traceback
        (OUT/'PROOF_FAILURE.txt').write_text(traceback.format_exc(),encoding='utf8')
        raise
