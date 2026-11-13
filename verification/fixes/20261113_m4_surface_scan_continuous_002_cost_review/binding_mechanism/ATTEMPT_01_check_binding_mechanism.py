"""Independent offline binding and mechanism reconstruction; no author imports."""
import ast,collections,hashlib,json,pathlib,subprocess,traceback
R=pathlib.Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=R/'verification/m4_surface_scan_continuous_consumption_002_cost';S=R/'verification/m4_surface_scan_continuous_consumption_002'
ROOT=pathlib.Path('D:/hefe');Q=ROOT/'verification/fixes/20261113_m4_surface_scan_continuous_002_quality_review'
O=ROOT/'verification/fixes/20261113_m4_surface_scan_continuous_002_cost_review/binding_mechanism'
D='21f08a9826adf5ef44a305e3d6d1898f0dac5e80';OLD='a798caf982e2d7eefe0bf52b739b9bef88526be4';RC='d05cecf6fe3ddfeb19e04518d3d80a8dbdc40488';PRODUCT='452b44d2dcf231d6675bef54e568db0431a29261'
SEAL='ccea554353a6f0607263124d2170ef3b2094a07e222c86276f522184b7f5316c';MARK='HUMAN_EYE_BLENDER_MCP:'
checks=[];inputs={};facts={};runtime_members={}
def sha(b):return hashlib.sha256(b).hexdigest()
def raw(p):
 p=pathlib.Path(p);b=p.read_bytes();inputs[str(p)]={'bytes':len(b),'sha256':sha(b)}
 for rt,members in runtime_members.items():
  if p.is_relative_to(rt):
   assert members[p.relative_to(rt).as_posix()]=={'bytes':len(b),'sha256':sha(b)},'sealed runtime member changed'
 return b
def j(p):return json.loads(raw(p))
def jl(p):return [json.loads(x) for x in raw(p).splitlines() if x]
def ck(name,ok):checks.append({'check':name,'passed':bool(ok)})
def git(*a,cwd=R):return subprocess.check_output(['git',*a],cwd=cwd)
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def tree(commit,cwd=R):
 result={}
 for row in git('ls-tree','-rz',commit,cwd=cwd).split(b'\0'):
  if row:m,path=row.split(b'\t',1);result[path.decode()]=m.split()[2].decode()
 return result
