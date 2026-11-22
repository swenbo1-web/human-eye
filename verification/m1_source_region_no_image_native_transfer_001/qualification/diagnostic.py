"""Use the same public native read and computation on both live qualifiers."""
import json
from hashlib import sha256
from pathlib import Path
from runpy import run_path
import sys
import time

NS = Path(__file__).resolve().parents[1]
V = NS.parent
TOOL = 'human_eye_scene_observe'
PROBE = {'direction':'TOP','view_span_m':0}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def body(result, *, error=False):
    require(result['isError'] is error and len(result['content'])==1 and result['content'][0]['type']=='text',
            'unexpected diagnostic status or image output')
    text = result['content'][0]['text']
    if error:
        require(text=='ValueError: render_local_arguments','common negative did not reach the expected argument rejection')
        return text
    return json.loads(text)


def cases():
    return json.loads((NS/'inputs/CASES.json').read_bytes())


def read_code():
    return (NS/'qualification/native_read.py').read_text(encoding='utf8')


def setup_code(raw):
    identities = [{k:row[k] for k in ('id','target','reference','faces')} for row in cases()]
    return ('import json, numpy\nfrom shapely.geometry import Polygon\nqualification_raw = json.loads('
            + repr(json.dumps(raw,separators=(',',':'))) + ')\nqualification_cases = ' + repr(identities)
            + "\nprint(json.dumps({'rows':len(qualification_raw['meshes']),'numpy_dot':int(numpy.dot([1,2],[3,4])),'shapely_area':Polygon([(0,0),(1,0),(0,1)]).area}))\n")


def solve_code():
    return (NS/'qualification/native_solve.py').read_text(encoding='utf8')


def ordinary(result):
    output=body(result)
    require(output['error'] is None and not output['stderr'], 'common ordinary execution failed')
    return json.loads(output['stdout'])


def product_forms(call):
    results=[]
    for case in cases():
        subset=body(call(TOOL,case['qa_selected']))
        require(subset['schema']=='source-region-brief-v2' and subset['status']=='complete'
                and subset['observation_status']=='image_not_requested' and not subset['images'],
                'candidate did not deliver requested selected no-image task evidence')
        whole=body(call(TOOL,case['qa_whole']))
        require(whole['status']=='observed' and whole['schema_version']=='task-query-v3'
                and whole['facts']['surface_proximity']['status']=='measured',
                'candidate whole-object control did not return a measured result')
        results.append([subset['schema'],whole['schema_version']])
    return results


def run_calls(call,label):
    body(call('render_local',PROBE),error=True)
    raw=ordinary(call('execute_blender_code',{'code':read_code()}))
    ready=ordinary(call('execute_python',{'code':setup_code(raw)}))
    require(ready=={'rows':6,'numpy_dot':11,'shapely_area':0.5},'common dependencies or current mesh roster unavailable')
    measured=ordinary(call('execute_python',{'code':solve_code()}))
    require(measured['meshes']==raw['meshes'] and measured['frame']==raw['frame']
            and measured['scale_length']==raw['scale_length']
            and set(measured['measurements'])=={'1','2','3'},'ordinary persistent computation/source row order lost')
    products=product_forms(call) if label=='QP' else []
    return {'passed':False,'phase':'await_actual_close','no_images':True,
            'ordinary_dependency_checks':ready,
            'product_forms':products}


def run_diagnostic(folder, endpoint, deadline, group, owner, result, *, plan=run_calls):
    from common import save

    label=result['label']
    require((label,group) in {('QN','N'),('QP','P')},'registered_qualification_slot_required')
    root=Path(folder)/'client'
    transport=run_path(str(V/'m4_source_region_display_001/harness/reused/stdio_checks.py'))
    client=transport['StdioClient'](
        [sys.executable,'-IB','-X','utf8',str(NS/'consumer/thin_stdio.py'),'--endpoint',str(endpoint),
         '--audit',str(root/'attachments')],folder,root/'transport',deadline)

    def call(name,arguments):
        i=len(result['diagnostic_calls'])+1
        directory=root/f'call_{i:02}'
        directory.mkdir()
        request={'jsonrpc':'2.0','id':f'qualification-{i}','method':'tools/call','params':{'name':name,'arguments':arguments}}
        save(directory/'REQUEST.json',request)
        row={'index':i,'name':name,'started_ns':time.perf_counter_ns(),
             'request_sha256':sha256((directory/'REQUEST.json').read_bytes()).hexdigest()}
        result['diagnostic_calls'].append(row)
        response=client.call(request)
        row['returned_ns']=time.perf_counter_ns()
        save(directory/'RESPONSE.json',response)
        save(directory/'RECEIPT.json',client.records[-1])
        row['response_sha256']=sha256((directory/'RESPONSE.json').read_bytes()).hexdigest()
        require(response.get('id')==request['id'] and isinstance(response.get('result'),dict)
                and 'error' not in response,'actual_qualification_RPC_failed/'+name)
        return response['result']

    try:
        init=client.call({'jsonrpc':'2.0','id':'initialize','method':'initialize','params':{
            'protocolVersion':'2025-03-26','capabilities':{},
            'clientInfo':{'name':'no-image-native-transfer-qualification','version':'1'}}})
        save(root/'INITIALIZE.json',init)
        client.call({'jsonrpc':'2.0','method':'notifications/initialized'})
        tools=client.call({'jsonrpc':'2.0','id':'list','method':'tools/list'})
        save(root/'TOOLS.json',tools)
        require(tools['result']['tools']==owner.tools,'actual_qualification_catalogue_changed')
        pending=plan(call,label)
    finally:
        result['diagnostic_close']=closed=client.finish()
        require(closed['confirmed'] and closed['exit_code']==0 and closed['process_handle_closed'],
                'actual_qualification_consumer_close_unconfirmed')
    save(Path(folder)/'QUALIFICATION_PENDING.json',pending)
    result['qualification_pending']=pending
