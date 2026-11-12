"""Small standalone scene residency and bridge resource-delta helpers."""
from copy import deepcopy
import math
import uuid
import weakref

PROTOCOL = 'human-eye-scene-delta-v1'


def _world_number_key(value):
    # Numeric equality merges +0.0/-0.0, although the unchanged forward map
    # can produce different IEEE signs. Keep that distinction in cached keys.
    return ('float_zero',value.hex()) if type(value) is float and value==0. else value


def identity(value):
    if value is None:return None
    uid=getattr(value,'session_uid',None)
    if type(uid) is int and uid:return ('uid',uid)
    pointer=getattr(value,'as_pointer',None)
    return ('ptr',int(pointer())) if callable(pointer) else ('python',id(value))


class SceneResidency:
    def __init__(self,bpy):
        self.instance_id=uuid.uuid4().hex;self.epoch=1;self.revision=0
        self.resources={};self.captures={};self.nearest={};self.by_object_id={};self.wire={}
        self.source_checks={}
        self.dirty={};self.serial=0;self.resource_serial=0;self.context=None;self.signature=None;self.callbacks=[]
        handlers=getattr(getattr(bpy,'app',None),'handlers',None)
        self.enabled=handlers is not None and hasattr(handlers,'depsgraph_update_post')
        if not self.enabled:return
        reference=weakref.ref(self)
        def updated(scene,graph):
            state=reference()
            if state is None:return
            for update in getattr(graph,'updates',()):
                state.serial+=1
                if bool(getattr(update,'is_updated_geometry',False)):
                    obj=getattr(update,'id',None);obj=getattr(obj,'original',obj)
                    key=identity(obj)
                    state.dirty[key]=state.dirty.get(key,0)+1
        def rebuilt(*args):
            state=reference()
            if state is not None:state.reset()
        persistent=getattr(handlers,'persistent',lambda fn:fn)
        for name,callback in [('depsgraph_update_post',updated),('undo_post',rebuilt),
                              ('redo_post',rebuilt),('load_post',rebuilt)]:
            target=getattr(handlers,name,None)
            if target is not None:
                callback=persistent(callback);target.append(callback);self.callbacks.append((target,callback))

    def close(self):
        for target,callback in self.callbacks:
            if callback in target:target.remove(callback)
        self.callbacks=[]

    def reset(self):
        self.epoch+=1;self.revision+=1
        self.resources.clear();self.captures.clear();self.nearest.clear();self.wire.clear()
        self.source_checks.clear()
        self.dirty.clear();self.context=None;self.signature=None

    def sync(self,context,signature,live):
        if self.context is not None and context!=self.context:self.reset()
        self.context=context
        current=(signature,self.serial)
        if current!=self.signature:
            self.revision+=1;self.signature=current;self.captures.clear();self.nearest.clear()
        self.resources={k:v for k,v in self.resources.items() if k in live}
        self.source_checks={k:v for k,v in self.source_checks.items() if k in live}
        self.dirty={k:v for k,v in self.dirty.items() if k in live}

    def token(self,selection_key):
        return dict(instance_id=self.instance_id,epoch=self.epoch,revision=self.revision,selection_key=selection_key)


def encode_capture(capture,known,bindings):
    """Only missing resource revisions cross the wire; metadata is always fresh."""
    scene=capture.get('capture',capture);state=scene.get('capture_state')
    if type(state) is not dict:return deepcopy(capture)
    compatible=(type(known) is dict and known.get('instance_id')==state['instance_id']
                and known.get('epoch')==state['epoch'] and type(known.get('resources')) is dict)
    have=known['resources'] if compatible else {}
    resources=[];meshes=[];sent=set()
    for mesh in scene['meshes']:
        binding=bindings.get(mesh['object_id'])
        if binding is None:return deepcopy(capture)
        resource,matrix,scale=binding
        rid=resource['resource_id'];revision=resource['revision']
        metadata={k:deepcopy(v) for k,v in mesh.items() if k not in ('vertices','faces','edges')}
        metadata['_scene_resource']=dict(id=rid,revision=revision,matrix=deepcopy(matrix),scale=scale)
        meshes.append(metadata)
        if have.get(rid)!=revision and rid not in sent:
            resources.append(dict(id=rid,revision=revision,vertices_local=deepcopy(resource['vertices_local']),
                                  faces=deepcopy(resource['faces']),edges=deepcopy(resource['edges'])))
            sent.add(rid)
    plain={k:deepcopy(v) for k,v in scene.items() if k!='meshes'};plain['meshes']=meshes
    payload={k:deepcopy(v) for k,v in capture.items() if k!='capture'} if 'capture' in capture else None
    if payload is not None:payload['capture']=plain
    else:payload=plain
    return dict(schema=PROTOCOL,capture=payload,resources=resources,
                live_resources=list({entry[0]['resource_id'] for entry in bindings.values()}))


