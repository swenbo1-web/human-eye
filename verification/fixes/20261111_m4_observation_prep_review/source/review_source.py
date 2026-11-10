"""Static evidence audit only. Does not import or execute product code."""
import ast
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import traceback
import zipfile

WT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B = WT / 'verification/m4_observation_baseline_001'
OUT = Path(__file__).resolve().parent
COMMIT = '107641ec19919d56aa843c1949261590fc338148'
PREP = '9c85ab9a0518e1fe2369113f59ce308a2d97b8d3'
CANON = '7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1'
checks, sections, errors = [], {}, []

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(b): return hashlib.sha256(b).hexdigest()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def check(name, value, **info):
    checks.append(dict(name=name, passed=bool(value), **info))
    if not value: errors.append(name)
def run(name, fn):
    try: sections[name] = fn()
    except Exception as exc:
        errors.append(name + ':checker_exception')
        sections[name] = dict(checker_exception=repr(exc), traceback=traceback.format_exc())
def lines(p): return [json.loads(x) for x in Path(p).read_bytes().splitlines() if x.strip()]
def body(reply): return json.loads(reply['result']['content'][0]['text'])
def git(*args): return subprocess.run(['git', '-C', str(WT), *args], check=True, capture_output=True).stdout

ready = read(B/'installation/READY.json')
install = read(Path(ready['receipt']))
release = Path(ready['release'])
site = Path(ready['install_root'])
identity = read(B/'installation/run_02/receipt/INSTALLED_IDENTITY_STDOUT.json')
manifest = identity['runtime_identity']['source_files']

