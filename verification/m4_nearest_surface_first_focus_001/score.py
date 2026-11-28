"""Independent engineering score for original cold nearest-surface and legacy focus."""
import argparse
import base64
from fractions import Fraction
import importlib.util
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
PREVIOUS=HERE.parent/'m4_reference_only_intent_holdout_001/audit.py'
spec=importlib.util.spec_from_file_location('intent_audit',PREVIOUS)
intent=importlib.util.module_from_spec(spec)
spec.loader.exec_module(intent)
old=intent.old
need,read,pin=intent.need,intent.read,intent.pin
BATCH='M4-NEAREST-SURFACE-FIRST-FOCUS-001'
ORDER=('K','T')
PIXELS=16
DOMAIN='zero_based_object_local_current_evaluated_capture_triangle_rows'


def point_on_triangle(point, vertices):
    def diff(a,b):
        return tuple(x-y for x,y in zip(a,b,strict=True))
    def dot(a,b):
        return sum(x*y for x,y in zip(a,b,strict=True))
    a,b,c=vertices
    u,v,d=diff(b,a),diff(c,a),diff(point,a)
    uu,uv,vv,du,dv=dot(u,u),dot(u,v),dot(v,v),dot(d,u),dot(d,v)
    base=uu*vv-uv*uv
    if not base:
        return False
    s,t=(du*vv-dv*uv)/base,(dv*uu-du*uv)/base
    return s>=0 and t>=0 and s+t<=1 and all(q==s*x+t*y for q,x,y in zip(d,u,v,strict=True))


def verify_exact_witness(focus,domain,true_case):
    value=focus['nearest_surface']
    witness=value['witness']
    need(value['status']=='measured' and bool(value['method'])
         and witness['scope']=='one_current_triangle_per_endpoint_non_exhaustive'
         and witness['index_domain']==DOMAIN
         and witness['ordered_geometry_sha256']==domain['geometry_sha']
         and witness['point_encoding'] in ('binary64_world_m','rational_world_m'),
         'nearest_surface_not_same_ordered_capture')
    rows,points=[],[]
    for side,key in (('a','object'),('b','reference')):
        node=witness[side]
        obj=focus[key]
        mesh=domain['capture']['meshes'][obj['object_index']]
        row=node['source_triangle_index']
        need(type(row) is int and 0<=row<len(mesh['faces'])
             and node['host_id']==mesh['object_id']==obj['host_id'] and node['instance_id']==obj['instance_id'],
             'nearest_surface_source_row_not_current_object')
        point=tuple(Fraction(number) for number in node['point_m'])
        triangle=tuple(tuple(Fraction(x) for x in mesh['vertices'][i]) for i in mesh['faces'][row])
        need(len(point)==3 and point_on_triangle(point,triangle),'nearest_point_not_on_claimed_source_surface')
        rows.append(row)
        points.append(point)
    rank=sum((x-y)**2 for x,y in zip(*points,strict=True))
    truths=[Fraction(v) for v in true_case['distances_squared_m2']]
    need(rank==min(truths)
         and math.isclose(value['distance_m'],math.sqrt(float(rank)),rel_tol=2e-15,abs_tol=0)
         and focus['primary_source_triangle_index']==rows[0]
         and rows[0] in true_case['closest_target_source_triangle_indices']
         and rows[1] in true_case['closest_reference_source_triangle_indices'],
         'nearest_surface_witness_does_not_attain_independent_minimum')
    return {'source_rows':rows,'squared_distance_m2':str(rank),'distance_m':value['distance_m'],
            'point_encoding':witness['point_encoding'],'method':value['method']}


