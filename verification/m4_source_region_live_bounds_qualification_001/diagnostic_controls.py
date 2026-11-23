"""Focused offline checks for the frozen host diagnostic and its cleanup."""

from hashlib import sha256
from itertools import product
import json
import math
from pathlib import Path
import sys
import time
from types import SimpleNamespace as Row

HERE = Path(__file__).resolve().parent
INSTALL = Path('D:/he_m1_m2_source_region_scoped_measurement_001/candidate_install/product')
DEPENDENCIES = 'D:/he_anchor_001/venv/Lib/site-packages'
OUT = Path('D:/he_m4_source_region_live_bounds_qualification_001/preflight/HOST_CONTROLS.json')
sys.path[:0] = [str(HERE), str(INSTALL), DEPENDENCIES]

import diagnostic
import numpy
from human_eye_plugin.blender_host import BlenderSceneHost, _acquisition_bounds, __file__ as host_file


IDENTITY = [[1.,0.,0.,0.], [0.,1.,0.,0.], [0.,0.,1.,0.], [0.,0.,0.,1.]]


def fake_mesh(coords):
    return Row(vertices=[Row(co=point) for point in coords], loops=[0,1,2],
               polygons=[Row(loop_start=0, loop_total=3)], loop_triangles=[Row(vertices=[0,1,2])],
               calc_loop_triangles=lambda: None)


class Evaluated:
    def __init__(self, matrix, geometry, *, fail=False):
        self.is_evaluated = True
        self.matrix_world = matrix
        self.data = fake_mesh(geometry)
        self.bound_box = list(product(*[(min(p[i] for p in geometry),max(p[i] for p in geometry))
                                       for i in range(3)]))
        self.events = []
        self.fail = fail

    def to_mesh(self):
        self.events.append('to_mesh')
        if self.fail:
            return fake_mesh([[math.nan,0.,0.],[1.,1.,1.],[2.,2.,2.]])
        return self.data

    def to_mesh_clear(self):
        self.events.append('to_mesh_clear')


class Object:
    def __init__(self, name, uid, evaluated, hidden=False):
        self.name = name
        self.type = 'MESH'
        self.session_uid = uid
        self._eval = evaluated
        self.data = evaluated.data
        self.hide_viewport = self.hide_render = hidden
        self.gets = []

    def visible_get(self, *, view_layer):
        return not self.hide_viewport

    def hide_get(self, *, view_layer):
        return self.hide_viewport

    def evaluated_get(self, graph):
        self.gets.append(graph)
        return self._eval


def finite_axis_and_mixed_checks():
    events = []
    points = [[0.,0.,0.],[1.,1.,0.],[1.,0.,1.]]
    mixed = [row[:] for row in IDENTITY]
    mixed[0][1] = .125
    objects = [Object('TargetA',10,Evaluated(IDENTITY,points)),
               Object('TargetB',11,Evaluated(mixed,points)),
               Object('Reference',12,Evaluated(IDENTITY,points),hidden=True)]
    graph = Row(object_instances=[],updates=[])
    layer = Row(name='sample-layer',depsgraph=graph,update=lambda:events.append('update'))
    scene = Row(name='sample-scene',session_uid=99,objects=objects,view_layers=[layer],
                frame_current=1,frame_subframe=0.,unit_settings=Row(scale_length=1.,system='METRIC',length_unit='METERS'))
    mock_bpy = Row(context=Row(scene=scene,view_layer=layer),app=Row(driver_namespace={}),
                   data=Row(filepath='OFFLINE_READ_FIXTURE'))
    host = BlenderSceneHost(mock_bpy)
    queries = [{'mode':'source_region','region':{'object':{'name':name},
                       'world_box_m':{'min':[-1.,-1.,-1.], 'max':[2.,2.,2.]}},
                'reference':{'name':'Reference'}, 'requested_facts':['surface_proximity']}
               for name in ('TargetA','TargetB')]
    packet = diagnostic.diagnose(host,queries,time.perf_counter_ns()+10**10)
    assert packet['prepost_equal'] and events==['update'] and all(all(g is graph for g in obj.gets) for obj in objects)
    output = {row['name']:row for row in packet['objects']}
    assert output['TargetA']['tight_candidate_world']==[[0.,0.,0.],[1.,1.,1.]]
    assert output['TargetB']['tight_fallback_reason']=='mixed_world_axis_binary64'
    assert output['Reference']['display']['visible_get'] is False
    assert output['Reference']['static_directory']['eligible'] is True
    a,b=(packet['work'][key] for key in ('point_only_fallback','full_vertex_truth_and_target_faces'))
    assert a['to_mesh_allocations']==a['to_mesh_clear']==1 and a['triangulations']==0
    assert b['to_mesh_allocations']==b['to_mesh_clear']==3 and b['triangulations']==2
    assert all(len(t['source_triangle_indices'])==1 for t in packet['queries'])
    assert objects[1]._eval.events==['to_mesh','to_mesh_clear','to_mesh','to_mesh_clear']
    return {'passed':True,'graph_updates':events,'truth_allocations':b['to_mesh_allocations'],
            'point_only_fallback_triangulations':a['triangulations'],'hidden_drawn':False}


