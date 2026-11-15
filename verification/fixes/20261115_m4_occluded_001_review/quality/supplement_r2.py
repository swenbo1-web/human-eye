from pathlib import Path
root=Path(__file__).parent
src=(root/'review_r1.py').read_text(encoding='utf8')
exec(compile(src[:src.index("result={'scope'")],str(root/'review_r1.py'),'exec'))
initial=len(checks)
formal=Path('D:/he_occluded_transfer_001/formal');framecount=0
bindings={}
for s in norm['slots']:
    sid=s['slot_id'];obs=read(formal/sid/'o/OBSERVATIONS.json');refs={}
    for frame in obs['frames']:
        framecount+=1;view=frame['view_name'];ref=frame.get('ref',frame.get('buffer_key'));refs[ref]=view
        check(sid+' formal frame files '+view,sha(frame['NPZ'])==frame['NPZ_sha256'] and sha(frame['PNG'])==frame['PNG_sha256'])
        arrays=np.load(frame['NPZ'])
        for k in ['color','owners','triangle_ids']:
            check(sid+' actual formal arrays vs qualification '+view+' '+k,hashlib.sha256(arrays[k].tobytes()).hexdigest()==actualframes[view]['arrays'][k])
    bindings[sid]=refs
    for p in s['panels']:
        for w in p.get('views',[]):check(sid+' current witness binding',refs[w['ref']]==w['view'])
    for p in s['pixel_targets']:check(sid+' current specified frame binding',refs[p['ref']]==p['view'])
    for source in s['sources']:
        if source['kind']!='cited_artifact':continue
        report=read(source['path'])
        for surface in report['surfaces']:
            name=surface.get('object_name',surface.get('object'));ids=surface.get('source_triangle_indices',surface.get('local_source_triangle_indices'));r=bykey[name,tuple(ids)];rid=r['id']
            center=surface.get('center_world_m',surface.get('world_center_m'));q=surface.get('rectangle_corners_world_m',surface.get('corners_world_m',surface.get('world_rectangle_corners_m')));normal=surface.get('front_direction_world',surface.get('front_unit_normal'))
            check(sid+' raw artifact center '+rid,tuple(F(x) for x in center)==r['c'])
            check(sid+' raw artifact corners '+rid,set(tuple(F(x) for x in p) for p in q)==set(r['q']))
            expected=np.array(list(map(float,r['n'])));expected/=np.linalg.norm(expected)
            check(sid+' raw artifact normal '+rid,max(abs(expected-np.array(normal)/np.linalg.norm(normal)))<=2e-14)
            for view,reason in surface.get('finite_pool_view_reasons',{}).items():
                nd=dot(r['n'],tuple(F(x) for x in cammap[view]['direction_rational']))
                expected='edge_on' if nd==0 else 'back_facing' if nd<0 else 'positive_area_occlusion' if shadows[view,rid] else 'in_view'
                check(sid+' raw artifact view reason '+rid+' '+view,reason==expected)
            for item in surface.get('finite_pool_view_evidence',[]):
                view=item['view'];row=pixelrows[view,rid]
                check(sid+' raw artifact facing/counts '+rid+' '+view,item['front_facing']==front[view,rid] and item['visible_surface_pixels']==row['surface_pixels'] and item['contrasting_boundary_pixels']==row['boundary_pixels'] and item['complete_readable']==row['complete_readable'])
                check(sid+' raw artifact per-view ref '+rid+' '+view,refs[item['image_ref']]==view)
                if 'positive_area_occlusion' in item:check(sid+' raw artifact occlusion '+rid+' '+view,item['positive_area_occlusion']==bool(shadows[view,rid]))
                if 'occluding_source_faces' in item:
                    claimed={(a['object_index'],a['local_source_triangle_index']) for a in item['occluding_source_faces']}
                    actual={(triangles[ti]['oi'],triangles[ti]['li']) for ti in shadows[view,rid]}
                    check(sid+' raw artifact blockers '+rid+' '+view,claimed==actual)

# Explicit whole-table P2 candidates are additional claims, independent of coverage.
p2=Path(next(s['raw_answer_path'] for s in norm['slots'] if s['slot_id']=='P2')).read_text(encoding='utf8')
abbr=dict(S='SCENE',T='TOP',L='LEFT',R='RIGHT',F='FRONT',B='BACK')
for line in p2.splitlines():
    if not line.startswith('| '):continue
    cells=[x.strip() for x in line.strip('|').split('|')]
    if not cells[0][:1].isdigit() or len(cells)!=7:continue
    index=int(cells[0].split()[0]);name=scene['objects'][index]['name']
    for fi,cell in enumerate(cells[1:]):
        if not cell.startswith('O:'):continue
        rid=bykey[name,(2*fi,2*fi+1)]['id'];claimed={abbr[x] for x in cell[2:].split(',')}
        check('P2 explicit candidate '+rid,claimed=={v for v in cammap if front[v,rid]})

# N1 sufficient blockers for each unknown face; these statements need not list all blockers.
exceptions={('RightUpright',(6,7)):lambda v:11,('LowerRearUnit',(10,11)):lambda v:2,('LowerFrontRail',(10,11)):lambda v:2,('UpperFrontRail',(10,11)):lambda v:2,('FrontRightUnit',(4,5)):lambda v:8 if v=='SCENE' else 1}
for rid,reason in reasons.items():
    if reason!='positive_area_occlusion_all_front_views':continue
    r=byid[rid];getblocker=exceptions.get((r['name'],tuple(r['local'])),lambda v:1)
    for view in cammap:
        if front[view,rid]:check('N1 sufficient blocker '+rid+' '+view,getblocker(view) in {triangles[t]['oi'] for t in shadows[view,rid]})

# N2 projected-area claims: independently unite exact plane-clipped shadows in XY.
sys.path.insert(0,'D:/he_occluded_transfer_001/shared_dependencies')
from shapely.geometry import Polygon,box
from shapely.ops import unary_union
claimed=[59.958,168,114.551,114.551,85.383,71.153];areas=[]
for view,reported in zip(['SCENE','TOP','LEFT','RIGHT','FRONT','BACK'],claimed):
    d=tuple(F(x) for x in cammap[view]['direction_rational']);polys=[]
    for t in triangles:
        if max(p[2] for p in t['q'])<=0:continue
        cp=clip(t['q'],lambda p:p[2]);xy=[(float(p[0]-p[2]*d[0]/d[2]),float(p[1]-p[2]*d[1]/d[2])) for p in cp]
        if len(xy)>=3:
            polygon=Polygon(xy)
            if polygon.area>0:polys.append(polygon)
    area=unary_union(polys).intersection(box(-7,-6,7,6)).area*float(d[2])/math.sqrt(float(dot(d,d)));areas.append(area)
    check('N2 projection area '+view,abs(area-reported)<=.0005)
extra=checks[initial:]
out={'passed':all(x['passed'] for x in checks),'base_checks':initial,'supplementary_checks':len(extra),'formal_frames_checked':framecount,'checks':extra,'N2_projected_areas':areas,'limitations':['No exhaustive natural-language theorem proving; explicit extra numerical/candidate/blocker claims targeted from manual final review.','Saved pixels checked, raster itself not rerun or independently reimplemented.','Product/adoption causality and necessity of extra reads outside this quality review.']}
with (OUT/'SUPPLEMENT_R2.json').open('x',encoding='utf8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
print(json.dumps({'passed':out['passed'],'supplementary_checks':len(extra),'failed':sum(not x['passed'] for x in extra),'formal_frames':framecount}))
