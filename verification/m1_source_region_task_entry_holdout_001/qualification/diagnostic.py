"""Check live read-only distances, useful sampled original, and partial-visibility scope."""

import base64
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
import time


NS = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(__file__).resolve().parent))
from bridge_preflight import OBSERVE, old_region, region, require


def score(truth,scope,body):
    task = body['task_result'] if scope=='selected' else body
    fact = task['facts']['surface_proximity']
    require(fact['status']=='measured','current_distance_is_not_measured/' + scope)
    value = fact['value']
    witness = value['nearest_witness']
    row = truth.score_measurement(scope,value['distance_m'],witness['a'],witness['b'])
    require(all(row[field] for field in ('distance_correct','actual_attaining_pair')),
            'current_distance_direction_or_witness_is_incorrect/' + scope)
    return row


def fixed_CLI(reply,output,png):
    replay = run_path(str(NS.parent/'m1_source_region_diagnostic_artifact_prototype_001/checks/cli.py'))
    helpers,policy = replay['policy']()
    output.mkdir()
    proof = []
    for seconds,header in replay['HEADERS']:
        items = helpers['model_items'](reply['result'],seconds)
        require(len(items[0]['text'].encode())==header,'wrong_fixed_cli_header')
        first = helpers['truncate_items'](items,policy['MCP_bytes'])
        history = helpers['truncate_items'](first,policy['history_approximate_tokens'],token_mode=True)
        for stage,retained in (('MCP',first),('history',history)):
            require(retained==items and replay['retained_image_identity'](retained)==[
                {'bytes':len(png),'sha256':sha256(png).hexdigest()}],'actual_brief_lost_required_text_or_image')
            raw = replay['encoded'](retained)
            (output/f'{header}_{stage}.json').write_bytes(raw)
            proof.append({'header_bytes':header,'stage':stage,'raw_sha256':sha256(raw).hexdigest(),'passed':True})
    return proof


