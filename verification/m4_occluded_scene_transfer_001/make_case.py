"""Generate one analytic CAPTURE_REPLAY layout without product or raster calls."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SHARED = HERE.with_name('m4_complete_witness_consumption_001') / 'make_case.py'
spec = importlib.util.spec_from_file_location('_transfer_frozen_camera_arithmetic', SHARED)
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
ORDER = shared.ORDER
DIRECTIONS = shared.DIRECTIONS
SIZE = shared.SIZE
publish = shared.publish
cameras_from_scene = shared.cameras_from_scene

BOX_TRIANGLES = [[0,3,2],[0,2,1],[4,5,6],[4,6,7],
                 [0,1,5],[0,5,4],[1,2,6],[1,6,5],
                 [2,3,7],[2,7,6],[3,0,4],[3,4,7]]
FACE_NAMES = ('bottom','top','front','right','back','left')


def box(name, center, half, axes=((1,0,0),(0,1,0),(0,0,1))):
    vertices = []
    for a,b,c in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                  (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)):
        vertices.append([center[k] + a*half[0]*axes[0][k]
                         + b*half[1]*axes[1][k] + c*half[2]*axes[2][k]
                         for k in range(3)])
    return dict(name=name,vertices=vertices,triangles=BOX_TRIANGLES)


def fixed_scene():
    objects = [
        box('RackBase',(0,0,-.25),(7,6,.25)),
        box('RackRoof',(0,0,6.25),(7,6,.25)),
        box('LeftUpright',(-6.5,0,3),(.5,5.5,3)),
        box('RightUpright',(6.5,0,3),(.5,5.5,3)),
        box('LowerRearUnit',(-3,1.5,1.5),(1.25,1.25,1)),
        box('UpperRearUnit',(0,2,4.25),(1.25,1,1)),
        box('FrontRightUnit',(2,-2,2.25),(1.25,1.25,1.5)),
        box('LowerFrontRail',(0,-5.25,1.5),(5.5,.25,.25)),
        box('UpperFrontRail',(0,-5.25,4.25),(5.5,.25,.25)),
        box('TurnedUnit',(-2.5,-2,4),(.75,.5,.75),
            ((.75,1,0),(-1,.75,0),(0,0,1))),
    ]
    center=(8,-7,9.5)
    u=(.375,.5,0)
    v=(-.25,.1875,.3125)
    objects.append(dict(name='SlantedIndicator',
        vertices=[[center[k]+a*u[k]+b*v[k] for k in range(3)]
                  for a,b in ((-1,-1),(1,-1),(1,1),(-1,1))],
        triangles=[[0,1,2],[0,2,3]]))
    objects.append(dict(name='ConnectedLBracket',
        vertices=[[7.5,2,3],[9.5,2,3],[9.5,2.5,3],
                  [8,2.5,3],[8,4,3],[7.5,4,3]],
        triangles=[[0,1,3],[1,2,3],[0,3,5],[3,4,5]]))
    return dict(objects=objects)


def synthetic_capture(scene):
    capture=shared.synthetic_capture(scene)
    instances={}
    for i,mesh in enumerate(capture['meshes']):
        mesh['object_id']='blender:'+shared.digest(['occluded-scene-transfer-001',mesh['name']])
        instances[mesh['object_id']]='synthetic-instance-'+str(i+1)
    capture['host_identity']['object_instances']=instances
    capture['replay_provenance']['origin']='fixed_binary_exact_rational_device_rack'
    return capture


def projected_sample(pose, world):
    import numpy as np
    point=np.array([*world,1.],dtype=np.float64)
    clip=np.asarray(pose['projection_matrix']) @ np.asarray(pose['view_matrix']) @ point
    screen=[(clip[0]/clip[3]+1)*255.5,(1-clip[1]/clip[3])*255.5]
    # Raster samples integer index + .5. Round to nearest sample center.
    return [int(round(value-.5)) for value in screen]


def task_points(cameras):
    by_name={row['name']:row for row in cameras['views']}
    return [dict(id='sample_A',view_name='TOP',
                 **dict(zip(('x','y'),projected_sample(by_name['TOP'],(-3,2,6.5))))),
            dict(id='sample_B',view_name='LEFT',
                 **dict(zip(('x','y'),projected_sample(by_name['LEFT'],(-7,0,-.25)))))]


def main():
    output=HERE/'inputs'
    output.mkdir(parents=True,exist_ok=True)
    scene=fixed_scene()
    cameras=cameras_from_scene(scene)
    capture=synthetic_capture(scene)
    points=task_points(cameras)
    targets=[dict(id='target_C',object_name='RackBase',object_index=0,source_triangle_indices=[2,3]),
             dict(id='target_D',object_name='RackBase',object_index=0,source_triangle_indices=[0,1])]
    files=[publish(output/'SCENE_GEOMETRY_RATIONAL.json',scene),
           publish(output/'CAMERAS.json',cameras),
           publish(output/'CAPTURE_REPLAY.json',capture),
           publish(output/'TASK_INPUTS.json',dict(schema='occluded-transfer-task-inputs-v1',
             pixel_samples=points,source_targets=targets,pixel_origin='zero-based upper-left'))]
    registration=dict(schema='occluded-transfer-case-inputs-v1',single_case=True,
        generator_path=str(Path(__file__).resolve()),
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        shared_camera_arithmetic_path=str(SHARED),
        shared_camera_arithmetic_sha256=hashlib.sha256(SHARED.read_bytes()).hexdigest(),
        python_executable=sys.executable,numpy_version=shared.np.__version__,
        objects=len(scene['objects']),vertices=sum(len(o['vertices']) for o in scene['objects']),
        source_triangles=sum(len(o['triangles']) for o in scene['objects']),
        view_names=list(ORDER),size_px=[SIZE,SIZE],files=files,
        geometry_numeric_encoding='All source JSON numbers are exact binary64 rationals in world metres.',
        capture_provenance='Synthetic CAPTURE_REPLAY. No Blender process used.',
        actual_product_calls=0,actual_raster_calls=0,actual_model_calls=0,actual_Blender_calls=0)
    publish(output/'CASE_INPUT_REGISTRATION.json',registration)
    print(json.dumps(registration))

if __name__=='__main__':
    main()