def actual_frame(folder,frame,domain,target,truth,group,primary,ref,actual_png):
    import numpy as np
    entry,_,png,npz=old.independent_frame(folder,frame,domain,target,sorted(set(truth)|set(group)),
                                         primary,ref,actual_png)
    counts=entry.pop('task_pixels_by_source_row')
    right=sum(counts[str(r)] for r in truth)
    anchor=None
    if right:
        with np.load(npz,allow_pickle=False) as data:
            d,owners,ids=(data[k] for k in ('depth','owners','triangle_ids'))
            rows=ids-int(domain['offsets'][target])
            locations=np.flatnonzero((owners==target)&np.isfinite(d)&(d>0)&np.isin(rows,truth))
            need(len(locations)==right,'true_piece_pixels_not_current_finite_samples')
            r,c=divmod(int(locations[0]),d.shape[1])
            anchor={'row':r,'column':c,'source_triangle_index':int(rows[r,c])}
    entry.update(task_pixels=right,group_pixels=sum(counts[str(r)] for r in group),
                 verified_truth_pixel=anchor,png=png.relative_to(folder).as_posix(),npz=npz.relative_to(folder).as_posix(),
                 camera=frame['pose'])
    return entry,{png,npz}


def score_request(folder,arm,label,job,row,case,domain,audit):
    key=row['id']
    prefix=folder/f'{key:02d}-{label}'
    tx,rx=prefix.with_suffix('.tx'),prefix.with_suffix('.rx')
    req,rep=read(tx),read(rx)
    need(pin(tx)=={'sha256':row['tx_sha'],'bytes':row['tx']}
         and pin(rx)=={'sha256':row['rx_sha'],'bytes':row['rx']}
         and req['id']==rep['id']==key
         and req['method']=='tools/call'
         and req['params']=={'name':'human_eye_scene_observe','arguments':job['arguments']},
         'not_the_registered_original_MCP_exchange')
    result=rep.get('result',{})
    if result.get('isError') or 'error' in rep:
        return {'status':'rejected','facts':result.get('content',rep.get('error'))},set()
    blocks=result['content']
    texts=[json.loads(item['text']) for item in blocks if item['type']=='text']
    pictures=[item for item in blocks if item['type']=='image']
    need(len(texts)==1 and len(pictures)+len(texts)==len(blocks),'invalid_MCP_block_shape')
    body,=texts
    focus,binding=body['facts']['focus'],body['binding']
    proc_path=folder/f'producer_{key:02d}.json'
    phys_path=folder/f'construction_{key:02d}.json'
    producer=read(proc_path)
    construction=read(phys_path)
    need(body['read_only'] and not body['execution_authority']
         and body['result_kind']=='active_observation' and body['observation_status']=='directed_focus'
         and focus==producer['facts']['focus'] and focus['selection']==job['arguments']['query']['focus']
         and all(body[x]==producer[x] for x in ('binding','work','status','session_id'))
         and focus['minimum_sample_pixels']==PIXELS and focus['complete_surface_visibility']=='unknown',
         'unexpected_focus_payload_or_publication')
    captured=domain['capture']
    for obj,name in ((focus['object'],job['arguments']['query']['objects'][0]['name']),
                     (focus['reference'],case['reference_name'])):
        idx=obj['object_index']
        need(type(idx) is int and 0<=idx<len(domain['ids'])
             and obj['object_name']==name==captured['meshes'][idx]['name']
             and domain['ids'][idx]==obj['host_id'] and domain['instances'][obj['host_id']]==obj['instance_id'],
             'wrong_current_object_instance')
    target=focus['object']['object_index']
    group,primary=focus['task_source_triangle_indices'],focus['primary_source_triangle_index']
    ref=focus['region_ref']
    state=captured['capture_state']
    need(focus['scope']==('one_current_evaluated_source_triangle' if arm=='b'
                          else 'multiple_current_evaluated_source_triangles')
         and group==ref['source_triangle_indices']==sorted(set(group)) and primary in group
         and all(type(i) is int and 0<=i<len(captured['meshes'][target]['faces']) for i in group)
         and ref['instance_id']==focus['object']['instance_id']
         and ref['host_id']==focus['object']['host_id']
         and ref['capture_generation']=={k:state[k] for k in ('instance_id','epoch','revision')}
         and ref['document_epoch']==binding['document_epoch']==captured['host_identity']['document_epoch']
         and ref['ordered_geometry_sha256']==domain['geometry_sha']
         and ref['region_id']=='source-region:'+old.fingerprint({k:v for k,v in ref.items() if k!='region_id'})
         and binding['capture_state']==state and binding['scene_revision']==captured['revision']
         and binding['display_identity']==domain['display_sha'],'stale_focus_selection')
    measured=None
    if arm=='b':
        need(group==[primary],'non_winner_neighbor_added')
        measured=verify_exact_witness(focus,domain,case)
        need(body['work']['surface_pair_count']==1 and body['work']['surface_pair_cache_hit'] is False,
             'cold_B_lookups_not_one_actual_surface_search')
    else:
        need(group==case['candidate_aabb_nominee_source_triangle_indices']
             and 'nearest_surface' not in focus and 'surface_pair_count' not in body['work'],
             'old_AABB_selection_changed')
    trace,events=old.trace_for(audit,key)
    rendered=[e['view_name'] for e in events if e.get('event')==old.RENDER_EVENT]
    views=focus['views']
    real=construction['raster_calls']
    frames=producer['constructed_frames']
    public=body['frames']
    solves=construction['m3_actual_solver_calls']
    captures=construction['capture_calls']
    need(len(solves)==int(arm=='b') and len(captures)==1
         and all(e['completed'] and construction['service_started_ns']<=e['started_ns']
                 <=e['closed_ns']<=construction['service_returned_ns'] for e in solves+captures),
         'actual_M3_or_capture_count_mismatch')
    need(construction['id']==key and construction.get('result_recorded') is True
         and not construction['limit_exceeded']
         and row['started_ns']<=construction['service_started_ns']<=construction['service_returned_ns']<=row['returned_ns']
         and all(r['completed'] and construction['service_started_ns']<=r['started_ns']<=r['closed_ns']
                 <=construction['service_returned_ns'] for r in real)
         and 0<len(real)==len(rendered)==len(frames)==row['new_rasters']==body['work']['raster_attempts']<=2
         and rendered==[f['view_name'] for f in frames]==[v['view_name'] for v in views]
         and len(pictures)==len(public)==len(producer['frames'])<=1
         and len(pictures)==trace['annotations']['mcp_native_image_block_count']
         and all(all(raw[k]==v for k,v in thin.items()) for raw,thin in zip(producer['frames'],public,strict=True)),
         'first_or_final_real_frames_not_in_original_raster_ledger')
    files,attempts,delivered=set(),[],None
    for frame,view in zip(frames,views,strict=True):
        published=bool(public and frame['frame_identity']==public[0]['frame_identity'])
        rgb=None
        if published:
            need(pictures[0]['mimeType']=='image/png','published_native_block_not_PNG')
            rgb=base64.b64decode(pictures[0]['data'],validate=True)
        item,current=actual_frame(folder,frame,domain,target,case['nearest_source_triangle_indices'],
                                  group,primary,ref,rgb)
        need(not files&current,'attempt_frames_reused')
        files.update(current)
        item['delivered']=published
        need(item['group_pixels']==view['verified_pixels']
             and item['first_source_pixels']==view['primary_verified_pixels'],'source_pixel_count_not_independent')
        if published:
            delivered=item
        attempts.append(item)
    sample=focus['sample']
    if delivered and delivered['group_pixels']:
        need(sample['frame_identity']==delivered['frame_identity'] and sample['image_ref']==delivered['image_ref']
             and sample['selected_surface_pixels']==delivered['group_pixels'],'wrong_delivered_sample_binding')
        point=sample['sampled_pixel']
        actual=intent.prove_pixel(folder/delivered['npz'],captured,target,point['row'],point['column'])
        need(actual['source_triangle_index']==point['source_triangle_index'] in group,'wrong_claimed_source_pixel')
    stop=focus['stop_reason']
    need((stop=='sample_target_met')==bool(delivered and delivered['group_pixels']>=PIXELS)
         and (attempts[0]['group_pixels']<PIXELS or len(attempts)==1),'stop_decision_not_attached_to_group')
    return {'status':'observed','primary_source_triangle_index':primary,
            'primary_hit':primary in case['nearest_source_triangle_indices'],'witness':measured,
            'first_task_pixels':attempts[0]['task_pixels'],'first_hit':attempts[0]['task_pixels']>=PIXELS,
            'delivered_task_pixels':delivered['task_pixels'] if delivered else 0,
            'delivered_hit':bool(delivered and delivered['task_pixels']>=PIXELS),'raster_attempts':len(real),
            'physical_raster_ns':sum(r['closed_ns']-r['started_ns'] for r in real),
            'actual_M3_searches':len(solves),'actual_M3_ns':sum(s['closed_ns']-s['started_ns'] for s in solves),
            'actual_capture_count':len(captures),'actual_capture_ns':sum(c['closed_ns']-c['started_ns'] for c in captures),
            'stop':stop,'attempts':attempts,'client_rtt_ms':row['rtt_ms'],'work':body['work'],
            'stage_elapsed_ns':{k:v['elapsed_ns'] for k,v in producer['stages'].items()
                                if type(v) is dict and 'elapsed_ns' in v},
            'MCP_TX':pin(tx),'MCP_RX':pin(rx),'producer':pin(proc_path),'rasters':pin(phys_path)},files