def source():
    rid = identity['runtime_identity']
    check('identity_manifest_137_unique_sorted', len(manifest)==137 and len({x['path'] for x in manifest})==137 and manifest==sorted(manifest,key=lambda x:x['path']))
    tree = ast.parse((WT/'human_eye_plugin/runtime_identity.py').read_text())
    roots = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_ROOT_MODULES' for t in n.targets))
    domain = set(roots)
    for pkg in ('human_eye_plugin','human_eye_module1_operators'):
        domain.update(pkg+'/'+p.name for p in (WT/pkg).glob('*.py'))
    check('manifest_complete_runtime_domain', domain=={x['path'] for x in manifest})
    canonical = digest(json.dumps(dict(base_version=rid['base_version'], implementation_revision=rid['implementation_revision'],files=manifest),sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    check('canonical_recomputed',canonical==CANON==rid['source_sha256']==ready['source_sha256'])
    entries={}
    for row in git('ls-tree','-r','-z',COMMIT).split(b'\0'):
        if row:
            meta,name=row.split(b'\t',1);entries[name.decode()]=meta.split()[2].decode()
    locations = {'worktree':WT,'source_run01':B/'installation/run_01/source_107641ec','source_run02':Path(install['source_root']),'installed':site}
    location_results={}
    for label,root in locations.items():
        bad=[]
        for row in manifest:
            raw=(root/row['path']).read_bytes()
            blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            if digest(raw)!=row['sha256'] or blob!=entries[row['path']]: bad.append(row['path'])
        check('137_source_bytes_and_git_'+label,not bad,mismatches=bad)
        location_results[label]=dict(count=137,mismatches=bad)
    wheel_rows=[]
    for runid in ('run_01','run_02'):
        wheel=next((B/'installation'/runid/'bundle').glob('*.whl'))
        with zipfile.ZipFile(wheel) as z:
            bad=[r['path'] for r in manifest if digest(z.read(r['path']))!=r['sha256']]
            check('137_wheel_sources_'+runid,not bad,mismatches=bad)
            record=next(n for n in z.namelist() if n.endswith('.dist-info/RECORD'))
            record_rows=list(csv.reader(io.StringIO(z.read(record).decode())))
            bad_record=[];checked=0
            for path,h,size in record_rows:
                if not h: continue
                raw=z.read(path);alg,encoded=h.split('=',1)
                if alg!='sha256' or base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')!=encoded or len(raw)!=int(size):bad_record.append(path)
                checked+=1
            check('wheel_RECORD_'+runid,not bad_record,checked=checked,mismatches=bad_record)
        if runid=='run_02':check('ready_wheel_hash',sha(wheel)==ready['wheel_sha256']==install['wheel_sha256'])
        wheel_rows.append(dict(run=runid,sha256=sha(wheel),record_members_checked=checked))
    binding=read(release/'admin/RUNTIME_BINDING.json')
    for filename,key in [('target_runtime_entry.py','launcher_sha256'),('installed_release.py','admin_sha256'),('RUNTIME_BINDING.json','binding_sha256')]:
        check('admin_hash_'+filename,sha(release/'admin'/filename)==install[key])
    check('binding_manifest_and_identity',binding['source_files']==manifest and binding['identity']['source_sha256']==CANON and binding['dependency_python']==ready['dependency_python'] and binding['site_packages']==ready['install_root'])
    check('admin_source_entry_equal',sha(release/'admin/target_runtime_entry.py')==sha(site/'human_eye_plugin/target_runtime_entry.py'))
    check('admin_source_installer_equal',sha(release/'admin/installed_release.py')==sha(site/'human_eye_plugin/installed_release.py'))
    check('isolated_identity_origins_installed',all(Path(p).is_relative_to(site) for p in identity['module_origins'].values()))
    check('isolated_identity_dependency_python',identity['python']==ready['dependency_python'])
    check('source_unchanged_since_product',not git('diff','--name-only',COMMIT,PREP,'--',*sorted(domain)).strip())
    return dict(canonical=canonical,source_locations=location_results,wheels=wheel_rows,recorded_identity_not_rerun=True,loaded_module_origins=len(identity['module_origins']),entry_sha256=sha(Path(ready['entry'])),binding_sha256=sha(release/'admin/RUNTIME_BINDING.json'))

def catalogue():
    p=B/'preflight/metadata_01';process=read(p/'PROCESS.json');result=read(p/'RESULTS.json')
    for fn,key in [('STDIN.jsonl','stdin_sha256'),('STDOUT.jsonl','stdout_sha256'),('STDERR.txt','stderr_sha256')]:check('metadata_raw_hash_'+fn,sha(p/fn)==process[key])
    replies=lines(p/'STDOUT.jsonl'); requests=lines(p/'STDIN.jsonl')
    replymap={r['id']:r for r in replies}; methodmap={r['method']:r.get('id') for r in requests}
    actual=replymap[methodmap['tools/list']]['result']['tools'];public=read(B/'preflight/P/PUBLIC_TOOLS.json')
    check('real_tools_list_equals_public',actual==public and sha(B/result['public_tools'])==result['public_tools_sha256'])
    rid=replymap[methodmap['initialize']]['result']['_meta']['human_eye']
    check('metadata_installed_identity',rid['source_sha256']==CANON and rid['source_file_count']==137 and rid['source_kind']=='installed_distribution' and rid['distribution_version']==ready['version'] and rid['identity_check']['compatible'])
    check('metadata_real_entry_and_success',process['argv'][0]==ready['dependency_python'] and process['argv'][3]==ready['entry'] and process['returncode']==0 and not process['timed_out'])
    return dict(tool_names=[t['name'] for t in actual],source_sha256=rid['source_sha256'],process_exit=process['returncode'])

def preflight():
    results={}; public=read(B/'preflight/P/PUBLIC_TOOLS.json');common=read(B/'preflight/COMMON_NATIVE.json');snap=B/'preflight/SOURCE_SNAPSHOT.json'
    for group in ('N','P'):
        d=B/'preflight/run_02'/group;o=d/'owner';t=d/'thin_probe';thin=read(t/'RESULT.json');iid=read(o/'IDENTITY.json');close=read(o/'CLOSE.json');finish=read(d/'OWNER_FINISH.json');actorlaunch=read(d/'ACTOR_LAUNCH.json')
        tx=lines(t/'TX.bin');rx=lines(t/'RX.bin');rxmap={r['id']:r for r in rx};txmap={r['id']:r for r in tx if 'id'in r}
        check(group+'_thin_raw_matches_result',rx==thin['responses'] and tx==read(t/'REQUESTS.json'))
        check(group+'_actual_catalogue',rxmap[2]['result']['tools']==[common]+(public if group=='P' else []) and read(d/'ACTUAL_PUBLIC_TOOLS.json')==rxmap[2]['result']['tools'])
        calls=[r for r in tx if r['method']=='tools/call'];callrows=[]
        for i,req in enumerate(calls,1):
            td=o/('tool_%02d'%i);resp=read(td/'RESPONSE.json')
            check(group+'_request_reply_'+str(i),read(td/'REQUEST.json')==req and resp==rxmap[req['id']])
            callrows.append(dict(id=req['id'],name=req['params']['name'],error=resp['result'].get('isError',False)))
        check(group+'_snapshot_same_bytes',sha(o/'INITIAL.json')==sha(o/'FINAL.json')==sha(snap))
        check(group+'_asset_bytes',sha(o/'native/input.blend')==iid['asset_sha256']==sha(B/'input/scene.blend'))
        check(group+'_common_native_identity',iid['common_native_sha256']==sha(B/'preflight/COMMON_NATIVE.json') and iid['python']==ready['dependency_python'] and not iid['private_geometry_warmup'])
        check(group+'_actor_binding_close',actorlaunch['pid']==iid['actor_parent_pid']==finish['actor_pid'] and close['actor_pid']==iid['actor_pid'] and close['actor_parent_pid']==iid['actor_parent_pid'] and finish['close']==close and finish['exit_code']==0 and finish['confirmed'])
        nc=close['native_close'];wc=close['worker_closed']
        check(group+'_native_close_receipts',nc['pid']==wc['pid']==nc['response']['pid'] and nc['response']['status']=='closed' and nc['exit_code']==0 and nc['process_reaped'] and wc['initial_geometry_fingerprint']==wc['final_geometry_fingerprint'] and not wc['poisoned'])
        check(group+'_original_deadline_retained',actorlaunch['worker_deadline_ns']==thin['original_chain_deadline_ns']==nc['original_deadline_ns']==wc['original_deadline_ns'])
        check(group+'_readonly_close_record',not close['errors'] and close['geometry_unchanged'] and close['asset_unchanged'] and nc['source_file_unchanged'] and nc['protected_files_unchanged'])
        for cr in thin['client_exit_receipts']:
            actualstart=read(Path(cr['directory'])/'STARTED.json');actualexit=read(Path(cr['directory'])/'EXIT.json')
            check(group+'_thin_started_exit_raw',actualstart==cr['started'] and actualexit==cr['exit'] and all(actualstart[k]==actualexit[k] for k in ('pid','kind','started_ns','instance_nonce')) and actualexit['normal_exit'] and actualexit['pid']==thin['runtime_pid'] and actualexit['requests']==len(tx) and not actualexit['backend_close_requested'])
        check(group+'_thin_process_receipts',thin['runtime_provenance']['confirmed'] and thin['runtime_provenance']['runtime_pid']==thin['runtime_pid'] and thin['runtime_provenance']['launcher_pid']==thin['launcher_pid'] and thin['runtime_exit']['confirmed'] and thin['runtime_exit']['exit_code']==0 and thin['process_reaped'] and thin['launcher_reaped'] and thin['exit_code']==0 and thin['launcher_exit_code']==0 and thin['client_exit_confirmed'])
        if group=='N':
            check('N_no_product',iid['runtime_identity'] is None and iid['product_serve_entry'] is None and close['plugin_close'] is None and len(calls)==1)
        else:
            init=read(o/'PLUGIN_INITIALIZE.json');rid=init['result']['_meta']['human_eye'];start=read(o/'plugin/START.json')
            check('P_installed_source',iid['runtime_identity']==rid and rid['source_sha256']==CANON and rid['source_file_count']==137 and rid['source_kind']=='installed_distribution' and rid['distribution_version']==ready['version'] and rid['identity_check']['compatible'])
            check('P_runtime_entry',start['command'][0]==ready['dependency_python'] and start['command'][3]==ready['entry']==iid['product_serve_entry'] and '--spatial-task-only'in start['command'])
            pluginreply={};pluginreq={}
            for pd in sorted((o/'plugin').glob('[0-9][0-9][0-9]')):
                for r in lines(pd/'RX.bin'):pluginreply[r['id']]=r
                for r in lines(pd/'TX.bin'):
                    if 'id'in r:pluginreq[r['id']]=r
            check('P_plugin_init_raw',pluginreply['private-init']==init)
            for id_ in (4,5,6):check('P_plugin_to_public_unmodified_'+str(id_),pluginreq[id_]==txmap[id_] and pluginreply[id_]==rxmap[id_])
            pc=close['plugin_close'];check('P_plugin_closed',pc['launcher_pid']==start['launcher_pid'] and pc['process_reaped'] and pc['exit_code']==0 and pc['confirmed'] and pc['error'] is None)
        results[group]=dict(calls=callrows,source_identity='no_product' if group=='N' else CANON,snapshot_sha256=sha(snap),actor_pid=iid['actor_pid'],actor_launcher=iid['actor_parent_pid'],native_worker_pid=nc['pid'],thin_runtime_pid=thin['runtime_pid'],thin_launcher_pid=thin['launcher_pid'],thin_normal_exit_receipt=True,plugin_launcher_pid=None if group=='N' else close['plugin_close']['launcher_pid'],image_scope=close['image_construction']['scope'])
    return results

def history_and_projection():
    pp=B/'preflight/postprocess_01';result=read(pp/'RESULTS.json');integrity=read(pp/'FINAL_INTEGRITY.json');aggregate=read(B/'preflight/run_02/RESULTS.json');presult=read(B/'preflight/run_02/P/PREFLIGHT_RESULT.json')
    bad=[rel for rel,h in result['source_files_sha256'].items() if sha(B/rel)!=h]
    check('postprocess_raw_167_pins',not bad,checked=len(result['source_files_sha256']),mismatches=bad)
    check('original_aggregate_failure_preserved',aggregate['passed'] is False and presult['passed'] is False and 'acquisition_invalid_triangle_structure' in json.dumps(presult['errors']) and sha(B/'preflight/run_02/RESULTS.json')==integrity['original_aggregate_result_preserved_sha256'])
    check('postprocess_no_greenwash',result['original_aggregate_passed'] is False and result['original_failure_retained'] is True and result['nearest_applicable_to_original_source'] is False and result['actual_backend_or_geometry_replays']==0)
    original3=body(read(B/'preflight/run_02/P/owner/tool_04/RESPONSE.json'));copied=read(pp/'ACTUAL_THREE_RELATIONS.json')
    check('three_relations_full_original_preserved',copied['original_result']==original3 and all(x['original_pair']==original3['candidates'][i] for i,x in enumerate(copied['independently_checked_pairs'])))
    refusal=body(read(B/'preflight/run_02/P/owner/tool_03/RESPONSE.json'));gap=read(pp/'NEAREST_SOURCE_GAP.json')
    check('nearest_original_refusal_preserved',gap['original_refusal']==refusal and 'acquisition_triangle_data_required:'in refusal['error'] and not gap['admitted'])
    check('refusal_truthful_unknown_no_action',refusal['tool_outcome']=='unknown' and all(refusal[k] is False for k in ('executed','verified','automatic_retry','execution_authority','host_mutation_started','connector_state_write_attempted','connector_state_write_committed')))
    snapshot=read(B/'preflight/SOURCE_SNAPSHOT.json');sizes={x['name']:sorted({len(face) for face in x['faces']}) for x in snapshot['objects']}
    check('nearest_gap_matches_original_polygons',sizes==gap['actual_original_polygon_sizes'] and len(sizes)==28 and all(v in ([4],[4,12]) for v in sizes.values()))
    check('nearest_guard_source_hash',sha(site/'human_eye_plugin/blender_host.py')==gap['installed_host_source_sha256'])
    badinputs=[p for p,v in integrity['original_and_copied_inputs'].items() if sha(p)!=v['expected_sha256'] or v['expected_sha256']!=v['actual_sha256']]
    check('original_and_copied_input_current_hashes',not badinputs,checked=len(integrity['original_and_copied_inputs']),mismatches=badinputs)
    proc=read(B/'installation/run_01/05_INSTALL.PROCESS.json');stderr=B/'installation/run_01/05_INSTALL.stderr.txt'
    check('installation_Win206_retained',proc['returncode']==1 and sha(stderr)==proc['stderr_sha256'] and '[WinError 206]'in stderr.read_text(encoding='utf-8'))
    check('same_installer_run01_run02',sha(B/'installation/run_01/INSTALL_CANDIDATE.py')==sha(B/'installation/run_02/INSTALL_CANDIDATE.py'))
    boot=B/'preflight/run_01/BOOTSTRAP_FAILURE.txt'
    check('bootstrap_failure_retained',boot.is_file() and 'KeyError: input/scene.blend'in boot.read_text())
    check('no_formal_GO_STARTED',not (B/'GO.json').exists() and not (B/'STARTED.json').exists())
    return dict(raw_original_files_rehashed=len(result['source_files_sha256']),initial_final_mesh_objects=28,failed_attempts_preserved=['installation/run_01 WinError206','preflight/run_01 bootstrap KeyError','preflight/run_02 expected-error assertion mismatch'],nearest_admitted=False,nearest_reason=refusal['error'],main_result_context_preserved=original3['context'],initial_source_unchanged=True,formal_GO_STARTED_absent=True,postprocessing_not_reexecuted=True)

for name,fn in [('source_and_install',source),('real_catalogue',catalogue),('raw_preflight',preflight),('history_and_same_raw_postprocess',history_and_projection)]:run(name,fn)
report=dict(schema='m4-prep-source-review-v1',status='passed_in_bounded_scope' if not errors else 'requires_review',product_commit=COMMIT,preparation_commit=PREP,source_sha256=CANON,review_method='Independent static rehash, Git blob comparison, raw JSON/RPC binding and source inspection; no product, Blender, model or entry execution',checks=checks,sections=sections,errors=errors,limits=['303 full artifact index and 305 Git-member audit delegated to parent; not duplicated.','Anonymous map was not read.','Runtime claims are checked against captured original receipts; no independent live rerun.','Independent geometry oracle and quality-handoff projection semantics are reviewed by other agents.','PID absence is only historical corroboration; normal exits here rely on STARTED/EXIT, launcher and backend close receipts.','New image observability is limited to original helper render hooks/workspace PNG scope, not a security sandbox.','This report does not issue formal sampling GO or approve the separate quality-pack projection defect.'])
OUT.mkdir(parents=True,exist_ok=True)
outfile=OUT/'SOURCE_ENTRY_REVIEW.json'
if outfile.exists():raise FileExistsError('Preserve prior review; choose a new output name before rerunning')
outfile.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(status=report['status'],checks=len(checks),failed=errors,path=str(outfile),sha256=sha(outfile)),ensure_ascii=False))
