"""Saved cache/state checker with the frozen generation/current accounting split."""

import copy
import difflib
import hashlib
import json
from pathlib import Path
import sys
import types

HERE = Path(__file__).resolve().parent
NS = HERE.parent
ORACLE = NS / 'oracle'
sys.path.insert(0, str(ORACLE))
import check_saved as frozen


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2)
        stream.write('\n')


def adapted_checker():
    original = Path(frozen.__file__).read_text(encoding='utf8')
    changes = {
        "len(all_frames) == full['work']['raster_completed'] == full['work']['local_verified_images']":
        "len(all_frames) == full['generation_work']['raster_completed'] == full['generation_work']['local_verified_images']",
        "work['capture_calls'] == work['geometry_parse_calls'] == work['mesh_conversions']":
        "actual_work['capture_calls'] == work['geometry_parse_calls'] == work['mesh_conversions']",
    }
    revised = original
    for old, new in changes.items():
        if revised.count(old) != 1:
            raise ValueError('frozen_state_adapter_expression_changed')
        revised = revised.replace(old, new)
    module = types.ModuleType('_cross_state_saved_adapter')
    module.__file__ = str(Path(frozen.__file__))
    module.__name__ = '_cross_state_saved_adapter'
    exec(compile(revised, module.__file__, 'exec'), module.__dict__)
    diff = ''.join(difflib.unified_diff(original.splitlines(True), revised.splitlines(True),
                                      fromfile='frozen/oracle/check_saved.py',tofile='saved-state-accounting-adapter'))
    return module, dict(original_sha256=hashlib.sha256(original.encode()).hexdigest(),
                        adapted_sha256=hashlib.sha256(revised.encode()).hexdigest(), diff=diff,
                        purpose='Current call work has zero new construction on cache hit. The preserved generation frames are checked against generation_work. Capture_calls is appended by the service outside generation_work.',
                        product_changes=0, live_operations=0)


def default_legacy(session, install, captures):
    audit = frozen.Audit()
    folder = session / 'product_calls/call_001'
    response = audit.read(folder / 'RESPONSE.json')
    full = audit.read(session / 'product_full/call_001/SERVICE_RESULT.json')
    parent = full['binding']
    capture = frozen.current_capture(captures,parent,audit)
    frozen.compare_geometry(capture,frozen.expected.fixture(),audit)
    frozen.source_binding_checks(capture,parent,install,audit)
    public = next(json.loads(block['text']) for block in response['result']['content'] if block['type']=='text')
    audit.check(public['schema'] == 'active-observation-brief-v2' and 'region_task' not in public, 'unchanged_default_brief_schema')
    images = [block for block in response['result']['content'] if block['type']=='image']
    frames = full['frames']
    audit.check(len(images) == len(frames) == full['work']['raster_attempts'] == 6, 'legacy_six_actual_frames')
    scope = dict(scope_id='global',binding=parent,facts=full['facts'])
    regions,mapping = frozen.patch_maps(scope,capture,audit)
    reviews = []
    observations = {row['view_name']: row for row in full['facts']['observations']}
    for frame, block in zip(frames,images,strict=True):
        audit.check(frozen.base64.b64decode(block['data'],validate=True)
                    == audit.file(frame['image_path'],frame['image_sha256'],session), 'original_legacy_native_image')
        # The wrapper identifies the existing single global scope for shared
        # buffer checks. These two fields are outside the legacy wire schema.
        wrapped_frame = dict(frame,scope_id='global',camera_identity=parent['camera_identity'])
        observation = dict(observations[frame['view_name']],scope_id='global',frame_identity=frame['frame_identity'])
        reviews.append(frozen.check_frame(wrapped_frame,observation,scope,capture,regions,mapping,session,audit))
    return dict(passed=True, checks=len(audit.checks), frames=reviews, input_pins=list(audit.pins.values()),
                wrapper_scope='In-memory single-scope adapter for saved buffer checks. Original legacy public bytes checked separately.')


