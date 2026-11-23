"""Reject bad visual references through real installed connector and loopback TCP."""
import ast
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import socket
import sys
from threading import Thread
from time import perf_counter_ns
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import experiment as trial
score=SimpleNamespace(**trial.run_path(str(HERE/'score.py')))

ROOT=trial.ROOT
PREFIX='HUMAN_EYE_BLENDER_MCP:'
COMMAND='capture_source_region_visual'
LIMIT=64*1024*1024
prior=trial.run_path(str(trial.PRIOR/'replay.py'))


def bytes_of(value):
    return json.dumps(value,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()


class Wire:
    def __init__(self,name,capture_count,intercept=None):
        from human_eye_plugin.blender_mcp_host import BlenderMCPHost

        self.folder=ROOT/'preflight_wire_controls_final'/name
        self.folder.mkdir(parents=True,exist_ok=False)
        self.server=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.server.bind(('127.0.0.1',0))
        self.server.listen(1)
        self.server.settimeout(10)
        install=trial.load(trial.B_BINDING)['install_root']
        self.connector=BlenderMCPHost(install,port=self.server.getsockname()[1],timeout_s=5)
        self.slot=self.connector._resident_slot
        sys.modules.pop(self.slot,None)
        self.capture_count,self.intercept=capture_count,intercept
        self.records=[]
        self.failure=None
    def serve(self):
        from human_eye_plugin.blender_mcp_host import _JSONObjectBoundary
        try:
            source,colors,queries=prior['frozen_inputs'](SimpleNamespace(
                terminal=trial.shared['TERMINAL'],asset=trial.shared['FIXTURE'],asset_sha256=score.ASSET))
            bpy=prior['replay_bpy'](source,colors)
            namespace={'__name__':'_visual_wire_control','bpy':bpy}
            for index in range(self.capture_count):
                peer,_=self.server.accept()
                with peer:
                    peer.settimeout(5)
                    decoder,data=_JSONObjectBoundary(),bytearray()
                    while True:
                        fragment=peer.recv(65536)
                        score.need(fragment and len(data)+len(fragment)<2*1024*1024,'control_request_missing_or_oversize')
                        data.extend(fragment)
                        if decoder.feed(fragment):
                            break
                    outer=json.loads(data)
                    code=outer['params']['code']
                    row,=[v for v in ast.parse(code).body if isinstance(v,ast.Assign)
                          and [ast.unparse(t) for t in v.targets]==['_request']]
                    request=json.loads(ast.literal_eval(row.value.args[0]))
                    params=request['params']
                    score.need(request['command']==COMMAND and any(
                        score.old.same_bits(params['query'],q) for q in queries)
                        and code==self.connector._observation_code(COMMAND,params,request['id']),
                        'control_replay_received_unregistered_or_nonconfigured_code')
                    stream=StringIO()
                    with redirect_stdout(stream):
                        exec(compile(code,'<installed-fixed-host-command>','exec'),namespace)
                    line=stream.getvalue()
                    score.need(line.startswith(PREFIX),'control_native_envelope_missing')
                    reply=json.loads(line[len(PREFIX):])
                    if index==1 and self.intercept is not None:
                        reply=self.intercept(deepcopy(reply),self.records[-1]['inner'])
                    cooked=bytes_of({'status':'success','result':{'executed':True,
                        'result':PREFIX+bytes_of(reply).decode()+'\n'}})
                    slot=self.folder/f'{index+1:03d}'
                    slot.mkdir()
                    (slot/'REQUEST.bin').write_bytes(data)
                    (slot/'RESPONSE.bin').write_bytes(cooked)
                    peer.sendall(cooked)
                    self.records.append({'request':request,'inner':reply,'tx':len(data),'rx':len(cooked)})
        except BaseException as failure:
            self.failure=failure
            raise
        finally:
            self.server.close()

    def run(self,checks):
        errors=[]
        def client():
            try:
                with self.connector.observation_transaction():
                    checks(self)
            except BaseException as failure:
                errors.append(failure)

        worker=Thread(target=client,name='installed-connector-control',daemon=True)
        worker.start()
        try:
            # The production Blender host rejects any off-main-thread read.
            self.serve()
        finally:
            worker.join(timeout=12)
            self.connector.close()
            sys.modules.pop(self.slot,None)
        if errors:
            raise errors[0]
        score.need(not worker.is_alive() and self.failure is None and len(self.records)==self.capture_count,
                   'control_close_or_registered_count_failed/'+str(self.failure))
        actual=[{'sequence':i,'tx':x['tx'],'rx':x['rx'],
                 'request':score.pin(self.folder/f'{i:03d}'/'REQUEST.bin'),
                 'response':score.pin(self.folder/f'{i:03d}'/'RESPONSE.bin')}
                for i,x in enumerate(self.records,1)]
        trial.save(self.folder/'WIRE_INDEX.json',{'completed':True,'calls':actual})

    def observe(self,query,limit=LIMIT):
        return self.connector.capture_source_region_visual(query,perf_counter_ns()+4_000_000_000,limit)

    def request_with_ack(self,query,known):
        params={'query':query,'known':known,'deadline_ns':perf_counter_ns()+4_000_000_000,'max_response_bytes':LIMIT}
        return self.connector._request(COMMAND,params)


def rejected(call,reason,type_name):
    try:
        call()
    except (RuntimeError,ValueError) as e:
        score.need(type(e).__name__==type_name and reason in str(e),'different_rejection/'+repr(e))
        return reason
    raise ValueError('input_incorrectly_accepted/'+reason)


def wrong_camera(reply,prior):
    reply['result']['camera_sha256']=prior['result']['camera_sha256']
    return reply


def wrong_epoch(reply,prior):
    reply['result']['proof']['generation']='1'*64
    return reply


def reorder(reply,prior):
    rows=reply['result']['capture']['retained_ordinals']
    rows[0],rows[-1]=rows[-1],rows[0]
    return reply


def unknown_mesh(reply,prior):
    meshes=reply['result']['capture']['meshes']
    i=next(i for i,m in enumerate(meshes) if isinstance(m,str))
    meshes[i]='e'*64
    return reply


def metadata_with_ref(reply,prior):
    pack=reply['result']['capture']
    for k in score.META:
        pack[k]=prior['result']['capture'][k]
    return reply


def wrong_binding_digest(reply,prior):
    reply['result']['capture']['sha256']='8'*64
    return reply


def main():
    from pathlib import Path
    b=trial.load(trial.B_BINDING)
    sys.path[:0]=[b['install_root'],b['dependency_root']]
    from human_eye_plugin import blender_mcp_host as installed
    score.need(Path(installed.__file__).parent.parent==Path(b['install_root']),'control_product_install_mismatch')
    first,second=(
        {'target':q['region']['object'],'reference':q['reference'],'world_box_m':q['region']['world_box_m']}
        for q in (trial.reference_inputs()[label]['query'] for label in score.ORDER))
    controls={}
    for name,tamper,needle in (
        ('different_box_camera',wrong_camera,'source_region_visual_wire_camera_digest'),
        ('different_generation',wrong_epoch,'source_region_visual_wire_unconfirmed_generation'),
        ('wrong_original_order',reorder,'source_region_visual_wire_mesh_order'),
        ('wrong_prior_mesh_digest',unknown_mesh,'source_region_visual_wire_unconfirmed_mesh'),
        ('mesh_without_verified_metadata',metadata_with_ref,'source_region_visual_wire_mesh_bypasses_metadata_receipt'),
        ('wrong_restored_capture_digest',wrong_binding_digest,'capture_digest_mismatch'),
    ):
        def verify_mutated_response(w):
            w.observe(first)
            controls[name]=rejected(lambda:w.observe(second),needle,'HostTransportError')
            score.need(not w.connector.is_alive and w.connector._visual_wire_cache is None,'ambiguous_wire_cache_retained')

        Wire(name,2,tamper).run(verify_mutated_response)

    def bad_ack(w):
        w.observe(first)
        controls['bad_ack']=rejected(lambda:w.request_with_ack(second,{'generation':'1'}),'source_region_visual_invalid_ack','HostRemoteError')
        recovered=w.observe(second)
        score.need(recovered['work']['mesh_wire_references']==2 and recovered['work']['metadata_wire_reference'],
                   'readonly_valid_recovery_lost_receipt')
        controls['bad_ack_followed_by_valid_read']='recovered_two_meshes_and_metadata'

    Wire('bad_ack_then_recovery',3).run(bad_ack)

    def over_budget(w):
        w.observe(first)
        controls['restored_budget']=rejected(lambda:w.observe(second,23000),
                                            'source_region_visual_document_budget_exceeded','HostRemoteError')
        recovered=w.observe(second)
        score.need(recovered['work']['mesh_wire_references']==0 and not recovered['work']['metadata_wire_reference'],
                   'failed_request_reused_unacknowledged_capture')
        controls['restored_budget_followed_by_full_compact_read']='recovered_without_references'
        controls['expired_input_before_dispatch']=rejected(
            lambda:w.connector.capture_source_region_visual(first,perf_counter_ns()-1,LIMIT),
            'source_region_visual_deadline','ValueError')

    Wire('restore_budget_then_recovery',3).run(over_budget)

    paths={p.parent.name:score.pin(p) for p in sorted((ROOT/'preflight_wire_controls_final').glob('*/WIRE_INDEX.json'))}
    trial.save(ROOT/'WIRE_CONTROLS.json',{'passed':True,'controls':controls,'actual_host_binary':'real installed fixed command',
        'fixture_kind':'sealed evaluated rail RNA replay','installed_source_sha256':b['source_sha256'],
        'formal_blender':0,'raster_calls':0,'wire_receipts':paths})
    print('wire controls',len(controls),'actual closed scenarios',len(paths))


if __name__=='__main__':
    main()
