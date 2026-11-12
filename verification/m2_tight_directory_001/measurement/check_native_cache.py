"""Finite fake-handler checks of the actual native cache code, no Blender."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS

HERE = Path(__file__).resolve().parent


class Vertices:
    def __init__(self):
        self.values = [[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]
    def __len__(self):
        return len(self.values)
    def foreach_get(self,field,output):
        assert field=='co'
        output[:] = [value for point in self.values for value in point]


class MeshObject:
    def __init__(self,name,uid):
        self.session_uid = uid
        self.name = self.name_full = name
        self.type = 'MESH'
        self.is_evaluated = True
        self.matrix_world = [[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
        self.data = NS(session_uid=uid+1000,vertices=Vertices(),polygons=[(0,1,2)])
    def evaluated_get(self,graph):
        return self
    def to_mesh(self):
        return self.data
    def to_mesh_clear(self):
        pass


def run():
    handlers = NS(depsgraph_update_post=[],undo_post=[],redo_post=[],load_post=[],persistent=lambda fn:fn)
    obj = MeshObject('ordinary',10)
    scene = NS(session_uid=100,objects=[obj],unit_settings=NS(scale_length=1.,system='METRIC',length_unit='METERS'),
               frame_current=1,frame_subframe=0.)
    graph = NS(updates=[],object_instances=[])
    bpy = NS(app=NS(handlers=handlers),data=NS(filepath='owned.blend'),
             context=NS(scene=scene,view_layer=NS(session_uid=200),evaluated_depsgraph_get=lambda:graph))
    namespace = {'bpy':bpy,'__name__':'_m2_native_cache_fake'}
    for name in ('reused/scene_residency.py','native_directory.py'):
        exec(compile((HERE/name).read_bytes(),str(HERE/name),'exec'),namespace)
    checks = []
    def read(label,expected_hit):
        result = namespace['_m2_native_directory']()
        work = namespace['_m2_native_last_work']
        assert work['directory_cache_hits']==expected_hit,(label,work)
        for row,current in zip(result['objects'],sorted(bpy.context.scene.objects,key=lambda item:item.name)):
            scale = bpy.context.scene.unit_settings.scale_length
            points = [[(sum(current.matrix_world[axis][column]*point[column] for column in range(3))
                        +current.matrix_world[axis][3])*scale for axis in range(3)] for point in current.data.vertices.values]
            assert row['bbox_min']==[min(point[axis] for point in points) for axis in range(3)]
            assert row['bbox_max']==[max(point[axis] for point in points) for axis in range(3)]
            assert row['name']==current.name
        checks.append({'case':label,'passed':True,'cache_hit':expected_hit,'work':work})
    read('cold',0)
    read('unchanged',1)
    obj.matrix_world[0][3] = .25
    read('pose',0)
    obj.data.vertices.values[1][0] += .125
    graph.updates = [NS(is_updated_geometry=True,id=obj.data)]
    for callback in handlers.depsgraph_update_post:
        callback(scene,graph)
    read('geometry_same_vertex_count_notification',0)
    graph.updates = []
    scene.unit_settings.scale_length = .5
    read('units',0)
    scene.frame_current = 2
    read('frame',0)
    scene.frame_subframe = .25
    read('subframe',0)
    obj.name = obj.name_full = 'renamed'
    read('rename',0)
    scene.objects = [MeshObject('renamed',11)]
    read('delete_same_name_replacement',0)
    for kind in ('undo_post','redo_post','load_post'):
        for callback in getattr(handlers,kind):
            callback(scene)
        read(kind,0)
    bpy.context.scene = NS(**vars(scene))
    bpy.context.scene.session_uid = 101
    read('switch_scene',0)
    read('new_scene_unchanged',1)
    namespace['_m2_native_state'].enabled = False
    read('notifications_unavailable_fresh_read',0)
    read('notifications_unavailable_repeat_fresh_read',0)
    return {'passed':True,'checks':checks,
            'scope':'actual native function and reused SceneResidency, fake bpy notifications; actual Blender all-event native invalidation unmeasured',
            'sources':{name:hashlib.sha256((HERE/name).read_bytes()).hexdigest()
                       for name in ('native_directory.py','reused/scene_residency.py','check_native_cache.py')}}


if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = run()
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed':True,'checks':len(result['checks'])}))
