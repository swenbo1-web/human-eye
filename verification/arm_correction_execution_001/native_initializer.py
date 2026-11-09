"""QA startup fixture/readonly observer; executed before the verified worker.

Only stdlib, bpy and mathutils are imported. The initializer assigns starting
bases (24 total), never candidate matrices. The hot observer calls the actual
bound product method once, with startup profiling already disabled.
"""
import copy
import hashlib
import json
import math
import marshal
import os
from pathlib import Path
import sys
import time

import bpy
from mathutils import Matrix

sys.dont_write_bytecode=True
_qa_output=Path(os.environ['ARM_EXEC_QA_OUTPUT'])
_qa_inputs=json.loads(Path(os.environ['ARM_EXEC_QA_INPUTS']).read_text(encoding='utf8'))
_qa_started=time.perf_counter_ns()
_qa_owned_objects=[];_qa_owned_meshes=[];_qa_owned_rigs=[]
_qa_records={row['event_id']:row for row in _qa_inputs['cases']}
_qa_work={'fixtures':0,'initial_basis_assignments':0,'candidate_assignments':0,'product_calls':0,'native_reads':0}
_qa_gates={'angle_deg':.001,'position_m':5e-6,'area_error':2e-5}


def _qa_save(name,value):
    (_qa_output/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')


def _qa_matrix(value):return [[float(x) for x in row] for row in value]
def _qa_norm(value):return math.sqrt(math.fsum(x*x for x in value))
def _qa_distance(a,b):return max((_qa_norm([x-y for x,y in zip(p,q)]) for p,q in zip(a,b)),default=0.)
def _qa_abs(a,b):
    if isinstance(a,list):return max((_qa_abs(x,y) for x,y in zip(a,b)),default=0.)
    return abs(a-b)


def _qa_angle(left,right):
    def frame(matrix):
        x=[matrix[k][0] for k in range(3)];n=_qa_norm(x);x=[v/n for v in x]
        y=[matrix[k][1] for k in range(3)];dot=math.fsum(a*b for a,b in zip(x,y))
        y=[a-dot*b for a,b in zip(y,x)];n=_qa_norm(y);y=[v/n for v in y]
        z=[x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0]]
        return (x,y,z)
    a,b=frame(left),frame(right)
    delta=[[math.fsum(x*y for x,y in zip(c,d)) for d in b] for c in a]
    sine=.5*_qa_norm([delta[2][1]-delta[1][2],delta[0][2]-delta[2][0],delta[1][0]-delta[0][1]])
    return math.degrees(math.atan2(sine,(sum(delta[i][i] for i in range(3))-1)*.5))


def _qa_area(points):
    center=[math.fsum(p[k] for p in points)/len(points) for k in range(3)]
    p=[[x-y for x,y in zip(row,center)] for row in points]
    return .5*_qa_norm([math.fsum(row[a]*p[(i+1)%len(p)][b]-row[b]*p[(i+1)%len(p)][a]
        for i,row in enumerate(p)) for a,b in ((1,2),(2,0),(0,1))])


def _qa_objective(rest,current,sections):
    ratios=[_qa_area([current[i] for i in row])/_qa_area([rest[i] for i in row]) for row in sections]
    return {'section_area_ratios':ratios,'max_section_area_loss':max(0.,1.-min(ratios))}