class SceneDeltaDecoder:
    def __init__(self):
        self._state=None;self._resources={};self._world={}
        self._world_transforms=0;self._transformed_vertices=0

    def work_totals(self):
        """Cumulative coordinate work committed by successful complete packets."""
        return dict(world_transforms=self._world_transforms,transformed_vertices=self._transformed_vertices)

    def baseline(self):
        if self._state is None:return None
        return dict(instance_id=self._state['instance_id'],epoch=self._state['epoch'],
                    resources={key:value['revision'] for key,value in self._resources.items()})

    def apply(self,packet):
        try:return self._apply(packet)
        except (KeyError,TypeError,IndexError,OverflowError) as exc:
            raise ValueError('malformed_scene_delta_packet') from exc

    def _apply(self,packet):
        if type(packet) is not dict:raise ValueError('scene_delta_packet_object')
        if packet.get('schema')!=PROTOCOL:
            self._state=None;self._resources={};self._world={}
            return deepcopy(packet)
        payload=deepcopy(packet['capture']);scene=payload.get('capture',payload);state=scene.get('capture_state')
        if (type(state) is not dict or type(state.get('instance_id')) is not str
                or any(type(state.get(k)) is not int or state[k]<0 for k in ('epoch','revision'))
                or type(state.get('selection_key')) is not str):raise ValueError('scene_delta_state')
        same=self._state is not None and all(self._state[k]==state[k] for k in ('instance_id','epoch'))
        resources=dict(self._resources) if same else {}
        # Existing cache entries are immutable. Stage replacements privately so
        # a later missing/invalid mesh cannot publish a partial new baseline.
        world=dict(self._world) if same else {}
        replaced=set()
        for resource in packet['resources']:
            if (type(resource) is not dict or type(resource.get('id')) is not str
                    or type(resource.get('revision')) is not int or resource['revision']<1):raise ValueError('scene_delta_resource')
            resources[resource['id']]=deepcopy(resource)
            replaced.add(resource['id'])
        live=packet.get('live_resources')
        if type(live) is not list or any(type(k) is not str for k in live):raise ValueError('scene_delta_live_resources')
        live=set(live)
        resources={key:value for key,value in resources.items() if key in live}
        world={key:value for key,value in world.items() if key[0] in live and key[0] not in replaced}
        vertices=faces=0
        used=set();touched=set();world_transforms=transformed_vertices=0
        for mesh in scene['meshes']:
            reference=mesh.pop('_scene_resource');resource=resources.get(reference['id'])
            if resource is None or resource['revision']!=reference['revision']:raise ValueError('scene_delta_missing_resource')
            local=resource['vertices_local'];matrix=reference['matrix'];scale=reference['scale']
            vertices+=len(local);faces+=len(resource['faces'])
            if vertices>500000 or faces>1000000:raise ValueError('scene_delta_geometry_budget')
            key=(reference['id'],reference['revision'],
                 tuple(tuple(_world_number_key(value) for value in row) for row in matrix),_world_number_key(scale))
            cached=world.get(key)
            if cached is None:
                cached=tuple(tuple((sum(matrix[r][c]*p[c] for c in range(3))+matrix[r][3])*scale
                                   for r in range(3)) for p in local)
                if any(not math.isfinite(v) for p in cached for v in p):raise ValueError('scene_delta_nonfinite_geometry')
                world[key]=cached;world_transforms+=1;transformed_vertices+=len(local)
            used.add(key);touched.add(reference['id'])
            mesh['vertices']=[list(point) for point in cached]
            mesh['faces']=[list(face) for face in resource['faces']];mesh['edges']=[list(edge) for edge in resource['edges']]
        # Retain other live selections, but discard obsolete poses of resources
        # present in this packet instead of accumulating their motion history.
        world={key:value for key,value in world.items() if key[0] not in touched or key in used}
        self._state=deepcopy(state);self._resources=resources;self._world=world
        self._world_transforms+=world_transforms;self._transformed_vertices+=transformed_vertices
        return payload
