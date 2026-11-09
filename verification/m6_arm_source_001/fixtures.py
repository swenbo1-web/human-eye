"""Indexed, counted bpy doubles; no full-asset vertex materialization."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import copy
import hashlib
import json
import uuid
from types import SimpleNamespace as NS

from human_eye_plugin import rig_pose


def identity(value):
    if value is None:return None
    uid=getattr(value,'session_uid',None)
    if type(uid) is int and uid:return ('uid',uid)
    pointer=getattr(value,'as_pointer',None)
    return ('ptr',int(pointer())) if callable(pointer) else ('python',id(value))


class Matrix(list):
    def copy(self):return Matrix([list(row) for row in self])
    def inverted(self):return Matrix(rig_pose.inverse(self))
    def __matmul__(self,other):
        if len(other)==4 and isinstance(other[0],(list,tuple)):
            return Matrix(rig_pose.multiply(self,other))
        return rig_pose.point(self,other)


def unit_matrix():return Matrix([[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]])


def host_matrix(matrix,scale):
    value=copy.deepcopy(matrix)
    for row in range(3):value[row][3]/=scale
    return Matrix(value)


class NamedCollection(list):
    def get(self,name,default=None):return next((v for v in self if v.name==name),default)
    def __getitem__(self,key):
        if isinstance(key,str):
            found=self.get(key)
            if found is None:raise KeyError(key)
            return found
        return super().__getitem__(key)


class Vertex:
    def __init__(self,index,co,weights,counters,kind):
        self.index=index;self.value=list(co);self.memberships=list(weights)
        self.counters=counters;self.kind=kind
    @property
    def co(self):
        self.counters[self.kind+'_coordinates']+=1
        return tuple(self.value)
    @property
    def groups(self):
        self.counters['weights_collections']+=1
        return [NS(group=group,weight=weight) for group,weight in self.memberships]


class IndexedVertices:
    def __init__(self,count,vertices,counters,kind):
        self.count=count;self.rows=vertices;self.counters=counters;self.kind=kind
    def __len__(self):
        self.counters[self.kind+'_len']+=1
        return self.count
    def __getitem__(self,index):
        self.counters[self.kind+'_index_reads']+=1
        if type(index) is not int or index not in self.rows:
            self.counters['unselected_vertex_requests']+=1
            raise AssertionError('full_asset_or_unselected_vertex_read:'+str(index))
        return self.rows[index]
    def __iter__(self):
        self.counters['full_vertex_iteration_attempts']+=1
        raise AssertionError('full_asset_vertex_iteration_forbidden')
    def foreach_get(self,*args):
        self.counters['full_vertex_bulk_attempts']+=1
        raise AssertionError('full_asset_vertex_foreach_get_forbidden')


class ForbiddenTopology:
    def __init__(self,count,counters):self.count=count;self.counters=counters
    def __len__(self):return self.count
    def __iter__(self):
        self.counters['full_topology_iteration_attempts']+=1
        raise AssertionError('inject_local_topology_reader_instead_of_full_mesh_iteration')
    def __getitem__(self,index):raise AssertionError('unexpected_native_global_polygon_access')


class Bone:
    def __init__(self,name,parent,rest,pose,counters):
        self.name=name;self.parent=parent;self.rest=Matrix(rest);self.pose=Matrix(pose)
        self.counters=counters;self.use_deform=True;self.inherit_rotation=True
        self.inherit_scale='FULL';self.use_local_location=True;self.bbone_segments=1
        self.use_envelope_multiply=False
    @property
    def matrix_local(self):
        self.counters['bone_rest_matrices']+=1
        return self.rest.copy()
    @property
    def matrix(self):
        self.counters['bone_pose_matrices']+=1
        return self.pose.copy()


class FakeResidency:
    def __init__(self):
        self.instance_id=uuid.uuid4().hex;self.epoch=1;self.revision=1
        self.dirty={};self.resources={};self.serial=0;self.enabled=True
    def token(self,selection_key):
        return dict(instance_id=self.instance_id,epoch=self.epoch,revision=self.revision,selection_key=selection_key)
    def reset(self):
        self.epoch+=1;self.revision+=1;self.dirty.clear();self.resources.clear()


class FakeHost:
    def __init__(self,bpy,counters):
        self.bpy=bpy;self.scene=bpy.context.scene;self.view_layer=bpy.context.view_layer
        self.counters=counters;self._residency=FakeResidency();self._residency_module=NS(identity=identity)
    def _main_thread(self):pass
    def _depsgraph(self):
        self.counters['depsgraph_reads']+=1
        return self.bpy.context.evaluated_depsgraph_get()
    def _scale(self):return float(self.scene.unit_settings.scale_length)
    def _sync_residency(self,*args):return True
    @staticmethod
    def object_id(obj):
        return 'blender:'+hashlib.sha256(json.dumps(['',obj.name],separators=(',',':')).encode()).hexdigest()
    @contextmanager
    def transaction(self):yield self


class SourceFixture:
    def __init__(self,case,total_vertices,unit_scale,mesh_world,rig_world):
        self.case=copy.deepcopy(case);self.packet=self.case['packet'];self.counters=Counter()
        self.unit_scale=unit_scale;self.mesh_world=Matrix(mesh_world);self.rig_world=Matrix(rig_world)
        ids=self.packet['vertex_ids'];self.indices=tuple(ids);self.total_vertices=max(total_vertices,max(ids)+1)
        self.native_vertices={};self.current_vertices={}
        to_mesh=rig_pose.multiply(rig_pose.inverse(self.mesh_world),self.rig_world)
        for index,rest,current,weights in zip(ids,self.packet['rest_vertices'],self.packet['current_vertices'],self.packet['weights']):
            memberships=[(i,float(w)) for i,w in enumerate(weights) if w]
            self.native_vertices[index]=Vertex(index,rig_pose.point(to_mesh,[v/unit_scale for v in rest]),memberships,self.counters,'rest')
            self.current_vertices[index]=Vertex(index,rig_pose.point(to_mesh,[v/unit_scale for v in current]),(),self.counters,'current')
        self.mesh_data=NS(session_uid=201,name='MeshData',
            vertices=IndexedVertices(self.total_vertices,self.native_vertices,self.counters,'rest'),
            polygons=ForbiddenTopology(2*self.total_vertices,self.counters),
            loop_triangles=ForbiddenTopology(2*self.total_vertices,self.counters),
            shape_keys=None,animation_data=None,library=None)
        self.current_data=NS(session_uid=202,
            vertices=IndexedVertices(self.total_vertices,self.current_vertices,self.counters,'current'))
        bones=NamedCollection()
        for source in self.packet['bone_chain']:
            parent=bones.get(source['parent']) if source['parent'] is not None else None
            bones.append(Bone(source['name'],parent,host_matrix(source['rest_matrix'],unit_scale),
                              host_matrix(source['pose_matrix'],unit_scale),self.counters))
        self.bones=bones
        self.rig=NS(name='Armature',name_full='Armature',type='ARMATURE',session_uid=102,
            matrix_world=self.rig_world,data=NS(session_uid=301,name='ArmatureData',bones=bones,pose_position='POSE'),
            pose=NS(bones=bones),constraints=[],modifiers=[],parent=None,animation_data=None,library=None,
            mode='OBJECT',is_evaluated=True)
        modifier=NS(type='ARMATURE',name='Armature',object=self.rig,use_vertex_groups=True,
            use_bone_envelopes=False,use_deform_preserve_volume=False,show_viewport=True,show_render=True,
            use_multi_modifier=False,vertex_group='',invert_vertex_group=False)
        self.mesh=NS(name='Mesh',name_full='Mesh',type='MESH',session_uid=101,matrix_world=self.mesh_world,
            data=self.mesh_data,modifiers=[modifier],constraints=[],parent=None,animation_data=None,
            library=None,mode='OBJECT',is_evaluated=True,vertex_groups=NamedCollection(
                [NS(name=bone.name,index=i) for i,bone in enumerate(bones)]))
        self.evaluated_mesh=NS(name='Mesh',type='MESH',is_evaluated=True,matrix_world=self.mesh_world,
            data=self.current_data,original=self.mesh)
        def evaluate_mesh(graph):
            self.counters['mesh_evaluated_get']+=1;return self.evaluated_mesh
        def evaluate_rig(graph):
            self.counters['rig_evaluated_get']+=1;return self.rig
        self.mesh.evaluated_get=evaluate_mesh;self.rig.evaluated_get=evaluate_rig
        self.graph=NS(updates=[],object_instances=[])
        layer=NS(objects=NS(active=self.mesh),update=lambda:None,depsgraph=self.graph)
        scene=NS(session_uid=1,name='LargeAsset',objects=NamedCollection([self.mesh,self.rig]),
            unit_settings=NS(scale_length=unit_scale,system='METRIC'),frame_current=1,frame_subframe=0.,view_layers=[layer])
        self.graph.scene_eval=NS(original=scene)
        self.bpy=NS(context=NS(scene=scene,view_layer=layer,evaluated_depsgraph_get=lambda:self.graph),
            data=NS(filepath='isolated_fake.blend'),app=NS(driver_namespace={}))
        self.host=FakeHost(self.bpy,self.counters)
        self.global_triangles=[[ids[i] for i in face] for face in self.packet['triangles']]
        self.selection=dict(mesh_name='Mesh',armature_name='Armature',bone_names=[bone.name for bone in bones],
            vertex_indices=list(ids),sections=[[ids[i] for i in section] for section in self.packet['sections']])

    def topology_reader(self,mesh,vertex_indices):
        self.counters['topology_reads']+=1
        assert mesh is self.mesh or mesh is self.mesh_data
        selected=set(vertex_indices)
        return [face[:] for face in self.global_triangles if all(i in selected for i in face)]

    def set_pose(self,packet):
        assert packet['vertex_ids']==self.packet['vertex_ids']
        transform=rig_pose.multiply(rig_pose.inverse(self.mesh_world),self.rig_world)
        for index,current in zip(self.indices,packet['current_vertices']):
            self.current_vertices[index].value=rig_pose.point(transform,[v/self.unit_scale for v in current])
        for bone,source in zip(self.bones,packet['bone_chain']):bone.pose=host_matrix(source['pose_matrix'],self.unit_scale)
        self.host.scene.frame_current+=1;self.host._residency.revision+=1
        self.graph.updates=[]

    def touch_geometry(self,kind='mesh'):
        target=self.rig.data if kind=='rig' else self.mesh_data
        key=identity(target);state=self.host._residency
        state.dirty[key]=state.dirty.get(key,0)+1;state.revision+=1;state.serial+=1

    def refresh_lbs(self):
        """Make changed fake native data consistent, using NumPy not source math.

        Raw storage values are used directly, so fixture preparation itself is
        excluded from the counted source-RNA reads.
        """
        import numpy as np
        relative=np.linalg.inv(np.asarray(self.rig_world))@np.asarray(self.mesh_world)
        inverse=np.linalg.inv(relative)
        transforms=[]
        for bone in self.bones:
            rest=np.asarray(bone.rest).copy();pose=np.asarray(bone.pose).copy()
            rest[:3,3]*=self.unit_scale;pose[:3,3]*=self.unit_scale
            transforms.append(pose@np.linalg.inv(rest))
        for index in self.indices:
            vertex=self.native_vertices[index]
            rest=(relative@np.r_[vertex.value,1.])[:3]*self.unit_scale
            current=np.zeros(3)
            for group,weight in vertex.memberships:
                if group<len(transforms):current+=weight*(transforms[group]@np.r_[rest,1.])[:3]
            self.current_vertices[index].value=(inverse@np.r_[current/self.unit_scale,1.])[:3].tolist()

    def replace_mesh(self):
        old=self.mesh;new=copy.copy(old);new.session_uid+=1000
        self.mesh=new;self.host.scene.objects[self.host.scene.objects.index(old)]=new
        self.evaluated_mesh.original=new
        self.host._residency.revision+=1
        return old,new

    def replace_rig(self):
        old=self.rig;new=copy.copy(old);new.session_uid+=1000
        self.rig=new;self.host.scene.objects[self.host.scene.objects.index(old)]=new
        self.mesh.modifiers[0].object=new
        self.host._residency.revision+=1
        return old,new

    def rebuild_epoch(self):self.host._residency.reset()


def build_fixture(case=None,total_vertices=1_000_000,unit_scale=1.,mesh_world=None,rig_world=None):
    if case is None:
        from verification.m6_arm_expert_001.synthetic import generate_dataset
        case=generate_dataset(split='train')[0]
    return SourceFixture(case,total_vertices,unit_scale,
                         unit_matrix() if mesh_world is None else mesh_world,
                         unit_matrix() if rig_world is None else rig_world)
