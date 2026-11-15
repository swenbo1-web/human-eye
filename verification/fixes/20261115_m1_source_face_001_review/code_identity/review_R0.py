"""Independent offline code, byte identity and actual execution contract review.
No product imports, no experiment replay, no renderer/model/Blender calls.
"""
import ast, base64, csv, hashlib, io, json, pathlib, subprocess, tomllib, zipfile
R=pathlib.Path('C:/Users/Administrator/.codex/worktrees/m1-source-face-binding-001/hefe')
N=R/'verification/m1_source_face_binding_001'
O=pathlib.Path('D:/hefe/verification/fixes/20261115_m1_source_face_001_review/code_identity')
BASE='1f3db153d4a46363ed3e64103d495bbc5ee65864'
HEAD='8f2a739e789b777358d84a168154bc7c50b929e5'
checks=0; groups={}; failures=[]; hashes={}; reads={}
def check(group,label,value):
 global checks
 checks+=1; groups[group]=groups.get(group,0)+1
 if not value:failures.append({'group':group,'check':str(label)})
def data(p):
 p=pathlib.Path(p).resolve()
 if p not in reads:reads[p]=p.read_bytes()
 return reads[p]
def sha(p):
 p=pathlib.Path(p).resolve()
 if p not in hashes:hashes[p]=hashlib.sha256(data(p)).hexdigest()
 return hashes[p]
def j(p):return json.loads(data(p))
def git(*args):return subprocess.check_output(['git',*args],cwd=R)
def expand(ranges):return [n for lo,hi in ranges for n in range(lo,hi+1)]
check('git','head',git('rev-parse','HEAD').decode().strip()==HEAD)
check('git','clean',not git('status','--porcelain'))
check('git','branch',git('branch','--show-current').decode().strip()=='codex/m1-source-face-binding-001')
manifest=j(N/'CONTENT_MANIFEST.json')
paths={row['path'] for row in manifest['files']}|{'verification/m1_source_face_binding_001/CONTENT_MANIFEST.json'}
changed=set(filter(None,git('diff','--name-only','-z',BASE,HEAD).decode().split('\0')))
check('git','exact1117',paths==changed and len(paths)==1117)
check('git','only one product',set(p for p in paths if not p.startswith('verification/m1_source_face_binding_001/'))=={'human_eye_plugin/live_spatial_mcp.py'})
for row in manifest['files']:check('content',row['path'],len(data(R/row['path']))==row['bytes'] and sha(R/row['path'])==row['sha256'])
tree={}
for row in git('ls-tree','-r','-z',HEAD).split(b'\0'):
 if row:
  info,path=row.split(b'\t',1);tree[path.decode()]=info.split()[2].decode()
for name in paths:
 raw=data(R/name); oid=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
 check('git_blob',name,tree[name]==oid)
for name in ['FROZEN.json','admin/QUALIFICATION_SEAL.json']:
 v=j(N/name)
 for path,digest in v['files_sha256'].items():check(name,path,sha(path)==digest)
quality=j(N/'admin/QUALITY_SEAL.json')
for row in quality['inputs']:check('quality_seal',row['path'],sha(row['path'])==row['sha256'])
for path,digest in j(N/'BASELINE.json')['old_protected_manifests'].items():check('old_protected',path,sha(path)==digest)
archive=j(N/'RUNTIME_ARCHIVE.json')
for row in archive['files']:
 check('archive',row['archive_path'],sha(row['original_path'])==sha(N/row['archive_path'])==row['sha256'] and len(data(row['original_path']))==row['bytes'])
for path,digest in j(N/'FINAL_AUDIT.json')['artifacts_sha256'].items():check('final_artifact',path,sha(N/path)==digest)
plan=j(N/'PLAN.json');bindings={}
for arm in 'AB':
 bind=j(plan['products'][arm]['path']);bindings[arm]=bind
 check('binding',arm,sha(plan['products'][arm]['path'])==plan['products'][arm]['sha256'])
 check('binding',arm+'141',len(bind['source_manifest'])==141)
 for row in bind['source_manifest']:
  name=row['path'];sourcegit=HEAD if arm=='B' else 'd12c7ab248452ff253452007d0635f2d662f0191'
  # Source Git bytes via one tree object per file; no product execution.
  raw=git('show',sourcegit+':'+name)
  check('installed_'+arm,name,hashlib.sha256(raw).hexdigest()==row['sha256']==sha(pathlib.Path(bind['install_root'])/name))
  if arm=='B':check('source_B',name,sha(R/name)==row['sha256'])
