"""Qualify both arms through the retained thin stdio and actual owner."""

import base64
import json
from pathlib import Path
from runpy import run_path
import sys

from bridge import PRODUCT_TOOL, TOOLS
from common import HERE, V, read, save, sha
from runtime import transport


TARGET='0135bbc4-c6c7-4003-a402-6f2e0283497d'
INIT={'jsonrpc':'2.0','id':'init','method':'initialize','params':{
    'protocolVersion':'2025-03-26','capabilities':{},
    'clientInfo':{'name':'yanyite-local-qualification','version':'001'}}}
LIST={'jsonrpc':'2.0','id':'list','method':'tools/list'}
NOTIFY={'jsonrpc':'2.0','method':'notifications/initialized'}
SELECT = """
import json
data=scene_data()
area=next(obj for obj in data['objects'] if obj['name']=='0135bbc4-c6c7-4003-a402-6f2e0283497d')
cube=next(obj for obj in data['objects'] if obj['name']=='Cube')
xyz=np.asarray(area['vertices'])
mesh=np.asarray(area['triangles'])
tri=xyz[mesh]
box=np.asarray(cube['vertices'])
minimum=box.min(axis=0)
maximum=box.max(axis=0)
def select(z_min,z_max):
    low=np.array([-.09,.13,z_min])
    high=np.array([.09,.18,z_max])
    return np.flatnonzero(((tri>=low)&(tri<=high)).all(axis=(1,2)))
lower,upper=select(.505,.565),select(.565,.63)
def probe(rows):
    ids=np.unique(mesh[rows])
    points=xyz[ids]
    gaps=np.concatenate((points-minimum,maximum-points),axis=1)
    i,face=np.unravel_index(np.argmin(gaps),gaps.shape)
    p=points[i]
    axis=face%3
    q=p.copy()
    q[axis]=minimum[axis] if face<3 else maximum[axis]
    dist=float(gaps[i,face])
    return {'triangles':len(rows),'vertices':len(ids),'distance_m':dist,'direction':((q-p)/dist).tolist(),
            'a':p.tolist(),'b':q.tolist(),'meets_0_40':dist>=.40}
l,u=probe(lower),probe(upper)
print(json.dumps({'lower':l,'upper':u,'nearer':'lower' if l['distance_m']<u['distance_m'] else 'upper'}))
"""
RENDER = """
frame=render_local('BACK',[0,.155,.5975],.25)
idx=frame['object_names'].index(area['name'])
arr=buffers[frame['ref']]
selected=np.intersect1d(np.unique(arr['triangle_ids'][arr['owners']==idx]-frame['source_face_offsets'][idx]),upper)
print(json.dumps({'frame_ref':frame['ref'],'source_triangle_index':int(selected[0]) if len(selected) else None,
                  'selected_sampled_triangle_count':len(selected)}))
"""


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def body(reply):
    return json.loads(reply['result']['content'][0]['text'])


def printed(reply):
    data = body(reply)
    require(not data.get('error'),'ordinary_machine_qualification_reported_error')
    return json.loads(data['stdout'])


def run_diagnostic(folder, endpoint, deadline, group, owner, result):
    folder = Path(folder)
    exe = [sys.executable,'-IB','-X','utf8',str(HERE/'thin_stdio.py'),
           '--endpoint',str(endpoint),'--audit',str(folder/'qualification_attachment')]
    wire = transport.StdioClient(exe,folder,folder/'qualification_stdio',deadline)
    verify_cli = run_path(str(V/'m1_region_task_first_packet_consumption_holdout_001/checks/evidence.py'))['fixed_cli']
    receipts = result['diagnostic_calls']

    def call(name, arguments):
        at = len(receipts)+1
        request = {'jsonrpc':'2.0','id':f'qualify-{at}','method':'tools/call',
                   'params':{'name':name,'arguments':arguments}}
        reply = wire.call(request)
        item = {'attempt':at,'name':name,'request':request,'wire':wire.records[-1],
                'is_error':reply.get('result',{}).get('isError')}
        receipts.append(item)
        require(item['is_error'] is False,'live_qualification_public_call_failed/'+str(at))
        item['cli'] = verify_cli(reply,require_all=True)
        return reply

    try:
        wire.call(INIT)
        wire.call(NOTIFY)
        listed = wire.call(LIST)['result']['tools']
        require(listed==owner.tools and [r for r in listed if r['name']!=PRODUCT_TOOL]==TOOLS,
                'actual_ordinary_catalogue_not_shared')
        first = printed(call('execute_python',{'code':SELECT}))
        details = {'numeric_ordinary':first,'diagnostic_only':True}
        if group=='N':
            frame = printed(call('execute_python',{'code':RENDER}))
            require(frame['selected_sampled_triangle_count']>0,'ordinary_live_frame_lacks_upper_samples')
            details['ordinary_frame'] = frame
            ref = frame['frame_ref']
        else:
            # Select actual same-capture rows from the retained namespace, not a historical answer list.
            for region, image in (('lower',False),('upper',True)):
                ids = owner.session.namespace[region].tolist()
                reply = call(PRODUCT_TOOL,{'include_image':image,'query':{'mode':'source_region',
                    'region':{'object':{'name':TARGET},'source_triangle_indices':ids},
                    'reference':{'name':'Cube'},'requested_facts':['surface_proximity']}})
                packet = body(reply)
                image_count = sum(r['type']=='image' for r in reply['result']['content'])
                require(packet['task_result']['facts']['surface_proximity']['status']=='measured'
                        and image_count==int(image),'actual_qualification_selected_measure_or_image_missing/'+region)
                details[region+'_public'] = {'source_triangle_count':len(ids),
                    'region_ref':packet['region_ref'],'schema':packet['schema'],'image_count':image_count}
                if image:
                    details['direct_image_reply'] = reply
            parent = owner.runtime.public_requests[-1]['producer_archive']
            frame, = read(parent['path'])['frames']
            ref = frame['image_ref']
        reply = call('read_images',{'refs':[ref]})
        caption, block = reply['result']['content']
        delivery = json.loads(caption['text'].splitlines()[1])
        path = Path(delivery['local_image_path']).resolve(strict=True)
        png = base64.b64decode(block['data'],validate=True)
        require(path.is_relative_to(folder.resolve()) and path.read_bytes()==png
                and delivery['image_sha256']==sha(path),'closed_local_original_PNG_binding_failed')
        details['original_png'] = {'path':str(path),'bytes':len(png),'sha256':sha(path),'ref':ref}
        save(folder/'QUALIFICATION_DIAGNOSTIC.json',details)
    finally:
        close = wire.finish()
        result['qualification_stdio_close'] = close
        require(close['confirmed'] is True and close['exit_code']==0,'actual_diagnostic_stdio_did_not_close')
