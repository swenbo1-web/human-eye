"""Read-only preparation identity audit. No product or evaluation module imports."""
from pathlib import Path
import ast,collections,datetime,hashlib,io,json,subprocess,tarfile,zipfile
WT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=WT/'verification/m4_local_relation_consumption_001'
OLD=WT/'verification/m4_observation_baseline_001'
ENG=WT/'verification/m4_local_relation_evidence_001'
OUT=Path(__file__).resolve().parent
SOURCES={}
def sha(v):return hashlib.sha256(v).hexdigest()
def raw(p):
 p=Path(p);v=p.read_bytes();SOURCES[str(p)]=sha(v);return v
def read(p):return json.loads(raw(p))
def check(c,s):
 if not c:raise AssertionError(s)
def git(*a):return subprocess.check_output(['git','-C',str(WT),*a])
def constants(b,names):
 return {n.targets[0].id:ast.literal_eval(n.value) for n in ast.parse(b).body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in names}
head=git('rev-parse','HEAD').decode().strip();status=git('status','--short').decode()
check(head=='169b0be061e91b126f46313478690564ccb2bd60','preparation commit')
plan=read(B/'PLAN.json');freeze=read(B/'FREEZE.json');ready=read(B/'PREP_READY.json');index=read(B/'ARTIFACT_INDEX.json')
check(sha(raw(B/'PLAN.json'))==freeze['plan_sha256']==ready['plan_sha256']=='698b74ec8607e499693d1d34394e4ae06f9bca2e52ac1bda456cc96d4e453761','plan binding')
check(sha(raw(B/'FREEZE.json'))==ready['freeze_sha256']=='3699408f1341ab951b5e5a6457f4026c5bb8db2eb0fc2ce92ec79f51601b344d','freeze binding')
check(sha(raw(B/'ARTIFACT_INDEX.json'))==freeze['artifact_index_sha256']==ready['artifact_index_sha256'],'index binding')
check(index['file_count']==len(index['files'])==ready['indexed_files']==680,'index denominator')
for row in index['files']:
 v=raw(WT/row['path']);check(len(v)==row['bytes'] and sha(v)==row['sha256'],'indexed file '+row['path'])
check(sum(r['bytes'] for r in index['files'])==index['bytes']==ready['indexed_bytes']==14738497,'index bytes')
files=list(index['files'])+[dict(path=(B/p).relative_to(WT).as_posix(),bytes=len(raw(B/p)),sha256=sha(raw(B/p))) for p in ('ARTIFACT_INDEX.json','FREEZE.json','PREP_READY.json')]
tree={}
for line in git('ls-tree','-r','-z',head,'--',B.relative_to(WT).as_posix()).split(b'\0'):
 if line:
  a,p=line.split(b'\t',1);tree[p.decode()]=a.split()[2].decode()
expected_paths={r['path'] for r in files};check(expected_paths<=set(tree),'all683 accounted files committed')
extra_paths=sorted(set(tree)-expected_paths)
check(len(extra_paths)==9 and all('/synthetic/' in p and p.endswith('/FREEZE.json') for p in extra_paths),'nine extra synthetic FREEZE originals')
files.extend(dict(path=p,bytes=len(raw(WT/p)),sha256=sha(raw(WT/p))) for p in extra_paths)
check(len(tree)==len(files)==692,'actual full commit denominator692')
ids=[tree[r['path']] for r in files];packed=subprocess.check_output(['git','-C',str(WT),'cat-file','--batch'],input=('\n'.join(ids)+'\n').encode());at=0
for row,oid in zip(files,ids):
 e=packed.index(b'\n',at);h=packed[at:e].split();size=int(h[2]);v=packed[e+1:e+1+size];at=e+size+2
 check(h[0].decode()==oid and h[1]==b'blob' and size==row['bytes'] and sha(v)==row['sha256'],'prep Git blob '+row['path'])
check(at==len(packed),'complete Git evidence framing')
for p,h in plan['dispatch_input_sha256'].items():check(sha(raw(B/p))==h,'dispatch input '+p)
for r in read(B/'INPUT_REUSE.json')['reused']:
 v=raw(WT/r['new']);check(v==raw(WT/r['original']) and len(v)==r['bytes'] and sha(v)==r['sha256'],'common original input '+r['new'])
reuse=read(B/'runtime/REUSE_BINDINGS.json')
for r in reuse['adapters']:
 v=raw(B/'runtime'/r['path']);old=raw(WT/r['source_path']);check(sha(v)==r['sha256'] and sha(old)==r['source_sha256'],'adapter pin')
 if r['byte_identical']:check(v==old,'byte identical actor/transport')
