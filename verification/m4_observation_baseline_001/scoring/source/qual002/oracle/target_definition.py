"""Independent QUAL002 target predicates from frozen QUAL001 world triangles.

No scene build, HumanEye imports, old nearest-rail selection, or pair-oracle run.
The private IDs below are derived outputs, not intent labels or input answers.
"""
from collections import Counter, defaultdict
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path


def need(value,message):
    if not value:
        raise ValueError(message)


def exact(value):
    return {'numerator':str(value.numerator),'denominator':str(value.denominator),'float':float(value)}


def cross(a,b):
    return a[0]*b[1]-a[1]*b[0]


def inside_triangle(p,tri):
    sides=[cross((b[0]-a[0],b[1]-a[1]),(p[0]-a[0],p[1]-a[1]))
           for a,b in zip(tri,tri[1:]+tri[:1])]
    return all(v>=0 for v in sides) or all(v<=0 for v in sides)


def closed_mesh(row):
    edges=Counter();directed=Counter()
    for face in row['triangles']:
        need(len(face)==3 and len(set(face))==3,'invalid original triangle')
        for a,b in zip(face,face[1:]+face[:1]):
            edges[tuple(sorted((a,b)))]+=1
            directed[a,b]+=1
    need(all(v==2 for v in edges.values()),'source mesh not closed')
    need(all(directed[a,b]==directed[b,a]==1 for a,b in edges),'inconsistent source winding')


def hollow_profile(row,axis):
    vertices=row['_vertices'];axes=[k for k in range(3) if k!=axis]
    levels=[sorted(set(p[k] for p in vertices)) for k in range(3)]
    if len(levels[axis])!=2 or any(len(levels[k])!=4 for k in axes):
        return False
    closed_mesh(row)
    for level in levels[axis]:
        triangles=[]
        for face in row['triangles']:
            points=[vertices[i] for i in face]
            if all(p[axis]==level for p in points):
                tri=[tuple(p[k] for k in axes) for p in points]
                need(cross((tri[1][0]-tri[0][0],tri[1][1]-tri[0][1]),
                           (tri[2][0]-tri[0][0],tri[2][1]-tri[0][1]))!=0,'degenerate cap')
                triangles.append(tri)
        occupancy=[]
        for i in range(3):
            for j in range(3):
                p=((levels[axes[0]][i]+levels[axes[0]][i+1])/2,
                   (levels[axes[1]][j]+levels[axes[1]][j+1])/2)
                if any(inside_triangle(p,tri) for tri in triangles):
                    occupancy.append((i,j))
        need(set(occupancy)=={(i,j) for i in range(3) for j in range(3)}-{(1,1)},
             'cap grid does not identify rectangular open-hole profile')
    return True


def shape_commit(row):
    payload={'data':row['data'],'local_vertices':row['local_vertices'],'triangles':row['triangles']}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),
                                     allow_nan=False).encode('utf8')).hexdigest()


