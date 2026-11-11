"""Saved-record mechanism audit. No evaluated model code or runtime imports."""
import hashlib,json
from pathlib import Path
OUT=Path(__file__).resolve().parent
BASE=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_selected_geometry_consumption_001')
REVIEW=OUT.parent
pins={}
def raw(p):
    data=p.read_bytes();pins[str(p)]=hashlib.sha256(data).hexdigest();return data
def rd(p):return json.loads(raw(p))
def text(p):return raw(p).decode('utf8')
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()

seal=rd(REVIEW/'QUALITY_SEAL.json')
assert seal['source_commit']=='de35ceda1f5e3f5af2c9ec02f0e4646808f417c2'
assert seal['root_complete_correct']==seal['fresh_independent_complete_correct']==seal['denominator']==9
mapping=rd(BASE/'private/ANON_MAP.json')
manual={
 'sgc01':{'route':'native directory -> native cached coordinates plus live polygons and derived centers', 'prior_program_cache':'Full world coordinates for all meshes stored in verts by call1; call1 exposes bounds/centers only.', 'post_relation_supplements':None,'post_relation_classes':[], 'original_native_geometry_delivery_call':2},
 'sgc02':{'route':'native directory -> relations -> mixed native shape and reference supplement', 'prior_program_cache':'No whole-scene coordinate cache; coords(o) rereads object vertices.', 'post_relation_supplements':1,'post_relation_classes':['in_scope_geometry_information:new_scene_read:N16','out_of_set_reference_information:new_scene_read:N12,N24','repeated_center_or_simple_distance:N15,N16,N18,N25,N04,N19'], 'mixed_calls':[3]},
 'sgc03':{'route':'native directory -> relations+full geometry -> outside-reference shapes and repeated centers', 'prior_program_cache':'Object references/functions only; complete N16 arrays were not model-visible before relation.', 'post_relation_supplements':0,'post_relation_classes':['out_of_set_reference_information:new_scene_read:N24,N12,N04,N19','repeated_center_or_simple_distance:new_scene_read_and_compute:N15,N18,N25,N16'], 'mixed_calls':[3], 'remaining_call_note':'bounds(objs[N16]) internally rereads vertices, but delivers only repeated center/arithmetic, not new in-scope local shape.'},
 'sgc04':{'route':'native directory/cache -> relations -> cached arrays first printed to model and center arithmetic', 'prior_program_cache':'Full world coordinates for all meshes stored in verts by call1; only bounds/centers exposed then.', 'post_relation_supplements':1,'post_relation_classes':['in_scope_geometry_information:consumer_cache_print:N16','out_of_set_reference_information:consumer_cache_print:N12,N24,N04,N19','repeated_center_or_simple_distance:consumer_cache_compute:N15,N16,N18,N25'], 'mixed_calls':[3], 'remaining_call_note':'Zero new scene acquisition in call3 does not remove this first model-visible local-shape delivery or its round trip.'},
 'sgc05':{'route':'native directory -> relations+full geometry -> final', 'prior_program_cache':'Loop coordinate buffer, not a whole-scene coordinate cache; only bounds/centers exposed.', 'post_relation_supplements':0,'post_relation_classes':[]},
 'sgc06':{'route':'native directory -> native vertices/faces -> fresh bounds checks and arithmetic/modifier read', 'prior_program_cache':'Loop coordinate buffer; no whole-scene stored vertex dictionary.', 'post_relation_supplements':None,'post_relation_classes':[], 'original_native_geometry_delivery_call':2,'native_third_call':'Reacquires bounds/centers, computes checks/gap from existing geometry and reads modifiers; not a repeated plugin solve because no plugin relation exists.'},
 'sgc07':{'route':'native directory -> relations+full geometry -> final', 'prior_program_cache':'Loop coordinate buffer, not whole-scene stored vertex dictionary; only bounds/centers exposed.', 'post_relation_supplements':0,'post_relation_classes':[]},
 'sgc08':{'route':'native directory -> native full-world cache plus selected vertex/face print and arithmetic', 'prior_program_cache':'Call2 creates world dictionary; call1 did not expose complete per-object shape arrays.', 'post_relation_supplements':None,'post_relation_classes':[], 'original_native_geometry_delivery_call':2},
 'sgc09':{'route':'native directory -> relations -> native local shape plus repeated center arithmetic', 'prior_program_cache':'Loop coordinate buffer only; call3 directly rereads vertices.', 'post_relation_supplements':1,'post_relation_classes':['in_scope_geometry_information:new_scene_read:N16,N13,N28','repeated_center_or_simple_distance:new_scene_read_and_compute:N15,N16,N18,N25'], 'mixed_calls':[3]}
}
cells=[]
for item in mapping['rows']:
    cell=BASE/'cells'/item['cell']; consumer=rd(cell/'CONSUMER.json')
    final=text(cell/'PUBLIC_FINAL.txt'); close=rd(cell/'owner/CLOSE.json')
    assert consumer['final']==final and consumer['external_group']==item['group']
    events=[json.loads(line) for line in text(cell/'events.jsonl').splitlines() if line]
    completed=[e['event']['item'] for e in events if e['event'].get('type')=='item.completed' and e['event'].get('item',{}).get('type')=='mcp_tool_call']
    worker=[json.loads(line) for line in text(cell/'owner/native/WORKER_EVENTS.jsonl').splitlines() if line]
    folders=sorted((cell/'owner').glob('tool_*'))
    assert len(folders)==len(completed)==close['tool_attempts']
    row={k:item[k] for k in ('cell','group','round')}
    row.update(manual[item['cell']]);row['quality_complete_correct']='sealed; not rescored by this audit'
    row['total_tool_attempts']=len(folders)
    row['physical_worker_RPC_including_snapshots_and_close']=len(worker)
    row['legacy_close_event_status']=worker[-1]['status']
    row['tool_calls']=[];row['geometry_requested']=False;row['geometry_correctly_used']=False
    row['source_records']={'final':str(cell/'PUBLIC_FINAL.txt'),'consumer':str(cell/'CONSUMER.json'),'closure':str(cell/'owner/CLOSE.json')}
    assert close['geometry_unchanged'] and close['asset_unchanged'] and close['confirmed']
    assert close['worker_closed']['initial_geometry_fingerprint']==close['worker_closed']['final_geometry_fingerprint']
    for idx,(folder,event) in enumerate(zip(folders,completed,strict=True),1):
        req=rd(folder/'REQUEST.json');resp=rd(folder/'RESPONSE.json');attempt=rd(folder/'ATTEMPT.json')
        assert req['params']['name']==event['tool'] and req['params']['arguments']==event['arguments']
        assert resp['result']['content']==event['result']['content'] and event['status']=='completed' and event.get('error') is None
        assert resp['result']['isError'] is False and attempt['is_error'] is False and attempt['exception'] is None
        assert worker[idx]['sequence']==idx+1 and worker[idx]['status']=='completed'
        assert attempt['started_ns']<=worker[idx]['started_ns']<=attempt['started_ns']+attempt['elapsed_ns']
        call={'index':idx,'name':req['params']['name'],'request':str(folder/'REQUEST.json'),'response':str(folder/'RESPONSE.json'),'attempt':str(folder/'ATTEMPT.json'),'response_bytes':attempt['response_bytes'],'worker_sequence':worker[idx]['sequence'],'public_delivery_content_matches_owner':True}
        if call['name']=='human_eye_spatial_relations':
            doc=json.loads(resp['result']['content'][0]['text'])
            assert doc['target']['name']=='N16' and [x['name'] for x in doc['candidates']]==['N13','N08','N28']
            source='4ebc3910652ee461d9fa7476c8df0ecf6312580d6a02e1066c0eac88bef5c76c' if item['group']=='G' else '53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732'
            assert doc['context']['runtime_source_sha256']==source and doc['context']['selected_count']==4 and doc['status']=='observed'
            call['context']=doc['context'];call['selected_names']=[doc['target']['name']]+[x['name'] for x in doc['candidates']]
            call['relations']=[{'name':x['name'],'class':x['closed_solid_relation']['value'],'surface_distance_m':x['surface_proximity']['value']['distance_m']} for x in doc['candidates']]
            if item['group']=='G':
                arg=req['params']['arguments']['geometry'];g=doc['geometry'];by_name={x['name']:x for x in g['objects']}
                assert arg['include_triangles'] is True and {x['name'] for x in arg['objects']}==set(by_name)=={'N16','N13','N08','N28'}
                binding={x['name']:x['object_id'] for x in [doc['target'],*doc['candidates']]}
                for obj in g['objects']:
                    assert obj['object_id']==binding[obj['name']]
                    assert all(len(t)==3 and all(0<=i<len(obj['vertices_world']) for i in t) for t in obj['triangles'])
                frame=by_name['N16']['vertices_world'];rod=by_name['N28']['vertices_world']
                levels={axis:sorted({p[k] for p in frame}) for k,axis in enumerate('xyz')}
                assert len(levels['x'])==4 and len(levels['y'])==2 and len(levels['z'])==4
                assert all(t in final for t in ('0.135','0.225','0.325','0.395','0.245','0.100','0.360'))
                row['geometry_requested']=row['geometry_correctly_used']=True
                row['adoption_scope']='Externally supported use of previously unexposed N16 opening/material extents and correct relation evidence; not a claim about hidden attention or every returned field.'
                row['geometry_fields_added']='Complete current captured world vertices and triangle connectivity for N16/N13/N08/N28; call1 only exposed bounds/centers.'
                row['adoption_final_feature_evidence']={'frame_inner_x':levels['x'][1:3],'frame_inner_z':levels['z'][1:3],'frame_y_extent':levels['y'],'rod_x':[min(p[0] for p in rod),max(p[0] for p in rod)],'rod_z':[min(p[2] for p in rod),max(p[2] for p in rod)],'strict_interior_point_used_in_final':[.245,.1,.36]}
                call['geometry_counts']={x['name']:{'vertices':len(x['vertices_world']),'triangles':len(x['triangles'])} for x in g['objects']}
                call['geometry_sha256']=digest(g);call['geometry_contract']=g['contract']
            else: assert 'geometry' not in req['params']['arguments'] and 'geometry' not in doc
        else:
            call['code']=req['params']['arguments']['code']
            parsed=json.loads(resp['result']['content'][0]['text'])
            assert parsed['status']=='success' and parsed['result']['executed'] is True
            call['delivered_stdout_bytes']=len(parsed['result']['result'].encode())
        row['tool_calls'].append(call)
    if item['group']=='G':row['avoided_same_class_local_supplement']=row['post_relation_supplements']==0 and row['geometry_correctly_used']
    row['relation_recomputation_tool_attempts_after_plugin']=0 if item['group'] in ('P','G') else None
    row['in_scope_complete_geometry_repeat_attempts_after_plugin']=0 if item['group'] in ('P','G') else None
    row['mixed_tool_attempts']=len(row.get('mixed_calls',[]))
    row['out_of_set_new_shape_attempts']=1 if item['cell'] in ('sgc02','sgc03','sgc04') else 0
    cells.append(row)