for r in reuse['live_common_sources']:check(sha(raw(WT/r['path']))==r['sha256'],'common helper current')
ids_report=read(B/'installations/IDENTITIES.json');schemas={};current_profiles={}
for group,original in [('P0',OLD/'installation/READY.json'),('P1',ENG/'installation/READY.json')]:
 v=raw(B/'installations'/(group+'_READY.json'));check(v==raw(original),'READY original bytes')
 install=json.loads(v);check(install==plan['installations'][group],'PLAN current READY equality')
 release=Path(install['release']);site=Path(install['install_root']);binding=read(release/'admin/RUNTIME_BINDING.json');manifest=binding['source_files'];check(len(manifest)==137,'137 current sources')
 archive=git('archive','--format=tar',install['commit'],'--',*[r['path'] for r in manifest])
 with tarfile.open(fileobj=io.BytesIO(archive),mode='r:') as t:blobs={m.name:t.extractfile(m).read() for m in t.getmembers() if m.isfile()}
 receipt=read(install['receipt']);wheel=next(Path(receipt['bundle']).glob('*.whl'));check(sha(raw(wheel))==install['wheel_sha256'],'original wheel hash')
 with zipfile.ZipFile(wheel) as z:
  for r in manifest:
   source_bytes=raw(site/r['path']);check(sha(source_bytes)==r['sha256'] and source_bytes==blobs[r['path']]==z.read(r['path']),'current installed source Git wheel '+group+' '+r['path'])
   if group=='P1':check(source_bytes==raw(WT/r['path']),'product checkout unchanged')
 con=constants(raw(site/'human_eye_plugin/runtime_identity.py'),{'BASE_VERSION','IMPLEMENTATION_REVISION','_ROOT_MODULES'})
 paths=set(con['_ROOT_MODULES'])|{p.relative_to(site).as_posix() for package in ('human_eye_plugin','human_eye_module1_operators') for p in (site/package).glob('*.py')}
 check(paths=={r['path'] for r in manifest},'no extra/missing runtime source')
 canonical=sha(json.dumps(dict(base_version=con['BASE_VERSION'],implementation_revision=con['IMPLEMENTATION_REVISION'],files=manifest),sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
 check(canonical==install['source_sha256']==freeze['product_sources'][group]['source_sha256'],'canonical')
 check(sha(raw(install['entry']))==install['launcher_sha256']==binding['launcher_sha256'],'current entry')
 check(sha(raw(release/'admin/installed_release.py'))==binding['admin_sha256'],'current admin')
 check(sha(raw(release/'admin/RUNTIME_BINDING.json'))==install['binding_sha256'],'current binding')
 check(binding['site_packages']==install['install_root'] and binding['target_release']==install['release'] and binding['dependency_python']==install['dependency_python'],'current config actual target')
 py=Path(install['dependency_python']);pyinfo=ids_report['profiles'][group]['dependency_python'];check(sha(raw(py))==pyinfo['sha256'] and sha(raw(py.parent.parent/'pyvenv.cfg'))==pyinfo['pyvenv_cfg_sha256'],'current Python and venv bytes')
 origin=ENG/'entry/run_01'/('baseline_S' if group=='P0' else 'candidate_S');schema=read(B/'schemas'/(group+'_PUBLIC_TOOLS.json'));check(raw(B/'schemas'/(group+'_PUBLIC_TOOLS.json'))==raw(origin/'PUBLIC_TOOLS.json'),'actual historical schema raw')
 init=read(origin/'ACTUAL_METADATA_INITIALIZE.json')['result']['_meta']['human_eye'];listed=read(origin/'ACTUAL_METADATA_TOOLS.json')['result']['tools'];check(schema==listed and len(schema)==2,'actual exact two schema')
 check(init['source_sha256']==canonical and init['source_kind']=='installed_distribution' and init['distribution_version']==install['version'],'historical identity matches current bytes')
 schemas[group]=schema
 current_profiles[group]={'commit':install['commit'],'source_files':137,'canonical':canonical,'version':install['version'],'current_source_wheel_git_match':True,'current_entry_binding_match':True,'schema_sha256':sha(raw(B/'schemas'/(group+'_PUBLIC_TOOLS.json'))),'current_dependency_python_sha256':sha(raw(py)),'runtime_identity':'historical actual identity only; no process launched during this preparation or review'}
check(plan['installation_ready']==plan['installations']['P0'],'legacy common dependency profile')
check(plan['installations']['P0']['dependency_python']==plan['installations']['P1']['dependency_python'],'common Python path')
newtext=schemas['P1'][0]['description'];oldtext=schemas['P0'][0]['description'];phrase='A supported transverse crossing includes its captured triangles and an approximate boundary location when publishable. '
check(newtext.replace(phrase,'',1)==oldtext,'only added local evidence sentence')
a=json.loads(json.dumps(schemas['P1']));a[0]['description']=oldtext;check(a==schemas['P0'],'input schemas and nearest identical')
native=read(B/'schemas/COMMON_NATIVE.json');check(native==read(B/'preflight/COMMON_NATIVE.json'),'common native copies')
native_tree=ast.parse(raw(WT/'verification/native_plugin_complex_003/actor.py'))
native_literal=next(ast.literal_eval(n.value) for n in native_tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='NATIVE')
check(native==native_literal,'common actual native definition')
cli=Path('C:/Users/Administrator/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe');check(sha(raw(cli))==plan['CLI_sha256'],'actual current CLI byte pin')
transport=ast.parse(raw(B/'runtime/consumer_transport.py'));settings=next(n for n in transport.body if isinstance(n,ast.FunctionDef) and n.name=='settings')
settings_value=next(ast.literal_eval(n.value) for n in settings.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='value')
check(settings_value['model']==plan['model']=='gpt-6.1-sol' and settings_value['model_reasoning_effort']==plan['requested_effort']=='medium','common requested model effort')
prepared=read(B/'runtime/PREPARED_INPUT.json');image=raw(B/plan['inputs']['image']);check(len(image)==plan['inputs']['image_bytes']==1185069 and sha(image)==prepared['initial_image']['sha256'],'one same image')
check(int.from_bytes(image[16:20],'big')==1200 and int.from_bytes(image[20:24],'big')==900,'frozen PNG dimensions')
check(plan['resolved_effort'] is None and plan['resolved_model'] is None and plan['image_delivery_contract']['provider_image_receipt'] is None,'availability and delivery not claimed')
order=[r['group'] for r in plan['sequence']];check(order==['N','P0','P1','P0','P1','N','P1','N','P0'],'Latin sequence')
check(collections.Counter(order)=={'N':3,'P0':3,'P1':3},'nine without old pooling')
for p in ('GO.json','STARTED.json','RUN_RESULT.json','cells'):check(not (B/p).exists(),'no formal state '+p)
history={p:read(B/p) for p in ready['failures_preserved']}
check(history['synthetic/run_01/RESULTS.json']['passed'] is False and history['synthetic/run_02/RESULTS.json']['passed'] is False,'original failures retained')
check(read(B/'synthetic/run_03/RESULTS.json')['passed'] is True,'later synthetic success exists')
dt=lambda x:datetime.datetime.fromisoformat(x.replace('Z','+00:00'))
elapsed=(dt(ready['measured_preparation_ended_utc'])-dt(ready['measured_preparation_started_utc'])).total_seconds();check(elapsed==ready['measured_preparation_wall_seconds']==875.063302,'prep window recompute')
pyc=sorted(p.relative_to(B).as_posix() for p in B.rglob('*.pyc'))
check(git('status','--short').decode()==status,'review did not change implementation status')
result={'scope':'Independent current-file and fixed-Git verification only. No product, Blender, model, CLI, installer or author verification code execution.','head':head,'git_status_before':status,'plan_sha256':ready['plan_sha256'],'freeze_sha256':ready['freeze_sha256'],'artifact_index_sha256':ready['artifact_index_sha256'],'indexed_files':680,'indexed_bytes':14738497,'index_plus_root_seals':683,'actual_fixed_commit_files_verified':692,'outside_index_synthetic_FREEZE_paths':extra_paths,'all_current_dispatch_hashes_match':True,'current_profiles':current_profiles,'current_CLI_sha256':sha(raw(cli)),'actor_transport_unchanged':True,'same_inputs':True,'only_schema_difference':'relations description adds available captured-triangle/boundary-location sentence; input schemas and nearest tool unchanged','formal_state_absent':True,'current_auth_quota_provider_availability':'unmeasured; historical ChatGPT login or same executable cannot prove current Pro capability','preparation_cost':{'measured_window_s':elapsed,'scope':ready['preparation_timing_scope'],'earlier_reading_later_commit_callback_and_coordination_tokens_fees':None,'historical_install_READY_elapsed_is_not_new_cost':True},'failures_preserved':{k:{'sha256':sha(raw(B/k)),'passed':v.get('passed'),'exception':v.get('exception',v.get('unexpected_error'))} for k,v in history.items()},'cleanup':{'rejection_preserved':True,'no_deletion_or_cleanup_performed_in_this_review':True,'local_pyc_files_retained':pyc,'no_retries_or_bypass_requested':True},'source_hashes':SOURCES}
(OUT/'SOURCE_REVIEW.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:result[k] for k in ('head','indexed_files','index_plus_root_seals','actual_fixed_commit_files_verified','current_profiles','preparation_cost','cleanup')},ensure_ascii=False))
