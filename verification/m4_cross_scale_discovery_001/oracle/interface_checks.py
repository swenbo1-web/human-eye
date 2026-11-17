"""Exercise the new validator against a sealed existing frame and pure counterexamples."""

import copy
from fractions import Fraction as F
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_saved as checker
import expected
import geometry_witness


def main():
    checks = []
    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))
    audit = checker.Audit()
    review_path = expected.PRIOR/'checks/global_FRAMES_R2.json'
    previous = audit.read(review_path)
    capture = previous['current_capture']
    full_path = Path('D:/he_m4_global_local_001/sessions/global/product_full/call_001/SERVICE_RESULT.json')
    full = audit.read(full_path)
    install = audit.read(expected.PRIOR/'B_RUN_BINDING.json')
    checker.source_binding_checks(capture, full['binding'], install, audit)
    scope = dict(scope_id='global', binding=full['binding'], facts=copy.deepcopy(full['facts']))
    regions, mapping = checker.patch_maps(scope,capture,audit)
    frame = dict(full['frames'][0],scope_id='global',camera_identity=full['binding']['camera_identity'])
    observation = dict(scope['facts']['observations'][0],scope_id='global',frame_identity=frame['frame_identity'])
    checked = checker.check_frame(frame,observation,scope,capture,regions,mapping,
                                 Path('D:/he_m4_global_local_001/sessions/global'),audit)
    check('sealed_known_good_frame_new_helper', checked['independent_ray_review']['all_actual_foreground_pixels_checked_for_source_membership_and_no_nearer_surface'])
    fixture = expected.fixture()
    _, eligible = expected.task_components(fixture,expected.MAIN)
    proofs = []
    for region in eligible:
        if region['object_name'] != 'Obj_06':
            proof = geometry_witness.prove(fixture,region,(4,-4,3))
            proofs.append(dict(object_name=region['object_name'],**proof))
            check('whole_rectangle_open/' + region['object_name'],proof['occluder_triangles_checked']==54)
    try:
        geometry_witness.prove(fixture,next(row for row in eligible if row['object_name']=='Obj_06'),(4,-4,3))
    except ValueError as error:
        check('covered_projection_refuses_complete',str(error).startswith('positive_area_front_occluder/'))
    else:
        check('covered_projection_refuses_complete',False)
    altered = copy.deepcopy(observation)
    altered['frame_identity'] = 'wrong-current-frame'
    try:
        checker.check_frame(frame,altered,scope,capture,regions,mapping,
                            Path('D:/he_m4_global_local_001/sessions/global'),checker.Audit())
    except ValueError as error:
        check('wrong_frame_counterexample',str(error)=='observation_frame_identity')
    else:
        check('wrong_frame_counterexample',False)
    result = dict(schema='cross-scale-saved-interface-controls-v1',passed=all(row['passed'] for row in checks),
        checks=checks, pixel_source_checks=len(audit.checks), proof_open=proofs,
        use_of_prior='One already accepted original frame validates the newly authored saved-byte helper. Added scope fields are in-memory interface inputs and are not evidence of a new cross-scale product execution.',
        old_matrix_replays=0,actual_operations=dict(Blender=0,MCP=0,raster=0,model=0),
        input_pins=list(audit.pins.values())+[expected.EXACT.pin(__file__),expected.EXACT.pin(checker.__file__)])
    with (HERE/'INTERFACE_CHECKS.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=result['passed'],controls=len(checks),saved_checks=len(audit.checks))))
    if not result['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
