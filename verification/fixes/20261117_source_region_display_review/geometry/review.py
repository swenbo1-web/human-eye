"""Independent current source/display/measurement review using saved artifacts.

Previously proved identical static geometry is pinned and compared bytewise,
then its exact box distance and source memberships are recomputed once. New
display/current-generation records and all eight measurements are checked.
"""
import ast
from collections import Counter
from fractions import Fraction as F
import hashlib
import itertools
import json
from pathlib import Path
import traceback

OUT=Path(__file__).resolve().parent
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
NS=AUTHOR/'verification/m4_source_region_display_001'
RUN=Path('D:/he_m4_source_region_display_001/sessions')
PRIOR=Path('D:/hefe/verification/fixes/20261117_real_asset_region_review/geometry')
PRIOR_SOURCE=Path('D:/he_m4_real_asset_region_001/sessions/main/SOURCE_initial.json')
PRIOR_FULL=Path('D:/he_m4_real_asset_region_001/sessions/main/product_full/call_001/SERVICE_RESULT.json')
checks=Counter()
pins={}


def check(value,label):
    if not value:raise AssertionError(label)
    checks[label]+=1


def raw(path):
    path=Path(path)
    value=path.read_bytes()
    pins[str(path)]=dict(bytes=len(value),sha256=hashlib.sha256(value).hexdigest())
    return value


def read(path):return json.loads(raw(path))


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')


def digest(value):return hashlib.sha256(canonical(value)).hexdigest()


def pure_functions(path,names,env):
    tree=ast.parse(raw(path).decode('utf8'))
    selected=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    check({n.name for n in selected}==set(names),'prior_independent_functions_found')
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),'exec'),env)
    return env


def geometry_domains():
    prior_result=read(PRIOR/'RESULT.json')
    baseline_raw=raw(PRIOR_SOURCE)
    check(hashlib.sha256(baseline_raw).hexdigest()==prior_result['input_pins'][str(PRIOR_SOURCE)]['sha256'],
          'previous_independently_verified_source_bytes_unchanged')
    baseline=json.loads(baseline_raw)
    env=pure_functions(PRIOR/'review.py',['sub','dot','cross','member','binary64_world','closed_box','box_distance'],
                       dict(F=F,itertools=itertools,check=check))
    baseline_full=read(PRIOR_FULL)
    arm=read(NS/'inputs/ARM_REGION.json')
    previous_arm=next(p for p in prior_result['input_pins'] if p.endswith('inputs\\ARM_REGION.json') or p.endswith('inputs/ARM_REGION.json'))
    check(pins[str(NS/'inputs/ARM_REGION.json')]['sha256']==prior_result['input_pins'][previous_arm]['sha256'],
          'same_historical_748_face_region_bytes')
    target_name=arm['object_name']
    original={o['name']:o for o in baseline['objects']}
    target=original[target_name]
    cube=original['Cube']
    check(len(target['native']['vertices'])==27304 and len(target['native']['polygons'])==29073
          and len(target['native']['triangles'])==53264,'baseline_character_source_counts')
    check([target['native']['triangle_polygons'][i] for i in arm['source_triangle_ids']]
          ==arm['source_polygon_ids'],'current_748_source_triangle_polygon_rows')
    check([[arm['source_vertex_ids'][i] for i in tri] for tri in arm['triangles_local']]
          ==[target['native']['triangles'][i] for i in arm['source_triangle_ids']],
          'current_compact_748_triangles_map_to_full_source_vertices')
    world={name:env['binary64_world'](o['native']['vertices'],o['matrix_world'],baseline['unit_scale'])
           for name,o in original.items()}
    selected=[tuple(map(F,world[target_name][i])) for i in arm['source_vertex_ids']]
    low,high,box_faces=env['closed_box']([tuple(map(F,p)) for p in world['Cube']],cube['native']['triangles'])
    minimum,bounds=env['box_distance'](selected,low,high,arm['source_vertex_ids'])
    point=tuple(map(F,world[target_name][24331]))
    projected=point[:2]+(high[2],)
    member=env['member']
    left_faces=[fi for fi in arm['source_triangle_ids'] if member(point,[tuple(map(F,world[target_name][j]))
                          for j in target['native']['triangles'][fi]])]
    right_faces=[fi for fi,tri in enumerate(cube['native']['triangles']) if member(projected,
                     [tuple(map(F,world['Cube'][j])) for j in tri])]
    check(minimum['attaining']==[24331] and left_faces==[48160,48161] and right_faces==[0],
          'exact_distance_attaining_source_memberships')
    check([target['native']['triangle_polygons'][i] for i in left_faces]==[26521,26521]
          and cube['native']['triangle_polygons'][right_faces[0]]==0,
          'current_nearest_source_and_reference_native_polygon_memberships')
    check(float(minimum['minimum'])==0.37011719389236364,'independent_binary64_box_surface_distance')
    return dict(arm=arm,baseline=baseline,original=original,world=world,target_name=target_name,
                camera=baseline_full['binding']['camera_specification'],distance=minimum['minimum'],
                nearest_a=point,nearest_b=projected,source_faces=left_faces,reference_faces=right_faces)


