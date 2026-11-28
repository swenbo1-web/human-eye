"""Exercise the fixed stdio instrumentation on the already sealed real cube capture."""
import argparse
import base64
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import sys
from zipfile import ZipFile

sys.path.insert(0,str(Path(__file__).resolve().parent))
import harness

PRIOR_ZIP='78a6f91037520e7c3d12b943aa1d001ca640a75d7b92868430d97d73ec1722bc'
PRIOR_CAPTURE='5d00cdd53eeeca53be2cc71fa0bea67358824204d17aa9f4941cf0ea73e8a792'


def run(root,prior):
    zip_path=prior/'sealed/ORIGINAL_RUNTIME.zip'
    harness.need(harness.digest(zip_path)==PRIOR_ZIP,'prior_cube_archive_changed')
    with ZipFile(zip_path) as archive:
        state=archive.read('slots/B/post_capture.json')
        historical_reply=json.loads(archive.read('slots/B/03-cold.rx'))['result']
    harness.need(harness.sha(state)==PRIOR_CAPTURE,'prior_cube_capture_changed')
    folder=root/'preflight/historical-stdio'
    folder.mkdir(exist_ok=False)
    settings=harness.frozen(root)
    _,identity=harness.product_runtime(settings)
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import run_stdio_mcp_server

    class ReplayReadHost:
        def __init__(self):
            self.closed=False
            self.calls=0
            self.data=json.loads(state)
        def capture_scene(self):
            self.calls+=1
            return deepcopy(self.data)
        @property
        def is_alive(self):
            return not self.closed
        def close(self):
            self.closed=True

    config=folder/'config.json'
    harness.save(config,dict(schema_version='1.0',enabled=True,project_root=str(folder),
        state_file='state.json',audit_file='audit.jsonl',request_budget_s=30,
        expected_identity={'source_sha256':identity['source_sha256']}))
    host=ReplayReadHost()
    use={'query':{'mode':'active_observation','objects':[{'name':'Box'}],'focus':'auto'},
         'include_image':True,'response_detail':'full'}
    request={'id':3,'label':'historical-box','arguments':use}
    service=LiveSpatialService(config,host=host,production_mode=True)
    raster,module=harness.emit_focus_source(service,folder,[request])
    tx=json.dumps({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{
        'name':'human_eye_scene_observe','arguments':use}},separators=(',',':'))+'\n'
    (folder/'03-historical-box.tx').write_text(tx,encoding='utf8',newline='\n')
    out=StringIO()
    try:
        run_stdio_mcp_server(service,StringIO(tx),out)
    finally:
        module.rasterize_attention=raster
    raw=out.getvalue().encode('utf8')
    (folder/'03-historical-box.rx').write_bytes(raw)
    result=json.loads(raw)['result']
    harness.need(not result['isError'] and host.closed and host.calls==1,'historical_actual_stdio_result_or_close')
    image=lambda body:base64.b64decode(next(x['data'] for x in body['content'] if x['type']=='image'),validate=True)
    harness.need(image(result)==image(historical_reply),'historical_native_png_changed')
    metrics=harness.read(folder/'construction_03.json')
    producer=harness.read(folder/'producer_03.json')
    harness.need(len(metrics['raster_calls'])==2 and all(x['completed'] for x in metrics['raster_calls'])
         and not metrics['limit_exceeded'] and len(producer['constructed_frames'])==2
         and producer['facts']['focus']['region_ref']['source_triangle_indices']==[0]
         and producer['facts']['focus']['stop_reason']=='sample_target_met','historical_actual_frame_capture_failed')
    harness.save(folder/'RESULT.json',{'passed':True,'actual_Blender':0,'actual_private_replay_rasters':2,
        'actual_stdout_sha256':harness.sha(raw),'historical_native_png_sha256':harness.sha(image(result)),
        'host_close_called':True,'actual_cube_wire_registered':True,
        'producer_has_two_original_candidate_frames':True})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=lambda x:Path(x).resolve(strict=True))
    p.add_argument('prior',type=lambda x:Path(x).resolve(strict=True))
    a=p.parse_args()
    run(a.root,a.prior)
