"""Numerical and before/after controls for the exact live-bounds verifier."""

from copy import deepcopy
from itertools import product
import json
import math
from pathlib import Path
from runpy import run_path
import sys
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
ROOT=Path('D:/he_m4_source_region_live_bounds_qualification_001')
sys.path.insert(0,str(HERE))
import verify as check
from diagnostic import direct_bounds, world_point


def must_reject(call, phrase):
    try:
        call()
    except ValueError as error:
        check.need(phrase in str(error),'wrong_boundary_rejection/'+str(error))
        return str(error)
    raise ValueError('negative_control_was_accepted/'+phrase)


def axis_cases():
    corners=list(map(list,product((-2.5,3.75),(-1.25,2.0),(-2.0,4.0))))
    unit_matrix=[
        [0.,-3.,0.,7.], [0.,0.,.5,-8.], [0.,0.,0.,-2.], [0.,0.,0.,1.],
    ]
    scale=.125
    world=[world_point(unit_matrix,p,scale) for p in corners]
    outward=check.host._acquisition_bounds(corners,unit_matrix,scale)
    guess, axes, why=direct_bounds(corners,unit_matrix,scale,outward)
    np_tight=check.numpy_tight(world)
    check.need(why is None and axes==[[1],[2],[]] and check.same_bits(guess,np_tight)
               and check.same_bits(guess,check.axis_candidate_value(corners,unit_matrix,scale))
               and check.contains(world,outward),'permuted_negative_constant_and_scaled_axis_bounds')
    changes={}
    identity=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
    for reason,matrix in (
            ('subnormal_nonzero_no_epsilon', [[1.,math.ulp(0.),0.,0.],*identity[1:]]),
            ('mixed_rotation', [[.5,.5,0.,0.],[-.5,.5,0.,0.],*identity[2:]])):
        limit=check.host._acquisition_bounds(corners,matrix,1.)
        none, axes, why=direct_bounds(corners,matrix,1.,limit)
        check.need(none is None and why=='mixed_world_axis_binary64' and len(axes[0])==2
                   and check.contains([world_point(matrix,p,1.) for p in corners],limit),
                   'nonzero_world_axis_term_treated_as_epsilon_zero')
        changes[reason]={'axis_support':axes,'actual_point_only_fallback_reason':why}
    bad={}
    for name,value in (('missing',None),('all_negative_one_sentinel',[[-1.,-1.,-1.]]*8),
                       ('nonfinite',[[math.inf,0.,0.]]*8),('missing_corner',corners[:-1])):
        limit=check.host._acquisition_bounds(value,identity,1.)
        none,_,why=direct_bounds(value,identity,1.,limit)
        check.need(limit is None and none is None and why and check.local_box(value) is None,
                   'unsupported_RNA_box_excluded_or_reused_tight')
        bad[name]=why
    basic=[[2.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
    giant=[[2e307 if k!=0 else 1e308 for k in range(3)]]*8
    unsupported,_,why=direct_bounds(giant,basic,1.,check.host._acquisition_bounds(giant,basic,1.))
    check.need(unsupported is None and why,'oversized_bound_created_exact_candidate')
    return {'scaled_negative_permutation_and_constant':{'unit_scale':scale,'numpy_tight_bits':check.bit_triplets(np_tight),
                'same_binary64_tight':True},
            'nonseparable':changes,'unknown':bad,'overflow_fallback':why}


def signed_zero():
    eps=math.ulp(0.)
    identity=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
    corners=list(map(list,product((-eps,eps),(1.,2.),(2.,3.))))
    scale=.125
    world=[world_point(identity,p,scale) for p in corners]
    box=check.host._acquisition_bounds(corners,identity,scale)
    none,axes,why=direct_bounds(corners,identity,scale,box)
    original,rev=check.numpy_tight(world),check.numpy_tight(world[::-1])
    check.need(none is None and why=='zero_plateau_sign_needs_ordered_world_scan'
               and original==rev and not check.same_bits(original,rev)
               and check.contains(world,box),'signed_zero_plateau_became_exact_or_failed_to_test_order')
    return {'axis_support':axes,'scale':scale,'point_only_fallback':why,
            'forward_order_Numpy_minmax':check.bit_triplets(original),
            'reverse_order_Numpy_minmax':check.bit_triplets(rev),'numeric_equal_but_binary64_distinct':True}


def hidden_and_stale():
    sys.path.insert(0,str(check.PRIOR))
    from sources import load_formal
    from human_eye_plugin.source_region import validate_region_ref
    case=load_formal('m4_yanyite_opposite_direction_product_native_001','75f75b920',
                     ('YANYITE_NEG_Y','YANYITE_POS_Y'))[0]
    prepared,query,_=check.VISUAL['prepare_case'](case)
    binding,capture=prepared.binding,case['capture']
    mask=binding['image_scope']['participation_mask']
    rows=[{'ordinal':i,'name':r['object_name'],'object_id':r['host_id']}
          for i,r in enumerate(binding['objects'])]
    protected={prepared.object_index, check.select_registered(rows,query['reference'])}
    reference=check.select_registered(rows,query['reference'])
    tight=[check.numpy_tight(m.vertices) for m in prepared.meshes]
    roster=check.retention(prepared.cameras,tight,protected)
    check.need(mask[reference] is False and reference in roster['kept']
               and all(reference in result for result in roster['per_view'].values())
               and len(prepared.meshes[reference].faces)==12,'actual_hidden_complete_reference_was_removed')
    selected=prepared.region_facts['vertices_world_m']
    wrong=check.host._observation_target_cameras(selected,[box for i,box in enumerate(tight) if i!=reference])
    without_hidden=check.old_camera_equal(wrong,prepared.cameras)
    check.need(not check.poses_pass(without_hidden),'hidden_reference_was_not_a_camera_depth_control')
    with check.np.load(case['npz'],allow_pickle=False) as image:
        no_hidden_pixels=int(check.np.count_nonzero(image['owners']==reference))
    check.need(no_hidden_pixels==0,'hidden_reference_participated_in_actual_archived_image')
    stale=deepcopy(capture)
    stale['capture_state']['revision']+=1
    old_ref=prepared.region_ref
    wrong_generation=must_reject(lambda:validate_region_ref(stale,old_ref),'capture_generation_changed')
    moved=deepcopy(capture)
    moved['meshes'][prepared.object_index]['vertices'][0][0]+=1.25
    wrong_pose=must_reject(lambda:validate_region_ref(moved,old_ref),'ordered_geometry_changed')
    source={x['object_id']:x for x in case['terminal']['objects']}
    ref_row=binding['objects'][reference]
    independent=source[ref_row['host_id']]
    changed={k:independent[k] for k in ('name','instance_id','matrix_world')}
    changed['instance_id']+='-stale'
    wrong_instance=must_reject(lambda:check.comparable_object(changed,independent),'actual_same_slot_instance')
    return {'actual_archive':case['proof'], 'hidden_reference_object':'Cube','reference_faces':12,
            'archived_visible_cube_pixels':no_hidden_pixels,'retained_in_all_six_and_measurement':True,
            'removing_hidden_reference_changes_original_camera':True,
            'wrong_generation_rejection':wrong_generation, 'wrong_pose_rejection':wrong_pose,
            'wrong_instance_rejection':wrong_instance}


def live_guard_contract():
    def source(start):
        return {'source':{'pid':42},'objects':[{'native':[[0.,1.,2.]],'evaluated':[[0.,1.,2.]]}],
                'scene_cameras':{'active':None},'layer_collections':{'name':'Root'},
                'source_face_offsets':[0,1],'display_object_mask':[True],'display_scope':'viewport',
                'display_read':'current','started_ns':start,'display_read_closed_ns':start+1,
                'geometry_read_closed_ns':start+2}

    first,last=source(1),source(11)
    pins,receipts={},{}
    for name,record in (('initial',first),('terminal',last)):
        raw=json.dumps(record,sort_keys=True).encode()
        pins[name.upper()+'_SOURCE.json']={'sha256':check.sha256(raw).hexdigest(),'bytes':len(raw)}
        receipts[name]={**pins[name.upper()+'_SOURCE.json'],'pid':42,
                        **{k:v for k,v in record.items() if k.endswith('_ns')},
                        'json_encoded_ns':record['started_ns']+3,'file_closed_ns':record['started_ns']+4}
    publication={'started_ns':0,'captures':receipts,'safe_worker_closed':{'closed_ns':16}}
    window={'started_ns':6,'closed_ns':10}
    args=(first,last,pins,publication,42,window)
    check.verify_live_guards(*args)
    wrong_pid=deepcopy(publication)
    wrong_pid['captures']['terminal']['pid']=43
    changed=deepcopy(last)
    changed['objects'][0]['native'][0][0]=-0.
    return {'representative_receipt_only':True,
            'wrong_pid':must_reject(lambda:check.verify_live_guards(first,last,pins,wrong_pid,42,window),
                                    'independent_capture_not_bound_to_current_process_file_and_read_window'),
            'overlapping_window':must_reject(
                lambda:check.verify_live_guards(first,last,pins,publication,42,{'started_ns':4,'closed_ns':10}),
                'independent_live_captures_do_not_bracket'),
            'changed_signed_native_coordinate':must_reject(
                lambda:check.verify_live_guards(first,changed,pins,publication,42,window),
                'guarded_native_evaluated_display_or_camera_state_changed')}


def main():
    prior=run_path(str(check.PRIOR/'controls.py'))
    np,_,images,raster,host,_,_=prior['runtime']()
    adapter=SimpleNamespace(**check.VISUAL)
    controls={
        'axis_limits_units_and_unknown':axis_cases(),'signed_zero':signed_zero(),
        'unknown_and_touch_retain':prior['bounds_controls'](host,adapter),
        'installed_X_exit_Y_overflow':prior['overflow_control'](np,host,raster,images,adapter),
        'actual_hidden_reference_and_stale':hidden_and_stale(),
        'same_process_guard_order_and_stability':live_guard_contract(),
    }
    ROOT.mkdir(parents=True,exist_ok=True)
    with (ROOT/'CONTROLS.json').open('x',encoding='utf8',newline='\n') as out:
        json.dump({'passed':True,'real_Blender':0,'models':0,'formal_rasters':0,
                   'offline_synthetic_overflow_raster_probes':2,
                   'source_pins': [check.pin(HERE /name) for name in ('verify.py','diagnostic.py','controls.py')],
                   'controls':controls},out,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        out.write('\n')
    print('PASS',', '.join(controls))


if __name__=='__main__':main()
