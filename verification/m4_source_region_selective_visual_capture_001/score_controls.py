"""Adversarial scoring controls using custody-bound historical raster/source bytes."""

from copy import deepcopy
from pathlib import Path
import json
from sys import argv, path

path.insert(0,str(Path(__file__).resolve().parent))
import score


def rejected(action, expected):
    try:
        action()
    except ValueError as failure:
        score.need(str(failure) == expected, 'control_rejected_for_unexpected_reason/' + str(failure))
        return expected
    raise ValueError('bad_control_passed/' + expected)


def run():
    reference = score.reference_inputs()
    case = reference['M21']
    original = case['producer']
    terminal = case['terminal']
    rows = score.same_source(terminal, terminal)
    shot, ref, chosen = score.case_selection(rows, case['query'])
    kept = list(range(len(rows)))
    mask = [r['visible_get'] for r in rows]
    frame, = original['frames']
    png, npz = case['png'].read_bytes(), case['npz'].read_bytes()
    raster = score.unpack_frame_arrays(frame,png,npz,mask,rows,kept)
    score.measurement(original,original,rows,shot,ref,chosen)
    score.roi_visibility(original,frame,raster,shot,chosen,original)
    hits = {}

    wrong = deepcopy(original)
    remapped = wrong['task_result']['source_mapping']['nearest_witness']['b']
    remapped['source_triangle_indices'] = [5]
    hits['wrong_exact_point_triangle_same_object'] = rejected(
        lambda: score.measurement(wrong,original,rows,shot,ref,chosen),
        'wrong_source_witness_triangle/b')
    wrong = deepcopy(original)
    wrong['facts']['visibility']['frame_identity'] = case['proof']['frame']['frame_identity'][:-1]
    hits['wrong_frame_with_same_native_png'] = rejected(
        lambda: score.roi_visibility(wrong,frame,raster,shot,chosen,original),
        'real_frame_ROI_visibility_changed')
    wrong = deepcopy(original)
    wrong['binding']['camera_specification']['views'][0]['far'] += .01
    hits['wrong_far_plane_same_named_camera'] = rejected(
        lambda: score.camera_contract(wrong,original,frame), 'registered_six_pose_binary64_mismatch')
    hits['private_legacy_reference'] = rejected(
        lambda: score.assert_no_old_refs({'frame':{'current':['source-region-image:abc']}}),
        'private_representation_reused_old_reference_namespace')
    wrong = deepcopy(terminal)
    matrix = wrong['objects'][0]['matrix_world']
    matrix[0][1] = -0.
    if score.same_bits(matrix, terminal['objects'][0]['matrix_world']):
        matrix[0][1] = 0.
    hits['changed_signed_zero_pose'] = rejected(
        lambda: score.same_source(terminal,wrong),
        'terminal_geometry_pose_or_display_changed/' + rows[0]['name'])
    wrong = deepcopy(original)
    wrong['binding']['objects'][shot]['instance_id'] = rows[ref]['instance_id']
    hits['wrong_instance_same_label_and_png'] = rejected(
        lambda: score.producer_domain(wrong,rows,kept,False),
        'producer_scope_order_or_instance_mismatch')
    hit = rows[shot]['evaluated']['vertices_world_m']
    tight = [[min(v[i] for v in hit) for i in range(3)],[max(v[i] for v in hit) for i in range(3)]]
    cam = original['binding']['camera_specification']
    hits['false_omission_of_selected_object'] = rejected(
        lambda: score.validate_omitted(tight,hit,cam), 'omitted_object_can_reach_registered_viewport')
    bad = deepcopy(cam)
    bad['views'][0]['projection_matrix'][1][1] = 1.7e308
    cloud = [[10.,10.,10.],[20.,20.,20.]]
    hits['X_early_out_cannot_hide_Y_overflow'] = rejected(
        lambda: score.validate_omitted(cloud,cloud,bad),
        'omitted_object_cannot_prove_finite_all_three_projected_axes')
    alternate = {**raster, 'depth':raster['depth'].copy()}
    pos = next(zip(*score.np.nonzero(raster['owners'] >= 0)))
    alternate['depth'][pos] = score.np.nextafter(alternate['depth'][pos],score.np.float64('inf'))
    hits['one_ulp_depth_change'] = rejected(
        lambda: score.same_raster(raster,alternate,'depth_control'), 'raster_bits_changed/depth_control/depth')
    return {'passed':True, 'formal_Blender':0,'held_frames_rendered_again':0,'controls':hits}


if __name__ == '__main__':
    result = run()
    if len(argv) == 2:
        with Path(argv[1]).open('x',encoding='utf8',newline='\n') as handle:
            json.dump(result,handle,ensure_ascii=False,indent=2,sort_keys=True)
            handle.write('\n')
    print(json.dumps(result,ensure_ascii=False))