def _qa_read(row):
    mesh=bpy.data.objects[row['selection']['mesh_name']];rig=bpy.data.objects[row['selection']['armature_name']]
    names=row['selection']['bone_names'];sentinel=bpy.data.objects[row['sentinel_name']]
    graph=bpy.context.evaluated_depsgraph_get();em=mesh.evaluated_get(graph);er=rig.evaluated_get(graph)
    bones=[er.pose.bones[name] for name in names]
    _qa_work['native_reads']+=1
    return {'static':{'rest_vertices':[list(v.co) for v in mesh.data.vertices],
        'triangles':[list(p.vertices) for p in mesh.data.polygons],
        'raw_weights':[[math.fsum(float(g.weight) for g in v.groups if g.group==i) for i in range(3)] for v in mesh.data.vertices],
        'bones':[{'name':name,'parent':getattr(rig.data.bones[name].parent,'name',None),
            'rest_matrix':_qa_matrix(rig.data.bones[name].matrix_local),
            'head':list(rig.data.bones[name].head_local),'tail':list(rig.data.bones[name].tail_local),
            'length':float(rig.data.bones[name].length),'inherit_scale':rig.data.bones[name].inherit_scale,
            'inherit_rotation':bool(rig.data.bones[name].use_inherit_rotation),'local_location':bool(rig.data.bones[name].use_local_location),
            'use_deform':bool(rig.data.bones[name].use_deform),'bbone_segments':int(rig.data.bones[name].bbone_segments),
            'constraints':[c.type for c in rig.pose.bones[name].constraints]} for name in names],
        'mesh_world':_qa_matrix(mesh.matrix_world),'rig_world':_qa_matrix(rig.matrix_world),
        'unit_scale_m':float(bpy.context.scene.unit_settings.scale_length),
        'frame':int(bpy.context.scene.frame_current)},
        'current_vertices':[list(v.co) for v in em.data.vertices],
        'poses':[_qa_matrix(b.matrix) for b in bones],
        'world_poses':[_qa_matrix(er.matrix_world@b.matrix) for b in bones],
        'basis':[_qa_matrix(rig.pose.bones[name].matrix_basis) for name in names],
        'heads':[list(b.head) for b in bones],'tails':[list(b.tail) for b in bones],
        'sentinel':{'world':_qa_matrix(sentinel.matrix_world),'vertices':[list(v.co) for v in sentinel.data.vertices],
                    'triangles':[list(p.vertices) for p in sentinel.data.polygons]}}


def _qa_cleanup(host):
    started=time.perf_counter_ns();host.close_residency()
    for name in reversed(_qa_owned_objects):
        obj=bpy.data.objects.get(name)
        if obj is not None:bpy.data.objects.remove(obj,do_unlink=True)
    for name in reversed(_qa_owned_meshes):
        data=bpy.data.meshes.get(name)
        if data is not None:bpy.data.meshes.remove(data)
    for name in reversed(_qa_owned_rigs):
        data=bpy.data.armatures.get(name)
        if data is not None:bpy.data.armatures.remove(data)
    _qa_save('CHILD_CLEANUP.json',{'pid':os.getpid(),'work':_qa_work,'profile_none':sys.getprofile() is None,
        'host_residency_closed':not getattr(getattr(host,'_residency',None),'callbacks',[]),
        'owned_objects_removed':all(bpy.data.objects.get(n) is None for n in _qa_owned_objects),
        'owned_meshes_removed':all(bpy.data.meshes.get(n) is None for n in _qa_owned_meshes),
        'owned_rigs_removed':all(bpy.data.armatures.get(n) is None for n in _qa_owned_rigs),
        'handler_counts_before_host':_qa_handler_baseline,
        'handler_counts_after_close':{n:len(getattr(bpy.app.handlers,n)) for n in _qa_handler_baseline},
        'all_handlers_removed':all(len(getattr(bpy.app.handlers,n))==count for n,count in _qa_handler_baseline.items()),
        'file_unsaved':not bool(bpy.data.filepath),'cleanup_ns':time.perf_counter_ns()-started})


