"""Independently bind all original failures to the sealed selective transport run."""

import argparse
import ast
from hashlib import file_digest, sha256
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from types import SimpleNamespace
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
VERIFICATION = HERE.parent
ROOT = VERIFICATION.parent
OLD = VERIFICATION / 'm2_source_region_cold_selective_transport_001'
RUN = Path('D:/he_m2_source_region_cold_selective_transport_001').resolve()
RECOVERY = Path('D:/he_m2_source_region_cold_selective_transport_recovery_001').resolve()
COMMIT = 'f75b94549'
ARTIFACTS = ('FROZEN.json','REPORT.md','RESULT.json','experiment.py','host.py','mcp_entry.py','verify.py',
             'install/PRODUCT_RUN_BINDING.json','PUBLIC_EVIDENCE.zip')
OLD_HOST = VERIFICATION / 'm2_source_region_shared_normalization_live_001/host.py'
OLD_CLOSE = VERIFICATION / 'm4_dense_panel_sweep_formal_001/harness/closure.py'
LABELS = {'AA':('assembly','A'),'AB':('assembly','B'),'YA':('yanyite','A'),'YB':('yanyite','B')}
LOCAL_GUARD = 'only_live_source_region_business_dispatch'
PRIVATE_GUARD = 'source_region query contains unsupported fields'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(path):
    with path.open('rb') as stream:
        return file_digest(stream,'sha256').hexdigest()


def pin(path):
    path = Path(path).resolve(strict=True)
    return {'path':str(path),'bytes':path.stat().st_size,'sha256':digest(path)}


def unique_object(items):
    result = {}
    for key,value in items:
        require(key not in result,'duplicate_historical_json_key/'+key)
        result[key] = value
    return result


def parse(raw):
    return json.loads(raw,object_pairs_hook=unique_object)


def read(path):
    return parse(path.read_bytes())


def git(*args):
    return subprocess.check_output(['git','-C',str(ROOT),*args])


def old_blob(commit,path):
    data = git('show',commit+':'+path.relative_to(ROOT).as_posix())
    require(path.read_bytes() == data,'old_committed_input_changed/'+str(path))
    return data


def archived_members(path,indexed):
    with ZipFile(path) as archive:
        names = archive.namelist()
        require(len(set(names)) == len(names) and set(names) == set(indexed),
                'old_archive_member_names_changed/'+path.name)
        for name in names:
            disk = (RUN/name).resolve(strict=True)
            expected = indexed[name]
            require(disk.is_relative_to(RUN) and disk.stat().st_size == expected['bytes']
                    and digest(disk) == expected['sha256'] and archive.getinfo(name).file_size == expected['bytes'],
                    'old_loose_original_changed/'+name)
            # Reading to EOF also checks the ZIP member CRC.
            with archive.open(name) as source:
                require(file_digest(source,'sha256').hexdigest() == expected['sha256'],
                        'old_archive_member_bytes_changed/'+name)


def archive_proof(result):
    published = result['local_original']
    index_path = RUN/'sealed/RAW_INDEX.json'
    archive_path = RUN/'sealed/ORIGINAL_RUNTIME.zip'
    archive = pin(archive_path)
    index = read(index_path)
    require(index['archive'] == archive and published['index'] == pin(index_path)
            and all(published[key] == archive[key] for key in ('path','bytes','sha256'))
            and index['member_count'] == published['member_count'] == len(index['members']) == 803,
            'old_runtime_archive_identity_changed')
    archived_members(archive_path,index['members'])

    public = result['public']
    public_path = OLD/'PUBLIC_EVIDENCE.zip'
    require(digest(public_path)==public['sha256'] and public_path.stat().st_size==public['bytes'],
            'old_public_archive_identity_changed')
    members = public['members']
    require(len(members) == 61 and all(index['members'][name] == row for name,row in members.items()),
            'old_public_archive_not_exact_subset')
    archived_members(public_path,members)
    return {'archive':archive,'index':pin(index_path),'members_verified':803,'public_members_verified':61}