def main():
    here=Path(__file__).resolve().parent
    fixes=here.parent.parent
    old=fixes/'20261103_spatial_perception_qual001'
    source=old/'admin'/'world_geometry.json'
    blob=source.read_bytes();document=json.loads(blob)
    need(document['schema']=='world-geometry-v1' and document['unit']=='m'
         and document['coordinate_frame']=='world','frozen world-metre geometry required')
    scene_sha=hashlib.sha256((old/'shared'/'scene.blend').read_bytes()).hexdigest()
    need(scene_sha==document['source_sha256'],'export does not bind actual frozen scene')
    rows=document['objects'];groups=defaultdict(list)
    for row in rows:
        row['_vertices']=[tuple(F(v) for v in p) for p in row['world_vertices']]
        row['_bounds']=[(min(p[k] for p in row['_vertices']),max(p[k] for p in row['_vertices'])) for k in range(3)]
        row['_center']=tuple((a+b)/2 for a,b in row['_bounds'])
        groups[row['data']].append(row)
    frame_groups=[group for group in groups.values() if len(group)==4
                  and all(hollow_profile(row,1) for row in group)]
    need(len(frame_groups)==1,'same-mesh four-frame candidate group not unique')
    frames=frame_groups[0]
    need(len({shape_commit(row) for row in frames})==1,'candidate group not actually identical local triangles')
    rail_groups=[group for group in groups.values() if len(group)==2
                 and all(hollow_profile(row,0) for row in group)]
    need(len(rail_groups)==1,'two same-mesh X-extruded hollow rails not unique')
    rails=sorted(rail_groups[0],key=lambda row:row['_center'][2])
    need(rails[0]['_center'][2]<rails[1]['_center'][2],'rails have no strict lower/upper order')
    beams=[];pipes=[]
    for row in rows:
        widths=[b-a for a,b in row['_bounds']]
        levels=[len(set(p[k] for p in row['_vertices'])) for k in range(3)]
        if levels==[2,2,2] and len(row['_vertices'])==8 and len(row['triangles'])==12 and widths[0]>=10*max(widths[1:]):
            closed_mesh(row);beams.append(row)
        if levels[2]==2 and widths[2]>4*max(widths[:2]):
            caps=[{(p[0],p[1]) for p in row['_vertices'] if p[2]==level}
                  for level in sorted(set(p[2] for p in row['_vertices']))]
            if len(caps[0])==12 and caps[0]==caps[1]:
                radii=[(x-row['_center'][0])**2+(y-row['_center'][1])**2 for x,y in caps[0]]
                if min(radii)>0 and max(radii)<=min(radii)*F(101,100):
                    closed_mesh(row);pipes.append(row)
    need(len(beams)==2,'two thin solid X crossbeams required by fixed fixture domain')
    beam=min(beams,key=lambda row:row['_center'][1])
    need(sum(row['_center'][1]==beam['_center'][1] for row in beams)==1,'frontmost crossbeam ambiguous')
    need(len(pipes)==2,'dual long vertical 12-gon pipe axes not unique')
    middle_z=(rails[0]['_center'][2]+rails[1]['_center'][2])/2
    rear_y=beam['_bounds'][1][1]
    pipe_mid=tuple(sum(row['_center'][k] for row in pipes)/2 for k in (0,1))
    radius=F(7,10)
    evaluations=[];sets=[set(),set(),set()]
    for row in sorted(frames,key=lambda row:row['object_id']):
        c=row['_center'];distance2=sum((c[k]-pipe_mid[k])**2 for k in (0,1))
        passed=[c[2]<middle_z,c[1]>rear_y,distance2<=radius**2]
        for index,accepted in enumerate(passed):
            if accepted:
                sets[index].add(row['object_id'])
        evaluations.append({'object_id':row['object_id'],'shared_mesh_data':row['data'],
            'bbox_center_world_m':[float(v) for v in c],
            'predicates':{'lower_band':passed[0],'behind_front_crossbeam':passed[1],'dual_pipe_XY_neighborhood':passed[2]},
            'center_Z_below_midplane_margin_m':exact(middle_z-c[2]),
            'center_Y_behind_rear_surface_margin_m':exact(c[1]-rear_y),
            'pipe_midpoint_XY_distance_squared_m2':exact(distance2),
            'pipe_midpoint_XY_distance_m':math.sqrt(float(distance2)),
            'radius_squared_minus_distance_squared_m2':exact(radius**2-distance2)})
    all_ids={row['object_id'] for row in frames}
    intersection=set.intersection(*sets)
    ablations=[set.intersection(*(sets[j] for j in range(3) if j!=i)) for i in range(3)]
    each_rejects=[all_ids-group for group in sets]
    need(len(intersection)==1,'three predicates fail to identify one target')
    need(all(len(group)>=2 for group in ablations),'a predicate is redundant: ablation remains unique')
    need(all(len(group)==1 for group in each_rejects) and len(set.union(*each_rejects))==3,
         'predicates do not each reject a different distractor')
    public_text=('从共享同一网格数据的四个同形通孔框架中找出同时满足以下三个条件的目标。'
        '中心均指世界轴对齐几何包围盒中心，单位为米；X为左右、Z为上下，前方为Y减小、后方为Y增大。\n'
        '1. 下部带：框架中心Z严格小于下、上两根空心导轨中心Z的平均值。\n'
        '2. 前横梁后方：框架中心Y严格大于最前方实心细横梁的后表面Y，也就是该横梁的最大Y。\n'
        '3. 双管水平邻域：框架中心的XY位置，到两根长竖直圆管轴线XY位置中点的欧氏距离不超过0.70米。\n'
        '这三个条件必须同时满足；不要用“离下导轨最近”替代第1项。')
    names=['lower_band','behind_front_crossbeam','dual_pipe_XY_neighborhood']
    result={'schema':'private-target-candidate-certificate-v1','task_id':'SPATIAL-PERCEPTION-QUAL-002',
        'source':{'kind':'unchanged QUAL001 final world geometry; independent predicate-only audit',
            'path':str(source.resolve()),'world_geometry_sha256':hashlib.sha256(blob).hexdigest(),
            'scene_sha256':scene_sha,'unit':'m','coordinate_frame':'world',
            'oracle_implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'no_builder_roles_or_old_oracle_answers_read':True,'scene_unchanged':True},
        'reference_identification':{'private_ids_are_derived_from_final_geometry_not_intent_labels':True,
            'candidate_rule':'unique shared mesh-data group of four identical local triangle meshes; Y extrusion cap grid identifies rectangular through holes',
            'candidate_mesh_data':frames[0]['data'],'candidate_ids':sorted(all_ids),
            'candidate_local_shape_commitment':shape_commit(frames[0]),
            'rail_rule':'unique same-data group of two X-extruded hollow rectangular profiles; ordered by geometric centerZ',
            'lower_rail_id':rails[0]['object_id'],'upper_rail_id':rails[1]['object_id'],
            'beam_rule':'frontmost of two closed 8-vertex/12-triangle axis boxes whose X span is at least 10 times both transverse spans',
            'front_crossbeam_id':beam['object_id'],
            'pipe_rule':'two closed long Z extrusions with identical 12-point cap footprints and nearly constant axis radius; Z span >4 times each transverse span',
            'dual_pipe_ids':sorted(row['object_id'] for row in pipes)},
        'predicate_constants':{'lower_upper_rail_Z_midplane_m':exact(middle_z),
            'front_crossbeam_rear_surface_Y_m':exact(rear_y),
            'dual_pipe_axis_XY_midpoint_m':[exact(v) for v in pipe_mid],
            'horizontal_neighborhood_radius_m':exact(radius),
            'distance_uses_XY_only':True,'lower_band_is_not_nearest_rail':True},
        'candidate_evaluations':evaluations,
        'predicate_pass_sets':{name:sorted(group) for name,group in zip(names,sets)},
        'distinct_single_predicate_rejections':{name:sorted(group) for name,group in zip(names,each_rejects)},
        'full_intersection':sorted(intersection),'target_id':next(iter(intersection)),
        'leave_one_out':{name:{'remaining_candidates':sorted(group),'count':len(group)} for name,group in zip(names,ablations)},
        'status':'three_predicates_necessary_and_jointly_unique_on_frozen_candidates',
        'public_task_text_zh':public_text,
        'scope_limits':['only target definition and candidate-set ablation; three pair-relation facts not rerun or changed',
            '0.70m is an explicit broad horizontal qualification circle, not an unstated perceptual meaning of near',
            'candidate-set necessity does not prove cognitive difficulty, image usefulness, HumanEye advantage, or task speed',
            'cap-grid recognition binds this controlled frozen fixture; not a general asset admission algorithm']}
    out=here/'TARGET_CANDIDATE_CERTIFICATE.json'
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'status':result['status'],'target_id':result['target_id'],
        'pass_sets':result['predicate_pass_sets'],'leave_one_out':result['leave_one_out'],
        'output':str(out.resolve())},ensure_ascii=False))


if __name__=='__main__':
    main()
