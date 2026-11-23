"""Publish only receipt identities, measured counters and camera evidence summaries."""

from hashlib import sha256
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path('D:/he_m4_source_region_visual_scope_proof_001')
VIEWS = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')
CASES = ('N19', 'N25', 'N12', 'M19', 'M21', 'YANYITE_NEG_Y', 'YANYITE_POS_Y')
PHASES = ('actual_raster', 'PNG_NPZ_publication', 'frame_metadata')
CAMERA_INPUTS = {
    'scene_and_display_order': {
        'recorded_source': 'actual same-capture packet and current evaluated view-layer display',
        'cold_host': 'enumerate current depsgraph instances, poses and visibility with same-generation validation',
    },
    'view_directions_and_resolution': {
        'recorded_source': 'six installed registered directions and original cameras',
        'cold_host': 'known before geometry; the resulting target XY extent is not known yet',
    },
    'selected_world_vertices_XY': {
        'recorded_source': 'bound original selected source triangles and their true world vertices',
        'cold_host': 'requires exact evaluated target mesh or validated current resident geometry',
    },
    'original_tight_scene_depth': {
        'recorded_source': 'exact min/max of every original world mesh, including the hidden reference',
        'cold_host': 'full evaluation or a validated same-generation tight directory; outer boxes differ',
    },
    'conservative_scene_depth': {
        'recorded_source': 'archived evaluated local vertex extrema with installed outward affine transformation',
        'cold_host': 'targeted-host code reads evaluated.bound_box and matrix; metadata enclosure and cheapness unverified here',
    },
    'ordered_source_offsets': {
        'recorded_source': 'actual original source counts and original drawing order',
        'cold_host': 'upper counts do not establish exact original offsets; keep private object/local source identity',
    },
    'reference': {
        'recorded_source': 'same current whole reference mesh, independent display mask',
        'cold_host': 'acquire whole reference or validated resident resource',
    },
}


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path)
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}


def summarize_lane(lane, original):
    extra = 0
    frames = lane['same_camera_by_view']
    counts = lane['counts']
    assert set(frames) == set(VIEWS)
    private_difference = original or counts['common']['objects'] < counts['complete']['objects']
    for view in VIEWS:
        row = frames[view]
        a,b = row['full'],row['scoped']
        assert all(row['equal'].values()) and row['PNG_byte_identity']
        if private_difference:
            assert a['frame_identity']!=b['frame_identity'] and a['image_scope_identity']!=b['image_scope_identity']
            assert a['npz']['sha256']!=b['npz']['sha256']
        per_view = lane['per_view_replay'][view]
        if not per_view['used_common_subset']:
            assert all(per_view['equal'].values()) and per_view['PNG_byte_identity']
            extra += 1
    return {
        'retained': counts,
        'phase_sums_ns': {arm:{field:sum(frames[v][arm]['stage_ns'][field] for v in VIEWS)
                               for field in PHASES} for arm in ('full', 'scoped')},
        'all_view_sparse_diagnostic_votes':lane['actual_search_full']['votes'],
        'production_sparse_search_votes':lane['actual_search_full']['actual_search_votes'],
        'chosen_view':lane['actual_route']['view'],
        'sparse_selection_ns':[lane['actual_search_full']['elapsed_ns'],lane['actual_search_common_subset']['elapsed_ns']],
        'independent_ordinal_domain':private_difference,
        'distinct_per_view_replays':extra,
        'original_frame_rejected':lane['cross_scope_original_frame_rejection'],
    }


