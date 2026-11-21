"""Qualify each treated shape through the actual installed tool and attached image."""

import json
from pathlib import Path
import sys
import time


NS = Path(__file__).resolve().parents[1]
TOOL = 'human_eye_scene_observe'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def args(*, detail='brief', name='Obj_09', include_image=True):
    return {'include_image': include_image, 'response_detail': detail,
            'query': {'mode': 'source_region', 'reference': {'name': 'Obj_04'},
                      'requested_facts': ['surface_proximity'],
                      'region': {'object': {'name': name}, 'source_triangle_indices': [0,1]}}}


def run_diagnostic(folder, endpoint, deadline, group, owner, result):
    from common import DETAILS, DUAL, load_retained, read, save, sha
    from runtime import transport

    truth = load_retained('_first_packet_truth_check', NS/'checks/truth.py')
    cli = load_retained('_first_packet_fixed_cli_check', NS/'checks/cli.py')
    retained = load_retained('_first_packet_prior_ordinary_proof', DUAL/'qualification/diagnostic.py')
    retained.TARGET = 'Obj_09'
    label = result['label']
    shape = DETAILS[label]
    local = folder/'client'
    client = transport.StdioClient([sys.executable,'-IB','-X','utf8',str(NS/'consumer/thin_stdio.py'),
        '--endpoint',str(endpoint),'--audit',str(local/'attachments')],folder,local/'transport',deadline)

    def call(name, arguments, *, expect_error=False):
        ordinal = len(result['diagnostic_calls']) + 1
        directory = local/f'call_{ordinal:02d}'
        directory.mkdir()
        request = {'jsonrpc':'2.0','id':f'qualification-{ordinal}','method':'tools/call',
                   'params':{'name':name,'arguments':arguments}}
        save(directory/'REQUEST.json',request)
        row = {'index':ordinal,'name':name,'request_sha256':sha(directory/'REQUEST.json'),
               'started_ns':time.perf_counter_ns()}
        result['diagnostic_calls'].append(row)
        reply = client.call(request)
        row['returned_ns'] = time.perf_counter_ns()
        save(directory/'RESPONSE.json',reply)
        save(directory/'RECEIPT.json',client.records[-1])
        row['response_sha256'] = sha(directory/'RESPONSE.json')
        require('error' not in reply and reply.get('result',{}).get('isError') is expect_error,
                'unexpected_qualification_tool_result/' + name + '/' + str(reply)[:550])
        return reply

    try:
        initialize = client.call({'jsonrpc':'2.0','id':'initialize','method':'initialize',
            'params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'first-packet-QA','version':'1'}}})
        save(local/'INITIALIZE.json',initialize)
        client.call({'jsonrpc':'2.0','method':'notifications/initialized'})
        catalogue = client.call({'jsonrpc':'2.0','id':'catalogue','method':'tools/list'})
        save(local/'TOOLS.json',catalogue)
        require(catalogue['result']['tools'] == owner.tools and group == 'P', 'the_common_tool_catalogue_changed')
        ordinary = call('execute_python', {'code':retained.NATIVE_READ})
        scene = json.loads(json.loads(ordinary['result']['content'][0]['text'])['stdout'])
        require(scene['counts'] == [9,54,56], 'ordinary_current_geometry_counts_differ')
        invalid = call(TOOL, args(detail='malformed'), expect_error=True)
        require('response_detail' in invalid['result']['content'][0]['text'], 'wrong_qualification_rejection')
        original = args(detail='brief' if shape == 'full' else 'full')
        reply = call(TOOL, original)
        rows = [json.loads(line) for line in (folder/'FIRST_PACKET_TREATMENT.jsonl').read_bytes().splitlines()]
        require(len(rows)==2 and rows[0]['product_arguments']==rows[0]['original_arguments']
                and rows[1]['original_arguments']==original
                and rows[1]['product_arguments']==dict(original,response_detail=shape), 'the_observed_first_treatment_differs')
        product = owner.runtime.public_requests[1]
        archive = product['producer_archive']
        producer = read(Path(archive['path']))
        images = [block for block in reply['result']['content'] if block['type']=='image']
        require(len(images)==1 and len(producer['frames'])==1,
                'this_treatment_did_not_deliver_exactly_one_current_original_image')
        frame = producer['frames'][0]
        pixels = truth.verify_frame(folder,frame,producer['binding'],images[0],
            scene=folder/'initial_capture/TERMINAL_SOURCE.json')
        delivery = cli.inspect_arm('A' if shape=='full' else 'B',reply,raw_output=local/'fixed_cli',
                                  expected_image_root=folder)
        require(delivery['passed'] and delivery['delivery']['frame']['frame_identity']==frame['frame_identity'],
                'current_authoritative_source_witness_or_fixed_delivery_missing')
        refill = call('read_images',{'refs':[frame['image_ref']]})
        returned = retained.image_proof(refill['result']['content'],folder,owner.runtime,frame['image_ref'])
        # Retain the original same-slot local file and its byte-verifiable provenance.
        require(returned['sha256']==frame['image_sha256'] and Path(returned['path'])==Path(frame['image_path']),
                'common_tool_could_not_read_the_identical_product_PNG')
    finally:
        result['diagnostic_close'] = closed = client.finish()
        require(closed['confirmed'] and closed['exit_code']==0, 'qualification_stdio_close_unconfirmed')
    proof = {'passed':True,'qualification_only':True,'response_detail':shape,'ordinary_source':scene,
             'product_request':product['request'],'product_image':returned,'product_geometry_and_pixels':pixels,
             'CLI':delivery,'case_rejected_then_recovered':True,'model_consumers':0}
    save(folder/'QUALIFICATION.json',proof)
    result['qualification'] = proof
