"""Independent stdlib-only inspection of saved outputs; no product imports/execution."""
from pathlib import Path
from fractions import Fraction
from collections import Counter
import ast, hashlib, json, re, struct, zipfile

OUT=Path(__file__).resolve().parent
V=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification')
B=V/'m4_routed_task_benefit_001'
R=Path('D:/he_routed_001/formal')
inputs={}; checks=[]; failures=[]; cache={}; summaries={}; duplicate_rows=[]
def raw(p):
    p=Path(p); b=p.read_bytes(); inputs[str(p)]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}; return b
def read(p): return json.loads(raw(p))
def check(name, condition, detail=None):
    checks.append(name)
    if not condition: failures.append({'check':name,'detail':detail})
def dec(s,at=0): return json.JSONDecoder().raw_decode(s,at)[0]
def response(s,n):
    rr=read(R/s/f'o/tool_{n:02d}/RESPONSE.json')['result']
    return json.loads(next(c['text'] for c in rr['content'] if c['type']=='text'))
def stdout(s,n): return response(s,n)['stdout']
def tab(t): return [dict(zip(t['columns'],r)) for r in t['rows']]

truth=read(V/'m4_region_localization_consumption_001/admin/TRUTH.json')
check('fixed_preexisting_truth_hash',inputs[str(V/'m4_region_localization_consumption_001/admin/TRUTH.json')]['sha256']=='ad1ba5127945a290f24bb519df8088ba280d9bf5cb3f6d73b9caa82f2d2712db')
targets=truth['targets']; by_tri={tuple(t['source_triangle_indices']):i for i,t in enumerate(targets)}
by_roi={t['roi_alias']:i for i,t in enumerate(targets)}
raw_map={f:i for i,t in enumerate(targets) for f in t['source_triangle_indices']}
scene=read(V/'m4_region_localization_consumption_001/inputs/SCENE_GEOMETRY_RATIONAL.json')['objects'][0]
check('all_source_faces_partition',set(raw_map)|set(truth['unsupported_triangle_indices'])==set(range(len(scene['triangles']))))
check('disjoint_source_sets',sum(len(t['source_triangle_indices']) for t in targets)==len(raw_map)==3336)

def npy(data):
    version=data[6]; nfmt='<H' if version==1 else '<I'; prefix=10 if version==1 else 12
    n=struct.unpack_from(nfmt,data,8)[0]; h=ast.literal_eval(data[prefix:prefix+n].decode('latin1')); b=data[prefix+n:]
    assert not h['fortran_order']
    d=h['descr']
    if d in ('<i4','|i4'): a=memoryview(b).cast('i')
    elif d in ('<i8','|i8'): a=memoryview(b).cast('q')
    elif d in ('|u1','<u1'): a=memoryview(b)
    elif d.startswith('<U'):
        k=int(d[2:])*4; a=[b[i:i+k].decode('utf-32-le').rstrip('\0') for i in range(0,len(b),k)]
    else: a=None
    return h,a

def frame_stats(frame):
    b=raw(frame['NPZ']); sha=hashlib.sha256(b).hexdigest()
    check('frame_npz_sha:'+frame['NPZ'],sha==frame['NPZ_sha256'])
    png=raw(frame['PNG']);check('frame_png_sha:'+frame['PNG'],hashlib.sha256(png).hexdigest()==frame['PNG_sha256'])
    if sha in cache: return cache[sha]
    import io
    z=zipfile.ZipFile(io.BytesIO(b)); arrays={n[:-4]:npy(z.read(n)) for n in z.namelist()}
    color=arrays['color'][1]; owners=arrays['owners'][1]; h,w=arrays['owners'][0]['shape']
    if 'triangle_ids' in arrays:
        ids=arrays['triangle_ids'][1]
        labels=[raw_map.get(x,138) if x>=0 else 139 for x in ids]
        check('raw_id_ranges:'+sha,all(-1<=x<len(scene['triangles']) for x in ids))
    else:
        pmap=[by_roi[r] for r in arrays['patch_roi_ids'][1]]
        ids=arrays['patch_owners'][1]
        labels=[pmap[x] if x>=0 else (139 if owners[i]<0 else 138) for i,x in enumerate(ids)]
        fm=arrays['face_patch_ids'][1]
        check('product_source_mapping:'+sha,all((pmap[p] if p>=0 else 138)==raw_map.get(f,138) for f,p in enumerate(fm)))
    counts=Counter(labels); boundary=bytearray(h*w)
    for p,left in enumerate(labels):
        x=p%w
        for q in ((p+1,) if x+1<w else ()) + ((p+w,) if p+w<h*w else ()):
            if left==labels[q]: continue
            ci=p*3;cj=q*3
            if sum((color[ci+k]-color[cj+k])**2 for k in range(3))>=576:
                boundary[p]=boundary[q]=1
    bc=Counter(labels[i] for i,v in enumerate(boundary) if v)
    result={'counts':counts,'boundary':bc,'labels':labels,'w':w,'h':h,'ids':ids}
    cache[sha]=result
    return result