EXPECTED_EXPORTS={
    'main': [('initial',True,False)],
    'state': [('initial',True,False),('cube_visible',True,True),('cube_restored',True,False),
              ('target_hidden',False,False),('target_restored',True,False)],
}


def fresh_exports(domain):
    output={}
    summaries=[]
    for session,states in EXPECTED_EXPORTS.items():
        for state,target_visible,cube_visible in states:
            current=read(RUN/session/('SOURCE_'+state+'.json'))
            check(current['unit_scale']==domain['baseline']['unit_scale'] and current['frame']==1
                  and current['subframe']==0.,'current_scale_frame_static')
            check(current['source_writes']==0 and current['saved_blend'] is False,'fresh_export_no_product_or_source_save')
            objects={o['name']:o for o in current['objects']}
            check(set(objects)==set(domain['original']),'same_complete_geometry_object_set')
            for name,obj in objects.items():
                previous=domain['original'][name]
                for key in ('matrix_world','native','evaluated','parent','modifiers','animation'):
                    check(canonical(obj[key])==canonical(previous[key]),'fresh_exact_geometry_vs_prior/'+key)
                check(obj['native']==obj['evaluated'],'fresh_native_evaluated_identical')
            expected={domain['target_name']:target_visible,'Cube':cube_visible}
            for name,visible in expected.items():
                display=objects[name]['display']
                check(display['visible_get'] is visible and display['hide_get'] is (not visible),
                      'fresh_expected_effective_visibility/'+name)
                check(display['hide_viewport'] is False,'hide_viewport_preserved')
                check(display['hide_render'] is (name=='Cube'),'original_hide_render_preserved')
            snapshot=current['display_snapshot']
            check(current['display_snapshot_sha256']==digest(snapshot),'fresh_display_snapshot_digest')
            snapshot_objects={o['name']:o for o in snapshot['objects']}
            check(all(snapshot_objects[name]==objects[name]['display'] for name in objects),
                  'fresh_mesh_display_rows_match_full_layer_snapshot')
            check(snapshot['view_layer']['name']=='ViewLayer' and snapshot['viewport'] is None,
                  'captured_active_view_layer_scope_without_3Dviewport_claim')
            check(all(o['type']!='ARMATURE' for o in current['objects_inventory']),
                  'actual_static_asset_without_armature')
            output[session,state]=current
            summaries.append(dict(session=session,state=state,geometry_identical_to_prior=True,
                target_visible=target_visible,Cube_visible=cube_visible,
                Cube_hide_render=objects['Cube']['display']['hide_render'],
                native_vertices=27304,native_polygons=29073,character_triangles=53264,
                Cube_triangles=12,selected_vertices=410,selected_triangles=748))
    check(len(summaries)==6,'six_fresh_exports_checked')
    return output,summaries


def current_captures(session):
    independent=Path('D:/hefe/verification/fixes/20261117_m4_cross_scale_review/geometry/review.py')
    env=pure_functions(independent,['captures'],dict(read=read,check=check,json=json))
    return env['captures'](session)