def verified_slot(root,arm,job,geometry,truth):
    folder=root/'slots'/arm.upper()
    if not (folder/'ledger.json').is_file():
        return {'closed':False,'cases':{tag:{'status':'unrun'} for tag in ORDER}}
    ledger=read(folder/'ledger.json')
    cases={}
    try:
        started,closed=read(folder/'ready.json'),read(folder/'closed.json')
        need(ledger['stdout_eof'] and ledger['server_exit']==closed['blender_exit']==0
             and started['pid']==closed['pid'] and started['source_kind']=='installed_distribution'
             and started['source_sha256']==job['candidate_source_sha256']
             and started['source_files']==len(job['runtime_sources'])
             and started['fixture_before']==closed['fixture_after']==pin(folder/'input.blend')['sha256']
               ==truth['asset_sha256']==ledger['fixture_sha'], 'formal_slot_did_not_close_current_fixture')
        end=closed['post_capture']
        need(intent.checked_pin(end['path'])==folder/'post_capture.json'
             and all(r.get('returned_ns',r.get('started_ns',0))<=end['started_ns'] for r in ledger['requests'])
             and end['started_ns']<=end['closed_ns']<=closed['native_close_started_ns']<=closed['closed_ns'],
             'terminal_source_read_not_bound_by_lifecycle')
        capture=read(folder/'post_capture.json')
        domain=intent.bind_geometry(capture,geometry)
        native=intent.previous.worker_custody(folder)
        registered=read(folder/'REGISTRATION_ADMISSION.json')
        need(registered['passed'] is True
             and set(registered['dispatches'])==set(ORDER)
             and intent.checked_pin(registered['attempts'])==folder/'REGISTRATION_ATTEMPTS.jsonl',
             'final_registration_receipt_mismatch')
        audit=[json.loads(line) for line in (folder/'audit.jsonl').read_bytes().splitlines()]
        order=[r['label'] for r in ledger['requests']]
        need(order[:2]==['init','tools'] and tuple(order[2:])==ORDER[:len(order)-2] and len(order)<=4,
             'unexpected_formal_ledger_order')
        initialize=read(folder/'01-init.rx')
        need(initialize['result']['_meta']['human_eye']['source_sha256']==job['candidate_source_sha256'],
             'formal_mcp_runtime_identity_mismatch')
        tools=read(folder/'02-tools.rx')['result']['tools']
        tool,=[t for t in tools if t['name']=='human_eye_scene_observe']
        needle=tool['inputSchema']['properties']['query']['properties']['focus']
        need(('nearest_surface' in json.dumps(needle))==(arm=='b'),'formal_MCP_schema_not_actual_arm')
    except (ValueError,KeyError,IndexError,TypeError,OSError) as error:
        labels={r.get('label') for r in ledger['requests']}
        return {'closed':False,'failure':str(error),
                'cases':{tag:{'status':'unverified' if tag in labels else 'unrun'} for tag in ORDER}}
    artifacts=set()
    for row in ledger['requests'][2:]:
        tag=row['label']
        try:
            cell,paths=score_request(folder,arm,tag,job['requests'][row['id']-3],row,truth['cases'][tag],domain,audit)
            need(not paths&artifacts,'cross_request_images')
            artifacts.update(paths)
            registration=registered['dispatches'][tag]
            need(intent.checked_pin(registration['tx'])==folder/f"{row['id']:02d}-{tag}.tx"
                 and intent.checked_pin(registration['rx'])==folder/f"{row['id']:02d}-{tag}.rx"
                 and (registration['m3_actual_solver_calls'],registration['capture_calls'],registration['raster_calls'])
                   ==(cell['actual_M3_searches'],cell['actual_capture_count'],cell['raster_attempts']),
                 'unbound_formal_registration')
            cell['worker_wire']=native[tag]
            cases[tag]=cell
        except (ValueError,KeyError,IndexError,TypeError,OSError) as error:
            cases[tag]={'status':'unverified','reason':str(error)}
    for tag in ORDER:
        cases.setdefault(tag,{'status':'unrun'})
    image_dir=folder/'state.json.active_observation'
    complete=all(v['status']=='observed' for v in cases.values()) and \
        artifacts==set(image_dir.glob('**/*.png'))|set(image_dir.glob('**/*.npz'))
    return {'closed':True,'cases_complete':complete,'cases':cases,'closure':pin(folder/'closed.json'),
            'current_source':pin(folder/'post_capture.json'),
            'owned_wall_ns':ledger['closed_ns']-ledger['started_ns']}


