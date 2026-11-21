"""Check live read-only geometry, the selected complete original, and whole-object range."""

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
    row = truth.score_measurement(scope,value['distance_m'],witness['direction_a_to_b'],witness['a'],witness['b'])
    require(all(row[field] for field in ('distance_correct','world_direction_correct','actual_attaining_pair')),
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
    retained.TARGET,retained.INDICES = 'N26',[4,5]
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
        require(native['counts']==[28,416,744],'ordinary_tools_did_not_read_current_evaluated_scene')

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
        require(raw['region_ref']['source_triangle_indices']==[4,5] and raw['region']['object_name']=='N26'
                and raw['task_result']['reference']['name']=='N07' and raw['visibility']['complete_witness']
                and Path(receipt['local_image_path'])==Path(frame['image_path']),
                'actual_current_selected_source_complete_witness_or_path_changed')
        proof = truth.verify_frame(folder,frame,producer['binding'],native_image,scene=scene_path)
        stages = fixed_CLI(reply,local/'fixed_CLI',png)

        whole_req = {'include_image':False,'query':{'mode':'task','objects':[{'name':'N26'},{'name':'N07'}],
                     'requested_facts':['surface_proximity']}}
        whole = call(OBSERVE,whole_req)
        whole_body = json.loads(whole['result']['content'][0]['text'])
        whole_row = score(truth,'whole',whole_body)
        refill = call('read_images',{'refs':[frame['image_ref']]})
        original = retained.image_proof(refill['result']['content'],folder,owner.runtime,frame['image_ref'])
        require(original['sha256']==frame['image_sha256'] and Path(original['path'])==Path(frame['image_path']),
                'equal_common_ability_to_open_the_original_did_not_hold')
    finally:
        result['diagnostic_close'] = close = client.finish()
        require(close['confirmed'] and close['exit_code']==0,'live_qualification_stdio_not_closed')
    verdict = {'passed':True,'arm_tool':tool,'independent_source':current,'complete_frame':proof,
               'selected':row,'whole':whole_row,'product_image':original,'fixed_CLI_stages':stages,
               'no_duplicate_raster_for_original_ref':True,'rejection_recovered':True,'model_consumers':0}
    save(folder/'QUALIFICATION.json',verdict)
    result['qualification'] = verdict
