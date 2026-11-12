"""Independent analytic controls and explicit API enclosure certificates."""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent

def exact(value):return F(int(value['numerator']),int(value['denominator']))
def dot(a,b):return sum(x*y for x,y in zip(a,b,strict=True))
def sub(a,b):return tuple(x-y for x,y in zip(a,b,strict=True))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def bounds(v):return [min(p[k] for p in v) for k in range(3)],[max(p[k] for p in v) for k in range(3)]
def encode(v):
    if isinstance(v,F):return {'numerator':str(v.numerator),'denominator':str(v.denominator)}
    if isinstance(v,dict):return {k:encode(x) for k,x in v.items()}
    if isinstance(v,(tuple,list)):return [encode(x) for x in v]
    return v

def member(point,vertices,faces):
    for index,face in enumerate(faces):
        a,b,c=[vertices[k] for k in face];u,v,w=sub(b,a),sub(c,a),sub(point,a)
        if dot(cross(u,v),w):continue
        uu,uv,vv=dot(u,u),dot(u,v),dot(v,v);den=uu*vv-uv*uv
        beta=(dot(w,u)*vv-dot(w,v)*uv)/den;gamma=(dot(w,v)*uu-dot(w,u)*uv)/den
        bary=(1-beta-gamma,beta,gamma)
        if min(bary)>=0:return {'triangle_id':index,'barycentric':bary}
    return None

def main():
    output={'schema':'surface-scan-independent-analytic-controls-v1','states':{},'checks':{}}
    for state in ('BASE','EDIT'):
        raw=json.loads((HERE/(state+'_SNAPSHOT.json')).read_bytes())
        truth=json.loads((HERE/(state+'_TRUTH.json')).read_bytes())
        objects={o['name']:o for o in raw['objects']}
        vertices={n:[tuple(F(x) for x in p) for p in o['vertices_world']] for n,o in objects.items()}
        records={tuple((r['object_a'],r['object_b'])):r for r in truth['pairs']}
        enclosures=[]
        for name,o in objects.items():
            m=[[F(x) for x in row] for row in o['matrix_world']]
            corners=[tuple(sum(m[k][j]*F(p[j]) for j in range(3))+m[k][3] for k in range(3))
                     for p in o['evaluated_bound_box_local']]
            lo,hi=bounds(corners);actual_lo,actual_hi=bounds(vertices[name])
            enclosed=all(lo[k]<=p[k]<=hi[k] for p in vertices[name] for k in range(3))
            enclosures.append({'name':name,'API_corner_bounds_m':[lo,hi],
                'actual_vertex_bounds_m':[actual_lo,actual_hi],'all_vertices_enclosed':enclosed,
                'component_count':len(vertices[name])*3})
        output['checks'][state+'_all_API_corners_enclose']=all(r['all_vertices_enclosed'] for r in enclosures)
        rail,slider=vertices['Obj_002'],vertices['Obj_008']
        ztop=max(p[2] for p in rail);zbottom=min(p[2] for p in slider)
        bottom_face=objects['Obj_008']['triangles'][1]
        weights=(F(7,40),F(13,40),F(20,40))
        b=tuple(sum(weights[i]*slider[bottom_face[i]][k] for i in range(3)) for k in range(3))
        a=(b[0],b[1],ztop)
        ra=member(a,rail,objects['Obj_002']['triangles']);sb=member(b,slider,objects['Obj_008']['triangles'])
        vertical={'target_point':a,'candidate_point':b,'target_member':ra,'candidate_member':sb,
                  'global_support_gap_m':zbottom-ztop,'exact_squared_distance_m2':(zbottom-ztop)**2}
        output['checks'][state+'_rail_slider_support_attained']=bool(ra and sb and b[2]==zbottom and zbottom>ztop)
        output['checks'][state+'_rail_slider_oracle_equal']=exact(records['Obj_002','Obj_008']['exact_squared_distance_m2'])==(zbottom-ztop)**2
        outer,inner=vertices['Obj_001'],vertices['Obj_024'];olo,ohi=bounds(outer);ilo,ihi=bounds(inner)
        candidates=[(ilo[k]-olo[k],k,'low') for k in range(3)]+[(ohi[k]-ihi[k],k,'high') for k in range(3)]
        gap,axis,side=min(candidates)
        b=next(v for v in inner if v[axis]==(ilo[axis] if side=='low' else ihi[axis]))
        a=tuple((olo[axis] if side=='low' else ohi[axis]) if k==axis else b[k] for k in range(3))
        nested={'strictly_contained':all(olo[k]<v[k]<ohi[k] for v in inner for k in range(3)),
                'minimum_box_slab_gap_m':gap,'outer_point':a,'inner_point':b,
                'outer_member':member(a,outer,objects['Obj_001']['triangles']),
                'inner_member':member(b,inner,objects['Obj_024']['triangles'])}
        output['checks'][state+'_nested_axis_boxes_support']=bool(nested['strictly_contained'] and nested['outer_member'] and nested['inner_member'] and gap>F(.002))
        output['checks'][state+'_nested_oracle_equal']=gap**2==exact(records['Obj_001','Obj_024']['exact_squared_distance_m2'])
        stop=vertices['Obj_017'];point=next(p for p in stop if p[2]==0)
        contact=member(point,outer,objects['Obj_001']['triangles'])
        output['checks'][state+'_contact_control']=bool(contact) and exact(records['Obj_001','Obj_017']['exact_squared_distance_m2'])==0
        output['states'][state]={'API_enclosures':enclosures,'rail_slider':vertical,'nested_boxes':nested,
                                'base_stop_contact':{'point':point,'base_member':contact}}
    output['passed']=all(output['checks'].values())
    output['checker_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with (HERE/'CONTROL_CERTIFICATES.json').open('x',encoding='utf8',newline='\n') as f:
        json.dump(encode(output),f,sort_keys=True,indent=2);f.write('\n')
    print(json.dumps({'passed':output['passed'],'checks':len(output['checks'])}))
    assert output['passed']

if __name__=='__main__':main()
