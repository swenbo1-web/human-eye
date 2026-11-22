"""Drive the single allowed no-model run for each arm using its real tool bridge."""

import ast
import json
from pathlib import Path
from runpy import run_path
import sys
import time

HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
ORACLE = V/'m4_dense_panel_sweep_001/truth/panel_truth.py'
NATIVE = V/'perf050_dense_micro_surface_holdout_001/qualification/native.py'
CONDITIONS = {'area_min_m2':19/4096,'area_max_m2':21/4096,'normal_z_min':0.75}
INVALID = {'direction':'TOP','view_span_m':0}
TOOL = 'human_eye_scene_observe'
DISCOVER = {'query':{'mode':'active_observation','region_task':CONDITIONS},
            'include_image':True,'response_detail':'full'}
MEASURE = {'query':{'mode':'source_region',
                    'region':{'object':{'name':'Component_417'},'source_triangle_indices':[0,1]},
                    'reference':{'name':'M4_Far_00'},'requested_facts':['surface_proximity']},
            'include_image':False}
TARGETS = (('Component_736','LEFT'),('Component_582','SCENE'))


def require(value, message):
    if not value:
        raise ValueError(message)


def document(reply):
    require(reply.get('isError') is False and reply['content'][0]['type']=='text',
            'qualification_tool_failed/'+str(reply)[:400])
    return json.loads(reply['content'][0]['text'])


def ordinary_document(reply):
    document_body = document(reply)
    require(document_body['error'] is None,'ordinary_calculation_failed')
    return json.loads(document_body['stdout'])


def native_code():
    tree = ast.parse(ORACLE.read_bytes())
    functions = {node.name:node for node in tree.body if isinstance(node,ast.FunctionDef)}
    identifiers = ('require','sub','dot','cross','pairs','numeric_vector',
                   'partition','boundary_rectangle','clip','visibility')
    constants = {'COUNTS':{'objects':20,'vertices':3502,'triangles':6160},
                 'DIRECTIONS':run_path(str(ORACLE))['DIRECTIONS']}
    prelude = ('from collections import defaultdict\nfrom fractions import Fraction\nfrom itertools import pairwise\n'
               'from math import gcd,lcm,sqrt\nfrom shapely.geometry import Polygon\nimport json')
    code = '\n\n'.join([prelude,*(f'{k} = {v!r}' for k,v in constants.items()),
                       *(ast.unparse(functions[name]) for name in identifiers),
                       (HERE/'native_case.py').read_text(encoding='utf8')])
    compile(code, '<dense-integrated-native-proof>', 'exec')
    return code


def native_read():
    return run_path(str(NATIVE))['NATIVE_READ']


def render_options(view, center):
    return {'direction':view,'target_world_m':center,'view_span_m':0.125,'include_image':True}


def required_product_refs(reply):
    packet = document(reply)
    decode = run_path(str(V/'m4_dense_region_brief_001/checks/brief_schema.py'))['decode_body']
    rows = decode(packet,len(reply['content']))['region_task']['rows']
    by_name = {row['object_name']:row for row in rows}
    refs = [by_name[name]['complete_witness']['image_ref'] for name,_ in TARGETS]
    require(len(set(refs))==2 and all(type(ref) is str and ref for ref in refs),
            'qualification_two_distinct_product_witnesses_required')
    return refs


def business(call, group):
    require(call('render_local', INVALID).get('isError') is True,'invalid_render_gate_accepted')
    if group == 'P':
        discovered = call(TOOL, DISCOVER)
        refs = required_product_refs(discovered)
        require(call('read_images',{'refs':refs}).get('isError') is False,'product_original_readback_failed')
        document(call(TOOL, MEASURE))
    elif group == 'N':
        current = ordinary_document(call('execute_python',{'code':native_read()}))
        report = ordinary_document(call('execute_python',{'code':native_code()}))
        require(current['source_ref']==report['source_ref'],'native_persistent_source_changed')
        regions = {row['object_name']:row for row in report['regions']}
        refs = []
        for target,view in TARGETS:
            rendered = call('render_local',render_options(view,regions[target]['center_world_m']))
            frame = document(rendered)['frame']
            require(frame['source_ref']==current['source_ref'],'native_frame_not_from_persistent_source')
            refs.append(frame['ref'])
        require(len(set(refs))==2 and call('read_images',{'refs':refs}).get('isError') is False,
                'native_original_readback_failed')
    else:
        raise ValueError('only_registered_N_P_qualifiers_supported')
    return {'passed':False,'phase':'public_calls_completed_pending_owned_close','refs':refs}


def run_diagnostic(folder, endpoint, deadline, group, owner, result):
    from common import save, sha

    require((result['label'],group) in (('QN','N'),('QP','P')),'wrong_qualification_slot_group')
    folder = Path(folder)
    root = folder/'client'
    transport = run_path(str(V/'m4_source_region_display_001/harness/reused/stdio_checks.py'))
    client = transport['StdioClient'](
        [sys.executable,'-IB','-X','utf8',str(NS/'consumer/thin_stdio.py'),
         '--endpoint',str(endpoint),'--audit',str(root/'attachments')],
        folder,root/'transport',deadline)

    def call(name, arguments):
        ordinal = len(result['diagnostic_calls'])+1
        directory = root/f'call_{ordinal:02d}'
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
        require(reply.get('id')==request['id'] and 'error' not in reply and isinstance(reply.get('result'),dict),
                'qualified_public_call_failed/'+name)
        return reply['result']

    try:
        initialize = client.call({'jsonrpc':'2.0','id':'initialize','method':'initialize',
                                  'params':{'protocolVersion':'2025-03-26','capabilities':{},
                                            'clientInfo':{'name':'dense-integrated-qualification','version':'1'}}})
        save(root/'INITIALIZE.json',initialize)
        client.call({'jsonrpc':'2.0','method':'notifications/initialized'})
        tools = client.call({'jsonrpc':'2.0','id':'list','method':'tools/list'})
        save(root/'TOOLS.json',tools)
        require(tools['result']['tools']==owner.tools,'qualified_public_catalogue_changed')
        pending = business(call,group)
    finally:
        result['diagnostic_close'] = close = client.finish()
        require(close['confirmed'] and close['exit_code']==0 and close['process_handle_closed'],
                'real_qualification_thin_stdio_close_unconfirmed')
    save(folder/'QUALIFICATION_PENDING.json',pending)
    result['qualification_pending'] = pending
