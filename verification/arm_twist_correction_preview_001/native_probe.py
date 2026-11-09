"""One owned, unsaved Blender feasibility check of the four fixed positives.

The QA script assigns the two proposed local bone matrices. The product is
still a pure preview and does not call Blender setters. No socket is opened.
"""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time
import traceback
import types


# Frozen before native execution; CPU double-precision gates remain separate.
NATIVE_GATES={'angle_deg':.001,'position_m':5e-6,'section_area_loss':2e-5}


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
    if not bpy.app.background or bpy.data.filepath:
        raise RuntimeError('fresh_unsaved_background_required')
    sys.dont_write_bytecode=True
    freeze=json.loads((output/'SOURCE_FREEZE.json').read_text(encoding='utf8'))
    if freeze['native_gates']!=NATIVE_GATES:raise RuntimeError('native_gate_freeze_mismatch')
    def hashes():
        return {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in freeze['files']}
    before=hashes()
    if before!=freeze['files']:raise RuntimeError('frozen_source_changed_before_import')
    package=types.ModuleType('human_eye_plugin');package.__path__=[str(root/'human_eye_plugin')]
    sys.modules['human_eye_plugin']=package
    sys.path[:0]=[str(Path(__file__).parent),str(root)]
    correction=importlib.import_module('human_eye_plugin.arm_twist_correction')
    cases_module=importlib.import_module('cases')
    oracle=importlib.import_module('oracle')
    cases=cases_module.make_cases()
    if len(cases)!=8 or any(case['expected_status']!='candidate' for case in cases[:4]):
        raise AssertionError('fixed_eight_cases_first_four_positive_required')
    report={'schema':'arm-correction-preview-native-feasibility-v1','passed':False,
        'blender_version':bpy.app.version_string,'blender_build_hash':bpy.app.build_hash.decode(),
        'background':True,'opened_blend_file':False,'saved_blend_file':False,
        'native_gates':NATIVE_GATES,'source_hashes_before':before,'cases':[],
        'work':{'preview_calls':0,'model_calls':0,'product_setters':0,
                'qa_initial_pose_assignments':0,'qa_candidate_pose_assignments':0,
                'native_readbacks':0,'fixtures_constructed':0},
        'limitations':['These four generated positive cases only, not a character or animation test.',
            'The two bone writes are QA operations, not a delivered product execution path.',
            'Native float32 gates are separate from CPU double-precision gates.',
            'Section area is not enclosed-mesh volume or an anatomical damage judgment.',
            'Nested timings are observations, not a comparative speed or learning-benefit claim.']}
    owned_objects=[];owned_meshes=[];owned_rigs=[];saved_error=None
    run_started=time.perf_counter_ns()

    def matrix(value):return [[float(x) for x in row] for row in value]
    def max_abs(left,right):return float(np.max(np.abs(np.asarray(left)-np.asarray(right))))
    def point_error(left,right):
        return float(np.linalg.norm(np.asarray(left)-np.asarray(right),axis=-1).max())
    def rotation_error(left,right):
        # Polar orthogonalization removes only float32 readback roundoff from
        # the *error measurement*, without changing any input or candidate.
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
    def require_pose(errors,label):
        if errors['max_angle_deg']>NATIVE_GATES['angle_deg'] or errors['max_translation_m']>NATIVE_GATES['position_m']:
            raise AssertionError({label:errors})
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
    def build(packet,index):
        name='HE_Correction_QA_'+str(index)
        mesh_data=bpy.data.meshes.new(name+'_mesh');owned_meshes.append(mesh_data.name)
        mesh_data.from_pydata(packet['rest_vertices'],[],packet['triangles']);mesh_data.update()
        mesh=bpy.data.objects.new(name+'_mesh',mesh_data);owned_objects.append(mesh.name)
        bpy.context.scene.collection.objects.link(mesh)
        rig_data=bpy.data.armatures.new(name+'_rig');owned_rigs.append(rig_data.name)
        rig=bpy.data.objects.new(name+'_rig',rig_data);owned_objects.append(rig.name)
        bpy.context.scene.collection.objects.link(rig)
        bpy.ops.object.select_all(action='DESELECT');rig.select_set(True)
        bpy.context.view_layer.objects.active=rig;bpy.ops.object.mode_set(mode='EDIT')
        rests=[np.asarray(spec['rest_matrix'],dtype=float) for spec in packet['bone_chain']]
        lengths=[float(np.linalg.norm(rests[i+1][:3,3]-rests[i][:3,3])) for i in range(2)]
        lengths.append(lengths[-1])
        for spec,length in zip(packet['bone_chain'],lengths):
            bone=rig_data.edit_bones.new(spec['name']);bone.head=(0.,0.,0.);bone.tail=(0.,length,0.)
            if spec['parent'] is not None:bone.parent=rig_data.edit_bones[spec['parent']]
            bone.use_connect=False;bone.matrix=Matrix(spec['rest_matrix']);bone.length=length
        bpy.ops.object.mode_set(mode='OBJECT')
        for bone in rig_data.bones:
            bone.use_deform=True;bone.bbone_segments=1;bone.use_envelope_multiply=False
            bone.use_inherit_rotation=True;bone.inherit_scale='FULL';bone.use_local_location=True
        groups=[mesh.vertex_groups.new(name=spec['name']) for spec in packet['bone_chain']]
        for index,row in enumerate(packet['weights']):
            for group,weight in zip(groups,row):
                if weight:group.add([index],float(weight),'REPLACE')
        modifier=mesh.modifiers.new(name+'_LBS','ARMATURE');modifier.object=rig
        modifier.use_vertex_groups=True;modifier.use_bone_envelopes=False
        modifier.use_deform_preserve_volume=False;modifier.use_multi_modifier=False
        modifier.show_viewport=True;modifier.show_render=True
        for spec,basis in zip(packet['bone_chain'],oracle.local_basis_matrices(packet)):
            pose=rig.pose.bones[spec['name']];pose.rotation_mode='QUATERNION';pose.matrix_basis=Matrix(basis)
            report['work']['qa_initial_pose_assignments']+=1
        bpy.context.view_layer.update();report['work']['fixtures_constructed']+=1
        return mesh,rig
    def static_read(mesh,rig,names):
        return {'rest_vertices':[list(vertex.co) for vertex in mesh.data.vertices],
            'triangles':[list(polygon.vertices) for polygon in mesh.data.polygons],
            'weights':[[sum(float(member.weight) for member in vertex.groups if member.group==i)
                        for i in range(3)] for vertex in mesh.data.vertices],
            'rest_matrices':[matrix(rig.data.bones[name].matrix_local) for name in names],
            'bone_lengths':[float(rig.data.bones[name].length) for name in names],
            'mesh_matrix_world':matrix(mesh.matrix_world),'rig_matrix_world':matrix(rig.matrix_world),
            'unit_scale_m':float(bpy.context.scene.unit_settings.scale_length)}
    def read(mesh,rig,names):
        started=time.perf_counter_ns();graph=bpy.context.evaluated_depsgraph_get()
        evaluated_mesh=mesh.evaluated_get(graph);evaluated_rig=rig.evaluated_get(graph)
        report['work']['native_readbacks']+=1
        poses=[evaluated_rig.pose.bones[name] for name in names]
        return {'current_vertices':[list(vertex.co) for vertex in evaluated_mesh.data.vertices],
            'global_pose_matrices':[matrix(evaluated_rig.matrix_world@pose.matrix) for pose in poses],
            'pose_matrices':[matrix(pose.matrix) for pose in poses],
            'local_basis_matrices':[matrix(rig.pose.bones[name].matrix_basis) for name in names],
            'head_positions':[list(pose.head) for pose in poses],
            'tail_positions':[list(pose.tail) for pose in poses],
            'elapsed_ns':time.perf_counter_ns()-started}

    try:
        # This process was created with factory startup; no user scene is open.
        for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
        scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
        sentinel_data=bpy.data.meshes.new('HE_Correction_QA_protected');owned_meshes.append(sentinel_data.name)
        sentinel_data.from_pydata([(8.,9.,10.),(9.,9.,10.),(8.,10.,10.)],[],[(0,1,2)]);sentinel_data.update()
        sentinel=bpy.data.objects.new('HE_Correction_QA_protected',sentinel_data);owned_objects.append(sentinel.name)
        scene.collection.objects.link(sentinel)
        def outside():return {'matrix_world':matrix(sentinel.matrix_world),
            'vertices':[list(v.co) for v in sentinel.data.vertices],
            'triangles':[list(p.vertices) for p in sentinel.data.polygons]}
        outside_before=outside()
        for index,case in enumerate(cases[:4],1):
            case_started=time.perf_counter_ns();packet=case['patch'];task=case['task']
            original_input=digest([packet,task]);names=[bone['name'] for bone in packet['bone_chain']]
            record={'case_id':case['case_id'],'passed':False,'asset_id':case['asset_id'],
                'input_sha256_before':original_input,'native_gates':NATIVE_GATES}
            report['cases'].append(record)
            preview_started=time.perf_counter_ns()
            report['work']['preview_calls']+=1
            preview=correction.preview_axial_redistribution(packet,task)
            record['preview_elapsed_ns']=time.perf_counter_ns()-preview_started
            if preview['status']!='candidate' or not preview.get('candidate'):
                raise AssertionError({'case':case['case_id'],'preview_status':preview['status'],'reason':preview.get('reason')})
            candidate=preview['candidate']
            if len(candidate['pose_matrices'])!=3 or len(candidate['local_basis_matrices'])!=3 or len(candidate['bone_changes'])!=2:
                raise AssertionError('exactly_three_pose_matrices_and_two_changes_required')
            for bone_index,change in zip((1,2),candidate['bone_changes']):
                if change['name']!=names[bone_index] or max_abs(change['basis_matrix'],candidate['local_basis_matrices'][bone_index])>1e-12:
                    raise AssertionError('declared_two_bone_changes_must_match_applied_local_matrices')
            construction_started=time.perf_counter_ns();mesh,rig=build(packet,index)
            record['fixture_construction_elapsed_ns']=time.perf_counter_ns()-construction_started
            static_before=static_read(mesh,rig,names);native_before=read(mesh,rig,names)
            record['joint_weight_proof']=cases_module.joint_weight_proof(packet)
            for proof in record['joint_weight_proof']:
                actual=[static_before['weights'][i] for i in packet['sections'][proof['section_index']]]
                if max_abs(actual,[proof['weights']]*len(actual))>1e-7:
                    raise AssertionError('native_joint_center_weight_mismatch')
            original_poses=[bone['pose_matrix'] for bone in packet['bone_chain']]
            initial_errors=pose_errors(native_before['pose_matrices'],original_poses)
            require_pose(initial_errors,'initial_native_pose_error')
            initial_vertex_error=point_error(native_before['current_vertices'],packet['current_vertices'])
            if initial_vertex_error>NATIVE_GATES['position_m']:raise AssertionError({'initial_vertex_error_m':initial_vertex_error})
            # These are the only candidate pose setters. The root bone is never
            # assigned during candidate application, and the two are FK-coupled.
            application_started=time.perf_counter_ns()
            for bone_index in (1,2):
                rig.pose.bones[names[bone_index]].matrix_basis=Matrix(candidate['local_basis_matrices'][bone_index])
                report['work']['qa_candidate_pose_assignments']+=1
            bpy.context.view_layer.update()
            record['qa_candidate_application_elapsed_ns']=time.perf_counter_ns()-application_started
            native_after=read(mesh,rig,names);static_after=static_read(mesh,rig,names)
            all_pose_errors=pose_errors(native_after['pose_matrices'],candidate['pose_matrices'])
            require_pose(all_pose_errors,'candidate_native_pose_error')
            end_errors=pose_errors([native_after['global_pose_matrices'][i] for i in (0,2)],
                                  [native_before['global_pose_matrices'][i] for i in (0,2)])
            require_pose(end_errors,'fixed_end_pose_error')
            centerline_error=max(point_error(native_after['head_positions'],native_before['head_positions']),
                                 point_error(native_after['tail_positions'],native_before['tail_positions']))
            ids={value:i for i,value in enumerate(packet['vertex_ids'])}
            protected_indices=[ids[value] for value in task['protected_vertex_ids']]
            protected_error=point_error([native_after['current_vertices'][i] for i in protected_indices],
                                        [native_before['current_vertices'][i] for i in protected_indices])
            candidate_vertex_error=point_error(native_after['current_vertices'],candidate['current_vertices'])
            before_objective=oracle.section_objective(static_before['rest_vertices'],native_before['current_vertices'],packet['sections'])
            after_objective=oracle.section_objective(static_before['rest_vertices'],native_after['current_vertices'],packet['sections'])
            expected_before=float(case['expected_before_j']);expected_after=float(case['expected_after_j'])
            before_j_error=abs(before_objective['max_section_area_loss']-expected_before)
            after_j_error=abs(after_objective['max_section_area_loss']-expected_after)
            checks={'initial_pose':initial_errors,'initial_vertices_max_m':initial_vertex_error,
                'candidate_pose':all_pose_errors,'fixed_end_global_pose':end_errors,
                'centerline_max_m':centerline_error,'protected_vertices_max_m':protected_error,
                'candidate_vertices_max_m':candidate_vertex_error,
                'before_j_error':before_j_error,'after_j_error':after_j_error,
                'static_data_exact':static_before==static_after,'outside_object_exact':outside_before==outside(),
                'input_packet_and_task_exact':original_input==digest([packet,task]),
                'target_met':after_objective['max_section_area_loss']<=task['max_section_area_loss']+NATIVE_GATES['section_area_loss']}
            raw={'case_id':case['case_id'],'source_input_sha256':original_input,
                'vertex_ids':packet['vertex_ids'],'sections':packet['sections'],
                'protected_vertex_ids':task['protected_vertex_ids'],'native_static':static_before,
                'native_before':native_before,'native_after':native_after,
                'candidate':{'u_deg':candidate['u_deg'],'pose_matrices':candidate['pose_matrices'],
                    'local_basis_matrices':candidate['local_basis_matrices'],'bone_changes':candidate['bone_changes']},
                'before_objective':before_objective,'after_objective':after_objective,
                'analytic_before_j':expected_before,'analytic_after_j':expected_after,'checks':checks}
            raw_path=output/('case_'+str(index).zfill(2)+'.json')
            raw_path.write_text(json.dumps(raw,indent=2,allow_nan=False),encoding='utf8',newline='\n')
            record.update({'checks':checks,'before_objective':before_objective,'after_objective':after_objective,
                'candidate_u_deg':candidate['u_deg'],'raw_native_readback_file':raw_path.name,
                'raw_native_readback_sha256':hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                'case_elapsed_ns':time.perf_counter_ns()-case_started})
            if (max(centerline_error,protected_error,candidate_vertex_error)>NATIVE_GATES['position_m']
                    or max(before_j_error,after_j_error)>NATIVE_GATES['section_area_loss']
                    or not all(checks[key] for key in ('static_data_exact','outside_object_exact','input_packet_and_task_exact','target_met'))):
                raise AssertionError({'native_case_failed':case['case_id'],'checks':checks})
            record['passed']=True
            bpy.data.objects.remove(mesh,do_unlink=True);bpy.data.objects.remove(rig,do_unlink=True)
        report['outside_object_exact']=outside_before==outside()
        report['passed']=len(report['cases'])==4 and all(row['passed'] for row in report['cases']) and report['outside_object_exact']
    except BaseException as exc:
        saved_error=exc;report['failure']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    finally:
        try:
            if bpy.context.object is not None and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
            remove_owned()
            report['owned_objects_removed']=all(bpy.data.objects.get(name) is None for name in owned_objects)
            report['owned_meshes_removed']=all(bpy.data.meshes.get(name) is None for name in owned_meshes)
            report['owned_rigs_removed']=all(bpy.data.armatures.get(name) is None for name in owned_rigs)
        except BaseException as exc:
            report['cleanup_failure']={'type':type(exc).__name__,'message':str(exc)}
        report['source_hashes_after']=hashes()
        report['source_bytes_unchanged']=report['source_hashes_after']==before
        report['blend_file_still_unsaved']=not bool(bpy.data.filepath)
        report['probe_elapsed_ns']=time.perf_counter_ns()-run_started
        report['passed']=bool(report['passed'] and report['source_bytes_unchanged'] and report['blend_file_still_unsaved']
            and all(report.get(key) for key in ('owned_objects_removed','owned_meshes_removed','owned_rigs_removed')))
        (output/'RESULT.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf8',newline='\n')
        print('ARM_CORRECTION_NATIVE '+json.dumps({'passed':report['passed'],'cases':len(report['cases']),
            'result':str(output/'RESULT.json')}),flush=True)
    if saved_error is not None:raise saved_error


if __name__=='__main__':main()