def actual_results(domain,exports):
    arm=domain['arm']
    result=[]
    display_identity={}
    for session,states in EXPECTED_EXPORTS.items():
        captured=current_captures(RUN/session)
        call_states=['initial','initial'] if session=='main' else ['initial','cube_visible','cube_restored','target_hidden','target_restored','target_restored']
        for number,state in enumerate(call_states,1):
            full=read(RUN/session/'product_full'/('call_'+str(number).zfill(3))/'SERVICE_RESULT.json')
            binding=full['binding']
            matches=[c for c in captured if c.get('revision')==binding['scene_revision']
                     and c.get('capture_state')==binding['capture_state']]
            check(bool(matches),'full_current_capture_exists')
            capture=matches[0]
            check(all(c==capture for c in matches),'same_current_capture_unambiguous')
            objmap={o['name']:o for o in capture['meshes']}
            check(set(objmap)==set(domain['world']),'capture_retains_hidden_geometry')
            for name,mesh in objmap.items():
                check(mesh['vertices']==domain['world'][name]
                      and mesh['faces']==domain['original'][name]['native']['triangles'],
                      'all_current_source_coordinates_triangles_unchanged/'+name)
            mapping=full['source_mapping']
            check(mapping['submesh_to_source_triangle_indices']==arm['source_triangle_ids']
                  and mapping['submesh_to_source_vertex_indices']==arm['source_vertex_ids'],
                  'actual_selected_source_mapping_748_by_410')
            check(mapping['triangles_source_vertices']==[objmap[domain['target_name']]['faces'][i] for i in arm['source_triangle_ids']],
                  'selected_triangle_rows_complete')
            ref=full['region_ref']
            check(ref['source_triangle_indices']==arm['source_triangle_ids'],'region_ref_keeps_selected_union')
            check(binding['camera_specification']==domain['camera'],'all_six_published_cameras_exactly_previous_qualification')
            snapshot=capture['display_snapshot']
            unsigned={k:v for k,v in snapshot.items() if k!='sha256'}
            check(snapshot['sha256']==digest(unsigned),'actual_current_host_display_snapshot_digest')
            layer=exports[session,state]['display_snapshot']
            check(snapshot['view_layer']['name']==layer['view_layer']['name']
                  and snapshot['view_layer']['instance_id']==layer['view_layer']['instance_id'],
                  'product_display_layer_same_as_fresh_export')
            source_rows={r['host_id']:r for r in snapshot['objects']}
            fresh_rows={r['name']:r for r in layer['objects']}
            mask=[]
            for obj in binding['objects']:
                row=source_rows[obj['host_id']]
                fresh=fresh_rows[obj['object_name']]
                for key in ('host_id','instance_id','visible_get','hide_get','hide_viewport','hide_render'):
                    check(row[key]==fresh[key],'fresh_product_display_row/'+key)
                mask.append(fresh['visible_get'])
            scope=binding['image_scope']
            check(scope['participation_mask']==mask and scope['identity']==binding['display_identity']==snapshot['sha256'],
                  'image_scope_uses_current_effective_visible_get')
            check(scope['scope']=='active_view_layer_effective_viewport'
                  and scope['participation_source']=='blender.visible_get(view_layer=captured_active_view_layer)',
                  'public_image_scope_is_view_layer_contract')
            for obj in scope['objects']:
                fresh=fresh_rows[obj['object_name']]
                check(obj['participates'] is fresh['visible_get'],'scope_objects_consistent_with_mask')
            measurement=full['task_result']
            check(measurement['measurement_scope']=='complete_selected_source_triangle_union_to_reference_triangle_surface',
                  'measurement_scope_retains_full_selected_union_and_reference_surface')
            check(measurement['reference']['name']=='Cube','hidden_reference_Cube_remains_measurement_target')
            fact=measurement['facts']['surface_proximity']
            check(fact['status']=='measured' and fact['value']['distance_m']==float(domain['distance']),
                  'distance_exact_answer_all_display_states')
            witness=fact['value']['nearest_witness']
            check(tuple(map(F,witness['a']))==domain['nearest_a']
                  and tuple(map(F,witness['b']))==domain['nearest_b']
                  and witness['direction_a_to_b']==[0.,0.,1.],'unchanged_world_nearest_witness')
            nearest=measurement['source_mapping']['nearest_witness']
            check(nearest['a']['source_triangle_indices']==[48160,48161]
                  and nearest['a']['source_vertex_indices']==[24331]
                  and nearest['b']['source_triangle_indices']==[0],'source_memberships_all_eight_measurements')
            visibility=full['facts']['visibility']
            check(visibility['complete_witness'] is None
                  and visibility['unknown']==['complete_surface_visibility'],'full_curved_surface_visibility_remains_unknown')
            if state in ('cube_visible','target_hidden'):
                check(full['status']=='partial' and full['observation_status']=='evidence_insufficient'
                      and visibility['status']=='unknown' and visibility['selected_surface_pixels']==0,
                      'zero_samples_have_explicit_observation_insufficient_state')
                check(visibility['reason']==('selected_region_displayed_without_pixels' if state=='cube_visible' else 'selected_region_not_displayed'),
                      'zero_sample_reason_distinguishes_occlusion_and_exclusion')
            else:
                check(full['status']=='complete' and full['observation_status']=='locally_observed'
                      and visibility['selected_surface_pixels']==35452,'visible_state_has_positive_actual_samples')
            display_identity[session,state]=binding['display_identity']
            result.append(dict(session=session,call=number,state=state,revision=binding['capture_state']['revision'],
                mask=mask,display_identity=binding['display_identity'],ordered_geometry_sha256=binding['ordered_geometry_sha256'],
                camera_identity=binding['camera_identity'],geometry_identity=binding['geometry_identity'],
                region_id=ref['region_id'],distance_m=fact['value']['distance_m'],status=full['status'],
                observation_status=full['observation_status'],selected_surface_pixels=visibility['selected_surface_pixels']))
        subset=[r for r in result if r['session']==session]
        check(len({r['ordered_geometry_sha256'] for r in subset})==1
              and len({r['geometry_identity'] for r in subset})==1,'one_complete_geometry_identity_through_display_changes')
        check(len({r['camera_identity'] for r in subset})==1,'one_camera_identity_through_display_changes')
    check(display_identity['state','initial']==display_identity['state','cube_restored']
          ==display_identity['state','target_restored'],'display_identity_restores_with_actual_flags')
    check(len(result)==8,'eight_current_measurements_checked')
    return result


