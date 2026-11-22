"""Bind the checked historical inputs, single-byte wrong scope and native computation."""

import contextlib
import io
import json
from pathlib import Path
from runpy import run_path
import sys

HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
C = run_path(str(HERE/'closed.py'))
VISUAL,DIAG,E = (C[key] for key in ('VISUAL','DIAG','E'))
W = VISUAL['W']
SOURCE = V/'m1_region_task_first_packet_consumption_holdout_recovery_001'
PREVIOUS = V/'m1_region_task_first_packet_projection_001/install/PRODUCT_RUN_BINDING.json'
DEPENDENCIES = V/'m5_harness_recovery_001/SHARED_DEPENDENCY.json'
CONTROLS = V/'m1_region_task_witness_image_path_001/checks/controls.py'
SLOT = Path('D:/he_m1_region_task_first_packet_consumption_holdout_recovery_001/slots/QB')
require,read,pin = (VISUAL[key] for key in ('require','read','pin'))


def preflight():
    installed = read(PREVIOUS)
    sys.path[:0] = [installed['dependency_root'],read(DEPENDENCIES)['dependency_root']]
    original = run_path(str(CONTROLS))
    historical = original['replay']()
    require(historical['passed'] and historical['new_exact_rejects']==3
            and historical['archived_normal_pass']==4,'historical_wrong_public_scope_control_failed')
    asset_record = read(SLOT/'SLOT_RESULT.json')
    truth = VISUAL['truth']()
    source,closed = E['verify_closed'](SLOT,asset_record,truth)
    wire = C['PRIOR']['closed_wire'](SLOT)
    require(closed['passed'],'historical_same_asset_real_closed_source_missing')
    qb_case = original['OriginalArchive'](SOURCE,SLOT.parent.parent,'recovery')
    item = original['take_discovery'](qb_case,'QB',1,3)
    reply = json.loads(item['rx'])
    producer = item['producer']
    passed = VISUAL['verify_product'](SLOT,reply,producer,source,require_paths=False,installed=installed)
    require(passed['passed'] and len(passed['witnesses'])==2 and len(passed['P_blockers'])==6,
            'current_scope_checker_does_not_accept_original_pixels_and_positive_area_regions')
    verified = W['verify_public_witnesses'](reply,producer)
    mutation,start = original['mutate_frame_index'](item['rx'],verified)
    try:
        VISUAL['verify_product'](SLOT,json.loads(mutation),producer,source,require_paths=False,installed=installed)
    except ValueError as error:
        require(str(error)==W['WITNESS_BINDING_ERROR'],'wrong_scoped_original_did_not_fail_exact_gate')
        rejection = str(error)
    else:
        raise ValueError('same_named_wrong_scope_was_treated_as_complete')

    measurement_path = SLOT/'client/call_05/RESPONSE.json'
    measure_producer = SLOT/'product_full/call_003/SERVICE_RESULT.json'
    measurement = VISUAL['verify_measurement'](read(measurement_path),read(measure_producer),source,
                                               parent_binding=producer['binding'])
    import numpy as np
    native = VISUAL['module'](VISUAL['DENSE_NATIVE'])
    validator = V/'m4_target_task_consumption_001/native_tools.py'
    code = DIAG['native_code']()
    run_path(str(validator))['validate_code'](code)
    context = {'np':np,'qualification_rows':native['live_rows'](source),
               'qualification_capture':{'source_ref':'sealed_offline_ordinary_arrays'}}
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(code,context)
    native_result = json.loads(output.getvalue())
    require(native_result['dependencies']=={'numpy':6,'shapely':1.0}
            and native_result['measurement']['squared_lower_bound']=='1/16'
            and native_result['measurement']['bound_reference_faces']==514
            and E['_RECOVERY']['measured'](native_result['measurement'],source,truth)==measurement,
            'ordinary_exact_surface_point_or_dependency_offline_proof_failed')
    for row in native_result['regions']:
        expected = truth['regions'][row['object_name']]
        require(all(row[key]==expected[key] for key in ('source_triangle_indices','center_world_m'))
                and {view:item['status'] for view,item in row['views'].items()}==
                    {view:item['status'] for view,item in expected['directions'].items()},
                'ordinary_offline_region_or_finite_direction_proof_failed')

    historical_pins = historical['checked_archived_members']
    essential = (Path(__file__),HERE/'visual.py',HERE/'closed.py',HERE/'diagnostic.py',HERE/'native_case.py',
                 DIAG['ORACLE'],VISUAL['TRUTH'],VISUAL['RECOVERY'],VISUAL['WITNESS'],VISUAL['DENSE_NATIVE'],
                 VISUAL['ORACLE'],PREVIOUS,DEPENDENCIES,CONTROLS,validator,
                 SOURCE/'FROZEN.json',SOURCE/'RAW_INDEX.json',SOURCE/'ORIGINAL_RUNTIME.zip',
                 V/'m1_region_task_first_packet_consumption_holdout_001/checks/evidence.py',
                 V/'m1_region_task_first_packet_consumption_holdout_001/FROZEN.json',
                 V/'m1_region_task_first_packet_consumption_holdout_001/RAW_INDEX.json',
                 V/'m1_region_task_first_packet_consumption_holdout_001/ORIGINAL_RUNTIME.zip',
                 V/'m4_dense_region_brief_001/checks/brief_schema.py',
                 V/'perf050_dense_micro_surface_holdout_recovery_001/qualification/frame.py',
                 V/'perf050_dense_micro_surface_holdout_recovery_001/qualification/verify.py',
                 V/'m4_cross_scale_live_qualification_001/checks/delivery.py',
                 V/'m4_cross_scale_live_task_formal_001/scoring/formal.py',
                 V/'m4_cross_scale_discovery_001/oracle/geometry_witness.py',
                 V/'m5_observe_measure_001/oracle.py',measurement_path,measure_producer,
                 SLOT/'native/WIRE/INDEX.json',SLOT/'native/WORKER_EVENTS.jsonl',
                 *(path for folder in (SLOT/'native/WIRE').iterdir() if folder.is_dir()
                   for path in folder.iterdir()))
    by_path = {Path(row['path']).resolve():row for row in historical_pins.values()}
    for path in essential:
        by_path[path.resolve()] = pin(path)
    return {'passed':True,'archived_scope_control':{
        'source':'real closed historical Product QB packet on exact same asset',
        'wire_bytes':len(item['rx']),'wrong_wire_bytes':len(mutation),'wrong_frame_index_offset':start,
        'rejected_for':rejection,'historical_other_same_length_rejects':historical['new_exact_rejects'],
        'original_raw_witnesses':passed['scoped_public_witnesses']},
        'archived_native_wire_closed_and_flushed':len(wire),
        'archived_fixture_witness_pixels':passed['witnesses'], 'measurement':measurement,
        'archived_native_calculation':native_result,
        'scope':'read-only sealed genuine wire replay and ordinary algorithm on retained current arrays',
        'live_Blender_starts':0,'live_models':0,'new_PNG_constructions':0,
        'source_pins':list(by_path.values())}


if __name__=='__main__':
    receipt = preflight()
    target = HERE/'QUALIFICATION_PREFLIGHT.json'
    with target.open('x',encoding='utf8',newline='\n') as stream:
        stream.write(json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'passed':receipt['passed'],'pins':len(receipt['source_pins'])}))
