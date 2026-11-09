"""Read a selected native Armature patch for the optional twist expert.

This adapter borrows the existing scene host transaction and residency version.
It never edits geometry, starts a worker, saves a file, or guesses sections.
Native Blender integration is a separate thin host/worker wiring step.
"""
from copy import deepcopy
import hashlib
import math

from . import rig_pose as r

MAX_VERTICES=8192
MAX_TRIANGLES=16384


class ArmTwistSourceError(ValueError):
    def __init__(self,reason,**details):
        self.reason=reason;self.details=details
        super().__init__(reason)


def _need(value,reason,**details):
    if not value:raise ArmTwistSourceError(reason,**details)


def _matrix(value,*,rigid=False):
    matrix=[[float(x) for x in row] for row in value]
    r.matrix(matrix)
    _need(not rigid or r.rigid(matrix),'nonrigid_source_frame')
    return matrix


def _point(matrix,value,scale):
    point=[float(x) for x in value]
    _need(len(point)==3 and all(math.isfinite(v) for v in point),'nonfinite_source_vertex')
    point=[v*scale for v in r.point(matrix,point)]
    _need(all(math.isfinite(v) for v in point),'nonfinite_source_vertex')
    return point


def _metre_matrix(value,scale):
    matrix=_matrix(value,rigid=True)
    for row in matrix[:3]:row[3]*=scale
    return matrix


def _native_topology(mesh,vertex_indices):
    """Native temporary BMesh; Python visits only selected incident faces.

    from_mesh/lookup construction still has whole-mesh C-side cost. No full
    Python vertex/face array is constructed; this is not an O(selected) claim.
    """
    import bmesh
    selected=set(vertex_indices);bm=bmesh.new()
    try:
        bm.from_mesh(mesh.data);bm.verts.ensure_lookup_table();bm.verts.index_update()
        faces={face for index in vertex_indices for face in bm.verts[index].link_faces
               if all(v.index in selected for v in face.verts)}
        _need(sum(len(face.verts)-2 for face in faces)<=MAX_TRIANGLES,'local_triangle_budget')
        result=[tuple(v.index for v in face.verts) for face in faces if len(face.verts)==3]
        polygons=[face for face in faces if len(face.verts)>3]
        if polygons:
            triangulated=bmesh.ops.triangulate(bm,faces=polygons)
            result.extend(tuple(v.index for v in face.verts) for face in triangulated['faces'])
        return result
    finally:bm.free()


class ArmTwistSource:
    def __init__(self,host,*,topology_reader=None):
        self.host=host;self.topology_reader=topology_reader or _native_topology

    def bind(self,selection):return BoundArmPatch(self,selection)


