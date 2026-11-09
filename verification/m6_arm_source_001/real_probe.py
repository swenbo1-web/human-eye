"""Root-owned fresh background Blender QA; invoke: -- outputdir rootpath.

Creates only generated test data in an empty unsaved background scene. Never
opens or saves a blend file. This script does not launch any child process.
"""
import gzip
import hashlib
import importlib
import json
from pathlib import Path
import sys
import traceback
import types


def main():
    import bpy
    import bmesh
    import numpy as np
    from mathutils import Matrix

    args=sys.argv[sys.argv.index('--')+1:]
    if len(args)!=2:raise ValueError('usage: -- outputdir rootpath')
    output,root=(Path(value).resolve() for value in args)
    output.mkdir(parents=True,exist_ok=True)
    if not bpy.app.background or bpy.data.filepath:
        raise RuntimeError('fresh_unsaved_background_required')
    sys.dont_write_bytecode=True
    package=types.ModuleType('human_eye_plugin');package.__path__=[str(root/'human_eye_plugin')]
    sys.modules['human_eye_plugin']=package
    Host=importlib.import_module('human_eye_plugin.blender_host').BlenderSceneHost
    Source=importlib.import_module('human_eye_plugin.arm_twist_source').ArmTwistSource
    source_names=('blender_host.py','scene_residency.py','arm_twist_source.py',
                  'arm_twist_expert.py','arm_twist_weights.py','rig_pose.py')
    def hashes():
        return {name:hashlib.sha256((root/'human_eye_plugin'/name).read_bytes()).hexdigest()
                for name in source_names}
    dataset=root/'verification/m6_arm_expert_001/run_01/dataset.json.gz'
    dataset_sha=hashlib.sha256(dataset.read_bytes()).hexdigest()
    cases=json.loads(gzip.decompress(dataset.read_bytes()))
    first=next(case for case in cases if len(case['packet']['bone_chain'])==2)
    asset=first['metadata']['asset_id']
    group=[case for case in cases if case['metadata']['asset_id']==asset]
    initial=next(case for case in group if case['metadata']['pose_family']=='anomalous_twist'
                 and case['metadata']['angle_deg']==120.)
    fifth=group[5]
    if fifth['metadata']['deformation']!='LBS_point_pose_times_inverse_rest':
        raise ValueError('saved_pose5_must_be_actual_lbs')
    packet=initial['packet']
    if len(packet['rest_vertices'])!=402 or len(packet['triangles'])!=800:
        raise ValueError('saved_402_vertex_800_triangle_fixture_required')
    report=dict(schema='m6-arm-source-native-probe-v1',passed=False,
        blender_version=bpy.app.version_string,blender_build_hash=bpy.app.build_hash.decode(),
        background=True,blend_file_opened=False,blend_file_saved=False,
        product_sources_before=hashes(),dataset_sha256_before=dataset_sha,
        test_asset=asset,initial_case=initial['metadata']['case_id'],pose5_case=fifth['metadata']['case_id'],
        states=[],depsgraph_events=[],limitations=[
            'Only this generated 402-point asset; larger asset work is not measured here.',
            'Native bmesh.from_mesh constructs the whole test mesh; Python extraction is local.',
            'No automatic role or section discovery; no real character or animation-time coverage.'])
    host=None;handler=None;phase=['construct'];saved_error=None

    def reference(value):
        if value is None:return None
        try:
            return dict(type=getattr(value,'id_type',type(value).__name__),
                name=getattr(value,'name_full',getattr(value,'name',None)),
                session_uid=int(getattr(value,'session_uid',0)))
        except ReferenceError:return {'invalid_rna':True}
    def updated(scene,graph):
        for update in graph.updates:
            value=update.id
            report['depsgraph_events'].append(dict(phase=phase[0],id=reference(value),
                original=reference(getattr(value,'original',value)),
                is_updated_geometry=bool(update.is_updated_geometry),
                is_updated_transform=bool(update.is_updated_transform)))
    handler=updated;bpy.app.handlers.depsgraph_update_post.append(handler)
    try:
        for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
        scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
        data=bpy.data.meshes.new('HE_ArmSource_TestMesh')
        data.from_pydata(packet['rest_vertices'],[],packet['triangles']);data.update()
        mesh=bpy.data.objects.new('HE_ArmSource_TestMesh',data);scene.collection.objects.link(mesh)
        rig_data=bpy.data.armatures.new('HE_ArmSource_TestRig')
        rig=bpy.data.objects.new('HE_ArmSource_TestRig',rig_data);scene.collection.objects.link(rig)
        bpy.context.view_layer.objects.active=rig;rig.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        for spec in packet['bone_chain']:
            bone=rig_data.edit_bones.new(spec['name']);bone.head=(0.,0.,0.);bone.tail=(0.,.25,0.)
            if spec['parent'] is not None:bone.parent=rig_data.edit_bones[spec['parent']]
            bone.use_connect=False;bone.matrix=Matrix(spec['rest_matrix']);bone.length=.25
        bpy.ops.object.mode_set(mode='OBJECT')
        for bone in rig_data.bones:
            bone.use_deform=True;bone.use_envelope_multiply=False;bone.bbone_segments=1
            bone.use_inherit_rotation=True;bone.inherit_scale='FULL';bone.use_local_location=True
        groups=[mesh.vertex_groups.new(name=bone['name']) for bone in packet['bone_chain']]
        for index,row in enumerate(packet['weights']):
            for group,weight in zip(groups,row):
                if weight:group.add([index],float(weight),'REPLACE')
        modifier=mesh.modifiers.new('HE_ArmSource_Armature','ARMATURE');modifier.object=rig
        for field,value in (('use_vertex_groups',True),('use_bone_envelopes',False),
                ('use_deform_preserve_volume',False),('use_multi_modifier',False),
                ('invert_vertex_group',False),('vertex_group',''),('show_viewport',True),('show_render',True)):
            setattr(modifier,field,value)
        def set_pose(case):
            for spec in case['packet']['bone_chain']:
                rig.pose.bones[spec['name']].matrix=Matrix(spec['pose_matrix'])
                bpy.context.view_layer.update()
        set_pose(initial)
        host=Host(bpy_module=bpy,execution_metadata=True,identity_metadata=True)
        selection=dict(mesh_name=mesh.name,armature_name=rig.name,
            bone_names=[bone['name'] for bone in packet['bone_chain']],
            vertex_indices=list(range(402)),sections=packet['sections'])
        bound=Source(host).bind(selection)

        def dirty():
            state=host._residency
            return [] if state is None else [dict(key=repr(key),count=value)
                for key,value in sorted(state.dirty.items(),key=lambda item:repr(item[0]))]
        def transform(matrix,point,unit):
            return ((matrix@np.r_[np.asarray(point,dtype=float),1.])[:3]*unit).tolist()
        def metre_matrix(matrix,unit):
            value=np.asarray(matrix,dtype=float).copy();value[:3,3]*=unit;return value
        def canonical(rows):
            result=set()
            for row in rows:
                row=tuple(row);offset=min(range(len(row)),key=row.__getitem__)
                result.add(row[offset:]+row[:offset])
            return result
        def check_native(capture):
            graph=bpy.context.evaluated_depsgraph_get()
            em=mesh.evaluated_get(graph);er=rig.evaluated_get(graph)
            unit=float(scene.unit_settings.scale_length)
            rest_relative=np.linalg.inv(np.asarray(rig.matrix_world,dtype=float))@np.asarray(mesh.matrix_world,dtype=float)
            current_relative=np.linalg.inv(np.asarray(er.matrix_world,dtype=float))@np.asarray(em.matrix_world,dtype=float)
            rest=[transform(rest_relative,mesh.data.vertices[i].co,unit) for i in selection['vertex_indices']]
            current=[transform(current_relative,em.data.vertices[i].co,unit) for i in selection['vertex_indices']]
            static=bound._static
            errors=dict(rest_max_abs=float(np.max(np.abs(np.asarray(rest)-static['rest_vertices']))),
                        current_max_abs=float(np.max(np.abs(np.asarray(current)-capture['current_vertices']))))
            weights=[]
            for index in selection['vertex_indices']:
                row=[0.]*len(groups)
                for membership in mesh.data.vertices[index].groups:
                    row[membership.group]=float(membership.weight)
                row=np.asarray(row);weights.append(row/row.sum())
            errors['weights_max_abs']=float(np.max(np.abs(np.asarray(weights)-static['weights'])))
            rest_bones=[metre_matrix(rig.data.bones[name].matrix_local,unit) for name in selection['bone_names']]
            poses=[metre_matrix(er.pose.bones[name].matrix,unit) for name in selection['bone_names']]
            errors['rest_bone_max_abs']=float(np.max(np.abs(np.asarray(rest_bones)-
                [bone['rest_matrix'] for bone in static['bone_chain']])))
            errors['pose_bone_max_abs']=float(np.max(np.abs(np.asarray(poses)-capture['pose_matrices'])))
            actual_faces=canonical(tuple(static['vertex_ids'][i] for i in row) for row in static['triangles'])
            direct_faces=canonical(tuple(poly.vertices) for poly in mesh.data.polygons)
            errors['topology_equal']=actual_faces==direct_faces
            errors['vertex_ids_equal']=static['vertex_ids']==selection['vertex_indices']
            assert all(value<=2e-9 for name,value in errors.items() if name.endswith('_abs')),errors
            assert errors['topology_equal'] and errors['vertex_ids_equal'],errors
            assert capture['source']['max_lbs_readback_error_m']<=2e-6,capture['source']
            return errors
        def record(name,action=None,*,expected_changed=None,expected_packet=None):
            phase[0]=name;before=bound.work_totals();before_dirty=dirty()
            before_prepared=id(bound.prepared) if bound.prepared is not None else None
            if action is not None:action()
            bpy.context.view_layer.update()
            capture=bound.capture()
            checks=check_native(capture)
            if expected_packet is not None:
                checks['saved_current_max_abs']=float(np.max(np.abs(np.asarray(capture['current_vertices'])-
                                                                     expected_packet['current_vertices'])))
                assert checks['saved_current_max_abs']<=5e-6,checks
            after=bound.work_totals()
            report['states'].append(dict(name=name,source=capture['source'],
                static_changed=capture['static_changed'],prepared_identity=id(bound.prepared),
                prepared_identity_before=before_prepared,dirty_before=before_dirty,dirty_after=dirty(),
                work_before=before,work_after=after,work_delta={key:after[key]-before[key] for key in after},
                direct_native_checks=checks))
            if expected_changed is not None:assert capture['static_changed'] is expected_changed,(name,capture)
            if expected_changed is False:assert before_prepared==id(bound.prepared),name
        record('initial',expected_changed=True,expected_packet=initial['packet'])
        record('stable_repeat',expected_changed=False,expected_packet=initial['packet'])
        record('pose_5_lbs',lambda:set_pose(fifth),expected_changed=False,expected_packet=fifth['packet'])
        selected=next(i for i,row in enumerate(packet['weights']) if 0.05<row[0]<.95)
        def change_rest():
            mesh.data.vertices[selected].co.x+=0.0005;mesh.data.update()
        record('raw_selected_coordinate',change_rest,expected_changed=True)
        def change_weights():
            current={entry.group:float(entry.weight) for entry in mesh.data.vertices[selected].groups}
            delta=min(.005,current[1]/2)
            groups[0].add([selected],current[0]+delta,'REPLACE')
            groups[1].add([selected],current[1]-delta,'REPLACE')
            mesh.data.update()
        record('selected_weight_sum_one',change_weights,expected_changed=True)
        def flip_topology():
            bm=bmesh.new()
            try:
                bm.from_mesh(mesh.data);bm.faces.ensure_lookup_table()
                bmesh.ops.reverse_faces(bm,faces=[bm.faces[0]])
                bm.to_mesh(mesh.data);mesh.data.update()
            finally:bm.free()
        record('selected_topology_flip',flip_topology,expected_changed=True)
        def relative_unit():
            rig.matrix_world=Matrix.Translation((.3,-.2,.1))@Matrix.Rotation(.4,4,'Z')
            mesh.matrix_world=Matrix.Translation((-.1,.1,.2))@Matrix.Rotation(-.2,4,'X')
            scene.unit_settings.scale_length=.125
        record('relative_transform_and_unit',relative_unit,expected_changed=True)
        report['work_final']=bound.work_totals();report['host_residency_work']=host.residency_work()
        report['passed']=True
    except BaseException as exc:
        report['failure']=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
        saved_error=exc
    finally:
        if host is not None:host.close_residency()
        if handler in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(handler)
        report['own_probe_handler_removed']=handler not in bpy.app.handlers.depsgraph_update_post
        report['host_residency_closed']=not getattr(getattr(host,'_residency',None),'callbacks',[])
        report['product_sources_after']=hashes()
        report['product_sources_unchanged']=report['product_sources_before']==report['product_sources_after']
        report['dataset_sha256_after']=hashlib.sha256(dataset.read_bytes()).hexdigest()
        report['dataset_unchanged']=report['dataset_sha256_before']==report['dataset_sha256_after']
        report['probe_source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        report['blend_file_still_unsaved']=not bool(bpy.data.filepath)
        report['passed']=(report['passed'] and report['product_sources_unchanged'] and report['dataset_unchanged']
                          and report['own_probe_handler_removed'] and report['host_residency_closed'])
        (output/'RESULT.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf8',newline='\n')
        print('M6_ARM_SOURCE_PROBE '+json.dumps(dict(passed=report['passed'],states=len(report['states']),
              result=str(output/'RESULT.json')),allow_nan=False),flush=True)
    if saved_error is not None:raise saved_error


if __name__=='__main__':main()
