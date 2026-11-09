"""Actual BlenderSceneHost -> ArmTwistSource -> pure preview on eight tasks.

The prior fixture recipe is reused solely to create owned native geometry.
Every preview input is the exported live capture, without QA normalization.
Only four positive cases receive two QA bone assignments each. No file saves,
images, sockets, product setters or diagnostic model predictions occur here.
"""
from copy import deepcopy
import hashlib
import importlib
import json
import math
from pathlib import Path
import sys
import time
import traceback
import types

NATIVE_GATES={'angle_deg':.001,'position_m':5e-6,'section_area_loss':2e-5}
PREVIEW_TOLERANCES={'angle_tolerance_deg':.001,'position_tolerance_m':5e-6,'area_tolerance':1e-6}
EXPECTED_REASONS={'candidate':'area_target_met_with_fixed_end_poses',
    'no_op':'area_target_already_met','unreachable':'best_allowed_u_exceeds_area_target',
    'not_applicable':'non_axial_or_ambiguous_pose'}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
        allow_nan=False).encode('utf8')).hexdigest()


def main():
    import bpy
    import numpy as np
    from mathutils import Matrix

    args=sys.argv[sys.argv.index('--')+1:]
    if len(args)!=2:raise ValueError('usage: -- outputdir rootpath')
    output,root=(Path(value).resolve() for value in args)
    output.mkdir(parents=True,exist_ok=True)
    if not bpy.app.background or bpy.data.filepath:raise RuntimeError('fresh_unsaved_background_required')
    sys.dont_write_bytecode=True
    freeze=json.loads((output/'SOURCE_FREEZE.json').read_text(encoding='utf8'))
    if freeze['native_gates']!=NATIVE_GATES or freeze['preview_tolerances']!=PREVIEW_TOLERANCES:
        raise RuntimeError('frozen_tolerance_mismatch')
    def hashes():return {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in freeze['files']}
    source_hashes_before=hashes()
    if source_hashes_before!=freeze['files']:raise RuntimeError('frozen_source_changed_before_import')
    package=types.ModuleType('human_eye_plugin');package.__path__=[str(root/'human_eye_plugin')]
    sys.modules['human_eye_plugin']=package;sys.path.insert(0,str(root))
    correction=importlib.import_module('human_eye_plugin.arm_twist_correction')
    Host=importlib.import_module('human_eye_plugin.blender_host').BlenderSceneHost
    Source=importlib.import_module('human_eye_plugin.arm_twist_source').ArmTwistSource
    identity=importlib.import_module('human_eye_plugin.runtime_identity').runtime_identity()
    if {entry['path']:entry['sha256'] for entry in identity['source_files']}!={
            name:freeze['files'][name] for name in freeze['runtime_source_files']}:
        raise RuntimeError('runtime_identity_manifest_does_not_match_frozen_sources')
    cases_module=importlib.import_module('verification.arm_twist_correction_preview_001.cases')
    oracle=importlib.import_module('verification.arm_twist_correction_preview_001.oracle')
    cases=cases_module.make_cases()
    if len(cases)!=8 or [case['expected_status'] for case in cases]!=[
            'candidate','candidate','candidate','candidate','no_op','no_op','unreachable','not_applicable']:
        raise AssertionError('exact_fixed_eight_task_statuses_required')
    report={'schema':'arm-correction-opt-native-source-preview-v1','passed':False,
        'blender_version':bpy.app.version_string,'blender_build_hash':bpy.app.build_hash.decode(),
        'runtime_source_identity':identity,'source_hashes_before':source_hashes_before,
        'native_gates':NATIVE_GATES,'preview_tolerances':PREVIEW_TOLERANCES,
        'fixture_recipe_reference':'verification/arm_twist_correction_preview_001/cases.py',
        'fixture_constructor_reference':'verification/arm_twist_correction_preview_001/native_probe.py:build (limited adaptation)',
        'cases':[],'work':{'fixtures_constructed':0,'source_captures':0,'preview_calls':0,
            'model_calls':0,'product_setters':0,'qa_initial_pose_assignments':0,
            'qa_candidate_pose_assignments':0,'native_readbacks':0},
        'opened_blend_file':False,'saved_blend_file':False,'images':0,
        'limitations':['Generated fixed tasks only; no real character, animation or author asset coverage.',
            'Captured effective weights are supplied unchanged; raw RNA weights are recorded separately.',
            'Candidate assignments are QA operations, not a product executor or write authorization.',
            'Source provenance does not establish repair intent or source constraints support.',
            'Source/capture/preview/QA/startup timing scopes are separate and nested scopes are not additive.',
            'Section area does not certify full enclosed volume, damage or a learning benefit.']}
    run_started=time.perf_counter_ns();saved_error=None
    owned_objects=[];owned_meshes=[];owned_rigs=[];active_host=None

    def matrix(value):return [[float(x) for x in row] for row in value]
    def max_abs(left,right):return float(np.max(np.abs(np.asarray(left)-np.asarray(right))))
    def point_error(left,right):return float(np.linalg.norm(np.asarray(left)-np.asarray(right),axis=-1).max())
    def rotation_error(left,right):
        def orthogonal(value):
            u,_,v=np.linalg.svd(np.asarray(value,dtype=float)[:3,:3]);result=u@v
            if np.linalg.det(result)<0:u[:,-1]*=-1;result=u@v
            return result
        delta=orthogonal(left).T@orthogonal(right)
        sine=np.linalg.norm([delta[2,1]-delta[1,2],delta[0,2]-delta[2,0],delta[1,0]-delta[0,1]])/2
        return float(np.degrees(np.arctan2(sine,(np.trace(delta)-1)/2)))
    def pose_errors(left,right):
        return {'max_matrix_abs':max_abs(left,right),
            'max_angle_deg':max(rotation_error(a,b) for a,b in zip(left,right)),
            'max_translation_m':point_error(np.asarray(left)[:,:3,3],np.asarray(right)[:,:3,3])}
    def pose_ok(errors):
        return errors['max_angle_deg']<=NATIVE_GATES['angle_deg'] and errors['max_translation_m']<=NATIVE_GATES['position_m']
    def handler_counts():return {name:len(getattr(bpy.app.handlers,name))
        for name in ('depsgraph_update_post','undo_post','redo_post','load_post')}
    report['handler_counts_before_all_fixtures']=handler_counts()
    def remove_owned():
        for name in reversed(owned_objects):
            obj=bpy.data.objects.get(name)
            if obj is not None:bpy.data.objects.remove(obj,do_unlink=True)
        for name in reversed(owned_meshes):
            data=bpy.data.meshes.get(name)
            if data is not None:bpy.data.meshes.remove(data)
        for name in reversed(owned_rigs):
            data=bpy.data.armatures.get(name)
            if data is not None:bpy.data.armatures.remove(data)
    def build(recipe,index):
        # Only fixture construction uses recipe doubles. Preview never does.
        name='HE_Correction_OPT_QA_'+str(index)
        data=bpy.data.meshes.new(name+'_mesh');owned_meshes.append(data.name)
        data.from_pydata(recipe['rest_vertices'],[],recipe['triangles']);data.update()
        mesh=bpy.data.objects.new(name+'_mesh',data);owned_objects.append(mesh.name)
        bpy.context.scene.collection.objects.link(mesh)
        rig_data=bpy.data.armatures.new(name+'_rig');owned_rigs.append(rig_data.name)
        rig=bpy.data.objects.new(name+'_rig',rig_data);owned_objects.append(rig.name)
        bpy.context.scene.collection.objects.link(rig)
        bpy.ops.object.select_all(action='DESELECT');rig.select_set(True)
        bpy.context.view_layer.objects.active=rig;bpy.ops.object.mode_set(mode='EDIT')
        rests=[np.asarray(bone['rest_matrix'],dtype=float) for bone in recipe['bone_chain']]
        lengths=[float(np.linalg.norm(rests[i+1][:3,3]-rests[i][:3,3])) for i in range(2)]
        lengths.append(lengths[-1])
        for spec,length in zip(recipe['bone_chain'],lengths):
            bone=rig_data.edit_bones.new(spec['name']);bone.head=(0.,0.,0.);bone.tail=(0.,length,0.)
            if spec['parent'] is not None:bone.parent=rig_data.edit_bones[spec['parent']]
            bone.use_connect=False;bone.matrix=Matrix(spec['rest_matrix']);bone.length=length
        bpy.ops.object.mode_set(mode='OBJECT')
        for bone in rig_data.bones:
            bone.use_deform=True;bone.bbone_segments=1;bone.use_envelope_multiply=False
            bone.use_inherit_rotation=True;bone.inherit_scale='FULL';bone.use_local_location=True
        groups=[mesh.vertex_groups.new(name=bone['name']) for bone in recipe['bone_chain']]
        for index,row in enumerate(recipe['weights']):
            for group,weight in zip(groups,row):
                if weight:group.add([index],float(weight),'REPLACE')
        modifier=mesh.modifiers.new(name+'_LBS','ARMATURE');modifier.object=rig
        modifier.use_vertex_groups=True;modifier.use_bone_envelopes=False
        modifier.use_deform_preserve_volume=False;modifier.use_multi_modifier=False
        modifier.show_viewport=True;modifier.show_render=True
        for spec,basis in zip(recipe['bone_chain'],oracle.local_basis_matrices(recipe)):
            pose=rig.pose.bones[spec['name']];pose.rotation_mode='QUATERNION';pose.matrix_basis=Matrix(basis)
            report['work']['qa_initial_pose_assignments']+=1
        bpy.context.view_layer.update();report['work']['fixtures_constructed']+=1
        return mesh,rig
    def static_read(mesh,rig,names):
        return {'rest_vertices':[list(v.co) for v in mesh.data.vertices],
            'triangles':[list(face.vertices) for face in mesh.data.polygons],
            'raw_rna_weights':[[sum(float(member.weight) for member in v.groups if member.group==i)
                               for i in range(3)] for v in mesh.data.vertices],
            'vertex_groups':[{'index':int(group.index),'name':group.name} for group in mesh.vertex_groups],
            'bones':[{'name':name,'parent':getattr(rig.data.bones[name].parent,'name',None),
                'rest_matrix':matrix(rig.data.bones[name].matrix_local),
                'rest_head':list(rig.data.bones[name].head_local),'rest_tail':list(rig.data.bones[name].tail_local),
                'length':float(rig.data.bones[name].length),'use_deform':bool(rig.data.bones[name].use_deform),
                'use_connect':bool(rig.data.bones[name].use_connect),'inherit_scale':rig.data.bones[name].inherit_scale,
                'inherit_rotation':bool(rig.data.bones[name].use_inherit_rotation),
                'local_location':bool(rig.data.bones[name].use_local_location),
                'bbone_segments':int(rig.data.bones[name].bbone_segments),
                'constraints':[constraint.type for constraint in rig.pose.bones[name].constraints]} for name in names],
            'mesh_matrix_world':matrix(mesh.matrix_world),'rig_matrix_world':matrix(rig.matrix_world),
            'unit_scale_m':float(bpy.context.scene.unit_settings.scale_length),
            'modifiers':[{'type':modifier.type,'object':getattr(modifier.object,'name',None),
                'use_deform_preserve_volume':bool(modifier.use_deform_preserve_volume),
                'use_vertex_groups':bool(modifier.use_vertex_groups),
                'use_bone_envelopes':bool(modifier.use_bone_envelopes)} for modifier in mesh.modifiers],
            'object_constraints':{'mesh':[constraint.type for constraint in mesh.constraints],
                                  'rig':[constraint.type for constraint in rig.constraints]},
            'animation_present':{'mesh':mesh.animation_data is not None,'mesh_data':mesh.data.animation_data is not None,
                'rig':rig.animation_data is not None,'rig_data':rig.data.animation_data is not None}}
    def read(mesh,rig,names):
        started=time.perf_counter_ns();graph=bpy.context.evaluated_depsgraph_get()
        em=mesh.evaluated_get(graph);er=rig.evaluated_get(graph)
        report['work']['native_readbacks']+=1;poses=[er.pose.bones[name] for name in names]
        return {'current_vertices':[list(v.co) for v in em.data.vertices],
            'pose_matrices':[matrix(pose.matrix) for pose in poses],
            'global_pose_matrices':[matrix(er.matrix_world@pose.matrix) for pose in poses],
            'local_basis_matrices':[matrix(rig.pose.bones[name].matrix_basis) for name in names],
            'head_positions':[list(pose.head) for pose in poses],
            'tail_positions':[list(pose.tail) for pose in poses],'elapsed_ns':time.perf_counter_ns()-started}

    try:
        for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
        scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
        data=bpy.data.meshes.new('HE_Correction_OPT_QA_protected');owned_meshes.append(data.name)
        data.from_pydata([(8.,9.,10.),(9.,9.,10.),(8.,10.,10.)],[],[(0,1,2)]);data.update()
        sentinel=bpy.data.objects.new('HE_Correction_OPT_QA_protected',data);owned_objects.append(sentinel.name)
        scene.collection.objects.link(sentinel)
        def outside():return {'matrix_world':matrix(sentinel.matrix_world),
            'points':[list(v.co) for v in sentinel.data.vertices],
            'faces':[list(face.vertices) for face in sentinel.data.polygons]}
        sentinel_original=outside();report['sentinel_before']=deepcopy(sentinel_original)
        for index,case in enumerate(cases,1):
            started=time.perf_counter_ns();recipe=case['patch'];names=[bone['name'] for bone in recipe['bone_chain']]
            record={'case_id':case['case_id'],'asset_id':case['asset_id'],'passed':False,
                'expected_status':case['expected_status'],'expected_reason':EXPECTED_REASONS[case['expected_status']],
                'qa_candidate_pose_assignments':0,'handler_counts_before_host':handler_counts()}
            report['cases'].append(record)
            recipe_digest=digest([recipe,case['task']]);construction_started=time.perf_counter_ns()
            mesh,rig=build(recipe,index);record['fixture_construction_elapsed_ns']=time.perf_counter_ns()-construction_started
            static_before=static_read(mesh,rig,names);native_before=read(mesh,rig,names);sentinel_before=outside()
            raw_path=output/('case_'+str(index).zfill(2)+'.json')
            raw={'case_id':case['case_id'],'fixture_recipe_input_sha256':recipe_digest,
                'native_static_before':static_before,'native_before':native_before,'sentinel_before':sentinel_before,
                'phase':'native_fixture_ready_source_not_yet_captured'}
            def save_raw():
                raw_path.write_text(json.dumps(raw,indent=2,allow_nan=False),encoding='utf8',newline='\n')
                record.update(raw_file=raw_path.name,raw_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest())
            save_raw()
            active_host=Host(bpy_module=bpy,execution_metadata=True,identity_metadata=True)
            selection={'mesh_name':mesh.name,'armature_name':rig.name,'bone_names':names,
                'vertex_indices':list(range(len(recipe['rest_vertices']))),'sections':deepcopy(recipe['sections'])}
            bound=Source(active_host).bind(selection);capture_started=time.perf_counter_ns()
            report['work']['source_captures']+=1;capture=bound.capture()
            record['source_capture_elapsed_ns']=time.perf_counter_ns()-capture_started
            record['source_work_totals']=bound.work_totals()
            if capture['static_patch'] is None:raise AssertionError('fresh_capture_must_export_static_patch')
            # The complete live static export is retained. This is format glue,
            # with no new normalization, geometry generation or oracle fields.
            patch=deepcopy(capture['static_patch']);patch['current_vertices']=deepcopy(capture['current_vertices'])
            for bone,pose in zip(patch['bone_chain'],capture['pose_matrices']):bone['pose_matrix']=deepcopy(pose)
            logical_to_native=dict(zip(recipe['vertex_ids'],patch['vertex_ids']))
            task=deepcopy(case['task']);task.update(PREVIEW_TOLERANCES)
            task['fixed_end_pose_matrices']=[deepcopy(capture['pose_matrices'][i]) for i in (0,2)]
            task['protected_vertex_ids']=[logical_to_native[value] for value in case['task']['protected_vertex_ids']]
            input_digest=digest([patch,task])
            raw.update({'phase':'source_input_ready_preview_not_yet_called','selection':selection,'capture':capture,
                'input_patch':patch,'input_task':task,'input_sha256':input_digest,
                'logical_to_native_vertex_id_mapping':[[logical,native] for logical,native in logical_to_native.items()],
                'raw_rna_weights':static_before['raw_rna_weights'],'source_exported_effective_weights':patch['weights']})
            save_raw();preview_started=time.perf_counter_ns()
            report['work']['preview_calls']+=1;preview=correction.preview_axial_redistribution(patch,task)
            record['preview_elapsed_ns']=time.perf_counter_ns()-preview_started
            record['source_identity']=capture['source'];record['preview_status']=preview['status']
            record['preview_reason']=preview['reason'];record['preview_work']=preview['work']
            report['work']['model_calls']+=preview['work']['model_calls']
            raw.update(preview=preview,phase='preview_returned_candidate_not_yet_applied');save_raw()
            if preview['status']!=case['expected_status'] or preview['reason']!=record['expected_reason']:
                raise AssertionError({'case':case['case_id'],'expected':case['expected_status'],
                    'actual':preview['status'],'reason':preview['reason']})
            candidate=preview.get('candidate');application_started=time.perf_counter_ns()
            if case['expected_status']=='candidate':
                if not candidate or len(candidate['bone_changes'])!=2:raise AssertionError('two_candidate_changes_required')
                for bone_index,change in zip((1,2),candidate['bone_changes']):
                    if change['name']!=names[bone_index] or max_abs(change['basis_matrix'],candidate['local_basis_matrices'][bone_index])>1e-12:
                        raise AssertionError('candidate_declared_change_mismatch')
                    rig.pose.bones[names[bone_index]].matrix_basis=Matrix(change['basis_matrix'])
                    record['qa_candidate_pose_assignments']+=1;report['work']['qa_candidate_pose_assignments']+=1
                bpy.context.view_layer.update()
            elif candidate is not None:raise AssertionError('noncandidate_must_not_emit_candidate')
            record['qa_candidate_application_elapsed_ns']=time.perf_counter_ns()-application_started
            native_after=read(mesh,rig,names);static_after=static_read(mesh,rig,names);sentinel_after=outside()
            expected_poses=candidate['pose_matrices'] if candidate else capture['pose_matrices']
            candidate_pose_errors=pose_errors(native_after['pose_matrices'],expected_poses)
            endpoint_errors=pose_errors([native_after['global_pose_matrices'][i] for i in (0,2)],
                                       [native_before['global_pose_matrices'][i] for i in (0,2)])
            initial_pose_errors=pose_errors(native_before['pose_matrices'],[bone['pose_matrix'] for bone in recipe['bone_chain']])
            centerline_error=max(point_error(native_after['head_positions'],native_before['head_positions']),
                                 point_error(native_after['tail_positions'],native_before['tail_positions']))
            protected_indices=[patch['vertex_ids'].index(value) for value in task['protected_vertex_ids']]
            protected_before=[native_before['current_vertices'][i] for i in protected_indices]
            protected_after=[native_after['current_vertices'][i] for i in protected_indices]
            protected_error=point_error(protected_before,protected_after)
            target_points=candidate['current_vertices'] if candidate else capture['current_vertices']
            target_point_error=point_error(native_after['current_vertices'],target_points)
            before_objective=oracle.section_objective(static_before['rest_vertices'],native_before['current_vertices'],patch['sections'])
            after_objective=oracle.section_objective(static_before['rest_vertices'],native_after['current_vertices'],patch['sections'])
            expected_after=case['expected_after_j'] if candidate else case['expected_before_j']
            before_j_error=None if case['expected_before_j'] is None else abs(before_objective['max_section_area_loss']-case['expected_before_j'])
            after_j_error=None if expected_after is None else abs(after_objective['max_section_area_loss']-expected_after)
            checks={'expected_status_and_reason':True,'source_current_vs_native_max_m':point_error(patch['current_vertices'],native_before['current_vertices']),
                'source_rest_vs_native_max_m':point_error(patch['rest_vertices'],static_before['rest_vertices']),
                'source_pose_vs_native_max_abs':max_abs(capture['pose_matrices'],native_before['pose_matrices']),
                'initial_recipe_pose_error':initial_pose_errors,'candidate_pose_error':candidate_pose_errors,
                'fixed_end_global_pose_error':endpoint_errors,'centerline_max_m':centerline_error,
                'protected_points_max_m':protected_error,'candidate_points_max_m':target_point_error,
                'before_j_error':before_j_error,'after_j_error':after_j_error,
                'static_before_after_exact':static_before==static_after,'sentinel_before_after_exact':sentinel_before==sentinel_after,
                'input_patch_task_exact':input_digest==digest([patch,task]),'fixture_recipe_exact':recipe_digest==digest([recipe,case['task']]),
                'no_candidate_no_writes':bool(candidate) or record['qa_candidate_pose_assignments']==0,
                'no_candidate_native_points_exact':bool(candidate) or native_before['current_vertices']==native_after['current_vertices']}
            if candidate:checks['candidate_target_met']=after_objective['max_section_area_loss']<=task['max_section_area_loss']+NATIVE_GATES['section_area_loss']
            raw={'case_id':case['case_id'],'phase':'independent_native_readback_complete',
                'fixture_recipe_input_sha256':recipe_digest,
                'logical_to_native_vertex_id_mapping':[[logical,native] for logical,native in logical_to_native.items()],
                'selection':selection,'capture':capture,'input_patch':patch,'input_task':task,'input_sha256':input_digest,
                'preview':preview,'native_static_before':static_before,'native_static_after':static_after,
                'raw_rna_weights':static_before['raw_rna_weights'],'source_exported_effective_weights':patch['weights'],
                'raw_rna_weight_sums':[math.fsum(row) for row in static_before['raw_rna_weights']],
                'source_effective_weight_sums':[math.fsum(row) for row in patch['weights']],
                'native_before':native_before,'native_after':native_after,'sentinel_before':sentinel_before,'sentinel_after':sentinel_after,
                'protected_vertex_ids':task['protected_vertex_ids'],'protected_points_before':protected_before,'protected_points_after':protected_after,
                'source_work_totals':bound.work_totals(),'before_objective':before_objective,'after_objective':after_objective,
                'analytic_before_j':case['expected_before_j'],'analytic_actual_after_j':expected_after,'checks':checks}
            raw_path.write_text(json.dumps(raw,indent=2,allow_nan=False),encoding='utf8',newline='\n')
            record.update({'checks':checks,'before_objective':before_objective,'after_objective':after_objective,
                'raw_file':raw_path.name,'raw_sha256':hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                'case_elapsed_ns':time.perf_counter_ns()-started})
            conditions=[pose_ok(initial_pose_errors),pose_ok(candidate_pose_errors),pose_ok(endpoint_errors),
                max(centerline_error,protected_error,target_point_error,checks['source_current_vs_native_max_m'],
                    checks['source_rest_vs_native_max_m'])<=NATIVE_GATES['position_m'],
                checks['source_pose_vs_native_max_abs']<=1e-9,
                all(value is None or value<=NATIVE_GATES['section_area_loss'] for value in (before_j_error,after_j_error)),
                all(checks[key] for key in ('static_before_after_exact','sentinel_before_after_exact','input_patch_task_exact',
                    'fixture_recipe_exact','no_candidate_no_writes','no_candidate_native_points_exact')),
                checks.get('candidate_target_met',True)]
            if not all(conditions):raise AssertionError({'case':case['case_id'],'checks':checks})
            active_host.close_residency()
            record['host_residency_closed']=not getattr(active_host._residency,'callbacks',[])
            record['handler_counts_after_close']=handler_counts()
            if not record['host_residency_closed'] or record['handler_counts_after_close']!=record['handler_counts_before_host']:
                raise AssertionError('source_host_handler_cleanup_failed')
            active_host=None;record['passed']=True
            bpy.data.objects.remove(mesh,do_unlink=True);bpy.data.objects.remove(rig,do_unlink=True)
        report['sentinel_after']=outside()
        report['passed']=len(report['cases'])==8 and all(row['passed'] for row in report['cases'])
        if report['work']['qa_candidate_pose_assignments']!=8:raise AssertionError('exactly_eight_candidate_assignments_required')
    except BaseException as exc:
        saved_error=exc;report['failure']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    finally:
        if active_host is not None:
            try:
                active_host.close_residency();report['failure_host_residency_closed']=not getattr(active_host._residency,'callbacks',[])
            except BaseException as exc:report['host_cleanup_failure']={'type':type(exc).__name__,'message':str(exc)}
        try:
            if bpy.context.object is not None and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
            remove_owned()
            report['owned_objects_removed']=all(bpy.data.objects.get(name) is None for name in owned_objects)
            report['owned_meshes_removed']=all(bpy.data.meshes.get(name) is None for name in owned_meshes)
            report['owned_rigs_removed']=all(bpy.data.armatures.get(name) is None for name in owned_rigs)
        except BaseException as exc:report['cleanup_failure']={'type':type(exc).__name__,'message':str(exc)}
        report['source_hashes_after']=hashes();report['source_bytes_unchanged']=report['source_hashes_after']==source_hashes_before
        report['handler_counts_after_all_fixtures']=handler_counts()
        report['all_source_handlers_removed']=report['handler_counts_after_all_fixtures']==report['handler_counts_before_all_fixtures']
        report['blend_file_still_unsaved']=not bool(bpy.data.filepath)
        report['probe_elapsed_ns']=time.perf_counter_ns()-run_started
        report['passed']=bool(report['passed'] and report['source_bytes_unchanged'] and report['blend_file_still_unsaved']
            and report['all_source_handlers_removed'] and all(report.get(key) for key in ('owned_objects_removed','owned_meshes_removed','owned_rigs_removed')))
        (output/'RESULT.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf8',newline='\n')
        print('ARM_CORRECTION_OPT_NATIVE '+json.dumps({'passed':report['passed'],'cases':len(report['cases']),
            'result':str(output/'RESULT.json')}),flush=True)
    if saved_error is not None:raise saved_error


if __name__=='__main__':main()