class BoundArmPatch:
    def __init__(self,source,selection):
        _need(type(selection) is dict and not set(selection)-{
            'mesh_name','armature_name','bone_names','vertex_indices','sections'},'selection_fields')
        _need(r.text(selection.get('mesh_name')),'selection_mesh_name')
        names=selection.get('bone_names')
        _need(type(names) is list and 2<=len(names)<=4 and all(r.text(n) for n in names)
              and len(set(names))==len(names),'selection_bone_chain')
        if 'armature_name' in selection:_need(r.text(selection['armature_name']),'selection_armature_name')
        sections=selection.get('sections')
        _need(type(sections) is list and 2<=len(sections)<=128,'selection_sections')
        used=set()
        for row in sections:
            _need(type(row) is list and 3<=len(row)<=256 and all(type(i) is int and i>=0 for i in row)
                and len(set(row))==len(row) and not used.intersection(row),'selection_section_indices')
            used.update(row)
        indices=selection.get('vertex_indices',sorted(used))
        _need(type(indices) is list and 6<=len(indices)<=MAX_VERTICES and all(type(i) is int and i>=0 for i in indices)
              and len(set(indices))==len(indices) and used.issubset(indices),'selection_vertex_indices')
        self._source=source;self._selection=deepcopy(selection);self._selection['vertex_indices']=list(indices)
        self._indices=tuple(indices);self._sections=tuple(tuple(s) for s in sections);self._names=tuple(names)
        self._selection_key=hashlib.sha256(r.encoded(self._selection)).hexdigest()
        self._prepared=None;self._static=None;self._witness=None;self._binding=None;self._notice=None
        self._static_revision=0
        self._work=dict(captures=0,static_reads=0,preparations=0,rest_vertices=0,weight_rows=0,
                        current_vertices=0,rest_bones=0,pose_bones=0,topology_reads=0)

    @property
    def prepared(self):return self._prepared

    def work_totals(self):return dict(self._work)

    def _inspect(self,host,graph,scale):
        identity=host._residency_module.identity
        mesh=host.scene.objects.get(self._selection['mesh_name'])
        _need(mesh is not None and mesh.type=='MESH','mesh_not_found')
        _need(getattr(mesh,'mode','OBJECT')=='OBJECT','mesh_edit_mode')
        _need(getattr(mesh.data,'shape_keys',None) is None,'shape_keys_unsupported')
        _need(getattr(mesh,'instance_type','NONE')=='NONE' and not getattr(mesh,'is_instancer',False),'mesh_instances_unsupported')
        _need(len(mesh.modifiers)==1 and mesh.modifiers[0].type=='ARMATURE','single_armature_required')
        modifier=mesh.modifiers[0];rig=modifier.object
        _need(rig is not None and rig.type=='ARMATURE','armature_not_found')
        present=host.scene.objects.get(rig.name)
        _need(present is not None and identity(present)==identity(rig),'armature_not_in_scene')
        _need(self._selection.get('armature_name',rig.name)==rig.name,'armature_binding_mismatch')
        _need(not getattr(rig.data,'is_editmode',False) and getattr(rig.data,'pose_position','POSE')=='POSE','armature_not_in_pose_state')
        for field,expected in (('use_vertex_groups',True),('use_bone_envelopes',False),
                ('use_deform_preserve_volume',False),('use_multi_modifier',False),
                ('invert_vertex_group',False),('vertex_group',''),('show_viewport',True)):
            _need(getattr(modifier,field,expected)==expected,'unsupported_modifier_'+field)
        _need(max(self._indices)<len(mesh.data.vertices),'native_vertex_index_out_of_range')
        bones=[]
        for index,name in enumerate(self._names):
            bone=rig.data.bones.get(name)
            _need(bone is not None,'bone_not_found',bone=name)
            _need(index==0 or getattr(getattr(bone,'parent',None),'name',None)==self._names[index-1],'bone_chain_mismatch')
            _need(getattr(bone,'use_deform',True) and not getattr(bone,'use_envelope_multiply',False),'unsupported_bone_deform')
            bones.append(bone)
        rig_world=_matrix(rig.matrix_world,rigid=True)
        relative=r.multiply(r.inverse(rig_world),_matrix(mesh.matrix_world))
        evaluated_mesh=mesh.evaluated_get(graph);evaluated_rig=rig.evaluated_get(graph)
        _need(getattr(evaluated_mesh,'is_evaluated',False) and getattr(evaluated_rig,'is_evaluated',False),'evaluation_unavailable')
        _need(identity(getattr(evaluated_mesh,'original',mesh))==identity(mesh)
              and identity(getattr(evaluated_rig,'original',rig))==identity(rig),'evaluated_object_binding')
        _need(len(evaluated_mesh.data.vertices)==len(mesh.data.vertices),'evaluated_vertex_count_mismatch')
        current_relative=r.multiply(r.inverse(_matrix(evaluated_rig.matrix_world,rigid=True)),_matrix(evaluated_mesh.matrix_world))
        state=host._residency
        binding=(state.instance_id,state.epoch,identity(host.scene),identity(mesh),identity(mesh.data),identity(rig),identity(rig.data))
        groups=tuple((int(group.index),str(group.name)) for group in mesh.vertex_groups)
        metadata=(scale,relative,len(mesh.data.vertices),len(mesh.data.polygons),groups,
                  tuple(getattr(getattr(b,'parent',None),'name',None) for b in bones))
        notice=(metadata,tuple(state.dirty.get(identity(item),0) for item in (mesh,mesh.data,rig,rig.data)))
        return mesh,rig,bones,relative,current_relative,evaluated_mesh,evaluated_rig,binding,notice

    def _read_static(self,mesh,rig,bones,relative,scale):
        self._work['static_reads']+=1
        rest=[];weights=[];raw=[];lookup={name:i for i,name in enumerate(self._names)}
        for index in self._indices:
            vertex=mesh.data.vertices[index];rest.append(_point(relative,vertex.co,scale));self._work['rest_vertices']+=1
            row=[0.]*len(bones);effective=[]
            for membership in vertex.groups:
                weight=float(membership.weight)
                _need(math.isfinite(weight) and weight>=0,'invalid_vertex_weight',index=index)
                if not weight:continue
                group_index=membership.group
                _need(type(group_index) is int and 0<=group_index<len(mesh.vertex_groups),'vertex_group_index')
                group=mesh.vertex_groups[group_index];bone=rig.data.bones.get(group.name)
                if bone is None or not getattr(bone,'use_deform',True):continue
                _need(group.name in lookup,'unselected_deform_bone_weight',index=index,bone=group.name)
                _need(not getattr(bone,'use_envelope_multiply',False),'unsupported_bone_deform')
                row[lookup[group.name]]+=weight;effective.append((group.name,weight))
            total=math.fsum(row)
            _need(total>0,'unweighted_selected_vertex',index=index)
            _need(abs(total-1.)<=1e-6,'nonunit_effective_weights',index=index,total=total)
            weights.append([value/total for value in row]);raw.append(sorted(effective));self._work['weight_rows']+=1
        global_faces=self._source.topology_reader(mesh,self._indices);self._work['topology_reads']+=1
        selected=set(self._indices);canonical=set()
        for face in global_faces:
            _need(len(face)==3 and all(type(i) is int and i in selected for i in face) and len(set(face))==3,'selected_triangle_indices')
            offset=min(range(3),key=lambda i:face[i]);row=tuple(face[offset:])+tuple(face[:offset]);canonical.add(row)
            _need(len(canonical)<=MAX_TRIANGLES,'local_triangle_budget')
        _need(canonical,'selected_topology_empty')
        local={index:i for i,index in enumerate(self._indices)}
        chain=[]
        for index,bone in enumerate(bones):
            chain.append(dict(name=bone.name,parent=self._names[index-1] if index else None,
                              rest_matrix=_metre_matrix(bone.matrix_local,scale)))
            self._work['rest_bones']+=1
        patch=dict(schema='arm-twist-patch-v1',unit='m',rest_vertices=rest,weights=weights,bone_chain=chain,
            triangles=[[local[i] for i in face] for face in sorted(canonical)],vertex_ids=list(self._indices),
            sections=[[local[i] for i in section] for section in self._sections])
        return patch,raw

    def capture(self,*,_export_static_patch=True):
        host=self._source.host;host._main_thread()
        with host.transaction():
            graph=host._depsgraph();scale=host._scale()
            tracked=host._sync_residency(graph,scale)
            mesh,rig,bones,relative,current_relative,em,er,binding,notice=self._inspect(host,graph,scale)
            state=host._residency;version=(state.instance_id,state.epoch,state.revision,state.serial)
            patch=self._static;witness=self._witness;prepared=self._prepared
            if not tracked or binding!=self._binding or notice!=self._notice:
                patch,witness=self._read_static(mesh,rig,bones,relative,scale)
            changed=(not tracked or binding!=self._binding or patch!=self._static or witness!=self._witness)
            if changed:
                from .arm_twist_expert import prepare_patch
                prepared=prepare_patch(patch)
            current=[]
            for index in self._indices:
                current.append(_point(current_relative,em.data.vertices[index].co,scale));self._work['current_vertices']+=1
            poses=[]
            for name in self._names:
                pose=er.pose.bones.get(name);_need(pose is not None,'evaluated_bone_not_found',bone=name)
                poses.append(_metre_matrix(pose.matrix,scale));self._work['pose_bones']+=1
            deforms=[r.multiply(pose,r.inverse(bone['rest_matrix'])) for pose,bone in zip(poses,patch['bone_chain'])]
            worst=0.
            for index,(rest,row,actual) in enumerate(zip(patch['rest_vertices'],patch['weights'],current)):
                mapped=[(weight,r.point(matrix,rest)) for weight,matrix in zip(row,deforms) if weight]
                predicted=[math.fsum(weight*point[k] for weight,point in mapped) for k in range(3)]
                error=max(abs(a-b) for a,b in zip(predicted,actual));worst=max(worst,error)
                tolerance=2e-6*max(1.,*(abs(v) for v in actual),*(abs(v) for v in predicted))
                _need(error<=tolerance,'same_index_lbs_readback_mismatch',index=self._indices[index],error_m=error)
            _need(version==(state.instance_id,state.epoch,state.revision,state.serial),'source_changed_during_capture')
            self._static=patch;self._witness=witness;self._prepared=prepared
            self._binding=binding;self._notice=deepcopy(notice)
            if changed:self._static_revision+=1;self._work['preparations']+=1
            self._work['captures']+=1
            source=dict(instance_id=state.instance_id,epoch=state.epoch,revision=state.revision,
                static_revision=self._static_revision,selection_key=self._selection_key,
                mesh=dict(name=mesh.name,object_id=host.object_id(mesh),instance=binding[3],data_instance=binding[4]),
                armature=dict(name=rig.name,object_id=host.object_id(rig),instance=binding[5],data_instance=binding[6]),
                frame=dict(number=int(host.scene.frame_current),subframe=float(getattr(host.scene,'frame_subframe',0.))),
                coordinate_frame='armature_local',unit='m',selected_vertices=len(self._indices),
                selected_bones=list(self._names),local_root_parent=getattr(getattr(bones[0],'parent',None),'name',None),
                tracking='scene_residency' if tracked else 'fresh_untracked',max_lbs_readback_error_m=worst)
            return dict(schema='arm-twist-source-capture-v1',source=source,static_patch=deepcopy(patch) if changed and _export_static_patch else None,
                        current_vertices=current,pose_matrices=poses,static_changed=changed)

    def analyze(self,model=None):
        capture=self.capture(_export_static_patch=False)
        report=self._prepared.analyze(capture['current_vertices'],capture['pose_matrices'],model=model)
        report['source_binding']='local_armature_source_adapter';report['source']=capture['source']
        return report