def main():
    runs = [read(ROOT/'cases'/k/'RUN_RESULT.json') for k in ('main','yanyite')]
    inputs = [item for run in runs for item in run['case_receipts']]
    controls_path, auxiliary_path = ROOT/'CONTROLS.json', ROOT/'AUXILIARY.json'
    controls,auxiliary=read(controls_path),read(auxiliary_path)
    assert controls['passed'] and controls['proof_sha256']==pin(HERE/'proof.py')['sha256']
    assert all(r['passed'] and r['live_blender']==r['models']==0 for r in runs)
    assert [item['label'] for item in inputs]==list(CASES) and runs[0]['product']==runs[1]['product']
    assert controls['installed_commit']==runs[0]['product']['git']
    index_file=ROOT/'sealed/RAW_INDEX.json'
    index=read(index_file)
    assert pin(index['archive']['path'])==index['archive']
    result={
        'task':'M4-SOURCE-REGION-VISUAL-SCOPE-PROOF-001',
        'plan':'5118b228d8a2a2addfb4ba17213da7b39bba21d3',
        'passed':True, 'scope':'offline equivalence under identical admissible matrices',
        'product':runs[0]['product'],
        'budget':{'live_Blender':0,'models':0,'builds':0,'installs':0,'product_changes':0,'extra_API':0},
        'camera_input_sources':CAMERA_INPUTS,
        'cases':{},
        'raw_originals':{'archive':index['archive'],'member_count':index['member_count'],'index':pin(index_file),
                         'synthetic_controls':pin(controls_path),'auxiliary_real_controls':pin(auxiliary_path)},
    }
    q={'main_and_Yanyite_original_frames':0, 'dense_original_frames':len(auxiliary['dense']['original_frame_replays']),
       'original_matrix_pairs':0,'new_conservative_matrix_pairs':0,'additional_per_view_raster_pairs':0,
       'old_vs_new_camera_matrix_changes':0,'old_vs_new_depth_changed_views':0,'old_vs_new_PNG_changes':0,
       'old_vs_new_RGB_changed_pixels':0,'old_vs_new_owners_changed_pixels':0,'old_vs_new_triangle_changed_pixels':0,
       'synthetic_control_groups':len(controls['controls'])}
    for item in inputs:
        case_path = item['result']['path']
        assert pin(case_path)==item['result']
        case = read(case_path)
        original=case['actual_archived_frame']
        old=case['original_camera_tight_world']
        outer=case['original_camera_cheap_hypothesis']
        new=case['separate_conservative_camera']
        assert case['passed'] and all(original['comparison_with_full_replay'].values())
        assert case['retained_measurement']['matches_original'] and outer['same_scope_as_original_tight_replay']
        assert new['status']=='passed_separate_camera_scope'
        a,b=(summarize_lane(lane,first) for lane,first in ((old,True),(new['same_new_camera'],False)))
        assert a['original_frame_rejected'] and b['original_frame_rejected']
        shift=new['against_original_full_raster']
        q['main_and_Yanyite_original_frames']+=1
        q['original_matrix_pairs']+=len(old['same_camera_by_view'])
        q['new_conservative_matrix_pairs']+=len(new['same_new_camera']['same_camera_by_view'])
        q['additional_per_view_raster_pairs']+=a['distinct_per_view_replays']+b['distinct_per_view_replays']
        q['old_vs_new_camera_matrix_changes']+=sum(not v['view_matrix_bitwise_equal'] and not v['projection_bitwise_equal'] for v in shift.values())
        q['old_vs_new_depth_changed_views']+=sum(v['depth_bit_change_pixels']>0 for v in shift.values())
        q['old_vs_new_PNG_changes']+=sum(not v['PNG_byte_identity'] for v in shift.values())
        q['old_vs_new_RGB_changed_pixels']+=sum(v['RGB_change_pixels'] for v in shift.values())
        q['old_vs_new_owners_changed_pixels']+=sum(v['owner_change_pixels'] for v in shift.values())
        q['old_vs_new_triangle_changed_pixels']+=sum(v['triangle_change_pixels'] for v in shift.values())
        result['cases'][case['label']]={
            'offline_proof':item['result'],'original_frame':original,'original_matrix':a,'new_conservative_matrix':b,
            'old_vs_new_camera':shift,'old_matrix_with_conservative_bound_counts':outer['counts'],
            'measurement':case['retained_measurement'],'original_prepare_wall_ns':case['prepared_original_ns'],
            'bounds_offline_input_validation_ns':case['bounds_original_readback_and_affine_ns'],
            'new_camera_preparation_ns':new['preparation_ns'],'offline_wall_ns':case['offline_case_window_ns'],
        }
    assert q=={'main_and_Yanyite_original_frames':7,'dense_original_frames':2,'original_matrix_pairs':42,
               'new_conservative_matrix_pairs':42,'additional_per_view_raster_pairs':52,
               'old_vs_new_camera_matrix_changes':42,'old_vs_new_depth_changed_views':42,'old_vs_new_PNG_changes':3,
               'old_vs_new_RGB_changed_pixels':4,'old_vs_new_owners_changed_pixels':0,'old_vs_new_triangle_changed_pixels':12,
               'synthetic_control_groups':5}
    result['quality']=q
    result['additional_cases']={
        'dense':{'roster':auxiliary['dense']['original_roster'],
                 'original_matrix_retained':auxiliary['dense']['old_all_six_retained'],
                 'exact_blockers':auxiliary['dense']['blocker_rows']},
        'rail_thin':{'exact_blockers':auxiliary['rail_thin']['blocker_rows']},
        'Yanyite_unselected_target':auxiliary['yanyite_self_occlusion'],
        'numeric_overflow':{k:controls['controls']['supernumeric_other_axis_after_x_exclusion'][k] for k in
                            ('full_replay_rejection','incorrectly_pruned_render_pixels','proof_result')},
    }
    with (HERE/'RESULT.json').open('x',encoding='utf8',newline='\n') as out:
        json.dump(result,out,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)
        out.write('\n')
    print(q)


if __name__=='__main__':
    main()