def malformed_vertex_cleans_up():
    evaluated=Evaluated(IDENTITY,[[0.,0.,0.],[1.,1.,0.],[1.,0.,1.]],fail=True)
    tally=diagnostic.fresh_tally()
    try:
        diagnostic.capture_vertices(evaluated,IDENTITY,1.,lambda:None,tally,target=True)
    except ValueError as error:
        assert str(error)=='diagnostic_nonfinite_local_vertex'
    else:
        raise AssertionError('nonfinite_vertex_after_allocation_not_rejected')
    assert evaluated.events==['to_mesh','to_mesh_clear']
    assert tally['to_mesh_attempts']==tally['to_mesh_allocations']==tally['to_mesh_clear']==tally['clear_attempts']==1
    assert tally['triangulations']==0
    return {'passed':True,'calls':evaluated.events,'counter':tally,'failure':'diagnostic_nonfinite_local_vertex'}


def signed_zero_ambiguity():
    minimum=math.ulp(0.)
    corners=list(product((-minimum,minimum),(1.,2.),(1.,2.)))
    candidate,axes,reason=diagnostic.direct_bounds(corners,IDENTITY,.5,_acquisition_bounds(corners,IDENTITY,.5))
    assert candidate is None and axes==[[0],[1],[2]] and reason=='zero_plateau_sign_needs_ordered_world_scan'
    points=[diagnostic.world_point(IDENTITY,p,.5) for p in [[-minimum,1.,1.],[minimum,2.,2.]]]
    assert diagnostic.bounds_bits(points)[0][0]=='8000000000000000'
    assert diagnostic.bounds_bits(points)[1][0]=='0000000000000000'
    old=numpy.asarray(points,dtype='float64')
    old_bounds=diagnostic.bounds_bits([list(old.min(axis=0)),list(old.max(axis=0))])
    return {'passed':True,'world_point_bits':diagnostic.bounds_bits(points),'old_numpy_reduction_bits':old_bounds,
            'fallback_reason':reason}


def main():
    path=Path(host_file).resolve()
    assert path.is_relative_to(INSTALL)
    result={'passed':True,'scope':'offline actual installed host implementation with fake RNA only',
            'diagnostic_sha256':sha256((HERE/'diagnostic.py').read_bytes()).hexdigest(),
            'installed_host_sha256':sha256(path.read_bytes()).hexdigest(),
            'tests':{'same_window_and_allocations':finite_axis_and_mixed_checks(),
                     'nonfinite_vertex_cleanup':malformed_vertex_cleans_up(),
                     'signed_zero_ordered_fallback':signed_zero_ambiguity()},
            'live_Blender':0,'models':0,'builds':0}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open('x',encoding='utf8',newline='\n') as file:
        json.dump(result,file,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)
        file.write('\n')
    print(result['diagnostic_sha256'],len(result['tests']))


if __name__=='__main__':
    main()