def evaluate(session):
    session = session.resolve()
    slot = frozen.read(session/'SLOT_RESULT.json')
    binding_path = Path(slot['run_binding_path'])
    install = frozen.read(binding_path)
    checker, adjustment = adapted_checker()
    control_current = dict(capture_calls=1,raster_completed=0,local_verified_images=0)
    control_generation = dict(raster_completed=3,local_verified_images=3,geometry_parse_calls=1,mesh_conversions=1)
    correction_controls = dict(original_current_frame_count_rejects_cache=3 != control_current['raster_completed'],
                               adapted_generation_frame_count_accepts=3 == control_generation['raster_completed'],
                               original_generation_capture_count_absent='capture_calls' not in control_generation,
                               adapted_current_capture_count_matches_geometry=control_current['capture_calls'] == control_generation['geometry_parse_calls'])
    if not all(correction_controls.values()):
        raise ValueError('saved_cache_accounting_counterexamples')
    audit = frozen.Audit()
    captures, commands = frozen.decode_captures(session,install,audit)
    legacy = default_legacy(session,install,captures)
    labels = ('initial','full','repeat','conditions','moved','restored')
    records = []
    for index,label in enumerate(labels,2):
        output = HERE/('state_' + label + '_QUALITY.json')
        record = checker.check_session(session,binding_path,'optimized',index,label=='moved')
        save(output,record)
        records.append(dict(label=label,call_index=index,report=str(output),report_sha256=frozen.PIXELS.sha(output),
                            current=record['current_capture']['capture_state'],quality_checks=record['check_count'],
                            frames=record['selected_frames'],outcomes=record['outcomes'],work=record['work']))
    initial, full, repeat, conditions, moved, restored = records
    for cached in (full,repeat):
        if (cached['frames'] != initial['frames'] or cached['outcomes'] != initial['outcomes']
                or cached['current'] != initial['current'] or cached['work']['result_cache_hit'] is not True
                or cached['work']['raster_attempts'] != 0):
            raise ValueError('same_current_task_cache_or_delivery_mismatch/' + cached['label'])
    if ({row['object_name'] for row in conditions['outcomes']} != {'Obj_02','Obj_06'}
            or len(conditions['frames']) != 2 or conditions['work']['result_cache_hit'] is True):
        raise ValueError('condition_cache_key_or_eligible_set')
    if moved['current'] == initial['current'] or restored['current'] in (initial['current'],moved['current']):
        raise ValueError('geometry_change_or_restore_old_generation_reused')
    original_pairs = {(row['object_name'],tuple(row['source_triangle_indices'])):(row['status'],row['reason']) for row in initial['outcomes']}
    for row in (moved,restored):
        state_pairs = {(outcome['object_name'],tuple(outcome['source_triangle_indices'])):(outcome['status'],outcome['reason']) for outcome in row['outcomes']}
        if state_pairs != original_pairs:
            raise ValueError('translated_or_restored_task_quality')
    result = dict(schema='cross-scale-independent-state-quality-v1',passed_checked_scope=True,default_legacy=legacy,
        records=records, state_request_count=7, predicted_rasters=17,
        actual_rasters=6+sum(row['work']['raster_attempts'] for row in records),
        saved_accounting_adapter=adjustment, adapter_controls=correction_controls,
        extra_live_operations=0, input_pins=list(audit.pins.values())+[frozen.expected.EXACT.pin(__file__)])
    save(HERE/'STATE_QUALITY.json',result)
    return result


if __name__=='__main__':
    root = Path(sys.argv[1]) if len(sys.argv)>1 else Path('D:/he_m4_cross_scale_001/sessions/state')
    result = evaluate(root)
    print(json.dumps(dict(passed=result['passed_checked_scope'],requests=result['state_request_count'],rasters=result['actual_rasters'])))