def _qa_attach(host):
    original=host.correct_arm_axial
    def observed(task):
        row=_qa_records[task['event_id']];index=row['index'];record={'event_id':task['event_id'],'case_id':row['case_id']}
        before_started=time.perf_counter_ns();before=_qa_read(row)
        record['qa_before_read_ns']=time.perf_counter_ns()-before_started
        result=None;failure=None;_qa_work['product_calls']+=1
        started=time.perf_counter_ns()
        try:
            result=original(task)
            return result
        except BaseException as exc:
            failure=repr(exc);raise
        finally:
            record['pure_product_method_ns']=time.perf_counter_ns()-started
            record.update(receipt=copy.deepcopy(result),product_error=failure,
                          product_audit=copy.deepcopy(getattr(host,'_last_arm_axial_audit',None)),native_before=before)
            try:
                mark=time.perf_counter_ns();after=_qa_read(row);record['qa_after_read_ns']=time.perf_counter_ns()-mark
                record['native_after']=after
                ids=row['protected_vertex_ids'];protected_before=[before['current_vertices'][i] for i in ids]
                protected_after=[after['current_vertices'][i] for i in ids]
                objective_before=_qa_objective(before['static']['rest_vertices'],before['current_vertices'],row['selection']['sections'])
                objective_after=_qa_objective(after['static']['rest_vertices'],after['current_vertices'],row['selection']['sections'])
                record.update(protected_points_before=protected_before,protected_points_after=protected_after,
                              actual_before=objective_before,actual_after=objective_after)
                expected=row['expected_entry_status'];positive=expected=='satisfied'
                endpoint_delta=max(_qa_abs(before['world_poses'][i],after['world_poses'][i]) for i in (0,2))
                endpoint_angle=max(_qa_angle(before['world_poses'][i],after['world_poses'][i]) for i in (0,2))
                endpoint_translation=_qa_distance([[before['world_poses'][i][k][3] for k in range(3)] for i in (0,2)],
                    [[after['world_poses'][i][k][3] for k in range(3)] for i in (0,2)])
                protected_delta=_qa_distance(protected_before,protected_after)
                centerline_delta=max(_qa_distance(before['heads'],after['heads']),_qa_distance(before['tails'],after['tails']))
                checks={'receipt_status':result is not None and result['status']==expected,
                    'setter_counts':result is not None and result['setter_attempts']==result['setter_returns']==(2 if positive else 0),
                    'target_met':not positive or objective_after['max_section_area_loss']<=row['max_section_area_loss']+row['area_tolerance'],
                    'static_exact':before['static']==after['static'],'sentinel_exact':before['sentinel']==after['sentinel'],
                    'protected_max_m':protected_delta,'centerline_max_m':centerline_delta,'endpoint_matrix_max_abs':endpoint_delta,
                    'endpoint_angle_deg':endpoint_angle,'endpoint_translation_m':endpoint_translation,
                    'no_write_native_exact':positive or before['current_vertices']==after['current_vertices'],
                    'profile_none':sys.getprofile() is None,'qa_candidate_assignments':0}
                record['checks']=checks
                record['passed']=all(checks[k] for k in ('receipt_status','setter_counts','target_met','static_exact','sentinel_exact',
                    'no_write_native_exact','profile_none')) and max(protected_delta,centerline_delta,endpoint_translation)<=_qa_gates['position_m'] and endpoint_angle<=_qa_gates['angle_deg']
            except BaseException as exc:record.update(passed=False,qa_error=repr(exc))
            try:
                mark=time.perf_counter_ns();_qa_save('case_'+str(index).zfill(2)+'.json',record)
                with (_qa_output/'OBSERVER_EVENTS.jsonl').open('a',encoding='utf8',newline='\n') as stream:
                    stream.write(json.dumps({'index':index,'event_id':task['event_id'],'evidence_write_ns':time.perf_counter_ns()-mark,
                        'pure_product_method_ns':record['pure_product_method_ns'],'passed':record.get('passed',False)},allow_nan=False)+'\n')
                if _qa_work['product_calls']==8:_qa_cleanup(host)
            except BaseException as exc:
                # An ancillary QA write must not replace the real receipt.
                try:_qa_save('OBSERVER_IO_FAILURE.json',{'event_id':task['event_id'],'error':repr(exc)})
                except BaseException:pass
    host.correct_arm_axial=observed
    _qa_save('OBSERVER_READY.json',{'pid':os.getpid(),'profile_none':sys.getprofile() is None,
        'product_method_module':original.__module__,'product_method_filename':original.__func__.__code__.co_filename,
        'product_method_firstlineno':original.__func__.__code__.co_firstlineno,
        'product_method_code_sha256':hashlib.sha256(marshal.dumps(original.__func__.__code__)).hexdigest(),
        'product_method_source_sha256':hashlib.sha256(Path(original.__func__.__code__.co_filename).read_bytes()).hexdigest(),
        'profile_scope':'startup_only_host_constructor_return','fixture_build_ns':time.perf_counter_ns()-_qa_started,
        'work':copy.deepcopy(_qa_work)})


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1.
for row in _qa_inputs['cases']:
    packet=row['fixture_packet'];names=row['selection']['bone_names']
    md=bpy.data.meshes.new(row['selection']['mesh_name']);_qa_owned_meshes.append(md.name)
    md.from_pydata(packet['rest_vertices'],[],packet['triangles']);md.update()
    mesh=bpy.data.objects.new(row['selection']['mesh_name'],md);_qa_owned_objects.append(mesh.name);bpy.context.scene.collection.objects.link(mesh)
    rd=bpy.data.armatures.new(row['selection']['armature_name']);_qa_owned_rigs.append(rd.name)
    rig=bpy.data.objects.new(row['selection']['armature_name'],rd);_qa_owned_objects.append(rig.name);bpy.context.scene.collection.objects.link(rig)
    bpy.ops.object.select_all(action='DESELECT');rig.select_set(True);bpy.context.view_layer.objects.active=rig;bpy.ops.object.mode_set(mode='EDIT')
    rests=packet['bone_chain'];lengths=[_qa_norm([rests[i+1]['rest_matrix'][j][3]-rests[i]['rest_matrix'][j][3] for j in range(3)]) for i in (0,1)]
    lengths.append(lengths[-1])
    for bone,length in zip(rests,lengths):
        b=rd.edit_bones.new(bone['name']);b.head=(0.,0.,0.);b.tail=(0.,length,0.)
        if bone['parent'] is not None:b.parent=rd.edit_bones[bone['parent']]
        b.use_connect=False;b.matrix=Matrix(bone['rest_matrix']);b.length=length
    bpy.ops.object.mode_set(mode='OBJECT')
    for b in rd.bones:
        b.use_deform=True;b.bbone_segments=1;b.use_envelope_multiply=False
        b.use_inherit_rotation=True;b.inherit_scale='FULL';b.use_local_location=True
    groups=[mesh.vertex_groups.new(name=n) for n in names]
    for i,weights in enumerate(packet['weights']):
        for group,weight in zip(groups,weights):
            if weight:group.add([i],weight,'REPLACE')
    modifier=mesh.modifiers.new('ArmExecLBS','ARMATURE');modifier.object=rig
    modifier.use_vertex_groups=True;modifier.use_bone_envelopes=False;modifier.use_deform_preserve_volume=False
    modifier.use_multi_modifier=False
    for name,basis in zip(names,row['initial_local_basis']):
        pose=rig.pose.bones[name];pose.rotation_mode='QUATERNION';pose.matrix_basis=Matrix(basis)
        _qa_work['initial_basis_assignments']+=1
    _qa_work['fixtures']+=1
sentinel_name=_qa_inputs['cases'][0]['sentinel_name'];sd=bpy.data.meshes.new(sentinel_name);_qa_owned_meshes.append(sd.name)
sd.from_pydata([(8.,9.,10.),(9.,9.,10.),(8.,10.,10.)],[],[(0,1,2)]);sd.update()
sentinel=bpy.data.objects.new(sentinel_name,sd);_qa_owned_objects.append(sentinel.name);bpy.context.scene.collection.objects.link(sentinel)
bpy.context.view_layer.update()
_qa_handler_baseline={n:len(getattr(bpy.app.handlers,n)) for n in ('depsgraph_update_post','undo_post','redo_post','load_post')}


def _qa_profile(frame,event,arg):
    if (event=='return' and frame.f_code.co_name=='__init__'
            and frame.f_globals.get('__name__')=='human_eye_blender_host_worker'
            and type(frame.f_locals.get('self')).__name__=='BlenderSceneHost'):
        sys.setprofile(None)
        try:_qa_attach(frame.f_locals['self'])
        except BaseException as exc:_qa_save('OBSERVER_READY.json',{'error':repr(exc),'profile_none':True})


sys.setprofile(_qa_profile)
