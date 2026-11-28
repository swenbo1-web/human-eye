"""Exercise the installed public MCP request deadline between SCENE and side rendering."""
from copy import deepcopy
from hashlib import sha256
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

STAGE = 'source_region_before_sparse_view'


def read(path):
    return json.loads(path.read_bytes())


def put(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as out:
        json.dump(value, out, sort_keys=True, indent=2)
        out.write('\n')


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def worker(site, capture_path, root):
    sys.path.insert(0, str(site))
    from human_eye_plugin import active_observation_images, live_service
    from human_eye_plugin.live_spatial_mcp import run_stdio_mcp_server
    from human_eye_plugin.runtime_identity import runtime_identity

    capture = read(capture_path)
    events = []
    request = None
    current_view = None
    identity = runtime_identity()

    class Host:
        def capture_scene(self):
            return deepcopy(capture)

        def close(self):
            events.append({'action':'production_host_close','request':request})

    class Requests:
        def readline(self, limit=-1):
            nonlocal request
            line = sys.stdin.readline(limit)
            if line:
                request = json.loads(line)['id']
            return line

    config = root/'CONFIG.json'
    put(config, {'schema_version':'1.0','enabled':True,'project_root':str(root),'state_file':'state.json',
                 'audit_file':'audit.jsonl','request_budget_s':30,
                 'expected_identity':{'source_sha256':identity['source_sha256']}})
    service = live_service.LiveSpatialService(config, host=Host(), production_mode=True)
    check = service._check_request_budget
    record = service.record_event
    raster = active_observation_images.rasterize_attention

    def expire_at_probe(stage, *, publication=False):
        if request == 'expires_after_scene' and stage == STAGE:
            budget = live_service._REQUEST_BUDGET.get()
            if not budget or budget['service'] is not service or not budget['guard_active']:
                raise ValueError('live_request_budget_guard_missing')
            budget['deadline'] = time.monotonic() - 1
            events.append({'action':'test_advance_actual_deadline','request':request,'stage':stage})
        return check(stage,publication=publication)

    def record_view(event, *args, **kwargs):
        nonlocal current_view
        if event == 'active_observation_render_attempt':
            current_view = kwargs['view_name']
        return record(event,*args,**kwargs)

    def track_raster(*args, **kwargs):
        start = time.perf_counter_ns()
        outcome = raster(*args, **kwargs)
        events.append({'action':'raster_completed','request':request,'view':current_view,
                       'started_ns':start,'closed_ns':time.perf_counter_ns()})
        return outcome

    service._check_request_budget = expire_at_probe
    service.record_event = record_view
    active_observation_images.rasterize_attention = track_raster
    try:
        run_stdio_mcp_server(service,input_stream=Requests())
    finally:
        put(root/'EVENTS.json',events)


def run(site, capture_path, request_path, root):
    root.mkdir(exist_ok=False,parents=True)
    normal = read(request_path)
    assert normal['method']=='tools/call' and normal['params']['arguments']['include_image'] is True
    args = normal['params']['arguments']
    assert args['query']['focus']['task_region']['relation']=='nearest_surface'
    messages = [{'jsonrpc':'2.0','id':'init','method':'initialize','params':{
        'protocolVersion':'2025-03-26','capabilities':{}, 'clientInfo':{'name':'test-actual-budget','version':'1'}}}]
    messages.extend(dict(normal,id=label) for label in ('expires_after_scene','recovered','same_request'))
    raw = b''.join(json.dumps(row,separators=(',',':'),ensure_ascii=False).encode('utf-8')+b'\n' for row in messages)
    (root/'TX.bin').write_bytes(raw)
    command = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),'worker',
               str(site),str(capture_path),str(root)]
    start = time.perf_counter_ns()
    child = subprocess.run(command,cwd=root,capture_output=True,input=raw,timeout=80,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    (root/'RX.bin').write_bytes(child.stdout)
    (root/'STDERR.bin').write_bytes(child.stderr)
    put(root/'PROCESS.json',{'argv':command,'started_ns':start,'closed_ns':time.perf_counter_ns(),
                             'returncode':child.returncode})
    events = read(root/'EVENTS.json')
    reply = {row['id']:row['result'] for row in map(json.loads,child.stdout.splitlines())}
    forced = reply['expires_after_scene']
    error = json.loads(forced['content'][0]['text'])
    after = reply['recovered']
    last = reply['same_request']
    success = json.loads(after['content'][0]['text'])
    repeated = json.loads(last['content'][0]['text'])
    frames_by_id = {label:[row['view'] for row in events if row['action']=='raster_completed'
                         and row['request']==label] for label in ('expires_after_scene','recovered','same_request')}
    require = (
        child.returncode==0
        and forced['isError'] is True
        and not any(row['type']=='image' for row in forced['content'])
        and 'live_request_expired' in json.dumps(error) and STAGE in json.dumps(error)
        and not after['isError'] and not last['isError']
        and success['facts']['focus']['sample']['selected_surface_pixels']>=16
        and repeated['facts']['focus']['sample']['image_ref']==success['facts']['focus']['sample']['image_ref']
        and frames_by_id=={'expires_after_scene':['SCENE'],'recovered':['FOCUS'],'same_request':[]}
        and events[-1]=={'action':'production_host_close','request':'same_request'}
    )
    put(root/'RESULT.json',{'passed':require,'zero_blender':True,'zero_models':True,'test_injection':STAGE,
            'capture_sha256':digest(capture_path),'actual_requirement_sha256':digest(request_path),
            'identity':reply['init']['_meta']['human_eye']['source_sha256'],'expiry':error,
            'frames_by_id':frames_by_id,'raw_rx_sha256':digest(root/'RX.bin'),'real_process_exit':child.returncode})
    return int(not require)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode',choices=('run','worker'))
    cli.add_argument('paths',type=lambda x:Path(x).resolve(),nargs='+')
    a=cli.parse_args()
    if a.mode=='worker':
        worker(*a.paths)
    else:
        raise SystemExit(run(*a.paths))