def evaluate(root):
    prep=root/'preflight'
    frozen=read(prep/'FROZEN_EXECUTION.json')
    need(frozen['batch']==BATCH and intent.checked_pin(frozen['formal_plan'])==prep/'FORMAL_PLAN.json',
         'audit_wrong_formal_freeze')
    fixture=frozen['fixture']
    geometry=read(intent.checked_pin(fixture['source']))
    truth=read(intent.checked_pin(fixture['truth']))
    need(set(truth['cases'])==set(ORDER) and frozen['fixture']['blend']['sha256']
         ==truth['asset_sha256']==geometry['asset_sha256']
         and truth['evaluated_source_sha256']==fixture['source']['sha256'],'audit_truth_not_frozen_to_fixture')
    jobs=read(prep/'FORMAL_PLAN.json')['jobs']
    slots={arm:verified_slot(root,arm,jobs[arm.upper()],geometry,truth) for arm in ('a','b')}
    totals={}
    for arm,slot in slots.items():
        cases=tuple(slot['cases'].values())
        totals[arm]={'registered':2,'verified':sum(v['status']=='observed' for v in cases),
                     'unrun':sum(v['status']=='unrun' for v in cases),
                     'failed':sum(v['status'] not in ('unrun','observed') for v in cases)}
        for key in ('primary_hit','first_hit','delivered_hit'):
            totals[arm][key]=sum(v.get(key) is True for v in cases if v['status']=='observed')
        totals[arm]['rasters']=sum(v.get('raster_attempts',0) for v in cases)
    a,b=totals['a'],totals['b']
    gates={'closed_custody':all(v['closed'] and v.get('cases_complete') for v in slots.values()),
           'both_candidate_primaries':b['primary_hit']==2,
           'both_candidate_first_renders':b['first_hit']==2,
           'both_candidate_deliveries':b['delivered_hit']==2,
           'total_raster_budget':a['rasters']<=4 and b['rasters']<=4}
    return {'batch':BATCH,'passed':all(gates.values()),'gates':gates,'counts':totals,'slots':slots}


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root',type=lambda p:Path(p).resolve(strict=True))
    cli.add_argument('output',type=Path)
    args=cli.parse_args()
    intent.save(args.output,evaluate(args.root))