def run_diagnostic(folder,endpoint,deadline,group,owner,result):
    from common import DUAL,NARROW_TOOL,load_retained,sha,save,read
    from runtime import transport

    truth = load_retained('_task_entry_current_scene_truth',NS/'checks/truth.py')
    retained = load_retained('_task_entry_prior_native_read',DUAL/'qualification/diagnostic.py')
    scene_path = folder/'initial_capture/TERMINAL_SOURCE.json'
    current = truth.verify_source(scene_path)
    side = result['label']
    tool = OBSERVE if side=='QA' else NARROW_TOOL
    local = folder/'client'
    client = transport.StdioClient([sys.executable,'-IB','-X','utf8',str(NS/'consumer/thin_stdio.py'),
        '--endpoint',str(endpoint),'--audit',str(local/'attachments')],folder,local/'transport',deadline)

    def call(name,arguments,*,expect_error=False):
        n = len(result['diagnostic_calls'])+1
        directory = local/f'call_{n:02d}'
        directory.mkdir()
        request = {'jsonrpc':'2.0','id':f'qualification-{n}','method':'tools/call',
                   'params':{'name':name,'arguments':arguments}}
        path = directory/'REQUEST.json'
        save(path,request)
        row = {'index':n,'name':name,'request_sha256':sha(path),'started_ns':time.perf_counter_ns()}
        result['diagnostic_calls'].append(row)
        response = client.call(request)
        row['returned_ns'] = time.perf_counter_ns()
        save(directory/'RESPONSE.json',response)
        save(directory/'RECEIPT.json',client.records[-1])
        row['response_sha256'] = sha(directory/'RESPONSE.json')
        require('error' not in response and response.get('result',{}).get('isError') is expect_error,
                'current_qualification_call_failed/' + name + '/' + str(response)[:600])
        return response

    try:
        hello = client.call({'jsonrpc':'2.0','id':'hello','method':'initialize',
            'params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'task-entry-qualification','version':'1'}}})
        save(local/'INITIALIZE.json',hello)
        client.call({'jsonrpc':'2.0','method':'notifications/initialized'})
        listed = client.call({'jsonrpc':'2.0','id':'catalogue','method':'tools/list'})
        save(local/'TOOLS.json',listed)
        require(group=='P' and listed['result']['tools']==owner.tools,'model_facing_catalogue_changed')
        ordinary = call('execute_python',{'code':retained.NATIVE_READ})
        native = json.loads(json.loads(ordinary['result']['content'][0]['text'])['stdout'])
        require(native['counts']==[11,64,62],'ordinary_tools_did_not_read_current_evaluated_scene')

        invalid = old_region(image=False,detail='invalid') if side=='QA' else {**region(),'response_detail':'full'}
        call(tool,invalid,expect_error=True)
        arguments = old_region(image=True) if side=='QA' else region()
        reply = call(tool,arguments)
        public_calls = owner.runtime.public_requests
        require(public_calls[-2]['request']['params']=={'name':tool,'arguments':invalid}
                and public_calls[-1]['request']['params']=={'name':tool,'arguments':arguments},
                'qualification_bridge_rewrote_a_legal_or_rejected_request')
        producer = read(Path(public_calls[-1]['producer_archive']['path']))
        frame, = producer['frames']
        raw = json.loads(reply['result']['content'][0]['text'])
        row = score(truth,'selected',raw)
        receipt, = raw['images']
        native_image, = [block for block in reply['result']['content'] if block['type']=='image']
        png = base64.b64decode(native_image['data'],validate=True)
        require(raw['region_ref']['source_triangle_indices']==[0,1,8,9] and raw['region']['object_name']=='Obj_08'
                and raw['task_result']['reference']['name']=='Obj_04' and raw['visibility']['complete_witness'] is None
                and 'complete_surface_visibility' in raw['visibility']['unknown']
                and Path(receipt['local_image_path'])==Path(frame['image_path']),
                'actual_current_selected_source_samples_unknown_or_path_changed')
        proof = truth.verify_frame(folder,frame,producer['binding'],native_image,scene=scene_path)
        require(proof['useful_partial_side_image'] and proof['side_pixels']>0 and proof['bottom_pixels']==0
                and not proof['complete_selection_geometry'],
                'current_partial_witness_does_not_support_the_frozen_visibility_contract')
        stages = fixed_CLI(reply,local/'fixed_CLI',png)
        # The brief publishes counts. The common tool can read the existing
        # frame's source ownership for the task's per-group evidence.
        ref = frame['image_ref']
        device_row = owner.runtime.device.by_ref[ref]
        obj = device_row['object_names'].index('Obj_08')
        offset = device_row['source_face_offsets'][obj]
        code = (f"im = buffers[{ref!r}]\n"
                f"print({{str(i): int(np.count_nonzero((im['owners'] == {obj}) & "
                f"(im['triangle_ids'] == {offset}+i))) for i in (0,1,8,9)}})")
        original_owner_probe = call('execute_python',{'code':code})
        sample_table = json.loads(original_owner_probe['result']['content'][0]['text'])['stdout']
        import ast
        sample_table = ast.literal_eval(sample_table)
        require(sample_table==proof['pixels_by_evaluated_triangle'],'common_tool_could_not_recover_current_face_group_samples')

        whole_req = {'include_image':False,'query':{'mode':'task','objects':[{'name':'Obj_08'},{'name':'Obj_04'}],
                     'requested_facts':['surface_proximity']}}
        whole = call(OBSERVE,whole_req)
        whole_body = json.loads(whole['result']['content'][0]['text'])
        whole_row = score(truth,'whole',whole_body)
        refill = call('read_images',{'refs':[frame['image_ref']]})
        ref = frame['image_ref']
        content = refill['result']['content']
        caption, = [block['text'] for block in content if block['type']=='text' and block['text'].startswith(ref+' ')]
        metadata = json.loads(caption.split('\n',1)[1])
        same, = [base64.b64decode(block['data'],validate=True) for block in content if block['type']=='image']
        file = Path(metadata['local_image_path'])
        require(file.is_absolute() and file.resolve(strict=True).as_posix()==metadata['local_image_path']
                and file.is_relative_to(folder) and file==Path(frame['image_path'])
                and same==png==file.read_bytes() and metadata['image_sha256']==frame['image_sha256'],
                'equal_common_ability_to_open_the_original_did_not_hold')
        original = {'ref':ref,'path':str(file),'bytes':len(png),'sha256':frame['image_sha256']}
    finally:
        result['diagnostic_close'] = close = client.finish()
        require(close['confirmed'] and close['exit_code']==0,'live_qualification_stdio_not_closed')
    verdict = {'passed':True,'arm_tool':tool,'independent_source':current,'partial_frame':proof,'common_actual_face_samples':sample_table,
               'selected':row,'whole':whole_row,'product_image':original,'fixed_CLI_stages':stages,
               'no_duplicate_raster_for_original_ref':True,'rejection_recovered':True,'model_consumers':0}
    save(folder/'QUALIFICATION.json',verdict)
    result['qualification'] = verdict
