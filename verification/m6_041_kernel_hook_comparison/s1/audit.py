"""041 S1 independent native evidence and whole-output checks."""
from __future__ import annotations
import collections, hashlib, json, math, statistics
from fractions import Fraction
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import s1
read=s1.read
def digest(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def work(row):
    a=row['audit']['work'];return a[0] if len(a)==1 else {}
def norm(value,source):
    if not isinstance(value,dict):return value
    obj=dict(value)
    if 'trace_id' in obj:obj['trace_id']="validated_trace"
    if 'binding' in obj:
        b=dict(obj['binding']);assert b['runtime_source_sha256']==source
        b['runtime_source_sha256']="validated_runtime"
        obj['binding']=b
    return obj
def geometric(value):
    r=dict(value)
    for k in ('binding','trace_id'):r.pop(k,None)
    return r
def face_test(p, task, indices):
    records=[]
    for side,point,index in zip(('left','right'),p,indices):
        mesh=task[side];tri=np.asarray(mesh['vertices'])[mesh['faces'][index]]
        a,u,v=tri[0],tri[1]-tri[0],tri[2]-tri[0]
        matrix=np.column_stack([u,v]);ab=np.linalg.lstsq(matrix,point-a,rcond=None)[0]
        gap=float(np.linalg.norm(matrix@ab+a-point))
        records.append(dict(face=index,gap=gap,barycentric_coefficients=ab.tolist(),
                            inside=bool(min(ab)>=-1e-9 and sum(ab)<=1+1e-9 and gap<=1e-11)))
    return records
def audit_case(slot,plan):
    record=read(slot/'SLOT.json'); A=s1.asset_for(record['scenario']); labels=plan['sequence'][record['scenario']]
    source=plan['arms'][record['arm']]['source_sha256']
    checks={'completed':record['completed'],'inventory':[r['label'] for r in record['rows']]==[k for k in labels if k!='edit'],
            'custody':record.get('geometry_preserved') is True and record.get('geometry_binds') is True}
    detail={}
    native=read(slot/'native/OWNERSHIP.json');startup=read(slot/'client/STARTUP.json');config=read(slot/'client/CONFIG.json')
    checks['host_bound']=native['ready']['port']==config['blender']['port'] and native['ready']['pid']==read(slot/'BEFORE.json')['pid'] and native['normal_queue_roundtrip_verified'] and native['normal_addon_unmodified']
    logs=list(map(json.loads,(slot/'client/AUDIT.jsonl').read_bytes().splitlines()))
    for r in record['rows']:
        k=r['label'];b=r['value'];c=b.get('coverage',{}) if isinstance(b,dict) else {}; wk=work(r)
        tr=r['audit'];checks[k+'_identity']=tr['source']==source
        r['semantic']=norm(b,source)
        if isinstance(b,dict) and 'binding' in b:
            obs=[e for e in logs if e.get('event')=='observe' and e.get('trace_id')==tr['trace_id']]
            binding=b['binding']
            checks[k+'_local_binding']=len(obs)==1 and obs[0]['scene_revision']==binding['scene_revision'] and obs[0]['pid']==startup['actual_pid'] and binding['runtime_source_sha256']==source
            detail[k+'_local_binding']={k:binding.get(k) for k in ('document_epoch','scene_revision','scene_fingerprint','directory_sha256','host_source_sha256')}
            if 'host_identity' in binding:
                ident=binding['host_identity']
                mesh=read(slot/'BEFORE.json')['geometry']
                expected={'blender:'+digest(['',n]):row['instance'] for n,row in mesh.items() if n in ('Target','Peer_000')}
                checks[k+'_selected_instances']=ident.get('object_instances')==expected and ident.get('capture_scope')=='selected_objects'
                detail[k+'_selected_instances']={'expected':expected,'actual':ident}
        if k=='missing':
            checks[k+'_unavailable']=bool(r['tool_error'] or r['rpc_error'] or b.get('status') not in ('observed','complete') or
                    b.get('result_kind')!='surface_nearest' or not b.get('nearest_objects'))
            continue
        checks[k+'_rpc']=not r['tool_error'] and r['rpc_error'] is None
        if k.startswith('nearest'):
            checks[k+'_closure']=b.get('status')=='complete' and c.get('unresolved')==0
            initial=read(slot/"BEFORE.json")["geometry"]; names={n for n,v in initial.items() if v["type"]=="MESH"}
            checks[k+'_directory']=c.get('targets_excluding_focal')==len(names)-1 and sum(c.get(j,0) for j in ('distance_valid','strictly_excluded','unresolved'))==len(names)-1
            if (k.endswith('warm') or k=='nearest_unchanged'):
                checks[k+'_warm']=wk.get('kernel_calls')==0 and wk.get('result_cache_hit') is True
            if k=='nearest_edited':
                original=record['rows'][0]['value']
                checks[k+'_recomputed']=wk.get('kernel_calls',0)>0 and wk.get('result_cache_hit') is False and b['binding']['scene_revision']!=original['binding']['scene_revision'] and record['changed_objects']==['Target']
            if not k.startswith('nearest_edited'):
                if A in ('D48','B02'):
                    if A=='D48':
                        truth=read(s1.INPUTS['D48_exact'])['winner_fraction_oracle'];win="Peer_000"
                        dist=truth['correctly_rounded_distance_m'];faces=truth['canonical_native_triangle_rows']
                    else:
                        truth=read(s1.INPUTS['B02_exact']);win=truth['nearest_names'][0];dist=truth['global_distance_m']
                        faces=next(t['canonical_native_rows'] for t in truth['retained_pair_truth'] if t['name']==win)
                    evid=b.get('best_known_evidence',[{}])[0]; points=[evid.get('point_a_world'),evid.get('point_b_world')]
                    data=read(s1.INPUTS[A+'_bundle']); winner=next(t for t in data['tasks'] if t['right_name']==win)
                    checks[k+'_truth']=[x['name'] for x in b.get('nearest_objects',[])]==[win] and b.get('distance_m')==dist
                    detail[k+'_canonical']=face_test(points,winner,faces)
                    checks[k+'_canonical_faces']=all(q['inside'] for q in detail[k+'_canonical'])
                    if A=='D48':checks[k+'_oracle_points']=points==truth['point_pair_binary64']
                    if k=='nearest':
                        expected={t['right_id'] for t in data['tasks']}
                        actual=set(wk.get('pairs',{}))
                        checks[k+'_actual_call_ids']=expected==actual and wk.get('kernel_calls')==len(expected) and all(wk['pairs'][i]['surface_pair_count']==1 and not wk['pairs'][i]['surface_pair_cache_hit'] for i in actual)
                        detail[k+'_call_ids']={"expected":sorted(expected),"actual":sorted(actual)}
                else:
                    cert=next(g for g in read(s1.INPUTS["scale_truth"])["snapshots"] if g['id']==('G60_D12' if A=='G60' else A))['global_nearest_unsigned']
                    checks[k+'_truth']=cert['distance_lower_m']-1e-15 <= b['distance_m']<=cert['distance_upper_m']+1e-15 and [o['name'] for o in b['nearest_objects']]==['Peer_000']
                if A=='G60':checks[k+'_against040']=geometric(b)==geometric(read(s1.INPUTS['G60_040_nearest']))
        elif k.startswith("scan"):
            count=sum(x["type"]=="MESH" for x in read(slot/'BEFORE.json')['geometry'].values())
            checks[k+'_coverage']=c.get('total_pairs')==count*(count-1)//2 and c.get('objects')==count and c.get('total_pairs')==sum(c.get(n,0) for n in ('bound_excluded','measured_match','measured_nonmatch','unknown','deferred'))
            checks[k+'_scope']=len(b.get('matches',[]))==c.get('measured_match') and b['delivery']['complete'] and b['delivery']['matches_total']==len(b['matches'])
            if A=='G60':
                checks[k+'_against040']=geometric(b)==geometric(read(s1.INPUTS['G60_040_scan']))
                checks[k+'_57_9']=(c['measured_match'],c['measured_nonmatch'],c['unknown'],c['deferred'])==(57,9,0,0)
            if A=='B02':
                truth=read(s1.INPUTS['B02_scan'])
                got={tuple(sorted(x['name'] for x in pair['objects'])) for pair in b['matches']}
                want={tuple(sorted(pair)) for pair in truth['matches']}
                checks[k+'_all_276']=len(truth['pairs'])==c['total_pairs']==276 and want==got
                pairs={tuple(sorted((p['object_a'],p['object_b']))):p for p in truth['pairs']}
                checks[k+'_distances']=all(math.isclose(pair['distance_m'],float(pairs[tuple(sorted(x['name'] for x in pair['objects']))]['distance_interval']['lower_decimal_m']),rel_tol=1e-10,abs_tol=1e-12) for pair in b['matches'])
            if A=='G508':
                cert=next(g for g in read(s1.INPUTS['scale_truth'])['snapshots'] if g['id']=='G508')
                named={o['logical_id']:o['name'] for o in read(s1.INPUTS['G508'])['objects']}
                found={tuple(sorted(o['name'] for o in pair['objects'])):pair for pair in b['matches']}
                for oracle in cert['pairs']:
                    name=named[oracle['candidate']];key=tuple(sorted(('Target',name)))
                    if oracle['distance_upper_m']<=b['threshold_m']:
                        checks[k+'_cert_'+name]=key in found and oracle['distance_lower_m']-1e-15<=found[key]['distance_m']<=oracle['distance_upper_m']+1e-15
                    elif oracle['distance_lower_m']>b['threshold_m']:
                        checks[k+'_cert_'+name]=key not in found
        elif k=="relation":
            pairs=b.get('pairs',[]);facts=pairs[0]['facts'] if pairs else {}
            checks[k+'_valid']=b.get('status')=='observed' and facts.get('closed_solid_relation',{}).get('value')=='separated'
            if A=='G508':
                closed=facts.get('closed_solid_relation',{});surface=facts.get('surface_proximity',{})
                detail['bounded_partial']={'closed':closed, 'surface_status':surface.get('status'),'coverage':c,'status':b.get('status')}
        elif A=="Yanyite":
            ref=read(s1.INPUTS['Yanyite'])['regions']['low' if k=='low' else 'high']
            checks[k+'_native_points_faces']=all(b.get(f)==v for f,v in [('point_a_m',ref['source_point_world_m']),('point_b_m',ref['reference_point_world_m']),
                 ('source_triangle_a',min(ref['source_witness_triangle_ids'])),('source_triangle_b',min(ref['cube_witness_triangle_ids'])),
                 ('distance_m',ref['distance_m']),('selected_triangle_count',ref['triangle_count'])])
    return record,checks,detail
def audit():
    plan=read(s1.PLAN); summary=[];rec={};errors=[]
    for scenario,a in plan['slots']:
        folder=(ROOT/'slots_recovery_02' if scenario=='Yanyite' else s1.SLOTS)/(scenario+'_'+a);label=folder.name
        try:
            slot,checks,detail=audit_case(folder,plan);rec[(scenario,a)]=slot
            summary.append(dict(slot=label,checks=checks,detail=detail,errors=slot['errors'],elapsed_ms=(slot['end_ns']-slot['started_ns'])/1e6,
              samples=[dict(label=r['label'],rtt_ms=r['business_ns']/1e6,source=r['audit']['source'],coverage=r['value'].get('coverage') if isinstance(r['value'],dict) else None,
                        cache=work(r).get('result_cache_hit'),kernel_calls=work(r).get('kernel_calls'),work_keys=list(work(r)),tx=r['timing']['tx_bytes'],rx=r['timing']['rx_bytes']) for r in slot['rows']]))
        except Exception:
            import traceback;errors.append([label,traceback.format_exc()])
    cross={}
    for scenario in s1.SEQUENCES:
        a,b=rec.get((scenario,'032')),rec.get((scenario,'r3'))
        if not a or not b:continue
        for left,right in zip(a['rows'],b['rows']):
            x,y=left['semantic'],right['semantic']; k=scenario+'/'+left['label']
            diff=[i for i in sorted(set(x)|set(y)) if x.get(i)!=y.get(i)] if isinstance(x,dict) and isinstance(y,dict) else []
            subdiff=[f for f in sorted(set(x.get('binding',{}))|set(y.get('binding',{}))) if x.get('binding',{}).get(f)!=y.get('binding',{}).get(f)]
            if 'host_identity' in subdiff:
                hx,hy=x['binding']['host_identity'],y['binding']['host_identity']
                if {f for f in set(hx)|set(hy) if hx.get(f)!=hy.get(f)}=={'document_epoch'}:
                    subdiff[subdiff.index('host_identity')]='host_identity.document_epoch'
            cross[k]={'equal_except_trace_build':digest(x)==digest(y),'equal':digest(x)==digest(y) or
                (diff==['binding'] and set(subdiff)<={'scene_fingerprint','document_epoch','host_identity.document_epoch','scene_revision'} and geometric(x)==geometric(y)),
                'geometry_equal':geometric(x)==geometric(y),'differing_fields':diff,'differing_binding_fields':subdiff,
                'delta_rtt_ms':(left['business_ns']-right['business_ns'])/1e6}
    result=dict(plan=s1.pin(s1.PLAN),slots=summary,cross=cross,errors=errors)
    i=1
    while (ROOT/('AUDIT_'+str(i)+'.json')).exists():i+=1
    s1.dump(ROOT/('AUDIT_'+str(i)+'.json'),result)
    print('slots',len(summary),'failed',[(s['slot'],[k for k,v in s['checks'].items() if not v]) for s in summary if not all(s['checks'].values())],
      'cross',sum(x['equal'] for x in cross.values()),len(cross),'errors',errors,flush=True)
if __name__=='__main__':audit()

