"""Find one exact current-camera selected centroid visible without hidden Cube.

No raster or live process. Floating projected candidates are prefiltered, then
the first three possible positives are independently checked with Fraction.
"""
from collections import Counter
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.path.insert(0,'D:/he_anchor_001/venv/Lib/site-packages')
import numpy as np

OUT=Path(__file__).resolve().parent
ROOT=Path('D:/he_m4_real_asset_region_001/sessions/main')
SRC=ROOT/'SOURCE_initial.json'
ARM=Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m4_real_asset_region_qualification_001/inputs/ARM_REGION.json')
FULL=ROOT/'product_full/call_001/SERVICE_RESULT.json'


def read(path):return json.loads(path.read_bytes())
def dot(a,b):return sum(x*y for x,y in zip(a,b))


def main():
    source,arm,full=read(SRC),read(ARM),read(FULL)
    body=next(o for o in source['objects'] if o['name']==arm['object_name'])
    vertices=[]
    for p in body['evaluated']['vertices']:
        vertices.append([(((row[0]*p[0]+row[1]*p[1])+row[2]*p[2])+row[3])*source['unit_scale']
                         for row in body['matrix_world'][:3]])
    faces=np.asarray(body['evaluated']['triangles'],dtype=np.int64)
    pose=full['frames'][0]['pose']
    basis=np.asarray(pose['view_matrix'],dtype=np.float64)[:3,:3]
    projected=np.asarray(vertices,dtype=np.float64)@basis.T
    triangles=projected[faces]
    low,high=triangles[:,:,:2].min(axis=1),triangles[:,:,:2].max(axis=1)
    selected=arm['source_triangle_ids']
    possible=[]
    blocked=0
    for fi in selected:
        center=triangles[fi].mean(axis=0)
        indices=np.flatnonzero(np.all(low-1e-12<=center[:2],axis=1)&np.all(high+1e-12>=center[:2],axis=1))
        a,b,c=np.moveaxis(triangles[indices],1,0)
        u,v=b[:,:2]-a[:,:2],c[:,:2]-a[:,:2]
        q=center[:2]-a[:,:2]
        det=u[:,0]*v[:,1]-u[:,1]*v[:,0]
        usable=np.abs(det)>1e-18
        s=np.divide(q[:,0]*v[:,1]-q[:,1]*v[:,0],det,out=np.zeros_like(det),where=usable)
        t=np.divide(u[:,0]*q[:,1]-u[:,1]*q[:,0],det,out=np.zeros_like(det),where=usable)
        z=a[:,2]+s*(b[:,2]-a[:,2])+t*(c[:,2]-a[:,2])
        nearer=usable&(s>=-1e-10)&(t>=-1e-10)&(s+t<=1+1e-10)&(z>center[2]+1e-10)
        if np.any(nearer):blocked+=1
        else:possible.append(fi)
    exact_basis=[tuple(map(F,row[:3])) for row in pose['view_matrix'][:3]]
    exact_vertices=[tuple(map(F,p)) for p in vertices]
    exact_projected=[tuple(dot(p,axis) for axis in exact_basis) for p in exact_vertices]
    exact_boxes=[]
    for face in faces:
        pts=[exact_projected[int(i)] for i in face]
        exact_boxes.append(tuple((min(p[k] for p in pts),max(p[k] for p in pts)) for k in (0,1)))
    proofs=[]
    for fi in possible[:3]:
        face=faces[fi]
        center=tuple(sum(exact_projected[int(i)][k] for i in face)/3 for k in range(3))
        world=tuple(sum(exact_vertices[int(i)][k] for i in face)/3 for k in range(3))
        pruned,exact_tests,degenerate,blockers=0,0,[],[]
        for other,bounds in enumerate(exact_boxes):
            if not all(lo<=center[k]<=hi for k,(lo,hi) in enumerate(bounds)):
                pruned+=1
                continue
            a,b,c=[exact_projected[int(i)] for i in faces[other]]
            ux,uy=b[0]-a[0],b[1]-a[1]
            vx,vy=c[0]-a[0],c[1]-a[1]
            qx,qy=center[0]-a[0],center[1]-a[1]
            det=ux*vy-uy*vx
            if det==0:
                # Keep even a line-coplanar possibility unresolved. A positive
                # result requires this set to be empty.
                degenerate.append(other)
                continue
            s,t=(qx*vy-qy*vx)/det,(ux*qy-uy*qx)/det
            exact_tests+=1
            if s<0 or t<0 or s+t>1:continue
            depth=a[2]+s*(b[2]-a[2])+t*(c[2]-a[2])
            if depth>center[2]:
                blockers.append(dict(source_triangle=other,depth_advance=str(depth-center[2])))
        view=tuple(dot(tuple(map(F,row)),world+(F(1),)) for row in pose['view_matrix'])
        ndc=tuple(dot(tuple(map(F,row)),view) for row in pose['projection_matrix'])
        visible=not blockers and not degenerate and all(-1<x<1 for x in ndc[:3])
        proofs.append(dict(source_triangle=fi,source_polygon=body['evaluated']['triangle_polygons'][fi],
            centroid_world_exact=list(map(str,world)),centroid_NDC=list(map(float,ndc[:3])),
            source_triangles_total=len(faces),exact_projected_AABB_rejections=pruned,
            exact_Gram_ray_tests=exact_tests,projected_degenerate_possible_rows=degenerate,
            positive_depth_blockers=blockers,visible_without_Cube=visible))
    result=dict(status='positive_exists' if any(p['visible_without_Cube'] for p in proofs) else 'not_proven',
        fixed_camera_changed=False,geometry_changed=False,filtered_only_hidden_object='Cube',
        selected_triangle_centroids=len(selected),floating_prefilter_possible=len(possible),floating_prefilter_blocked=blocked,
        exact_candidate_selection='first three source-row-ordered possible positives; no scene or camera tuning',
        proofs=proofs,scope='one or more triangle-centroid geometric visibility witnesses; no full curved-surface or raster readability proof',
        input_pins=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (SRC,ARM,FULL)],
        new_operations=dict(Blender=0,MCP=0,raster=0,image_encoding=0,model=0,paid_API=0))
    (OUT/'VISIBLE_BODY_PROBE.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=result['status'],floating_possible=len(possible),
                         exact_proofs=[dict(face=p['source_triangle'],visible=p['visible_without_Cube'],tests=p['exact_Gram_ray_tests']) for p in proofs])))


if __name__=='__main__':main()
