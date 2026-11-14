"""Root independent saved-world/brief audit. No product imports or executions."""
from collections import Counter
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
NS=ROOT/'verification/m4_active_observation_region_anchors_001'
OUT=Path(__file__).resolve().parent
INPUTS={}
CHECKS=Counter()
FAILURES=[]
FIELDS=('center_world_m','half_edge_u_world_m','half_edge_v_world_m','front_direction_world')

def read(path):
    path=Path(path); b=path.read_bytes(); INPUTS[str(path)]=hashlib.sha256(b).hexdigest()
    return b
def load(path): return json.loads(read(path))
def ck(value,label,group='world'):
    CHECKS[group]+=1
    if not value: FAILURES.append({'group':group,'label':label})
def vec(v): return tuple(Q(x) for x in v)
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def rows(t):
    ck(all(len(r)==len(t['columns']) for r in t['rows']), 'table row width','delivery')
    return [dict(zip(t['columns'],r)) for r in t['rows']]
def hull2(points,axis):
    # Convex hull of all face-referenced positions, independent of product boundary traversal.
    axes=[i for i in range(3) if i!=axis]
    pairs=sorted({tuple(p[i] for i in axes):p for p in points}.items())
    def turn(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def chain(seq):
        result=[]
        for p in seq:
            while len(result)>1 and turn(result[-2][0],result[-1][0],p[0])<=0:result.pop()
            result.append(p)
        return result
    return [p[1] for p in chain(pairs)[:-1]+chain(list(reversed(pairs)))[:-1]]
def inside(p,c,u,v):
    offset=sub(p,c)
    return dot(offset,cross(u,v))==0 and abs(dot(offset,u))<=dot(u,u) and abs(dot(offset,v))<=dot(v,v)

def main():
    archive=load(NS/'EXTERNAL_ARCHIVE.json')
    records={r['original_relative_path']:r for r in archive['files']}
    def saved(rel):
        rec=records['run/acceptance_01/'+rel]; b=read(ROOT/rec['archive_path'])
        ck(len(b)==rec['bytes'] and hashlib.sha256(b).hexdigest()==rec['sha256'],rel,'binding')
        return json.loads(b)
    caps=[saved(f'server/CAPTURE_{i:02}.json') for i in range(1,4)]
    raw=[saved(f'server/RESULT_{i:02}.json') for i in range(1,4)]
    index=saved('server/INDEX_01.json')
    geom=load(NS/'inputs/JOINED.json')['objects'][0]
    mesh=caps[0]['meshes'][0]; vertices=list(map(vec,mesh['vertices'])); faces=mesh['faces']
    ck(vertices==list(map(vec,geom['vertices'])),'actual vs frozen world vertices','binding')
    ck(faces==geom['triangles'],'actual vs frozen face order','binding')
    ck(len(vertices)==1913 and len(faces)==3337,'actual source denominator','binding')
    ck(all(c['meshes']==caps[0]['meshes'] for c in caps),'three captures preserve source','binding')
    current=raw[0]['facts']['regions']
    support=raw[0]['facts']['scope']['patch_support']
    mappings={r['roi_id']:r['triangle_indices'] for r in support['regions']}
    ck(len(current)==len(mappings)==138,'138 source-linked regions')
    ck([r['roi_id'] for r in current]==sorted(mappings),'stable order')
    old=load(NS/'inputs/historical/JOINED_SERVICE_RESULT.json')
    oldregs={r['roi_id']:r for r in old['facts']['regions']}
    derived={}; seen=set(); tri_counter=0
    for row in current:
        rid=row['roi_id']; ids=mappings[rid]
        ck(not seen.intersection(ids),rid+' disjoint ownership'); seen.update(ids)
        triangles=[[vertices[v] for v in faces[i]] for i in ids]
        normals=[cross(sub(t[1],t[0]),sub(t[2],t[0])) for t in triangles]
        n=normals[0]; axis=max(range(3),key=lambda i:abs(n[i]))
        ck(n!=(0,0,0),rid+' source nondegenerate')
        points={p for t in triangles for p in t}
        ck(all(dot(sub(p,triangles[0][0]),n)==0 for p in points),rid+' source coplanar')
        quad=hull2(points,axis)
        ck(len(quad)==4,rid+' convex source four corners')
        if dot(cross(sub(quad[1],quad[0]),sub(quad[2],quad[0])),n)<0:quad.reverse()
        start=min(range(4),key=lambda i:quad[i]);quad=quad[start:]+quad[:start]
        edgeu=sub(quad[1],quad[0]);edgev=sub(quad[3],quad[0]);normal=cross(edgeu,edgev)
        ck(dot(edgeu,edgev)==0 and sub(quad[2],quad[1])==edgev,rid+' source rectangle')
        ck(all(dot(x,n)>0 for x in normals),rid+' common source winding')
        ck(sum(x[axis] for x in normals)==2*normal[axis],rid+' total source area')
        c=tuple(sum(p[k] for p in quad)/4 for k in range(3))
        u=tuple(x/2 for x in edgeu);v=tuple(x/2 for x in edgev)
        front=tuple(x/max(map(abs,normal)) for x in normal)
        actual=[vec(row[f]) for f in FIELDS]
        ck(actual==[c,u,v,front],rid+' source derived descriptors')
        rebuilt=[tuple(c[k]+su*u[k]+sv*v[k] for k in range(3)) for su,sv in [(-1,-1),(1,-1),(1,1),(-1,1)]]
        ck(rebuilt==quad,rid+' source corners reconstructed')
        wire=json.dumps(quad,default=str,sort_keys=True,separators=(',',':')).encode()
        ck('roi_'+hashlib.sha256(wire).hexdigest()[:24]==rid,rid+' source identity')
        for t in triangles:
            ck(all(inside(p,c,u,v) for p in t),rid+' triangle in rectangle');tri_counter+=1
        ck(row['object_index']==0,rid+' joined object')
        ck((row['status'],row['reason'])==(oldregs[rid]['status'],oldregs[rid]['reason']),rid+' old status retained','retention')
        derived[rid]=(c,u,v,front)
    ck(len(seen)==3336 and set(range(3337))-seen=={48},'full support plus triangle48')
    payloads=[]
    for i in (3,4,5):
        reply=saved(f'stdio/rpc_{i:02}/RX.bin'); canonical=saved(f'stdio/rpc_{i:02}/RESPONSE.json')
        ck(reply==canonical,f'rpc{i} actual received bytes parse','delivery')
        ck(reply['result']['isError'] is False,f'rpc{i} success','delivery')
        payloads.append(json.loads(reply['result']['content'][0]['text']))
    briefs=payloads[:2]
    ck(load(NS/'examples/JOINED_BRIEF.json')==briefs[0],'example actual default','delivery')
    for i,(b,s) in enumerate(zip(briefs,raw)):
        ck(b['schema']=='active-observation-brief-v3',f'{i} v3 no full fallback','delivery')
        rr=rows(b['regions']);pp=rows(b['pixels']);images=rows(b['images']);objects=rows(b['objects'])
        ck(len(rr)==138 and len(pp)==414 and len(images)==3 and len(objects)==1,f'{i} public denominators','delivery')
        for j,r in enumerate(rr):
            source=s['facts']['regions'][j]
            ck(all(r[f]==source[f] for f in FIELDS),f'{i}:{j} full exact descriptor','delivery')
            ck(r['triangle_count']==len(mappings[r['roi_id']]),f'{i}:{j} source face count','delivery')
            ck([vec(r[f]) for f in FIELDS]==list(derived[r['roi_id']]),f'{i}:{j} independent world','delivery')
        for p in pp:
            view=images[p['image_index']]['view_name'];rid=rr[p['region_index']]['roi_id']
            obs=next(o for o in s['facts']['observations'] if o['view_name']==view)
            source=next(r for r in obs['pixel_rows'] if r['roi_id']==rid)
            ck(all(source[k]==v for k,v in p.items() if k not in ('image_index','region_index')),f'{i}:{view}:{rid} exact pixel semantics','delivery')
        ck(b['location_conventions']==s['facts']['location_conventions'],f'{i} one conventions','delivery')
    ck(payloads[2]['facts']==raw[2]['facts'],'cached full exact source facts','delivery')
    ck(briefs[0]['regions']==briefs[1]['regions'] and briefs[0]['pixels']==briefs[1]['pixels'],'hot/default vs explicit brief same public facts','delivery')
    rr=rows(briefs[0]['regions']);pp=rows(briefs[0]['pixels']);im=rows(briefs[0]['images']);answers=[]
    questions=load(NS/'QUESTIONS.json')['questions']
    for q in questions[:3]:
        given=q['given'];matches=[(i,r) for i,r in enumerate(rr) if vec(r[FIELDS[0]])==vec(given[FIELDS[0]]) and vec(r[FIELDS[3]])==vec(given[FIELDS[3]])]
        ck(len(matches)==1,q['id']+' public unique center/facing','questions')
        i,r=matches[0];pix=[p for p in pp if p['region_index']==i]
        ck(r['roi_id']==q['expected']['world']['roi_id'],q['id']+' matches frozen face','questions')
        if 'view' in given:
            pixel=next(p for p in pix if im[p['image_index']]['view_name']==given['view'])
            ck(all(pixel[k]==v for k,v in q['expected']['pixel'].items() if k not in ('roi_id','object_index','view')),q['id']+' public pixel answer','questions')
            answers.append({'id':q['id'],'roi_id':r['roi_id'],'status':r['status'],'pixel':pixel})
        else:
            ck(r['status']=='unknown' and all(not p['front_facing'] and not p['readable'] for p in pix),q['id']+' finite-pool unknown','questions')
            answers.append({'id':q['id'],'roi_id':r['roi_id'],'status':r['status'],'all_views_backfacing':True})
    point=vec(questions[3]['given']['triangle_center_world_m'])
    containing=[rid for rid,(c,u,v,n) in derived.items() if inside(point,c,u,v)]
    ck(not containing,'Q4 not within any supported rectangle','questions')
    unknown=rows(briefs[0]['scope']['patch_support']['unsupported_components'])
    ck(len(unknown)==1 and unknown[0]['triangle_index_ranges']==[[48,48]] and unknown[0]['status']=='unknown','Q4 unknown source index retained','questions')
    actual_tri=[vertices[k] for k in faces[48]]
    ck(actual_tri==list(map(vec,questions[3]['given']['triangle_vertices_world_m'])),'Q4 actual private geometry matches supplied triangle','questions')
    ck(all(not any(k in r for k in FIELDS) for r in unknown),'unsupported public rows have no world descriptor','questions')
    units=load(NS/'units_01/UNIT_RESULT.json')
    ck(units['passed'] and units['run']==86 and not units['errors'] and not units['failures'],'author recorded86/86','author_record')
    # Bind the static code/test review. These tests were read, never executed here.
    for f in ['human_eye_plugin/active_observation.py','human_eye_plugin/active_observation_host.py','human_eye_plugin/live_spatial_mcp.py','verification/test_active_observation_region_world.py','verification/test_active_observation_region_delivery.py','verification/test_active_observation_region_anchors.py']:
        read(ROOT/f)
    for path,sha in list(INPUTS.items()):ck(hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha,path+' unchanged','input_integrity')
    result={'passed':not FAILURES,'checks':dict(CHECKS),'failures':FAILURES,'inputs':INPUTS,'source_regions':138,'source_triangles_checked':tri_counter,'answers':answers,'Q4_scope':'Public world vectors prove no supported rectangle at supplied location. Unsupported index48 exists, but public fields do not geometrically bind it to that point; do not grade exact index-location association as known without native evidence.','author_unit_tests_read':86,'root_product_unit_tests_run':0,'root_product_imports':0,'root_Blendermodelrasterbenchmark_calls':0,'preparation_errors':['One read-only rg command used a Windows wildcard path and exited1; reran with -g filter. No product execution.']}
    (OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:result[k] for k in ['passed','checks','failures','source_regions','source_triangles_checked','Q4_scope']},ensure_ascii=False))
if __name__=='__main__':main()