def wire(v):return json.dumps(v,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()+b'\n'
def total(rows,key):return sum(x[key] for x in rows)
def main():
 dt,ot,root_tree=tree(D),tree(OLD),tree(RC,ROOT);rel=B.relative_to(R).as_posix();head=git('rev-parse','HEAD').decode().strip();status=git('status','--porcelain=v1').decode()
 ck('clean fixed cost delivery',head==D and status=='')
 man=j(B/'DELIVERY_MANIFEST.json');order=j(B/'WORK_ORDER.json');seal=j(B/'inputs/QUALITY_SEAL.json');declared=j(B/'INPUTS.json');author=j(B/'mechanism/MECHANISM.json');run=j(S/'RUN_RESULT.json')
 paths={x['path'] for x in man['files']}|{'DELIVERY_MANIFEST.json'};changed={p for p in set(ot)|set(dt) if ot.get(p)!=dt.get(p)}
 ck('exact 29 new cost files and old tree untouched',len(paths)==29 and changed=={rel+'/'+x for x in paths} and not any(rel+'/'+x in ot for x in paths))
 ck('all new content hashes and Git blobs',all(sha(raw(B/x['path']))==x['sha256'] and len(raw(B/x['path']))==x['bytes'] and blob(raw(B/x['path']))==dt[rel+'/'+x['path']] for x in man['files']) and blob(raw(B/'DELIVERY_MANIFEST.json'))==dt[rel+'/DELIVERY_MANIFEST.json'])
 ck('cost parent original and root dispatch ids',man['source_delivery_commit']==man['parent_commit']==order['source_delivery_commit']==OLD and man['root_dispatch_commit']==order['root_commit']==RC and man['quality_seal_sha256']==SEAL)
 for x in order['inputs']:
  p=pathlib.Path(x['source']);b=raw(p);ck('root frozen copied input '+pathlib.Path(x['path']).name,raw(B/x['path'])==b and sha(b)==x['sha256'] and len(b)==x['bytes'] and blob(b)==root_tree[p.relative_to(ROOT).as_posix()])
 ck('root quality seal and its evidence unchanged',sha(raw(Q/'QUALITY_SEAL.json'))==SEAL and all(sha(raw(Q/p))==h for p,h in seal['independent_evidence_sha256'].items()))
 ck('original batch manifest and anonymous ZIP unchanged',sha(raw(S/'DELIVERY_MANIFEST.json'))==seal['delivery_manifest_sha256'] and sha(raw(S/'quality/ANONYMOUS_QUALITY.zip'))==seal['anonymous_package_sha256'])
 for rec in run['records']:
  rt=pathlib.Path(rec['runtime_folder']);mp=pathlib.Path(rec['folder'])/'RUNTIME_MANIFEST.json';mb=raw(mp);ck(rec['cell']+' previous accepted runtime index Git binding',blob(mb)==ot[mp.relative_to(R).as_posix()]);runtime_members[rt]=json.loads(mb)['members']
 scope_count=collections.Counter();bad=[]
 for x in declared['files']:
  p=pathlib.Path(x['path']);b=raw(p);scope=x['provenance'];scope_count[scope]+=1;good=sha(b)==x['sha256']
  if scope=='current_cost_material':good=good and blob(b)==dt[p.relative_to(R).as_posix()]
  elif scope=='sealed_source':good=good and blob(b)==(ot[p.relative_to(R).as_posix()] if p.is_relative_to(R) else root_tree[p.relative_to(ROOT).as_posix()])
  elif scope=='sealed_runtime_archive_member':good=good and any(p.is_relative_to(rt) and members.get(p.relative_to(rt).as_posix())=={'bytes':len(b),'sha256':sha(b)} for rt,members in runtime_members.items())
  else:good=False
  if not good:bad.append(str(p))
 ck('752 INPUTS byte hashes and independently bound provenance',len(declared['files'])==len({x['path'] for x in declared['files']})==752 and not bad and scope_count=={'current_cost_material':11,'sealed_runtime_archive_member':386,'sealed_source':355})
 source_paths=['human_eye_plugin/'+x for x in ['blender_host.py','live_service.py','read_context.py','surface_scan.py','task_query.py','scene_cache.py']];prod_tree=tree(PRODUCT);installed=R/'.human-eye/releases/9.7.2+m4.surface.scan.compact.r1/site-packages'
 ck('six mechanism sources fixed product and installation',all(blob(raw(R/p))==prod_tree[p] and raw(R/p)==raw(installed/p) for p in source_paths))
 aturn={(x['cell'],x['turn_index']):x for x in author['turns']};aep={x['cell']:x for x in author['episodes']};turn_rows=[];mechanisms=[];native=[]
 for rec in run['records']:
  cell=rec['cell'];group=rec['group'];rt=pathlib.Path(rec['runtime_folder']);owner=rt/'owner';er=j(rt/'c/EPISODE_RESULT.json');tools=j(owner/'TOOLS.json');attempts=tools['tools'];events=jl(owner/'native/WORKER_EVENTS.jsonl');byseq={x['sequence']:x for x in events};wi=j(owner/'native/WIRE/INDEX.json');wires=[]
  for w in wi:
   n=w['sequence'];fp=owner/f'native/WIRE/{n:03}';tx,rx=raw(fp/'REQUEST.bin'),raw(fp/'RESPONSE.bin');rq,rs=json.loads(tx),json.loads(rx);event=byseq[n];matches=[x['attempt'] for x in attempts if x['started_ns']<=event['started_ns']<x['started_ns']+x['elapsed_ns']];assert len(matches)<=1
   ck(cell+f' actual WIRE {n}',len(tx)==w['request_bytes'] and len(rx)==w['response_attempted_bytes'] and w['response_sendall_completed'])
   item={'sequence':n,'attempt':matches[0] if matches else None,'tx':len(tx),'rx':len(rx),'request':rq,'response':rs,'event':event};wires.append(item)
  ck(cell+' all host events partitioned exactly once',len(wires)==len(events) and len({x['sequence'] for x in wires})==len(wires) and len([x for x in wires if x['attempt'] is None])==6)
  audits=jl(owner/'audit.jsonl') if group=='C' else [];obs={x['trace_id']:x for x in audits if x.get('event')=='observe'};basepairs={};prior_defs=set();packets=[]
  for t in er['turns']:
   idx=t['turn_index'];fp=pathlib.Path(t['folder']);lo=t['status_before']['business_attempts'];hi=t['status_after']['business_attempts'];selected=[x for x in attempts if lo<x['attempt']<=hi];event_rows=jl(fp/'events.jsonl');complete=[x['event']['item'] for x in event_rows if x['event'].get('type')=='item.completed' and x['event'].get('item',{}).get('type')=='mcp_tool_call'];assert len(complete)==len(selected)
   metrics={'cell':cell,'group':group,'turn_index':idx,'tool_attempts':len(selected),'tool_text_bytes':0,'owner_response_bytes':0,'host_tx_bytes':0,'host_rx_bytes':0,'image_blocks':0,'final_bytes':len(raw(fp/'PUBLIC_FINAL.txt'))};codes=[]
   for attempt,ci in zip(selected,complete):
    n=attempt['attempt'];f=owner/f'tool_{n:02}';req=j(f/'REQUEST.json');res=j(f/'RESPONSE.json');assert req['params']['name']==ci['tool'] and req['params']['arguments']==ci['arguments'];content=res['result']['content'];assert ci['result']['content']==content
    ck(cell+f' tool {n} direct response and CLI content',len(wire(res))==attempt['response_bytes'] and attempt==j(f/'ATTEMPT.json') and attempt['exception'] is None and attempt['is_error'] is False and ci['status']=='completed' and ci['error'] is None)
    metrics['tool_text_bytes']+=sum(len(x['text'].encode()) for x in content if x['type']=='text');metrics['owner_response_bytes']+=len(wire(res));metrics['image_blocks']+=sum(x['type']=='image' for x in content);host=[x for x in wires if x['attempt']==n];metrics['host_tx_bytes']+=total(host,'tx');metrics['host_rx_bytes']+=total(host,'rx')
    if req['params']['name']=='execute_blender_code':
     code=req['params']['arguments']['code'];treecode=ast.parse(code);defs={x.name for x in ast.walk(treecode) if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))};calls={x.func.id for x in ast.walk(treecode) if isinstance(x,ast.Call) and isinstance(x.func,ast.Name)};attrs={x.func.attr for x in ast.walk(treecode) if isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute)};reused=sorted((calls&prior_defs)-defs)
     evalnames={q.id for x in ast.walk(treecode) if isinstance(x,ast.Assign) and isinstance(x.value,ast.Call) and isinstance(x.value.func,ast.Attribute) and x.value.func.attr=='evaluated_get' for q in x.targets if isinstance(q,ast.Name)};data=any(isinstance(x,ast.Attribute) and x.attr=='data' and isinstance(x.value,ast.Name) and x.value.id in evalnames for x in ast.walk(treecode));matmul=any(isinstance(x,ast.MatMult) for x in ast.walk(treecode));prior_defs|=defs
     ck(cell+f' code {n} actual worker execution',len(host)==1 and host[0]['request']['params']['code']==code and host[0]['event']['script_sha256']==sha(code.encode()) and host[0]['event']['status']=='completed')
     codes.append({'attempt':n,'prior_calls':reused,'current_mesh':'to_mesh' in attrs or data,'triangulate':'calc_loop_triangles' in attrs,'world_matmul':matmul,'code_sha256':sha(code.encode())})
    else:
     observation=json.loads(content[0]['text']);work=obs[observation['trace_id']]['task_work'];pairs=work.get('pairs',{});hits={k for k,v in pairs.items() if v['surface_pair_cache_hit']};misses=set(pairs)-hits
     ck(cell+f' turn{idx} independent pair rows tally',len(hits)==work['cache_hits'] and len(misses)==work['kernel_calls'] and len(pairs)==work['pair_calls'] and all(v['surface_dependency_used'] for v in pairs.values()))
     frames=[]
     for h in host:
      txt=h['response'].get('result',{}).get('result','');lines=[line[len(MARK):] for line in txt.splitlines() if line.startswith(MARK)]
      for line in lines:frames.append((json.loads(line)['result'],h['event'],len(line.encode())))
     assert len(frames)==1
     packet,hevent,framebytes=frames[0];packets.append(packet);capture=packet['capture'];delta=capture['work']['residency_delta'];cache=work['measurement_cache_after'];common=set(basepairs)&set(pairs);changed={k for k in common if basepairs[k]['surface_dependency_key']!=pairs[k]['surface_dependency_key']};unchanged=common-changed;new=set(pairs)-set(basepairs);names={o['id']:o['name'] for o in observation['objects']}
     ck(cell+f' turn{idx} host packet work matches audit',capture['work']==work['acquisition_work'] and capture['binding']==observation['binding'])
     if idx==1:basepairs=pairs
     if idx==3:ck(cell+' EDIT 104 reuse 8 changed 2 new with exact affected object',len(unchanged)==104 and len(changed)==8 and len(new)==2 and unchanged==hits and changed|new==misses and all('Obj_008' in [names[q] for q in json.loads(k)] for k in changed|new))
     mechanism={'cell':cell,'turn_index':idx,'kernel_calls':len(misses),'pair_cache_hits':len(hits),'result_cache_hit':work['result_cache_hit'],'resources':len(packet['resources']),'resource_vertices':sum(len(x['vertices_local']) for x in packet['resources']),'world_transforms':delta['world_transforms'],'world_vertices':delta['world_vertices_transformed'],'resource_builds':delta['resource_builds'],'frame_json_bytes':framebytes,'accounted_payload_allowance_bytes':cache['accounted_bytes'],'changed_dependency_pairs':len(changed),'new_candidate_pairs':len(new) if idx>1 else 0,'scene_revision':capture['capture']['revision']};mechanisms.append(mechanism)
     ck(cell+f' turn{idx} author mechanism direct facts',all(aturn[(cell,idx)]['plugin_mechanism'][0][k]==mechanism[k] for k in ['kernel_calls','result_cache_hit']) and aturn[(cell,idx)]['plugin_mechanism'][0]['acquisition_work']==capture['work'])
   if group=='N' and idx>1:
    expected={'N1':'triangle_surface_distance','N2':'surface_distance','N3':'tri_pair_distances'}[cell];reused=set(q for x in codes for q in x['prior_calls']);ck(cell+f' turn{idx} current reacquisition plus prior algorithm',expected in reused and any(x['current_mesh'] and x['triangulate'] and x['world_matmul'] for x in codes));native.append({'cell':cell,'turn_index':idx,'reused':sorted(reused),'scripts':codes})
   aa=aturn[(cell,idx)];ck(cell+f' turn{idx} all layers match author rows',metrics['tool_attempts']==aa['tool_attempts'] and metrics['tool_text_bytes']==aa['consumer_visible_tool_text_utf8_bytes'] and metrics['owner_response_bytes']==aa['owner_encoded_response_bytes'] and metrics['host_tx_bytes']==aa['host_business_wire']['request_bytes'] and metrics['host_rx_bytes']==aa['host_business_wire']['response_bytes'] and metrics['final_bytes']==aa['final_answer_utf8_bytes'] and metrics['image_blocks']==0);turn_rows.append(metrics)
  if group=='C':
   captures=[p['capture']['capture'] for p in packets];msets=[{m['name']:m['_scene_resource'] for m in x['meshes']} for x in captures];resource={r['id']:r for r in packets[0]['resources']};changed=[name for name in msets[0] if msets[0][name]!=msets[2][name]];res0=msets[0]['Obj_008'];res2=msets[2]['Obj_008']
   ck(cell+' exact resources residency and sole 8-point pose change',len(resource)==24 and all(p['live_resources']==packets[0]['live_resources'] for p in packets) and [len(p['resources']) for p in packets]==[24,0,0] and len({x['capture_state']['instance_id'] for x in captures})==1 and [x['revision'] for x in captures]==[1,1,2] and msets[0]==msets[1] and changed==['Obj_008'] and res0['id']==res2['id'] and res0['revision']==res2['revision'] and len(resource[res0['id']]['vertices_local'])==8)
   rows=[x for x in mechanisms if x['cell']==cell];ck(cell+' complete reconstructed counter progression',[x['kernel_calls'] for x in rows]==[112,0,10] and [x['pair_cache_hits'] for x in rows]==[0,0,104] and [x['world_transforms'] for x in rows]==[24,0,1] and [x['world_vertices'] for x in rows]==[530,0,8] and [x['resource_builds'] for x in rows]==[24,0,0] and [x['accounted_payload_allowance_bytes'] for x in rows]==[181984,181984,198307])
 summary={g:{k:sum(x[k] for x in turn_rows if x['group']==g) for k in ['tool_attempts','tool_text_bytes','owner_response_bytes','host_tx_bytes','host_rx_bytes','image_blocks','final_bytes']} for g in ['N','C']}
 expected={'N':[19,60398,63239,37856,60417,0,27350],'C':[9,71202,77820,301215,1036542,0,26828]};ck('group sums independently reproduced',all(list(summary[g].values())==expected[g] for g in expected))
 ck('author failures retained and unchanged',j(B/'mechanism/attempts/01/ISSUE.json')['originals_changed'] is False and sha(raw(B/'mechanism/attempts/01/build_mechanism.py'))==j(B/'mechanism/attempts/01/ISSUE.json')['source_sha256'] and sha(raw(B/'mechanism/attempts/01/MECHANISM.json'))==j(B/'mechanism/attempts/01/ISSUE.json')['result_sha256'])
 ck('author tree unchanged after offline review',git('rev-parse','HEAD').decode().strip()==head and git('status','--porcelain=v1').decode()==status)
 facts.update(delivery_files=29,inputs752=dict(scope_count),group_summary=summary,turns=turn_rows,plugin_mechanism=mechanisms,native_followups=native,AL_current=False,AL_own_write=611,AL_parent_write=632)
 facts['limits']=['Checks describe the same six episodes; no new experiments or ablation.','Payload/entry accounted bytes are not cache RAM; peak RSS is process-lifetime peak.','CLI tool text is not provider serialized input or billed tokens.','N reuses algorithms and reacquires current geometry; dynamic native kernel counts unknown.','Whole-task time and usage reviewed independently elsewhere.','18 thin EXIT unknown and prior failed batches remain unchanged.']
if __name__=='__main__':
 O.mkdir(parents=True,exist_ok=True)
 try:main()
 except Exception:checks.append({'check':'independent script exception','passed':False,'traceback':traceback.format_exc()})
 result={'all_passed':all(x['passed'] for x in checks),'checks':len(checks),'failed':[x for x in checks if not x['passed']],'input_paths':len(inputs),'facts':facts,'new_model_Blender_product_API_runs':0}
 for name,value in [('RESULTS.json',result),('CHECKS.json',checks),('INPUT_HASHES.json',inputs)]: (O/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print(json.dumps({k:v for k,v in result.items() if k!='facts'},ensure_ascii=False,indent=2))
