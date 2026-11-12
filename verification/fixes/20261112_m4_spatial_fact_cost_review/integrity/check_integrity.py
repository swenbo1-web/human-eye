"""Independent saved-data integrity audit; no product modules or live calls."""
from pathlib import Path
import ast,datetime,hashlib,json,subprocess,tomllib,zipfile

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
ROOT_REVIEW=Path('D:/hefe')
HERE=Path(__file__).resolve().parent
B='verification/m4_spatial_fact_consumption_001/'
C=B+'cost_review_01/'
CURRENT='a44a6138b9d354ecc98a4fbd76095f0536d6973f'
AUTHOR='5cdf62f311f94890ca569d06c1a858f1578225e4'
PREP='02c7784ec4e23e9b03a3485367d8db54b4d5db34'
QUALITY='3a4b090532e01920110e6ee2be1702bc1c45c265'
PRODUCT='e836e03f4b3821f869c72ac3e50df5204f28b50f'
EXPECTED_SOURCE='2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390'
SEAL_PATH='verification/fixes/20261112_m4_spatial_fact_consumption_review/QUALITY_SEAL.json'
sha=lambda data:hashlib.sha256(data).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args])
def read(path):return json.loads((ROOT/path).read_bytes())
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
assert git('rev-parse','HEAD').decode().strip()==CURRENT
assert git('status','--porcelain')==b''
reader=subprocess.Popen(['git','-C',str(ROOT),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
def blob(commit,path):
    reader.stdin.write((commit+':'+path+'\n').encode());reader.stdin.flush()
    head=reader.stdout.readline().split();assert len(head)==3 and head[1]==b'blob',(commit,path,head)
    raw=reader.stdout.read(int(head[2]));assert reader.stdout.read(1)==b'\n'
    return head[0].decode(),raw
def check_blob(commit,path,raw):
    _,data=blob(commit,path);assert data==raw,(commit,path)

try:
    original=read(C+'ORIGINAL_DATA_INDEX.json')
    assert original['author_commit']==AUTHOR
    rows=original['original_batch_files'];assert len(rows)==1087
    indexed={row['path']:row for row in rows};assert len(indexed)==1087
    author_paths=set(git('ls-tree','-r','--name-only',AUTHOR,'--',B).decode().splitlines())
    assert set(indexed)==author_paths
    for path,row in indexed.items():
        assert path.startswith(B) and not path.startswith(C) and '..' not in Path(path).parts
        raw=(ROOT/path).read_bytes();oid,fixed=blob(AUTHOR,path)
        assert raw==fixed and oid==row['git_blob'] and len(raw)==row['bytes'] and sha(raw)==row['sha256'],path
        check_blob(CURRENT,path,raw)
    changes=git('diff','--name-status',AUTHOR,CURRENT).decode().splitlines()
    assert len(changes)==27 and all(line.startswith('A\t'+C) for line in changes)
    manifest=read(C+'REVIEW_MANIFEST.json');new_rows=manifest['files'];assert len(new_rows)==26
    new_paths={C+row['path'] for row in new_rows}|{C+'REVIEW_MANIFEST.json'}
    assert new_paths=={line.split('\t')[1] for line in changes}
    for row in new_rows:
        path=C+row['path'];raw=(ROOT/path).read_bytes()
        assert len(raw)==row['bytes'] and sha(raw)==row['sha256'],path
        check_blob(CURRENT,path,raw)
    check_blob(CURRENT,C+'REVIEW_MANIFEST.json',(ROOT/(C+'REVIEW_MANIFEST.json')).read_bytes())

    seal_raw=(ROOT/(C+'quality_source/QUALITY_SEAL.json')).read_bytes()
    assert sha(seal_raw)=='fa467d121359d8ffff45693887de2598f1d34a811bf031849215042ef0e44852'
    check_blob(QUALITY,SEAL_PATH,seal_raw)
    assert (ROOT_REVIEW/SEAL_PATH).read_bytes()==seal_raw
    seal=json.loads(seal_raw);assert seal['author_evidence_commit']==AUTHOR
    assert seal['private_map_cost_usage_read_before_seal'] is False
    for row in seal['files']:
        raw=(ROOT_REVIEW/row['path']).read_bytes()
        assert len(raw)==row['bytes'] and sha(raw)==row['sha256'],row['path']
        check_blob(QUALITY,row['path'],raw)
    assert len(seal['files'])==20
    quality_review_path='docs/M4_SPATIAL_FACT_CONSUMPTION_001_QUALITY_REVIEW.md'
    check_blob(QUALITY,quality_review_path,(ROOT/(C+'quality_source/QUALITY_REVIEW.md')).read_bytes())
    work=read(C+'WORK_ORDER.json')
    commit_times={commit:git('show','-s','--format=%cI',commit).decode().strip() for commit in (AUTHOR,QUALITY,CURRENT)}
    dt=lambda v:datetime.datetime.fromisoformat(v)
    assert dt(commit_times[AUTHOR])<dt(seal['sealed_at_utc'])<=dt(commit_times[QUALITY])<dt(work['recorded_utc'])<dt(commit_times[CURRENT])

    plan=read(B+'PLAN.json');freeze=read(B+'FREEZE.json');go=read(B+'GO.json')
    plan_raw=(ROOT/(B+'PLAN.json')).read_bytes();plan_hash=sha(plan_raw)
    assert plan_hash==freeze['plan_sha256']=='d40c81babcb1a9d1826752df4dfe23e5d790536bd23cf0798edc0bbc90f9e672'
    check_blob(PREP,B+'PLAN.json',plan_raw)
    assert go['plan_sha256']==plan_hash and go['authorized'] is True and go['max_consumers']==6
    for path,digest in plan['dispatch_input_sha256'].items():
        raw=(ROOT/B/path).read_bytes();assert sha(raw)==digest,path
        check_blob(PREP,B+path,raw)
    for path,digest in plan['external_input_sha256'].items():assert sha(Path(path).read_bytes())==digest,path
    binding=read(B+'preflight/SOURCE_BINDING.json');runtime_manifest=binding['source_manifest'];assert len(runtime_manifest)==137
    ready=read(B+'installations/P_READY.json');installed=Path(ready['install_root'])
    assert ready['commit']==PRODUCT and ready['source_sha256']==binding['source_sha256']==EXPECTED_SOURCE
    for row in runtime_manifest:
        raw=(ROOT/row['path']).read_bytes();assert sha(raw)==row['sha256']
        check_blob(PRODUCT,row['path'],raw);check_blob(AUTHOR,row['path'],raw);check_blob(CURRENT,row['path'],raw)
        assert (installed/row['path']).read_bytes()==raw,row['path']
    constants={node.targets[0].id:ast.literal_eval(node.value) for node in ast.parse((ROOT/'human_eye_plugin/runtime_identity.py').read_bytes()).body
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)
        and node.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION')}
    assert sha(canonical(dict(base_version=constants['BASE_VERSION'],implementation_revision=constants['IMPLEMENTATION_REVISION'],files=runtime_manifest)))==EXPECTED_SOURCE
    asset=(ROOT/B/plan['inputs']['scene']).read_bytes();asset_sha=sha(asset)
    assert asset_sha==plan['inputs']['scene_sha256']==binding['asset_sha256']
    assert Path(binding['actual_asset_copy']).read_bytes()==asset
    schema={group:read(B+'schemas/'+group+'_CONSUMER_TOOLS.json') for group in ('N','P')}
    common=read(B+'schemas/COMMON_NATIVE.json')
    native_ast=ast.parse((ROOT/'verification/native_plugin_complex_003/actor.py').read_bytes())
    original_common=next(ast.literal_eval(node.value) for node in native_ast.body
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='NATIVE' for t in node.targets))
    assert original_common==common
    original_common_digest=sha((json.dumps(original_common,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode())
    assert schema['N']==[common] and schema['P'][0]==common and len(schema['P'])==2
    assert schema['P'][1:]==read(B+'schemas/P_PUBLIC_TOOLS.json')
    old_tools=read(Path(binding['previous_actual_tools_list']))
    assert sha(Path(binding['previous_actual_tools_list']).read_bytes())==binding['previous_actual_tools_list_sha256']
    # Previous actual tools record may wrap the JSON-RPC result once.
    previous_decl=old_tools['result']['tools'] if 'result' in old_tools else old_tools['response']['result']['tools']
    assert [tool for tool in previous_decl if tool['name']=='human_eye_scene_observe']==schema['P'][1:]
    config=read(B+'preflight/CONSUMER_CONFIGURATION.json')
    run=read(B+'RUN_RESULT.json');sequence=plan['sequence']
    assert len(run['records'])==run['started_cells']==run['maximum_consumers']==6
    assert run['all_planned_dispatched'] is True and run['no_replacements'] is True and run['stop'] is None
    assert [r['group'] for r in sequence]==['N','P','P','N','N','P']
    assert [r['cell'] for r in sequence]==['spc01','spc02','spc03','spc04','spc05','spc06']
    summaries=[];threads=set();native_workspaces=set();tools_lists=0;archive_members=0
    mappings=read(B+'private/ANON_MAP.json')['rows'];mapping_by_cell={r['cell']:r for r in mappings}
    for slot,record in zip(sequence,run['records']):
        name=slot['cell'];base=B+'cells/'+name+'/';group=slot['group']
        assert all(record[k]==slot[k] for k in ('cell','group','round','task'))
        consumer=read(base+'CONSUMER.json');owner=read(base+'owner/CLOSE.json');finish=read(base+'OWNER_FINISH.json')
        launch=read(base+'ACTOR_LAUNCH.json');session=read(base+'owner/native/SESSION.json');cfg=read(base+'ACTOR_CONFIG.json')
        assert record['consumer']==consumer and record['finish']==finish
        assert record['errors']==[] and consumer['errors']==[] and consumer['unexpected_tool_deviations']==[]
        assert consumer['status']=='completed' and consumer['exit_code']==0 and consumer['process_reaped'] is True
        assert consumer['safe_to_continue'] is True and consumer['valid_completion'] is True
        assert consumer['thread_id'] not in threads;threads.add(consumer['thread_id'])
        assert consumer['deadline_ns']==consumer['started_ns']+450*10**9
        deadline=record['cell_started_ns']+570*10**9
        assert record['worker_deadline_ns']==launch['worker_deadline_ns']==session['deadline_ns']==deadline
        assert record['cell_ended_ns']<deadline and record['within_570s'] is True
        assert consumer['input_image_count']==consumer['public_image_count']==0 and '--image' not in consumer['argv']
        assert consumer['input_sha256']==plan['inputs']['prompt_sha256']
        argv=consumer['argv'];settings={}
        for i,arg in enumerate(argv):
            if arg=='-c':
                key,value=argv[i+1].split('=',1);assert key not in settings
                settings[key]=tomllib.loads('value='+value)['value']
        for key,value in config['settings'].items():assert settings[key]==value,(name,key)
        assert sha(Path(argv[0]).read_bytes())==plan['CLI_sha256']
        server=settings['mcp_servers.arm_engine']
        assert set(server['tools'])==set(consumer['expected_tool_names'])=={tool['name'] for tool in schema[group]}
        assert all(row['approval_mode']=='approve' for row in server['tools'].values())
        assert all(flag in argv for flag in ('--ignore-user-config','--ignore-rules','--ephemeral','--strict-config'))
        assert finish['confirmed'] is True and finish['exit_code']==0 and finish['close']==owner
        assert finish['actor_pid']==launch['pid']==owner['actor_parent_pid']
        assert owner['errors']==[] and owner['confirmed'] is True and owner['geometry_unchanged'] is True and owner['asset_unchanged'] is True
        assert (ROOT/(base+'owner/INITIAL.json')).read_bytes()==(ROOT/(base+'owner/FINAL.json')).read_bytes()
        native=owner['native_close'];worker=owner['worker_closed']
        assert native['pid']==worker['pid']==session['pid']
        assert native['process_reaped'] is True and native['exit_code']==0 and native['error'] is None
        assert native['response']['status']=='closed' and native['response']['pid']==session['pid']
        assert native['original_deadline_ns']==worker['original_deadline_ns']==deadline
        assert worker['poisoned'] is False and worker['final_geometry_fingerprint']==worker['initial_geometry_fingerprint']
        assert read(base+'owner/native/WORKER_CLOSED.json')==worker
        native_close_files=[path for path in indexed if path.startswith(base+'owner/native/CLOSE_') and path.endswith('.json')]
        assert len(native_close_files)==1 and read(native_close_files[0])==native
        assert session['workspace'] not in native_workspaces;native_workspaces.add(session['workspace'])
        assert Path(session['asset_copy']).read_bytes()==asset
        assert cfg['asset_sha256']==session['asset_sha256']==asset_sha
        assert owner['zero_new_images_budget_met'] is True and owner['image_construction']['status']=='not_observed_in_recorded_scope'
        bridge=consumer['bridge_cleanup']
        assert bridge['confirmed'] is None and bridge['receipt_status']=='unknown' and bridge['missing_exit_count']==1
        assert len(bridge['instances'])==1 and bridge['instances'][0]['exit'] is None
        bridge_path=Path(bridge['instances'][0]['directory'])
        assert not (bridge_path/'EXIT.json').exists()
        assert json.loads((bridge_path/'STARTED.json').read_bytes())==bridge['instances'][0]['started']
        identity=read(base+'owner/IDENTITY.json')
        assert identity['common_native_sha256']==original_common_digest
        runtime_summary=None
        if group=='P':
            assert identity['runtime_identity']['source_sha256']==EXPECTED_SOURCE and identity['runtime_identity']['source_kind']=='installed_distribution'
            product_config=read(base+'owner/product_config.json')
            expected_config={'schema_version':'1.0','enabled':True,'observe_on_prompt':False,'project_root':str(installed),
                'state_file':str(ROOT/(base+'owner/state.json')),'audit_file':str(ROOT/(base+'owner/audit.jsonl')),
                'quad_size':128,'request_budget_s':30.,'max_sessions':4,'expected_identity':{'source_sha256':EXPECTED_SOURCE},
                'blender':{'host':session['host'],'port':session['port'],'timeout_s':30.}}
            assert product_config==expected_config
            plugin_start=read(base+'owner/plugin/START.json');plugin_close=read(base+'owner/plugin/CLOSE.json')
            assert '--spatial-task-only' not in plugin_start['command'] and plugin_start['command'][3]==ready['entry']
            assert owner['plugin_close']==plugin_close and plugin_close['launcher_pid']==plugin_start['launcher_pid']
            assert plugin_close['confirmed'] is True and plugin_close['process_reaped'] is True and plugin_close['exit_code']==0 and plugin_close['reader_stopped'] is True
            proof=read(base+'owner/PRODUCT_RUNTIME_PROOF.json');runtime_exit=owner['product_runtime_exit']
            assert proof['confirmed'] is True and proof['launcher_pid']==plugin_start['launcher_pid']
            assert proof['parent_chain'][0]['pid']==proof['runtime_pid'] and proof['parent_chain'][-1]['pid']==proof['launcher_pid']
            assert proof['proved_ns']<min(row['started_ns'] for row in owner['tools'])
            assert runtime_exit['confirmed'] is True and runtime_exit['exited'] is True and runtime_exit['exit_code']==0 and runtime_exit['handle_closed'] is True
            assert runtime_exit['observed_ns']>=proof['proved_ns']
            plugin_tools=read(base+'owner/PLUGIN_TOOLS.json')['result']['tools']
            assert [tool for tool in plugin_tools if tool['name']=='human_eye_scene_observe']==schema['P'][1:]
            runtime_summary={'runtime_pid':proof['runtime_pid'],'launcher_pid':proof['launcher_pid'],'retained_handle_exit_confirmed':True}
        else:
            assert owner['plugin_close'] is None and owner['product_runtime_exit'] is None and identity['runtime_identity'] is None
        # Inspect exact saved MCP response, not only the producer's tools/list assertion.
        found=0
        for path in indexed:
            if path.startswith(base+'attachments/') and path.endswith('/TX.bin'):
                request=json.loads((ROOT/path).read_bytes())
                if request.get('method')=='tools/list':
                    response=read(path[:-6]+'RX.bin')
                    assert response['result']['tools']==schema[group]
                    found+=1
        assert found==1;tools_lists+=found
        anonymous=mapping_by_cell[name]['anonymous_id']
        with zipfile.ZipFile(ROOT/(B+'runtime/handoff_01/private/raw/'+anonymous+'.zip')) as archive:
            members=archive.namelist();assert len(members)==len(set(members))
            expected={path[len(base):] for path in indexed if path.startswith(base)}
            assert set(members)==expected
            for member in members:assert archive.read(member)==(ROOT/(base+member)).read_bytes()
            archive_members+=len(members)
        final=(ROOT/(base+'PUBLIC_FINAL.txt')).read_bytes()
        assert (ROOT/(B+'runtime/handoff_01/public/'+anonymous+'/answer.txt')).read_bytes()==final
        summaries.append({'cell':name,'group':group,'consumer_completed_and_reaped':True,'owner_launcher_pid':launch['pid'],
            'owner_actual_pid':owner['actor_pid'],'native_pid':session['pid'],'native_reaped_exit_0':True,
            'runtime':runtime_summary,'thin_client_receipt':'unknown','thin_client_exit_file_absent':True,
            'original_deadline_preserved':True,'tools_list_equals_frozen':True,'archive_exact_members':len(members)})
    result={'passed':True,'scope':'Independent saved-source and lifecycle-evidence audit; no product/model/Blender/API calls or geometry rescoring.',
        'fixed_original_commit':AUTHOR,'fixed_cost_commit':CURRENT,'original_files_verified':len(rows),
        'new_files_verified':len(new_paths),'review_manifest_entries':len(new_rows),'git_changes_only_new_cost_review_files':True,
        'quality_seal_sha256':sha(seal_raw),'quality_sealed_files_verified':len(seal['files']),
        'quality_order':{'author_commit':commit_times[AUTHOR],'sealed_at':seal['sealed_at_utc'],'quality_commit':commit_times[QUALITY],
            'unseal_local_record':work['recorded_utc'],'cost_commit':commit_times[CURRENT],
            'recorded_order_valid':True,'earliest_private_access_independently_observable':False,
            'limitation':'Git/seal/record timestamps establish recorded artifact order, not an exhaustive access log. Local unseal work order explicitly records preceding read-only inspection.'},
        'runtime_sources_worktree_git_install_equal':137,'runtime_source_sha256':EXPECTED_SOURCE,
        'frozen_dispatch_inputs_verified':len(plan['dispatch_input_sha256']),'frozen_external_inputs_verified':len(plan['external_input_sha256']),
        'actual_tools_lists_verified':tools_lists,'product_configs_bound_to_private_sessions':3,'original_archive_members_verified':archive_members,
        'six_cells':summaries,'thin_exit_unknown_cells':6,'distinct_consumer_threads':len(threads),'distinct_native_workspaces':len(native_workspaces),
        'limitations':['Saved source-bound process receipts were checked; no new operating-system live process probe was run.',
            'Thin-client missing EXIT remains unknown and is not upgraded by independent backend exit receipts.',
            'Terminal geometry/hash equality and recorded native audit do not prove absence of every transient operation.',
            'No provider/model resolved identity, exact provider call count or fee is inferred.',
            'No cost arithmetic or geometry quality re-scoring in this subtask.'],
        'AL':{'context_bound':True,'assignment_current':False,'task_access':'parent_read_only','borrowed_parent_handle':False,'parent_task_written':False}}
    (HERE/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('passed','original_files_verified','new_files_verified','quality_sealed_files_verified','runtime_sources_worktree_git_install_equal','actual_tools_lists_verified','original_archive_members_verified','thin_exit_unknown_cells')},sort_keys=True))
finally:
    reader.stdin.close();reader.stdout.close();assert reader.wait(timeout=30)==0