build=j(N/'build/BUILD_INSTALL.json');wheel=build['wheel']
check('wheel','sha',sha(wheel['file'])==wheel['sha256']==bindings['B']['wheel_sha256'])
with zipfile.ZipFile(wheel['file']) as z:
 check('wheel','count',len(z.namelist())==wheel['members'])
 for row in bindings['B']['source_manifest']:check('wheel_source',row['path'],hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256'])
 record=next(n for n in z.namelist() if n.endswith('.dist-info/RECORD'))
 for name,digest,size in csv.reader(io.StringIO(z.read(record).decode())):
  if digest:
   raw=z.read(name);encoded=base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')
   check('wheel_record',name,digest=='sha256='+encoded and len(raw)==int(size))
# Parse only, never execute any product AST.
source='human_eye_plugin/live_spatial_mcp.py';old=ast.parse(git('show',BASE+':'+source));new=ast.parse(data(R/source))
def nodes(tree):return {(type(n).__name__,getattr(n,'name',str(i))):ast.dump(n,include_attributes=False) for i,n in enumerate(tree.body)}
a,b=nodes(old),nodes(new);changed_nodes={k for k in a.keys()|b.keys() if a.get(k)!=b.get(k)}
check('code','exact two functions',changed_nodes=={('FunctionDef','_project_active_patch_support'),('FunctionDef','project_active_observation_brief')})
check('code','final snapshot',sha(R/source)==sha(N/'product_candidate_02.py')=='2be839c39ffcc5bde5fa92d7b028f8f9e5e8ab34d65aed90a51037f1a74503f5')
check('code','once followup',j(N/'ENGINEERING_REPORT.json')['candidate_count']==2 and j(N/'ENGINEERING_REPORT.json')['hot_attempt_count']==1)
source_text=data(R/source).decode();check('code','only one helper caller',source_text.count('_project_active_patch_support(')==2)
# Validate actual B public output against independently expanded full-source maps.
F=pathlib.Path('D:/he_source_face_001/formal');seq=['A1','B1','B2','A2','A3','B3'];threads=[];configbase=None;toolsbase=None
def merge(dst,src):
 for k,v in src.items():
  if isinstance(v,dict):merge(dst.setdefault(k,{}),v)
  else:dst[k]=v
def config(argv):
 out={}
 for i,arg in enumerate(argv):
  if arg=='-c':merge(out,tomllib.loads(argv[i+1]))
 return out
binding_results=[]
for slot in seq:
 s=F/slot;arm=slot[0];act=j(s/'ACTOR_CONFIG.json');res=j(s/'RESULT.json');consumer=j(s/'c/CONSUMER.json');cfg=config(consumer['argv'])
 check('slots',slot+' identity',act['comparison_arm']==arm and act['group']==res['group']=='P')
 check('slots',slot+' caps',act['max_tool_calls']==12 and act['max_render_attempts']==6 and act['phase_render_cap']==36 and act['whole_render_cap']==48)
 check('slots',slot+' source',act['expected_product_source_sha256']==bindings[arm]['source_sha256'])
 check('slots',slot+' deadline',res['deadline_ns']-res['started_ns']==450_000_000_000 and consumer['deadline_ns']==res['deadline_ns']==act['worker_deadline_ns'])
 check('slots',slot+' fresh valid',consumer['status']=='completed' and consumer['turn_index']==1 and consumer['expected_thread_id'] is None and res['outer_valid_completion'])
 threads.append(consumer['thread_id'])
 check('prompt',slot,consumer['input_sha256']==plan['expected_prompt_sha256']==sha(plan['inputs']['prompt']))
 check('config',slot+' model',cfg['model']==consumer['model']=='gpt-6.1-sol' and cfg['model_reasoning_effort']=='medium' and cfg['service_tier']=='default')
 check('config',slot+' isolation',all(cfg['features'][k] is False for k in ['hooks','memories','apps','multi_agent','goals']) and cfg['skills']['include_instructions'] is False)
 check('config',slot+' authorization',all(v['approval_mode']=='approve' for v in cfg['mcp_servers']['arm_engine']['tools'].values()))
 server=cfg.pop('mcp_servers');normalized=cfg
 if configbase is None:configbase=normalized
 check('config',slot+' equal',normalized==configbase)
 schema=j(s/'o/TOOLS_SCHEMA.json')
 if toolsbase is None:toolsbase=schema
 check('tools',slot+' equal',schema==toolsbase and len(schema)==5)
 check('tools',slot+' current product first',j(s/'o/tool_01/REQUEST.json')['params']['name']=='active_observation')
 check('lifecycle',slot+' owner close',j(s/'o/CLOSE.json')['confirmed'] and j(s/'o/CLOSE.json')['server_thread_stopped'])
 for k in ['consumer_process_cleanup','owner_process_cleanup']:
  c=res[k];check('lifecycle',slot+k,c['confirmed'] and c['reaped'] and c['process_handle_closed'] and c['exit_code']==0)
 check('lifecycle',slot+' held thin',res['runtime_exit']['confirmed'] and res['runtime_exit']['exited'] and res['runtime_exit']['handle_closed'] and res['runtime_exit']['exit_code']==1)
 check('lifecycle',slot+' thin receipt unknown retained',res['bridge_cleanup']['receipt_status']=='unknown' and res['bridge_cleanup']['missing_exit_count']==1)
 metrics=j(s/'o/METRICS.json')
 check('isolation',slot+' forbidden reads',metrics['native']['audit']['forbidden_old_evidence_reads']==0 if 'native' in metrics else True)
 full=j(s/'o/product_call_01/SERVICE_RESULT.json');reply=j(s/'o/tool_01/RESPONSE.json');public=json.loads(reply['result']['content'][0]['text'])
 expected=full['facts']['scope']['patch_support']['regions'];rows=[dict(zip(public['regions']['columns'],v)) for v in public['regions']['rows']]
 check('actual_mapping',slot+' schema',public['schema']=='active-observation-brief-v'+('5' if arm=='B' else '4'))
 check('actual_mapping',slot+' rows',len(rows)==len(expected)==61)
 if arm=='B':
  for row,truth in zip(rows,expected):
   ints=expand(row['source_triangle_index_ranges'])
   check('actual_mapping',slot+row['roi_id'],row['roi_id']==truth['roi_id'] and row['object_index']==truth['object_index'] and ints==sorted(truth['triangle_indices']) and len(ints)==row['triangle_count'])
  binding_results.append({'slot':slot,'mapped_regions':len(rows),'mapped_source_triangles':sum(r['triangle_count'] for r in rows)})
check('slots','six unique',len(set(threads))==6)
check('slots','fixed sequence',[x['slot'] for x in plan['sequence']]==seq)
frozen=j(N/'FROZEN.json');qseal=j(N/'admin/QUALIFICATION_SEAL.json');batch=j(F/'BATCH_TIMING.json')
check('chronology','freeze before qualification',frozen['before_publication_ns']<qseal['before_publication_ns']<batch['started_ns'])
check('qualification','one attempt',qseal['qualification_attempts']==1 and qseal['actual_rasters']==6 and qseal['comparison_models']==0)
check('qualification','only Q01',[x.name for x in pathlib.Path('D:/he_source_face_001/preparation').iterdir() if x.is_dir()]==['Q01'])
check('formal','only six slots',set(p.name for p in F.iterdir() if p.is_dir())==set(seq)|{'slot_records'})
check('AL','honest pending',j(N/'BASELINE.json')['AL']['task_registration']=='pending_current_chat_host_binding' and not j(N/'AL_COMPLETION_CONTEXT.json')['context_bound'])
out={'passed':not failures,'checks':checks,'groups':groups,'failures':failures,'unique_hashed_files':len(hashes),'changed_ast_nodes':sorted(changed_nodes),'public_binding_checks':binding_results,'new_product_model_Blender_raster_calls':0,'limitations':['No product code executed; code assessed by AST/source and actual saved public/full outputs.','Old compatibility and independent synthetic fixture cases assessed from source/harness and saved evidence, not rerun.','Provider resolved effort remains unexposed; host requested setting checked.','Author AL task registration remains pending; parent review task binding does not retroactively register the author.']}
O.mkdir(parents=True,exist_ok=True)
with (O/'RESULT.json').open('x',encoding='utf8',newline='\n') as f:json.dump(out,f,ensure_ascii=False,indent=2)
print(json.dumps({'passed':out['passed'],'checks':checks,'failures':failures,'unique_hashed_files':len(hashes)}))