totals={group:{'tool_attempts':sum(x['total_tool_attempts'] for x in cells if x['group']==group),'physical_worker_RPC':sum(x['physical_worker_RPC_including_snapshots_and_close'] for x in cells if x['group']==group),'tool_response_bytes':sum(c['response_bytes'] for x in cells if x['group']==group for c in x['tool_calls'])} for group in ('N','P','G')}
g=[x for x in cells if x['group']=='G'];p=[x for x in cells if x['group']=='P']
mechanism={'natural_geometry_requested':sum(x['geometry_requested'] for x in g),'correctly_used_and_same_class_supplement_avoided':sum(x['avoided_same_class_local_supplement'] for x in g),'G_same_class_local_supplement_attempts':sum(x['post_relation_supplements'] for x in g),'P_same_class_local_supplement_attempts':sum(x['post_relation_supplements'] for x in p),'passed_frozen_gate':all(x['avoided_same_class_local_supplement'] for x in g) and sum(x['post_relation_supplements'] for x in g)<sum(x['post_relation_supplements'] for x in p),'actual_tool_calls_G_vs_P':[totals['G']['tool_attempts'],totals['P']['tool_attempts']],'actual_tool_calls_G_vs_N':[totals['G']['tool_attempts'],totals['N']['tool_attempts']]}
assert mechanism['correctly_used_and_same_class_supplement_avoided']==3 and mechanism['G_same_class_local_supplement_attempts']==0 and mechanism['P_same_class_local_supplement_attempts']==3
assert totals['N']['tool_attempts']==7 and totals['P']['tool_attempts']==9 and totals['G']['tool_attempts']==7
assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==value for path,value in pins.items())
report={'source_commit':seal['source_commit'],'quality_seal_sha256':pins[str(REVIEW/'QUALITY_SEAL.json')],'quality_fixed_before_mechanism':True,'method':'Read raw owner requests/responses/attempts, exact public completed content, consumer finals and source/closure records; classify externally observable information operations. No model code executed.','mechanism':mechanism,'totals':totals,'cells':cells,'source_sha256':pins,'new_product_processes':0,'new_Blender_sessions':0,'new_model_consumers':0,'new_images':0,'source_unchanged':True,'limits':['Token and cost acceptance belongs to separate cost audit; bytes do not identify exact token attribution.','Legacy worker close events remain unknown; confirmed separate close/exit records do not relabel those events.','No new PRODUCT_RUNTIME_PROOF or thin-client EXIT was inferred.','Quality was sealed 9/9 by root and fresh scorer and is not changed by route classification.']}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_bytes((json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode())
print(json.dumps({'mechanism':mechanism,'totals':totals,'source_records':len(pins)},ensure_ascii=False))
