"""Analytic warped apertures; fixed input truth does not call the planner."""
import math


def transform(p):return [p[2],p[1],-p[0]]  # exact 90-degree Y rotation
def cases():
    return [dict(id='curved_body_planar_rim',rim_warp=False,half=[.02,.1],blocker=None,want=True,pairs=12,far=True),
        dict(id='twisted_rim',rim_warp=True,half=[.02,.1],blocker=None,want=True,pairs=12,far=True),
        dict(id='center_blocked_edges_visible',rim_warp=True,half=[.02,.1],blocker=[-.006,.006,-.15,.15],want=True,pairs=10,far=True),
        dict(id='feature_blocked',rim_warp=True,half=[.02,.1],blocker=[-.04,.04,-.14,.14],want=False,pairs=0,far=True),
        dict(id='fully_blocked',rim_warp=True,half=[.02,.1],blocker=[-1.2,1.2,-1.2,1.2],want=False,pairs=0,far=True),
        dict(id='overview_sufficient',rim_warp=True,half=[.2,.2],blocker=None,want=False,pairs=12,far=False),
        dict(id='subpixel_width',rim_warp=True,half=[.0001,.1],blocker=None,want=False,pairs=12,far=True)]


def audit_cases():
    base=cases()[1]
    return cases()+[dict(base,id='dense_remote',dense='remote'),
        dict(base,id='dense_projected_blocker',dense='blocker',blocker=[-.04,.04,-.14,.14],want=False,pairs=0),
        dict(base,id='centroid_refinement',refinement='centroid'),
        dict(base,id='sliver_refinement',refinement='sliver',known_failure=True)]


def refine_boundary(native,edges,sliver=False):
    obj=native['objects'][0];updated=[];done=False
    for face in obj['faces']:
        edge=next(((a,b) for a,b in edges if a in face and b in face),None)
        if edge is None or (done and not sliver):updated.append(face);continue
        a,b=edge;c=next(i for i in face if i not in edge);v=obj['world_vertices'];q=len(v)
        v.append([(.99999*(v[a][k]+v[b][k])/2+.00001*v[c][k]) if sliver else sum(v[j][k] for j in face)/3 for k in range(3)])
        updated.extend([[face[0],face[1],q],[face[1],face[2],q],[face[2],face[0],q]]);done=True
    obj['faces']=updated


def source(case):
    a,b=case['half'];local=[[-1,-1,1],[1,-1,-1],[1,1,1],[-1,1,-1],[-a,-b,a*b],[a,-b,-a*b],[a,b,a*b],[-a,b,-a*b]]
    if not case['rim_warp']:
        for p in local[4:]:p[2]=0.
    quads=[[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
    faces=[t for p in quads for t in ([p[0],p[1],p[2]],[p[0],p[2],p[3]])]
    objects=[dict(object_id='target',world_vertices=[transform(p) for p in local],faces=faces)]
    box_faces=[[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,4,5],[0,5,1],[2,3,7],[2,7,6],[0,2,6],[0,6,4],[1,5,7],[1,7,3]]
    def box(name,bounds):
        points=[[x,y,z] for z in bounds[4:] for y in bounds[2:4] for x in bounds[:2]]
        objects.append(dict(object_id=name,world_vertices=[transform(p) for p in points],faces=box_faces))
    if case['far']:box('reference',[99,101,-1,1,-1,1])
    if case['blocker']:
        for sign in (-1,1):box('blocker'+str(sign),case['blocker']+([.1,.3] if sign==1 else [-.3,-.1]))
    if case.get('dense'):
        vertices=[];dense_faces=[];n=12
        for i in range(n+1):
            for j in range(n+1):
                a,b=-1+2*i/n,-1+2*j/n
                vertices.append(transform([100.,a,b] if case['dense']=='remote' else [a,b,.2]))
        for i in range(n):
            for j in range(n):
                a=i*(n+1)+j;b=a+n+1;dense_faces.extend([[a,b,b+1],[a,b+1,a+1]])
        objects[1]=dict(object_id='reference',world_vertices=vertices,faces=dense_faces)
    native=dict(objects=objects);edges=[[4,5],[5,6],[6,7],[7,4]]
    if case.get('refinement'):refine_boundary(native,edges,sliver=case['refinement']=='sliver')
    return native,edges


def oracle_samples(case,offset):
    a,b=case['half'];result=[]
    for t in (.25,.5,.75):
        for p,out in (([-a,-b+2*b*t],[-1,0]),([a,-b+2*b*t],[1,0]),([-a+2*a*t,-b],[0,-1]),([-a+2*a*t,b],[0,1])):
            pair=[]
            for sign in (1,-1):
                x,y=[p[k]+sign*offset*out[k] for k in range(2)]
                pair.append(transform([x,y,0.]))
            block=case['blocker'];visible=block is None or not (block[0]<=p[0]<=block[1] and block[2]<=p[1]<=block[3])
            result.append(dict(pair=pair,visible=visible))
    return result