def old_function(source,path,name,namespace,*,class_name=None):
    tree = ast.parse(source,filename=str(path))
    scope = tree.body
    if class_name is not None:
        klass, = (node for node in scope if isinstance(node,ast.ClassDef) and node.name==class_name)
        scope = klass.body
    node, = (node for node in scope if isinstance(node,ast.FunctionDef) and node.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
    return namespace[name],node


def forbidden(*_args,**_kwargs):
    raise AssertionError('legacy_rejection_must_precede_host_dispatch')


def reproduced_paths(commit,source):
    observe,_ = old_function(old_blob(commit,OLD_HOST),OLD_HOST,'observe',{'require':require},class_name='Slot')
    namespace = {'host':SimpleNamespace(PRIVATE_TOOL='m2_private_source_region_measure')}
    private,_ = old_function(source,OLD/'experiment.py','call_private',namespace)
    tree = ast.parse(source,filename=str(OLD/'experiment.py'))
    formal, = (node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='live_slot')
    wrap, = (node for node in ast.walk(formal) if isinstance(node,ast.Call)
             and ast.unparse(node.func)=='slot.observe')
    return observe,private,compile(ast.Expression(body=wrap),str(OLD/'experiment.py'),'eval')


def reject(call,message):
    try:
        call()
    except ValueError as exc:
        require(str(exc) == message,'old_rejection_reason_changed/'+str(exc))
        return str(exc)
    raise ValueError('expected_historical_rejection_was_admitted/'+message)


def old_product_validator(binding):
    installed = Path(binding['install_root']).resolve(strict=True)
    source = installed/'human_eye_plugin/query_policy.py'
    actual = git('show',binding['preparation_git']+':human_eye_plugin/query_policy.py')
    require(source.read_bytes() == actual,'old_installed_query_validator_changed')
    sys.path[:0] = [str(installed),binding['dependency_root']]
    from human_eye_plugin import query_policy

    require(Path(query_policy.__file__).resolve() == source,'historical_candidate_policy_import_path_changed')
    return query_policy.validate_source_region_query, pin(source)


def whole_entry(path,expected):
    return pin(path) == expected


def verify_source(slot,expected,closed):
    initial = closed['initial_source']
    terminal = closed['terminal_source']
    materials = []
    for row,directory in ((initial,slot/'initial_capture'),(terminal,slot)):
        expected_path = directory/'TERMINAL_SOURCE.json'
        proof = pin(expected_path)
        require(all(proof[key] == row[key] for key in ('path','bytes','sha256'))
                and row['status'] == 'complete' and row['terminal'] is True
                and row['worker']['pid'] == expected['pid']
                and row['worker']['sha256'] == proof['sha256']
                and row['worker']['bytes'] == proof['bytes'],
                'legacy_terminal_source_not_same_closed_process/'+slot.name)
        data = read(expected_path)
        root = data['source']
        require(root['pid'] == expected['pid']
                and Path(root['asset_copy']).resolve() == (slot/'native/input.blend').resolve()
                and root['asset_sha256'] == digest(slot/'native/input.blend'),
                'legacy_source_asset_identity_changed/'+slot.name)
        materials.append((data,proof))
    independent = closed['independent_before_after']
    keys = ('source','objects','source_face_offsets','display_object_mask','layer_collections','scene_cameras')
    require(independent['passed'] is True and independent['same_owned_scene'] is True
            and independent['checked'] == list(keys)
            and all(materials[0][0][key] == materials[1][0][key] for key in keys)
            and independent['initial_sha256'] == materials[0][1]['sha256']
            and independent['terminal_sha256'] == materials[1][1]['sha256']
            and initial['worker']['file_closed_ns'] < terminal['worker']['started_ns'] < closed['closed_ns'],
            'legacy_independent_first_last_do_not_agree/'+slot.name)
    return materials[0][1],materials[1][1]


def verify_wire(slot,arm,packed,guard,private,wrap,validate):
    directory = slot/'mcp'
    rpc = sorted(directory.glob('rpc_*/TX.bin'))
    calls = [(path,read(path)) for path in rpc if read(path).get('method')=='tools/call']
    worker = [parse(line) for line in (slot/'mcp_io/MCP_IO.jsonl').read_bytes().splitlines()]
    business = [row for row in worker if row['method']=='tools/call']
    if arm == 'A':
        baseline = SimpleNamespace(preflight=False,label=slot.name,runtime=SimpleNamespace(
            budget=SimpleNamespace(admit_business=forbidden),public_request=forbidden))
        baseline.observe = lambda arguments: guard(baseline,arguments)
        require(not calls and not business,'legacy_A_has_business_wire/'+slot.name)
        return {'reproduced_error':reject(lambda:eval(wrap,{'slot':baseline,'query':packed}),LOCAL_GUARD),
                'rejects_before_budget_admission':True,'requests':0}

    require(len(calls)==len(business)==1,'legacy_B_rejection_wrong_business_count/'+slot.name)
    tx,request = calls[0]
    rx = tx.with_name('RX.bin')
    response = read(rx)
    receipt = read(tx.with_name('RECEIPT.json'))
    meter, = business
    request_id = 'private-observe-1'
    budget_calls = []
    slot_stub = SimpleNamespace(label=slot.name,runtime=SimpleNamespace(
        budget=SimpleNamespace(admit_business=lambda *args:budget_calls.append(args))),
        client=SimpleNamespace(call=lambda value:value))
    actual_old_call = private(slot_stub,packed,request_id)
    require(budget_calls == [(slot.name,'formal')] and actual_old_call == request and
            request['params']['arguments'] == {'include_image':False,'query':packed} and
            request['id'] == response['id'] == receipt['id'] == meter['id'] == meter['response_id'] == request_id,
            'legacy_B_actual_request_nesting_changed/'+slot.name)
    content = response['result']['content']
    require(response['result']['isError'] is True and len(content) == 1 and content[0]['type']=='text',
            'legacy_B_rejection_result_shape_changed/'+slot.name)
    error = parse(content[0]['text'])
    require(error['status']=='error' and error['error']==PRIVATE_GUARD and error['executed'] is False
            and error['host_mutation_started'] is False and error['execution_authority'] is False,
            'legacy_B_rejection_result_changed/'+slot.name)
    p_tx,p_rx = pin(tx),pin(rx)
    rxb = rx.read_bytes()
    normalized_rx = rxb[:-2]+b'\n' if rxb.endswith(b'\r\n') else rxb
    require(meter['TX_sha256']==p_tx['sha256']
            and receipt['TX_bytes']==meter['TX_bytes']==p_tx['bytes']
            and receipt['RX_bytes']==p_rx['bytes'] and receipt['RX_sha256']==p_rx['sha256']
            and meter['RX_text_UTF8_LF_bytes']==len(normalized_rx)
            and meter['RX_text_UTF8_LF_sha256']==sha256(normalized_rx).hexdigest()
            and meter['raster_actual']==0 and meter['raster_reservation'] is None,
            'legacy_B_client_or_worker_wire_receipt_changed/'+slot.name)
    exact = request['params']['arguments']['query']
    return {'reproduced_error':reject(lambda:validate(exact),PRIVATE_GUARD),
            'normalized_query':validate(exact['query']), 'requests':1,'tx':p_tx,'rx':p_rx,
            'worker':pin(slot/'mcp_io/MCP_IO.jsonl'),'client':pin(tx.with_name('RECEIPT.json'))}


def raw_closure(slot,label,closed,score):
    proof = read(slot/'NATIVE_RUNTIME_PROOF.json')
    function = run_path(str(OLD_CLOSE))['ready_closure']
    verdict = function(closed['runtime_close'],'P',proof)
    require(verdict == closed['closure_verification'] and verdict['passed'] is True
            and verdict['status']=='ready_closed' and closed['status']=='failed'
            and len(closed['errors']) == 1 and closed['errors'][0]['stage'] == 'caller' and not closed['preflight'],
            'legacy_owned_ready_close_not_verified/'+label)
    eof = read(slot/'mcp_io/EOF.json')
    worker_exit = read(slot/'mcp_io/WORKER_EXIT.json')
    meter = read(slot/'mcp_io/REAL_HOST_STAGES.json')
    worker_close = closed['runtime_close']['public_MCP_close']
    require(eof['pid']==worker_exit['pid']==meter['pid'] and
            eof['source_sha256']==worker_exit['source_sha256']==meter['source_sha256']
            and eof['closed'] is True and eof['host_close_called'] is True
            and eof['input_eof_observed'] is True and worker_exit['production_returned'] is True
            and worker_exit['production_return_code']==0 and worker_close['production_eof_and_exit_verified']
            and meter['requests']==[] and score['actual_measurement_TCP_calls'] == score['successful_measurements'] == 0,
            'legacy_mcp_health_or_zero_host_measurements_unproven/'+label)
    wire = sorted((slot/'native/WIRE').glob('*/REQUEST.bin'))
    require(len(wire)==3 and all(read(path).get('type')=='execute_code' for path in wire[:2])
            and read(wire[-1])=={'type':'close'}
            and read(wire[-1].with_name('RESPONSE.bin'))==closed['runtime_close']['Blender_close']['response'],
            'legacy_native_wire_contains_unexpected_measurement/'+label)
    for path,source in zip(wire[:2],(closed['initial_source'],closed['terminal_source']),strict=True):
        outer = ast.parse(read(path)['params']['code'])
        compiler, = (node for node in ast.walk(outer) if isinstance(node,ast.Call)
                     and ast.unparse(node.func)=='compile')
        tail = ast.parse(ast.literal_eval(compiler.args[0])).body[-1].value
        require(ast.unparse(tail.func)=='capture_device'
                and ast.literal_eval(tail.args[1])==source['worker_path']
                and len(tail.keywords)==1 and tail.keywords[0].arg=='terminal'
                and ast.literal_eval(tail.keywords[0].value) is True,
                'legacy_native_capture_was_not_independent_terminal_export/'+label)
    first,last = verify_source(slot,verdict,closed)
    return {'pid':verdict['pid'],'worker_pid':eof['pid'],'native_wire_nonmeasurement_calls':len(wire),
            'source_initial':first,'source_terminal':last,'host_measurements':0,'ready_closed':True}


def prove():
    commit = git('rev-parse',COMMIT).decode().strip()
    require(commit.startswith(COMMIT),'legacy_git_identity_changed')
    texts = {name:old_blob(commit,OLD/name) for name in ARTIFACTS}
    for path in (OLD_HOST,OLD_CLOSE):
        old_blob(commit,path)
    fixed = parse(texts['FROZEN.json'])
    result = parse(texts['RESULT.json'])
    old_digest = sha256(texts['FROZEN.json']).hexdigest()
    require(fixed['labels']==list(LABELS) and fixed['builds']==result['installed_builds']
            and result['passed'] is False and result['accepted_for_live_use'] is False
            and old_digest==result['freeze_sha256'],'legacy_freeze_and_rejected_result_mismatch')
    archive = archive_proof(result)
    old_review_path = RUN/'FORMAL_FAILURE_REVIEW.json'
    old_score_path = RUN/'SCORE.json'
    sequence_path = RUN/'FORMAL_SEQUENCE.jsonl'
    old_review = read(old_review_path)
    score = read(old_score_path)
    require(old_review == result['formal'] and old_review['passed'] is False
            and old_review['failed_slots']==old_review['started_slots']==old_review['closed_slots']==4
            and old_review['successful_slots']==old_review['replacement_slots']==0
            and score['passed'] is False and score['freeze_sha256']==old_digest
            and not score['arms'] and not score['pairs'] and set(score['errors'])==set(LABELS),
            'old_four_failures_denominator_changed')
    sequence = [parse(line) for line in sequence_path.read_bytes().splitlines()]
    require([(entry['event'],entry['label']) for entry in sequence] == [
            (event,label) for label in LABELS for event in ('start','exit')]
            and all(a['perf_ns']<b['perf_ns'] for a,b in zip(sequence,sequence[1:])),
            'old_four_slots_boundary_sequence_changed')
    guard,private,wrap = reproduced_paths(commit,texts['experiment.py'])
    binding = parse(texts['install/PRODUCT_RUN_BINDING.json'])
    validate,validator_pin = old_product_validator(binding)
    sources = [pin(OLD/name) for name in ARTIFACTS]
    sources.extend([archive['archive'],archive['index'],pin(OLD_HOST),pin(OLD_CLOSE),
                    pin(old_review_path),pin(old_score_path),pin(sequence_path),validator_pin])
    slots = {}
    for index,(label,(asset,arm)) in enumerate(LABELS.items()):
        start,exit = sequence[2*index:2*index+2]
        slot = RUN/'slots'/label
        bound = old_review['slots'][label]
        pub_path = slot/'SLOT_PUBLICATION.json'
        res_path = slot/'SLOT_RESULT.json'
        lease_path = slot/'HOST_RECEIPT.json'
        pub,old_result,closed = map(read,(pub_path,res_path,lease_path))
        packed = fixed['requests'][asset][0]
        require(set(packed)=={'include_image','query'} and packed['include_image'] is False
                and packed==bound['actual_wrong_query'] and packed['query']==bound['correct_single_query']
                and start['freeze_sha256']==pub['freeze_sha256']==old_result['freeze_sha256']==old_digest
                and pub['status']==old_result['status']==bound['status']=='failed'
                and pub['label']==old_result['label']==closed['label']==label
                and old_result['closure']==closed and exit['exit_code']==1 and exit['safe_closed'] is True
                and whole_entry(pub_path,exit['publication']) and whole_entry(res_path,pub['result'])
                and whole_entry(res_path,bound['closed_result']) and whole_entry(lease_path,bound['closure'])
                and old_result['error']['type']=='ValueError' and
                score['errors'][label]['message']=='actual_closed_slot_not_frozen/'+label,
                'legacy_unmodified_failed_publication_changed/'+label)
        closure = raw_closure(slot,label,closed,bound)
        wire = verify_wire(slot,arm,packed,guard,private,wrap,validate)
        n = wire['requests']
        require(n==len(old_result['observations'])==bound['formal_business']==int(arm=='B')
                and closed['budget']['slots'][label]['business_admissions']==n
                and (wire['reproduced_error'] in old_result['error']['message'])
                and wire['reproduced_error']==bound['reason'],
                'legacy_failure_not_reproduced_with_original_read_gate/'+label)
        if arm == 'B':
            historical = bound['stdio_failure']
            require(wire['tx']==historical['tx'] and wire['rx']==historical['rx']
                    and wire['normalized_query']==validate(packed['query'])
                    and historical['is_error'] is True,'legacy_saved_B_wire_digest_changed/'+label)
            sources.extend(wire[key] for key in ('tx','rx','worker','client'))
        sources.extend([pin(pub_path),pin(res_path),pin(lease_path),pin(slot/'mcp_io/REAL_HOST_STAGES.json'),
                        pin(slot/'mcp_io/EOF.json'),pin(slot/'mcp_io/WORKER_EXIT.json'),
                        closure['source_initial'],closure['source_terminal']])
        slots[label] = {'asset':asset,'arm':arm,'old_gate':'failed','exit_code':1,'closure':closure,
                        'wire_reproduction':wire,'result':pin(res_path)}
    counts = closed['budget']['counts']
    require(counts['Blender_start_attempts']==counts['Blender_spawned_confirmed']==4
            and counts['business_admissions']==2 and counts['consumer_admissions']==counts['all_raster_actual']
            ==counts['Blender_spawned_unknown']==counts['pending_raster_reservations']==0,
            'legacy_final_cumulative_denominators_changed')
    return {'passed':True,'kind':'independent_historical_custody_and_failure_reproduction','old_git':commit,
            'old_freeze_sha256':old_digest,'previous_formal_passed':False,'old_slots_started':4,
            'old_slots_failed':4,'old_slots_closed':4,'old_successful_measurements':0,
            'old_host_measurement_calls':0,'old_models':0,'old_rasters':0,'new_blender':0,'new_models':0,
            'old_archive':archive,'slots':slots,
            'source_pins':list({row['path']:row for row in sources}.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=RECOVERY/'preflight/LEGACY.json')
    args = parser.parse_args()
    expected = RECOVERY/'preflight/LEGACY.json'
    require(sys.flags.isolated and sys.dont_write_bytecode and args.output.resolve()==expected
            and not expected.exists(),'only_new_recovery_legacy_receipt_allowed')
    result = prove()
    expected.parent.mkdir(parents=True,exist_ok=True)
    with expected.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,indent=2,ensure_ascii=False,sort_keys=True,allow_nan=False)
        stream.write('\n')
    print('Legacy verified',result['old_archive']['members_verified'],'members',
          result['old_slots_failed'],'closed failures and 0 measurements',flush=True)


if __name__=='__main__':
    main()