def fixture_receipts(domain,exports):
    receipts=[]
    previous_fingerprint=None
    initial=None
    for stage,(name,object_name,hidden) in enumerate((('CUBE_VISIBLE','Cube',False),('CUBE_RESTORED','Cube',True),
        ('TARGET_HIDDEN',domain['target_name'],True),('TARGET_RESTORED',domain['target_name'],False)),1):
        record=read(RUN/'state'/(name+'_RECEIPT.json'))
        check(record['response']['status']=='success','fixture_display_receipt_success')
        value=record['response']['result']
        check(value['stage']==stage and value['target_name']==object_name and value['hidden'] is hidden,
              'fixture_exact_prespecified_display_action')
        check(value['fixture_hide_set_setters']==1 and value['product_setters']==0
              and value['source_asset_saved'] is False,'fixture_single_hide_set_no_product_write_or_save')
        if previous_fingerprint is not None:
            check(previous_fingerprint==value['before_fingerprint'],'fixture_display_fingerprint_chain')
        if initial is None:initial=value['before_fingerprint']
        previous_fingerprint=value['after_fingerprint']
        receipts.append(dict(stage=stage,name=name,target_name=object_name,hidden=hidden,
                             original_deadline_ns=record['original_deadline_ns']))
    check(previous_fingerprint==initial,'all_display_flags_restore_initial_fingerprint')
    check(exports['state','initial']['display_snapshot']==exports['state','target_restored']['display_snapshot'],
          'full_fresh_display_layer_snapshot_restored')
    return receipts


def main():
    domain=geometry_domains()
    exports,export_summaries=fresh_exports(domain)
    results=actual_results(domain,exports)
    receipts=fixture_receipts(domain,exports)
    out=dict(status='passed_checked_scope',checks=sum(checks.values()),checks_by_kind=dict(checks),
        product_commit='29f35a77',author_commit='aa45f033ce662b7453dda77084b36da34640f558',
        prior_mathematical_matrix_replay='same exact native/evaluated/matrix bytes proved against pinned prior reviewed source; no repeated all-polygon matrix',
        exports=export_summaries,measurements=results,fixture_display_actions=receipts,
        exact_distance_m=float(domain['distance']),exact_distance_rational=str(domain['distance']),
        source_point=24331,source_triangles=[48160,48161],source_polygon=26521,reference_triangle=0,
        all_region_vertices_strictly_inside_reference=True,
        distance_semantics='unsigned selected-triangle-surface to complete Cube-triangle-surface distance; selected region is inside Cube',
        actual_complete_surface_visibility='unknown',input_pins=pins,
        new_operations=dict(Blender=0,MCP=0,raster=0,image_encoding=0,model=0,paid_API=0))
    (OUT/'RESULT.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=out['status'],checks=out['checks'],fresh_exports=len(export_summaries),
        actual_measurements=len(results),fixture_actions=len(receipts),distance=out['exact_distance_m'])))


if __name__=='__main__':
    try:main()
    except BaseException:
        (OUT/'FAILURE.txt').write_text(traceback.format_exc(),encoding='utf8')
        raise