def expand(ranges): return tuple(i for first,last in ranges for i in range(first,last+1))

for slot in ('N1','P1','P2','N2','N3','P3'):
    final=raw(R/slot/'c/final.txt').decode('utf8');public=raw(R/slot/'c/PUBLIC_FINAL.txt').decode('utf8')
    check(slot+':same_final',final==public)
    obs=read(R/slot/'o/OBSERVATIONS.json')
    frames={f['ref']:f for f in obs['frames']}; stats={ref:frame_stats(f) for ref,f in frames.items()}
    tools=[]
    for p in sorted((R/slot/'o').glob('tool_*/REQUEST.json')):
        req=read(p)['params'];res=read(p.with_name('RESPONSE.json'))['result'];texts=[c['text'] for c in res['content'] if c['type']=='text']
        tools.append({'number':p.parent.name,'name':req['name'],'arguments':req['arguments'],'isError':res['isError'],'response_text':texts})
    claims=[]
    def add(i,status,witnesses,reason): claims.append({'i':i,'observed':status in ('covered','observed'),'witnesses':witnesses,'reason':reason})
    if slot=='N1':
        s=stdout(slot,9); rows=dec(s,s.index('\n[[')+1)
        for row in rows:
            i=by_tri[expand(row[1])]; ws=[{'view':row[3],'ref':row[4],'pixels':row[5],'boundary_pixels':row[6]}] if row[2]=='observed' else []
            add(i,row[2],ws,row[3] if not ws else '')
    elif slot=='N2':
        rows=[]
        for n in (11,12):
            s=stdout(slot,n); marker=re.search(r'coverage_v1\.rows\[[^\]]+\]=',s);rows+=dec(s,marker.end())
        for row in rows:
            i=by_tri[expand([row[1]])];e=row[3];ws=[{'view':e[0],'ref':e[1],'pixels':e[2],'boundary_pixels':e[3],'pixel':e[4]}] if row[2]=='observed' else []
            add(i,row[2],ws,e if not ws else '')
    elif slot=='N3':
        unique={}
        for n in (8,9,10,11):
            s=stdout(slot,n);m=re.search(r'COVERAGE_ROWS_[A-Z0-9_]+=',s);rows=dec(s,m.end())
            for row in rows:
                if row['id'] in unique:
                    duplicate_rows.append({'slot':slot,'id':row['id'],'same':unique[row['id']]==row})
                    check('N3:repeated_row_same:'+str(row['id']),unique[row['id']]==row)
                unique[row['id']]=row
        for row in unique.values(): add(by_tri[expand(row['tri_ranges'])],row['status'],row['evidence'],row['status'])
    else:
        p=response(slot,1); regions=tab(p['regions']);pixels=tab(p['pixels']);images=tab(p['images'])
        check(slot+':product_first_actual_call',tools[0]['name']=='active_observation' and not tools[0]['isError'])
        check(slot+':json_parse_actual',"json.loads(last_observation_json)" in tools[1]['arguments']['code'] and not tools[1]['isError'])
        check(slot+':product_call_count',sum(t['name']=='active_observation' for t in tools)==1)
        for row in regions:
            target=targets[by_roi[row['roi_id']]]
            check(slot+':region_geometry:'+row['roi_id'],row['center_world_m']==[float(Fraction(x)) for x in target['center_world_m']] and row['front_direction_world']==[float(Fraction(x)) for x in target['front_direction_world']])
            c,u,v=[row[k] for k in ('center_world_m','half_edge_u_world_m','half_edge_v_world_m')]
            corners={tuple(c[k]+su*u[k]+sv*v[k] for k in range(3)) for su,sv in ((-1,-1),(1,-1),(1,1),(-1,1))}
            check(slot+':region_corners:'+row['roi_id'],corners=={tuple(float(Fraction(x)) for x in point) for point in target['quad_world_m']})
        if slot=='P1':
            s=stdout(slot,6);d=dec(s,s.index('{'))
            for row in d['rows']:
                i=by_tri[expand(row[1])];check('P1:source_matches_roi:'+str(row[0]),i==by_roi[regions[row[0]]['roi_id']])
                ws=[{'view':d['images'][e[0]][0],'ref':d['images'][e[0]][1],'pixels':e[1],'boundary_pixels':e[2],'pixel':e[3]} for e in row[4]]
                add(i,row[2],ws,row[3])
        else:
            for region in regions:
                ws=[]
                if region['status']=='covered':
                    px=pixels[region['complete_witness_pixel_index']];im=images[px['image_index']]
                    ws=[{'view':im['view_name'],'ref':im['image_ref'],'pixels':px['visible_surface_pixels'],'boundary_pixels':px['contrasting_boundary_pixels'],'pixel':px['visible_pixel_anchor']}]
                add(by_roi[region['roi_id']],region['status'],ws,region['unobserved_reason'])
        for n,px in enumerate(pixels):
            im=images[px['image_index']];st=stats[im['image_ref']];i=by_roi[regions[px['region_index']]['roi_id']]
            check(slot+':public_pixel_counts:'+str(n),(px['visible_surface_pixels'],px['contrasting_boundary_pixels'])==(st['counts'][i],st['boundary'][i]))
            if px['readable']: check(slot+':readable_happens_complete:'+str(n),targets[i]['by_view'][im['view_name']]['geometry_complete'])
        if slot=='P3':
            artifact=read(R/slot/'o/scratch/surface_inspection.json')
            check('P3:artifact_native_observation_is_public_product',artifact['native_observation']==p)
            check('P3:artifact_world_corners',all({tuple(p) for p in row['world_corners_m']}=={tuple(float(Fraction(x)) for x in pt) for pt in targets[by_roi[row['roi_id']]]['quad_world_m']} for row in artifact['supported_surfaces']))
    check(slot+':all138_unique',len(claims)==len(set(c['i'] for c in claims))==138 and {c['i'] for c in claims}==set(range(138)))
    check(slot+':covered_exact115',{targets[c['i']]['key'] for c in claims if c['observed']}==set(truth['reachable_keys']))
    check(slot+':remaining_exact23',{targets[c['i']]['key'] for c in claims if not c['observed']}==set(truth['finite_pool_unknown_keys']))
    wc=0
    for c in claims:
        i=c['i'];t=targets[i]
        if c['observed']:
            check(slot+':witness_exists:'+str(i),bool(c['witnesses']))
            for e in c['witnesses']:
                wc+=1; f=frames[e['ref']];st=stats[e['ref']];n=st['counts'][i];bc=st['boundary'][i]
                check(slot+':witness:'+str(i)+':'+e['view'],f['view_name']==e['view'] and t['by_view'][e['view']]['geometry_complete'] and n>=16 and bc>=4 and n==e['pixels'] and bc==e['boundary_pixels'])
                if e.get('pixel') is not None:
                    x,y=e['pixel'];check(slot+':anchor:'+str(i)+':'+e['view'],st['labels'][y*st['w']+x]==i)
        else:
            check(slot+':unknown_unreachable:'+str(i),not t['valid_geometric_views'])
    scene_ref=next(ref for ref,f in frames.items() if f['view_name']=='SCENE');sc=stats[scene_ref]
    check(slot+':Q1_actual_pixel',sc['labels'][247*sc['w']+109]==72)
    check(slot+':Q1_counts',(sc['counts'][72],sc['boundary'][72])==(354,73))
    check(slot+':Q2_scene_occluded',sc['counts'][131]==0 and targets[131]['by_view']['SCENE']['front_facing'] and not targets[131]['by_view']['SCENE']['geometry_complete'])
    name='BACK' if slot in ('P2','P3') else 'LEFT';xy={'N1':(327,427),'P1':(343,426),'N2':(327,415),'N3':(327,415),'P2':(419,224),'P3':(419,224)}[slot]
    ref=next(ref for ref,f in frames.items() if f['view_name']==name);st=stats[ref]
    check(slot+':Q2_owned_anchor',st['labels'][xy[1]*st['w']+xy[0]]==131 and targets[131]['by_view'][name]['geometry_complete'])
    check(slot+':Q3_pool_front',all(not row['front_facing'] for row in targets[107]['by_view'].values()))
    check(slot+':final_unsupported48',bool(re.search(r'triangle\s*\*?\*?\s*48',final,re.I)))
    check(slot+':no_old_evidence_access',obs['audit']['forbidden_old_evidence_reads']==0 and not obs['audit']['forbidden_product_calls'])
    summaries[slot]={'claims':len(claims),'covered':sum(c['observed'] for c in claims),'remaining':sum(not c['observed'] for c in claims),'all_cited_witnesses_checked':wc,'registered_actual_frames':len(frames),'product_calls':len(obs['active']),'business_calls':len(tools),'error_tools':[t['number'] for t in tools if t['isError']], 'claim_source':'native rows' if slot[0]=='N' else 'mixed native discovery + product coverage' if slot=='P1' else 'product facts with native SCENE verification' if slot=='P2' else 'product JSON/artifact'}
    (OUT/(slot+'_TOOLS.json')).write_text(json.dumps(tools,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

suffix=raw(B/'inputs/PROMPT_SUFFIX.txt')
check('common_suffix_sha',hashlib.sha256(suffix).hexdigest()=='3f848a42070580ad479e3de6507b9ffe09c59b9651c784c17608f0d752c1205a')
for group in ('N','P'):
    check('prompt_construction:'+group,raw(B/f'inputs/PROMPT_{group}.txt')==raw(B/f'inputs/PREFIX_{group}.txt')+b'\n\n'+suffix)
n=read(R/'N1/o/TOOLS_SCHEMA.json');p=read(R/'P1/o/TOOLS_SCHEMA.json')
common={r['name']:r for r in n};pc={r['name']:r for r in p}
check('common_tools_identical',all(pc[k]==v for k,v in common.items()))
check('only_extra_active_tool',set(pc)-set(common)=={'active_observation'})
result={'method':'Independent stdlib-only parsing of actual final/tool/NPZ artifacts; fixed pre-existing independent geometric truth. No scorer imports, no product/model/Blender/raster executions. Pixel counts computed once per unique NPZ bytes; every slot frame hash checked.', 'new_product_model_blender_raster_calls':0,'checks':len(checks),'failures':failures,'slots':summaries,'duplicate_N3_rows':duplicate_rows,'unique_NPZ_processed':len(cache),'known_limits':['Geometric completeness uses fixed pre-existing independent rational oracle, not a new geometry solver run.','Final-answer semantics manually read; 18 position facts independently tied to current saved arrays and oracle.','No direct measure of model internal trust or spontaneous adoption.','P1 and P3 treat readable as complete; all readable observations happen geometrically complete on this fixture.'], 'intermediate_text_error':{'slot':'N3','tool':'tool_08','text':'No finite-pool unknowns','resolution':'Same tool has 23 remaining rows; later REMAINING_SET and formal final preserve 23 unobserved and finite-pool limitation.'}}
(OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'INPUTS.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'checks':len(checks),'failures':failures,'slots':summaries,'unique_NPZ_processed':len(cache)},ensure_ascii=False,indent=2))
