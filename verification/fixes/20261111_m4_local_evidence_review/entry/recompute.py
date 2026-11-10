"""Independent evidence reads only. No product, Blender, model or author code import."""
from pathlib import Path
import ast,base64,collections,csv,hashlib,io,json,statistics,subprocess,tarfile,zipfile
WT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE=WT/'verification/m4_local_relation_evidence_001'
PREV=WT/'verification/m4_observation_baseline_001'
OUT=Path(__file__).resolve().parent
SOURCES={}
def sha(b):return hashlib.sha256(b).hexdigest()
def raw(p):
 p=Path(p);b=p.read_bytes();SOURCES[str(p)]=sha(b);return b
def read(p):return json.loads(raw(p))
def lines(p):return [json.loads(x) for x in raw(p).splitlines() if x]
def compact(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def check(c,message):
 if not c:raise AssertionError(message)
def git(*args):return subprocess.check_output(['git','-C',str(WT),*args])
def stats(v):return dict(samples=v,sum=sum(v),median=statistics.median(v),min=min(v),max=max(v))
head=git('rev-parse','HEAD').decode().strip();status_before=git('status','--short').decode()
check(head=='e6a620cd68e23b87dc60387eb28a9d70411e6ec8','fixed evidence HEAD')
index=read(BASE/'EVIDENCE_INDEX.json');included=collections.Counter()
for row in index['files']:
 data=raw(BASE/row['path']);check(len(data)==row['bytes'] and sha(data)==row['sha256'],'indexed file '+row['path'])
 included[str(row['include_in_git'])]+=1
# Bind the committed subset to the sealed Git evidence commit too, not only checkout.
prefix=BASE.relative_to(WT).as_posix()+'/'
tree={}
for entry in git('ls-tree','-r','-z',head,'--',prefix).split(b'\0'):
 if entry:
  meta,path=entry.split(b'\t',1);tree[path.decode()]=meta.split()[2].decode()
committed=[row for row in index['files'] if row['include_in_git']]
oids=[tree[prefix+row['path']] for row in committed]
packed=subprocess.check_output(['git','-C',str(WT),'cat-file','--batch'],input=('\n'.join(oids)+'\n').encode())
offset=0
for row,oid in zip(committed,oids):
 end=packed.index(b'\n',offset);header=packed[offset:end].split();size=int(header[2]);data=packed[end+1:end+1+size];offset=end+size+2
 check(header[0].decode()==oid and header[1]==b'blob' and size==row['bytes'] and sha(data)==row['sha256'],'committed indexed blob '+row['path'])
check(offset==len(packed),'complete Git batch consumption')
final=read(BASE/'FINAL_ACCEPTANCE.json')
for p,h in final['artifacts'].items():check(sha(raw(BASE/p))==h,'final seal '+p)
source=read(BASE/'CANDIDATE_SOURCE.json');versions={'baseline':read(PREV/'installation/READY.json'),'candidate':read(BASE/'installation/READY.json')}
identity={}
for role,ready in versions.items():
 receipt=read(ready['receipt']);bundle=Path(receipt['bundle']);build=read(bundle/'BUILD.json');site=Path(ready['install_root']);release=Path(ready['release'])
 wheel=next(bundle.glob('*.whl'));check(sha(raw(wheel))==ready['wheel_sha256'],'wheel digest')
 manifest=build['runtime_identity']['source_files'];check(len(manifest)==137,'source denominator')
 archive=git('archive','--format=tar',ready['commit'],'--',*[r['path'] for r in manifest])
 with tarfile.open(fileobj=io.BytesIO(archive),mode='r:') as tf:git_bytes={m.name:tf.extractfile(m).read() for m in tf.getmembers() if m.isfile()}
 with zipfile.ZipFile(wheel) as z:
  records=[n for n in z.namelist() if n.endswith('.dist-info/RECORD')];check(len(records)==1,'one RECORD')
  zip_count=0
  for n in z.namelist():
   if n.endswith('/'):continue
   b=z.read(n);check(raw(site/n)==b,'wheel/install member '+n);zip_count+=1
  record_rows=list(csv.reader(io.StringIO(z.read(records[0]).decode())))
  for p,h,s in record_rows:
   if not h:check(p==records[0] and not s,'only RECORD unhashable');continue
   check(h=='sha256='+base64.urlsafe_b64encode(hashlib.sha256(z.read(p)).digest()).decode().rstrip('=') and int(s)==len(z.read(p)),'wheel RECORD '+p)
  for row in manifest:
   p=row['path'];b=git_bytes[p];check(sha(b)==row['sha256'] and b==z.read(p)==raw(site/p)==raw(Path(receipt['source_root'])/p),'Git/source/wheel/install '+p)
   if role=='candidate':check(b==raw(WT/p),'candidate checkout '+p)
 constants={n.targets[0].id:ast.literal_eval(n.value) for n in ast.parse(git_bytes['human_eye_plugin/runtime_identity.py']).body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION')}
 canon=sha(json.dumps(dict(base_version=constants['BASE_VERSION'],implementation_revision=constants['IMPLEMENTATION_REVISION'],files=manifest),sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
 check(canon==ready['source_sha256'],'canonical identity')
 if role=='candidate':check(source['manifest']==manifest and source['canonical']==canon,'candidate manifest')
 binding=read(release/'admin/RUNTIME_BINDING.json');check(sha(raw(ready['entry']))==ready['launcher_sha256']==binding['launcher_sha256'],'actual entry hash')
 check(sha(raw(release/'admin/RUNTIME_BINDING.json'))==ready['binding_sha256'],'binding digest')
 check(sha(raw(release/'admin/installed_release.py'))==receipt['admin_sha256']==binding['admin_sha256'],'admin digest')
 check(binding['source_files']==manifest and binding['site_packages']==ready['install_root'] and binding['dependency_python']==ready['dependency_python'],'binding targets')
 identity[role]={'commit':ready['commit'],'version':ready['version'],'canonical':canon,'runtime_files':len(manifest),'all_wheel_members':zip_count,'RECORD_rows':len(record_rows),'wheel_sha256':ready['wheel_sha256'],'entry_sha256':ready['launcher_sha256'],'same_git_source_wheel_install':True}
check(versions['candidate']['dependency_python']==versions['baseline']['dependency_python'],'same dependency Python')
reuse=read(BASE/'entry/RUNNER_REUSE.json')
for r in reuse['files']:check(sha(raw(WT/r['path']))==r['sha256'],'reused runtime '+r['path'])
run=read(BASE/'entry/run_01/RESULTS.json');reservations=lines(BASE/'entry/OWNED_SCENE_STARTS.jsonl');check(len(run['cases'])==len(reservations)==4,'four scenes no substitutes')
check([r['ordinal'] for r in reservations]==[1,2,3,4],'reservation order')
protected=run['protected_before'];check(protected==run['protected_after'],'protected declared unchanged')
for p,h in protected.items():check(sha(raw(p))==h,'protected raw '+p)
snapshot=read(PREV/'preflight/SOURCE_SNAPSHOT.json');records=[]
def identity_match(value,ready):
 check(value['source_kind']=='installed_distribution' and value['source_sha256']==ready['source_sha256'] and value['distribution_version']==ready['version'] and value['source_file_count']==137,'actual initialize identity')
def frames(folder):
 receipt=read(folder/'RPC.json');out=[]
 for d in sorted(p for p in folder.iterdir() if p.is_dir() and p.name.isdigit()):
  req=read(d/'TX.bin');r=read(d/'RECEIPT.json');tx=raw(d/'TX.bin');rx=raw(d/'RX.bin') if (d/'RX.bin').exists() else b''
  check(len(tx)==r['sent_bytes']==r['attempted_send_bytes'] and len(rx)==r['received_bytes'],'raw RPC lengths')
  check(r['send_confirmed'] and r['error'] is None,'raw RPC success')
  check(r==receipt['requests'][len(out)],'receipt list equality')
  out.append({'request':req,'receipt':r,'response':json.loads(rx) if rx else None,'tx':len(tx),'rx':len(rx)})
 check(sum(x['tx'] for x in out)==receipt['tx_bytes'] and sum(x['rx'] for x in out)==receipt['rx_bytes'],'aggregate RPC bytes')
 return out
for case in run['cases']:
 role,profile=case['role'],case['profile'];ready=versions[role];f=BASE/'entry/run_01'/(role+'_'+profile)
 check(not case['errors'] and case['passed'],'case pass');check(case['worker_deadline_ns']-case['started_ns']==570*10**9 and case['ended_ns']<case['worker_deadline_ns'],'deadline')
 meta=frames(f/'metadata');rpc=frames(f/'owner/plugin');check(len(meta)==4 and len(rpc)==10,'metadata4 production10 RPC')
 for init in (meta[0]['response'],rpc[0]['response']):identity_match(init['result']['_meta']['human_eye'],ready)
 check(rpc[0]['response']==read(f/'owner/PLUGIN_INITIALIZE.json'),'saved initialize raw')
 start=read(f/'owner/plugin/START.json');check(start['command'][0]==ready['dependency_python'] and start['command'][3]==ready['entry'],'actual command fixed entry')
 check(('--spatial-task-only' in start['command'])==(profile=='S'),'profile command')
 public=read(f/'PUBLIC_TOOLS.json');listed=meta[2]['response']['result']['tools'];check(all(t in listed for t in public) and len(public)==2,'actual selected schema')
 if profile=='S':check(public==listed,'S exactly actual two tools')
 initial=read(f/'owner/INITIAL.json');final_snapshot=read(f/'owner/FINAL.json');check(initial==final_snapshot==snapshot,'full initial final frozen snapshot')
 events=lines(f/'owner/native/WORKER_EVENTS.jsonl');execute=[e for e in events if 'script_sha256' in e];close_events=[e for e in events if 'sequence' in e and 'script_sha256' not in e]
 check(len(execute)==8 and len(close_events)==1,'8 capture reads plus one close')
 for e in execute:
  check(e['status']=='completed' and not e['script_error'] and not e['changed_or_new_PNG_files'] and e['render_events_before']==e['render_events_after'],'worker successful no image')
  # Helper hashes in-memory code, then write_text uses Windows newline translation.
  code=raw(f/'owner/native'/('call_'+str(e['sequence']))/'SCRIPT.py').replace(b'\r\n',b'\n')
  check(sha(code)==e['script_sha256'],'executed source code after helper newline translation')
 audit=[e for e in lines(f/'owner/audit.jsonl') if e.get('event')=='observe'];check(len(audit)==6,'six actual observations')
 thin=read(f/'thin_probe/RESULT.json');txlines=raw(f/'thin_probe/TX.bin').splitlines();rxlines=raw(f/'thin_probe/RX.bin').splitlines();check(len(txlines)==9 and len(rxlines)==8,'thin public frame counts')
 replies={x['id']:x for x in map(json.loads,rxlines)}
 check(replies['client-list']['result']['tools'][1:]==public,'public actual schema forwarding')
 bridge=next((f/'thin_probe/attachments').glob('bridge_*'));exit_=read(bridge/'EXIT.json');check(exit_['normal_exit'] and exit_['requests']==9 and exit_['complete_tx_bytes']==len(raw(f/'thin_probe/TX.bin')) and exit_['complete_rx_bytes']==len(raw(f/'thin_probe/RX.bin')),'thin graceful EXIT')
 close=read(f/'owner/CLOSE.json');check(close['confirmed'] and not close['errors'] and close['geometry_unchanged'] and close['asset_unchanged'],'owner close')
 check(close['plugin_close']['confirmed'] and close['plugin_close']['exit_code']==0 and close['plugin_close']['process_reaped'] and close['plugin_close']['reader_stopped'],'plugin close')
 check(close['native_close']['process_reaped'] and close['native_close']['exit_code']==0 and close['native_close']['response']['status']=='closed','native closed')
 check(case['actor_runtime_exit']['confirmed'] and case['actor_runtime_exit']['exit_code']==0 and case['thin_probe_lifecycle']['runtime_exit']['confirmed'],'runtime handles exit')
 check(read(f/'METADATA_CLOSE.json')['close']['confirmed'],'metadata close')
 rows=[];request_params=[]
 for i in range(1,7):
  t=f/'owner'/('tool_'+str(i).zfill(2));req=read(t/'REQUEST.json');resp=read(t/'RESPONSE.json');a=read(t/'ATTEMPT.json');m=read(t/'ENTRY_MEASUREMENT.json');p=rpc[i+3]
  check(req==p['request'] and resp==p['response']==replies['relation-'+str(i)],'actual raw forwarded request response')
  check(len(compact(resp)+b'\n')==a['response_bytes']==a['produced_response_bytes'],'owner encoded bytes');check(not a['is_error'] and a['exception'] is None,'tool success')
  body=json.loads(resp['result']['content'][0]['text']);check(body==m['original_body'],'raw body measurement')
  check(m['product_stdio_receipt']==p['receipt'] and m['product_stdio_RX_bytes']==p['rx'] and m['product_stdio_TX_bytes']==p['tx'],'raw measurement counters')
  work=audit[i-1]['task_work'];check(work==m['task_work'],'real audit work')
  physical=[e for e in execute if a['started_ns']<=e['started_ns']<=a['started_ns']+a['elapsed_ns']];check(len(physical)==m['worker_received_request_count']==1 and [e['sequence'] for e in physical]==m['worker_received_request_sequences'],'received host requests')
  check(work['result_cache_hit']==(i>1) and work['closed_solid_pair_count']==(3 if i==1 else 0) and work['surface_pair_count']==(3 if i==1 else 0),'cold warm actual counters')
  check(work.get('rank_calls')==1 if i==1 else work.get('rank_calls') in (None,0),'rank counter: first1, warm absent/zero preserved')
  facts=m['facts'];local=facts[0]['closed'].get('local_evidence');check(bool(local)==(role=='candidate') and all('local_evidence' not in x['closed'] for x in facts[1:]),'one local evidence fact')
  check(body.get('binding',body.get('context'))['runtime_source_sha256']==ready['source_sha256'],'body runtime binding')
  request_params.append(compact(req['params']))
  rows.append({'index':i,'peer_ns':p['receipt']['elapsed_ns'],'owner_ns':a['elapsed_ns'],'product_rx_bytes':p['rx'],'owner_rx_bytes':a['response_bytes'],'product_tx_bytes':p['tx'],'body_text_bytes':len(resp['result']['content'][0]['text'].encode()),'local_bytes':len(compact(local)) if local else 0,'task_work':work,'worker_received':len(physical),'facts':facts})
 check(len(set(request_params))==1,'six same application parameters')
 # Raw host capture and triangle source binding, not a mathematical overlap oracle.
 firstout=raw(f/'owner/native/call_2/stdout.txt').decode();host=json.loads(firstout.split('HUMAN_EYE_BLENDER_MCP:',1)[1])['result'];resources={r['id']:r for r in host['resources']};meshes={m['name']:m for m in host['capture']['meshes']};snap={o['name']:o for o in initial['objects']}
 for name in ('N16','N13','N08','N28'):
  m=meshes[name]['_scene_resource'];r=resources[m['id']];check(r['vertices_local']==snap[name]['vertices_local'] and m['matrix']==snap[name]['matrix_world'],'actual captured geometry '+name)
 if role=='candidate':
  local=rows[0]['facts'][0]['closed']['local_evidence'];check(local['triangle_indices']==[12,11],'source triangle pair')
  for k,name in enumerate(('N16','N13')):
   m=meshes[name]['_scene_resource'];r=resources[m['id']];inds=r['faces'][local['triangle_indices'][k]];mat=m['matrix'];world=[[sum(mat[axis][j]*r['vertices_local'][v][j] for j in range(3))+mat[axis][3] for axis in range(3)] for v in inds]
   check(world==local['triangle_vertices_world_m'][k],'raw triangle world source '+name)
  check(all(x['facts'][0]['closed']['local_evidence']==local for x in rows),'cold warm exact local equality')
 records.append({'role':role,'profile':profile,'case_wall_s':(case['ended_ns']-case['started_ns'])/1e9,'first_peer_ms':rows[0]['peer_ns']/1e6,'repeated_peer_ms':stats([x['peer_ns']/1e6 for x in rows[1:]]),'first_owner_ms':rows[0]['owner_ns']/1e6,'repeated_owner_ms':stats([x['owner_ns']/1e6 for x in rows[1:]]),'metadata_rpc':{'id_requests':3,'notifications':1,'tx':sum(x['tx'] for x in meta),'rx':sum(x['rx'] for x in meta)},'product_rpc':{'id_requests':9,'notifications':1,'tx':sum(x['tx'] for x in rpc),'rx':sum(x['rx'] for x in rpc)},'thin_public':{'id_requests':8,'notifications':1,'tx':len(raw(f/'thin_probe/TX.bin')),'rx':len(raw(f/'thin_probe/RX.bin'))},'worker_execute_requests':8,'worker_close_requests':1,'exits_confirmed':True,'rows':rows})
comparison=[]
for profile in ('C','S'):
 b=next(r for r in records if r['profile']==profile and r['role']=='baseline');c=next(r for r in records if r['profile']==profile and r['role']=='candidate')
 for old,new in zip(b['rows'],c['rows']):
  clean=lambda facts:[{**r,'closed':{k:v for k,v in r['closed'].items() if k!='local_evidence'}} for r in facts]
  check(clean(old['facts'])==clean(new['facts']) and old['task_work']==new['task_work'],'pairwise old facts and complete work unchanged')
 comparison.append({'profile':profile,'first_peer_delta_ms':c['first_peer_ms']-b['first_peer_ms'],'repeated_peer_median_delta_ms':c['repeated_peer_ms']['median']-b['repeated_peer_ms']['median'],'response_delta_bytes_each':[new['product_rx_bytes']-old['product_rx_bytes'] for old,new in zip(b['rows'],c['rows'])]})
check(git('status','--short').decode()==status_before,'implementation status unchanged by read review')
result={'independent_scope':'Raw identities, bytes, counters, timing and exit records only. No product execution or mathematical oracle; author records are cross-checked, no original test rerun.','head':head,'git_status_before':status_before,'indexed_files_verified':len(index['files']),'index_retention_counts':dict(included),'identity':identity,'four_cases':records,'comparison':comparison,'denominator':{'owned_scenes':4,'metadata_processes':4,'tool_requests':24,'first_requests':4,'repeats':20,'worker_received_tool_requests':24,'worker_execute_including_initial_final':32,'worker_close_requests':4,'model_consumers':0},'limitations':['One fixed-order first request and five repeats per process; no stable latency or model-task benefit inferred.','Peer includes existing trace IO/serialization and overlaps owner; case wall includes metadata/startup/thin client/close and must not be added again.','Counts are received requests, not unreceived transport attempts.','No model tokens or fees in this engineering-only batch.','Terminal unchanged snapshots and files do not prove absence of arbitrary reverted transient mutation.','Mathematical local evidence validity is delegated separately.'],'source_hashes':SOURCES}
(OUT/'ENTRY_REVIEW.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:result[k] for k in ('indexed_files_verified','index_retention_counts','identity','comparison','denominator')},ensure_ascii=False))
