"""Read-only saved PREP evidence audit; no imports of project modules or runtime starts."""
import argparse, ast, base64, csv, hashlib, io, json, math, struct, subprocess, zipfile
from datetime import datetime
from fractions import Fraction
from pathlib import Path

WT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HEAD='13f3b279f2a57581e3cebd032d64ec9e2bfdb0ae'
G='00b13060a3cbe709b38f6e98ce04a6e5c3dabfb4'
P='e077fce38b5951efff8166b3b688d05ffa2ebf04'
PREFIX='verification/m4_selected_geometry_consumption_001'
BATCH=WT/PREFIX
HERE=Path(__file__).resolve().parent
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=HERE/'audit.json');args=parser.parse_args()
    checks=[]
    def ck(name,passed,detail=None):checks.append({'check':name,'passed':bool(passed),'detail':detail})
    def git(*argv):return subprocess.run(['git','-C',str(WT),*argv],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout
    def blobs(commit,paths):
        raw=subprocess.run(['git','-C',str(WT),'cat-file','--batch'],input=''.join(commit+':'+p+'\n' for p in paths).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
        pos=0;result={}
        for path in paths:
            end=raw.index(b'\n',pos);oid,kind,size=raw[pos:end].decode().split();size=int(size);assert kind=='blob'
            result[path]=(oid,raw[end+1:end+size+1]);pos=end+size+2
        assert pos==len(raw)
        return result
    before=git('status','--short').decode();ck('fixed_HEAD_and_clean',git('rev-parse','HEAD').decode().strip()==HEAD and before=='')
    index=read(BATCH/'INDEX.json');ready=read(BATCH/'PREP_READY.json');plan=read(BATCH/'PLAN.json')
    indexed={r['path']:r for r in index['files']};expected=set(indexed)|{PREFIX+'/'+p for p in index['self_reference_files']}
    tracked=set(git('ls-tree','-r','--name-only',HEAD,'--',PREFIX).decode().splitlines())
    disk={p.relative_to(WT).as_posix() for p in BATCH.rglob('*') if p.is_file()};bytecode={p for p in disk if '__pycache__' in p.split('/') or p.endswith('.pyc')}
    ck('401_indexed_403_total',len(indexed)==len(index['files'])==401 and len(expected)==403)
    ck('exact_Git_and_disk_sets',expected==tracked==disk-bytecode,{'missing':sorted(expected-tracked),'extra':sorted(tracked-expected),'local_bytecode_files':len(bytecode)})
    files=[];failures=[]
    for path,(oid,raw) in blobs(HEAD,sorted(expected)).items():
        ok=raw==(WT/path).read_bytes()
        if path in indexed:ok=ok and sha(raw)==indexed[path]['sha256'] and len(raw)==indexed[path]['bytes']
        if not ok:failures.append(path)
        files.append({'path':path,'sha256':sha(raw),'bytes':len(raw),'git_blob':oid})
    ck('403_Git_disk_index_bytes',not failures,failures)
    ck('index_bytes_and_READY_binding',sum(r['bytes'] for r in index['files'])==index['bytes']==22883875 and sha((BATCH/'INDEX.json').read_bytes())==ready['index_sha256'])
    ck('PLAN_binding',sha((BATCH/'PLAN.json').read_bytes())==ready['plan_sha256']==read(BATCH/'FREEZE.json')['plan_sha256'])
    fixed=read(BATCH/'installation/run_01/FIXED_BUILD_INPUTS.json');manifest=fixed['manifest'];runtime=[r['path'] for r in manifest]
    gblobs=blobs(G,runtime);headblobs=blobs(HEAD,runtime);receipt=read(BATCH/'installation/run_01/receipt/ISOLATED_INSTALL.json');inst=read(BATCH/'installation/READY.json')
    ck('137_current_runtime_frozen',len(runtime)==len(set(runtime))==137 and all(gblobs[p][1]==headblobs[p][1]==(WT/p).read_bytes() for p in runtime))
    ck('no_product_diff_since_preparation_start',git('diff','--name-only',plan['preparation_start_commit'],HEAD,'--',*runtime)==b'')
    wheel=next(Path(receipt['bundle']).glob('*.whl'));wheel_report=[]
    ck('G_fixed_wheel_identity',sha(wheel.read_bytes())==inst['wheel_sha256']==receipt['wheel_sha256'] and inst['commit']==fixed['commit']==G and inst['version']=='9.7.2+sg.r1')
    with zipfile.ZipFile(wheel) as z:
        source_bad=[]
        for r in manifest:
            raw=gblobs[r['path']][1]
            if not (sha(raw)==r['sha256'] and raw==z.read(r['path'])==(Path(receipt['source_root'])/r['path']).read_bytes()==(Path(inst['install_root'])/r['path']).read_bytes()):source_bad.append(r['path'])
        ck('G_137_Git_source_wheel_installed',not source_bad,source_bad)
        recname=next(p for p in z.namelist() if p.endswith('.dist-info/RECORD'))
        rows=list(csv.reader(io.StringIO(z.read(recname).decode())));record_bad=[]
        for name,digest,size in rows:
            if digest:
                raw=z.read(name);actual='sha256='+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')
                if digest!=actual or int(size)!=len(raw):record_bad.append(name)
            wheel_report.append({'name':name,'record_hash_present':bool(digest)})
        ck('G_RECORD',not record_bad,{'rows':len(rows),'failed':record_bad})
    constants={}
    for node in ast.parse(gblobs['human_eye_plugin/runtime_identity.py'][1]).body:
        if isinstance(node,ast.Assign):
            for t in node.targets:
                if isinstance(t,ast.Name) and t.id in ('BASE_VERSION','IMPLEMENTATION_REVISION'):constants[t.id]=ast.literal_eval(node.value)
    canonical=sha(json.dumps({'base_version':constants['BASE_VERSION'],'implementation_revision':constants['IMPLEMENTATION_REVISION'],'files':manifest},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    ck('G_canonical',canonical==inst['source_sha256']==plan['candidate_source_sha256']=='4ebc3910652ee461d9fa7476c8df0ecf6312580d6a02e1066c0eac88bef5c76c')
    pprep=WT/'verification/m4_local_relation_evidence_001/installation';pready=read(pprep/'READY.json');pfixed=read(pprep/'run_01/FIXED_BUILD_INPUTS.json');pblobs=blobs(P,[r['path'] for r in pfixed['manifest']])
    ck('P_reused_original_READY',read(BATCH/'installations/P_READY.json')==pready==plan['installations']['P'])
    ck('P_137_installed_matches_fixed_Git',len(pfixed['manifest'])==137 and all(sha(pblobs[r['path']][1])==r['sha256'] and pblobs[r['path']][1]==(Path(pready['install_root'])/r['path']).read_bytes() for r in pfixed['manifest']))
    ck('G_READY_copies',read(BATCH/'installations/G_READY.json')==inst==plan['installations']['G'])
    s=read(BATCH/'smoke/run_01/RESULTS.json');bind=read(BATCH/'smoke/INPUT_BINDINGS.json');pins=bind['source_files_sha256']
    ck('smoke_fixed_bindings',bind==read(BATCH/'smoke/run_01/FIXED_INPUTS.json') and len(pins)==306 and set(pins)==set(s['source_checks']))
    pin_bad=[]
    for name,digest in pins.items():
        path=Path(name) if Path(name).is_absolute() else WT/name
        if sha(path.read_bytes())!=digest or s['source_checks'][name] is not True:pin_bad.append(name)
    ck('306_current_and_pre_post_pins',not pin_bad,pin_bad)
    init=read(BATCH/'smoke/run_01/ACTUAL_INITIALIZE.json')['result']['_meta']['human_eye']
    ck('actual_G_loaded_identity',init['source_sha256']==canonical and init['source_file_count']==137 and init['distribution_version']=='9.7.2+sg.r1' and init['source_kind']=='installed_distribution' and init['identity_check']['compatible'])
    events=[json.loads(line) for line in (BATCH/'smoke/run_01/native/WORKER_EVENTS.jsonl').read_bytes().splitlines() if line]
    ck('one_smoke_three_business_plus_close',len(s['rows'])==3 and events==s['worker_events'] and len(events)==4 and [e['sequence'] for e in events]==[1,2,3,4] and events[-1]['status']=='unknown')
    ck('three_business_unprofiled_and_no_images',all(e['status']=='completed' and 'qa_work' not in e and e['render_events_before']==e['render_events_after']==0 and not e['changed_or_new_PNG_files'] for e in events[:3]))
    ck('actual_PID_and_owned_exit',s['passed'] and not s['errors'] and s['product_close']['confirmed'] and s['product_close']['exit_code']==0 and s['product_close']['process_reaped'] and s['product_runtime_exit']['confirmed'] and s['product_runtime_exit']['exited'] and s['product_runtime_exit']['exit_code']==0 and s['native_close']['process_reaped'] and s['native_close']['exit_code']==0 and s['native_close']['source_file_unchanged'] and s['native_close']['protected_files_unchanged'] and not s['worker_closed']['poisoned'] and s['worker_closed']['initial_geometry_fingerprint']==s['worker_closed']['final_geometry_fingerprint'])
    rpc=read(BATCH/'smoke/run_01/product/RPC.json');ck('7_stdio_four_metadata_no_extra_business',len(rpc['requests'])==7 and [r['method'] for r in rpc['requests']]==['initialize','notifications/initialized','tools/list','ping','tools/call','tools/call','tools/call'])
    resources={};state=None;cores=[];geometry=[];resource_deltas=[]
    for i,row in enumerate(s['rows'],1):
        mode=row['mode'];folder=BATCH/'smoke/run_01/native'/f'call_{i}'
        raw=(folder/'stdout.txt').read_text(encoding='utf8');packets=[json.loads(line.split(':',1)[1]) for line in raw.splitlines() if line.startswith('HUMAN_EYE_BLENDER_MCP:')]
        ck(mode+'_one_raw_capture',len(packets)==1 and packets[0]==row['capture_proof']['capture_envelope'])
        packet=packets[0]['result'];cap=packet['capture'];resource_deltas.append(len(packet['resources']))
        for r in packet['resources']:resources[r['id']]=r
        if state is None:state=cap['capture_state']
        ck(mode+'_same_capture_revision_and_instance',cap['capture_state']==state and cap['revision']==row['body']['context']['scene_revision'] and set(packet['live_resources'])==set(resources))
        public=[row['body']['target'],*row['body']['candidates']];ident=cap['host_identity']
        ck(mode+'_public_host_identity',ident['document_epoch']==row['body']['context']['host_identity']['document_epoch'] and all(ident['object_instances'][obj['object_id']]==obj['instance_id'] for obj in public))
        expected_geometry=[]
        for name in ('N16','N28'):
            mesh=next(m for m in cap['meshes'] if m['name']==name);ref=mesh['_scene_resource'];r=resources[ref['id']]
            matrix,scale=ref['matrix'],ref['scale'];local=r['vertices_local']
            ck(mode+'_'+name+'_finite_source',all(math.isfinite(x) for p in local+matrix for x in p) and math.isfinite(scale) and r['revision']==ref['revision'])
            # Exact rational affine evaluation from raw binary floats, followed by one float conversion.
            world=[[float((sum((Fraction(matrix[axis][k])*Fraction(point[k]) for k in range(3)),Fraction(matrix[axis][3])))*Fraction(scale)) for axis in range(3)] for point in local]
            faces=r['faces'];ck(mode+'_'+name+'_triangle_indices',all(len(t)==3 and len(set(t))==3 and all(type(k) is int and 0<=k<len(world) for k in t) for t in faces))
            expected_geometry.append({'name':name,'object_id':mesh['object_id'],'vertices_world':world,'triangles':faces})
        expected_public=[{k:v for k,v in o.items() if k!='triangles'} for o in expected_geometry] if mode=='vertices' else expected_geometry
        ck(mode+'_geometry_from_independent_exact_forward_map',('geometry' not in row['body']) if mode=='OFF' else row['body']['geometry']['objects']==expected_public)
        ck(mode+'_same_core_runtime_source',row['body']['context']['runtime_source_sha256']==canonical)
        cores.append({k:v for k,v in row['body'].items() if k not in ('trace_id','geometry')})
        geometry.append({'mode':mode,'vertices':sum(len(o['vertices_world']) for o in expected_geometry),'triangles':sum(len(o['triangles']) for o in expected_geometry),'objects':expected_geometry})
        io_path=BATCH/'smoke/run_01/product'/f'{i+4:03}'
        ck(mode+'_raw_wire_saved_response',json.loads((io_path/'RX.bin').read_bytes())==row['response'] and json.loads((io_path/'TX.bin').read_bytes())==row['request'] and json.loads(row['response']['result']['content'][0]['text'])==row['body'])
    ck('40_vertices_76_faces',all(g['vertices']==40 and g['triangles']==76 for g in geometry))
    ck('same_core_and_resources_4_0_0',cores[0]==cores[1]==cores[2] and resource_deltas==[4,0,0])
    ck('cold_false_warm_true_result_cache', [r['result_cache_hit'] for r in s['task_work']]==[False,True,True] and all(r[k]==0 for r in s['task_work'][1:] for k in ['closed_solid_pair_count','exact_pair_count','surface_pair_count']))
    reuse=read(BATCH/'INPUT_REUSE.json');bad=[]
    for r in reuse['reused']:
        if not ((WT/r['new']).read_bytes()==(WT/r['original']).read_bytes() and sha((WT/r['new']).read_bytes())==r['sha256']):bad.append(r['new'])
    ck('9_common_inputs_original_bytes',len(reuse['reused'])==9 and not bad,bad)
    rb=read(BATCH/'runtime/REUSE_BINDINGS.json')
    ck('actor_transport_original_bytes',all((BATCH/'runtime'/name).read_bytes()==(WT/rb['files'][name]['source']).read_bytes() and sha((BATCH/'runtime'/name).read_bytes())==rb['files'][name]['current_sha256'] for name in ('actor.py','consumer_transport.py')))
    ck('common_CLI_pinned',sha(Path(rb['CLI']['path']).read_bytes())==rb['CLI']['sha256']==plan['CLI_sha256'])
    transport_ast=ast.parse((BATCH/'runtime/consumer_transport.py').read_bytes());settings_fn=next(n for n in transport_ast.body if isinstance(n,ast.FunctionDef) and n.name=='settings')
    common_settings=ast.literal_eval(settings_fn.body[0].value)
    ck('common_provider_model_settings',common_settings['model']=='gpt-6.1-sol' and common_settings['model_reasoning_effort']=='medium' and common_settings['forced_login_method']=='chatgpt' and common_settings['model_provider']=='openai_http' and common_settings['model_providers.openai_http']['base_url']=='https://chatgpt.com/backend-api/codex' and common_settings['features.hooks'] is False and common_settings['features.memories'] is False)
    common=read(BATCH/'synthetic/FROZEN_INPUTS_01.json')['common_parameters'];oldplan=read(WT/'verification/m4_local_relation_consumption_001/PLAN.json')
    ck('14_common_budget_parameters',len(common)==14 and all(plan[k]==v==oldplan[k] for k,v in common.items()),common)
    image=(BATCH/'input/INITIAL.png').read_bytes();prepared=read(BATCH/'runtime/PREPARED_INPUT.json')['initial_image']
    ck('actual_common_image_1200_900',image[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',image[16:24])==(1200,900) and len(image)==prepared['bytes']==1185069 and sha(image)==prepared['sha256']==plan['inputs']['image_sha256'])
    ck('31_dispatch_pins',len(plan['dispatch_input_sha256'])==31 and all(sha((BATCH/p).read_bytes())==digest for p,digest in plan['dispatch_input_sha256'].items()))
    ck('no_formal_consumers_or_GO',ready['model_consumers']==0 and ready['formal_GO'] is False and not (BATCH/'GO.json').exists() and not (BATCH/'cells').exists())
    costs=read(BATCH/'PREPARATION_COST.json');elapsed=(s['ended_ns']-s['started_ns'])/1e9
    ck('smoke_cost_window',elapsed==costs['smoke_program_elapsed_s']==1.9181463)
    ck('install_cost_window',inst['elapsed_ns']/1e9==costs['G_build_install_program_elapsed_s']==3.8376324)
    window=costs['coordinator_window'];chat=(datetime.fromisoformat(window['snapshot_at_utc'])-datetime.fromisoformat(window['started_at_utc'])).total_seconds()
    ck('separate_overlapping_coordination_window',chat==window['elapsed_s'] and costs['do_not_add_overlapping_windows'] and costs['program_intervals_overlap_chat_window'])
    ck('old_attribution_and_failures_unchanged',git('diff','--name-only',plan['preparation_start_commit'],HEAD,'--','verification/m4_default_latency_attribution_001','verification/m4_relation_selected_evidence_001')==b'')
    ck('implementation_status_unchanged',before==git('status','--short').decode())
    failed=[c for c in checks if not c['passed']]
    result={'scope':'saved PREP source/wheel/geometry/common-input audit only','HEAD':HEAD,'passed':not failed,'checks':checks,'failed_checks':failed,'check_count':len(checks),'files':files,'wheel_record':wheel_report,'geometry':geometry,'common_settings':common_settings,'preparation_cost':costs,'new_Blender_or_product_or_model_calls':0,'formal_model_input_usage':None,'formal_benefit':None}
    with args.output.open('x',encoding='utf8',newline='\n') as out:json.dump(result,out,ensure_ascii=False,indent=2,allow_nan=False);out.write('\n')
    print(json.dumps({'passed':not failed,'checks':len(checks),'failed':failed,'output':str(args.output)},ensure_ascii=False))
    return 0 if not failed else 1
if __name__=='__main__':raise SystemExit(main())
