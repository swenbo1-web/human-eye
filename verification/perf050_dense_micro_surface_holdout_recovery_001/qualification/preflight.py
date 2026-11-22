"""Preflight the actual diagnostic and archived closed predicates without Blender or models."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
from shutil import copyfile
from types import SimpleNamespace
import sys
import time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
NS = HERE.parent
sys.path[:0] = [str(NS/'harness'), str(HERE)]
import diagnostic
import verify
from common import ASSET_SHA256, CATALOGUE, PRODUCT_BINDING, SEAL, read, save, sha


LIVE = Path('D:/he_perf050_dense_micro_surface_holdout_001/slots/QP')
SEMANTIC = Path('D:/he_perf050_dense_micro_surface_holdout_001_product_preflight')


def rejects(operation, reason):
    try:
        operation()
    except ValueError as error:
        if str(error) != reason:
            raise
    else:
        raise AssertionError('unexpected_preflight_accept/' + reason)
    return reason


def archived_capture(pins, root, request):
    oracle = run_path(str(verify.V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    original = read(LIVE/'SLOT_RESULT.json')
    rejects(lambda:verify.verify_closed(LIVE,original),'closed_QP_required_business_sequence_incomplete')
    wires = verify.closed_wire(LIVE)
    d = LIVE/'owner/tool_02'
    product, actual = verify.product_result(LIVE,{'request':read(d/'REQUEST.json'),'response':request,'owner':d},1)
    captures,commands = oracle['decode_captures'](LIVE,read(PRODUCT_BINDING),oracle['Audit']())
    descriptor,capture = verify.current_capture_for(commands,captures,wires,product)
    oracle['source_binding_checks'](capture,product['binding'],read(PRODUCT_BINDING),oracle['Audit']())
    terminal = read(LIVE/'TERMINAL_SOURCE.json')
    closed = verify.discovery(LIVE,request,product,terminal,capture)
    verify.require(actual == closed['raster_attempts']==3 and set(closed['images'])=={'S021','S055'},
                   'historical_actual_discovery_preflight_changed')
    frame = product['frames'][0]
    device = read(LIVE/'DEVICE_EVIDENCE.json')['frames'][0]
    binding = product['binding']
    original = verify.FRAME['frame_participants']
    checks = {}

    stale = deepcopy(capture)
    stale['capture_state']['revision'] += 1
    checks['wrong_generation'] = rejects(lambda:original(device,frame,binding,stale,terminal),
                                          'product_frame_capture_generation_mismatch')
    wrong_frame = dict(frame,scope_id='fake_scope')
    checks['wrong_scope'] = rejects(lambda:original(device,wrong_frame,binding,capture,terminal),
                                     'product_frame_scope_identity_mismatch')
    missing = dict(capture)
    missing.pop('display_snapshot')
    checks['missing_required_display_scope'] = rejects(lambda:original(device,frame,binding,missing,terminal),
                                                         'current_closed_capture_display_snapshot_unknown')
    partial, native, row = deepcopy(capture),deepcopy(terminal),deepcopy(device)
    host = row['object_ids'][0]
    snapshot = partial['display_snapshot']
    next(obj for obj in snapshot['objects'] if obj['host_id']==host)['visible_get'] = False
    snapshot['sha256'] = verify.FRAME['fingerprint']({k:v for k,v in snapshot.items() if k!='sha256'})
    index = next(i for i,obj in enumerate(native['objects']) if obj['object_id']==host)
    native['objects'][index]['visible_get'] = native['display_object_mask'][index] = row['display_object_mask'][0] = False
    checks['partial_display_with_unmasked_product'] = rejects(lambda:original(row,frame,binding,partial,native),
                                                                'unmasked_scene_product_cannot_prove_partial_display')
    bad_display = deepcopy(capture)
    bad_display['display_snapshot']['objects'][0]['visible_get'] = None
    bad_display['display_snapshot']['sha256'] = verify.FRAME['fingerprint']({k:v for k,v in bad_display['display_snapshot'].items() if k!='sha256'})
    checks['unknown_current_visibility'] = rejects(lambda:original(device, frame,binding,bad_display,terminal),
                                                     'current_display_or_ordered_geometry_mismatch/' + capture['meshes'][0]['name'])
    real_exists = Path.is_file
    with patch.object(Path,'is_file',lambda path:False if path==LIVE/'native/WIRE/INDEX.json' else real_exists(path)):
        checks['previous_WIRE_not_flushed'] = rejects(lambda:verify.closed_wire(LIVE),'native_wire_not_yet_flushed')
    original_iter = Path.iterdir
    drop = LIVE/'native/WIRE/002/RESPONSE.bin'
    with patch.object(Path,'iterdir',lambda path:(item for item in original_iter(path) if item!=drop)):
        checks['incomplete_flushed_wire'] = rejects(lambda:verify.closed_wire(LIVE),'native_wire_pair_incomplete')
    root.mkdir(exist_ok=False)
    for path in (LIVE/'SLOT_RESULT.json', LIVE/'RUNTIME_CLOSE.json', LIVE/'DEVICE_EVIDENCE.json',
                 LIVE/'TERMINAL_SOURCE.json', LIVE/'product_full/call_001/SERVICE_RESULT.json',
                 d/'REQUEST.json', d/'RESPONSE.json', d/'RECEIPT.json', *sorted((LIVE/'native/WIRE').rglob('*.bin'))):
        pins.add(path)
    for row in closed['images'].values():
        pins.add(Path(row['path']))
    return {'old_slot_original_refusal':'closed_QP_required_business_sequence_incomplete','native_wire':descriptor,
            'actual_discovery':closed,'negative_controls':checks}


def public_replay(folder, discovery, measurement, closed_images, *, drop_measurement=False):
    from bridge import Owner
    from frame_device import FrameDevice

    folder.mkdir()
    deadline = time.perf_counter_ns()+45_000_000_000
    class ReplayedProduct:
        def __init__(self):
            self.product_tools = read(CATALOGUE)
            self.public_requests = []
            self.folder = folder
            self.device = FrameDevice(runroot=folder,asset_sha256=ASSET_SHA256,group='P',label='QP',phase='qualification',
                                      native_call=self.forbid,terminal_call=self.forbid)
            self.buffers,self.cameras = self.device.buffers,self.device.cameras
            self.image_specification = self.device.image_specification
            for title,row in closed_images.items():
                local = folder / f'{title}.png'
                copyfile(row['path'],local)
                self.device.by_ref[row['ref']] = {'PNG':str(local),'PNG_sha256':row['sha256'],'size_px':[512,512],'origin':'archive'}

        def forbid(self, *args, **kwargs):
            raise AssertionError('preflight_attempted_Blender')

        def public_request(self, arguments):
            if arguments == diagnostic.PRODUCT['DISCOVER']:
                return {'jsonrpc':'2.0','id':'retained_discovery','result':discovery}
            if arguments == diagnostic.PRODUCT['MEASURE'] and not drop_measurement:
                return {'jsonrpc':'2.0','id':'retained_measurement','result':measurement}
            raise ValueError('preflight_selected_measurement_missing')

    runtime = ReplayedProduct()
    owner = Owner(runtime, {'label':'QP','group':'P','phase':'qualification',
                            'worker_deadline_ns':deadline,'output':str(folder/'owner')})
    result = {'diagnostic_calls':[]}
    try:
        endpoint = owner.start(folder/'ENDPOINT.json')
        if drop_measurement:
            try:
                diagnostic.run_diagnostic(folder,endpoint,deadline,'P',owner,result)
            except ValueError as error:
                verify.require('qualification_product_error' in str(error), 'incorrect_preflight_missing_measurement_exit')
            else:
                raise AssertionError('missing_measurement_admitted_during_diagnostic')
        else:
            diagnostic.run_diagnostic(folder,endpoint,deadline,'P',owner,result)
    finally:
        closed = owner.close()
    verify.require(closed['confirmed'] and not closed['errors'] and not closed['transport_errors']
                   and result['diagnostic_close']['confirmed'] and result['diagnostic_close']['exit_code']==0,
                   'actual_offline_diagnostic_or_owner_close_failed')
    if drop_measurement:
        rejects(lambda:verify.verify_closed(folder,result),'closed_QP_required_business_sequence_incomplete')
        verify.require(not (folder/'QUALIFICATION_PENDING.json').exists(), 'preflight_failed_workflow_created_pending_receipt')
        return {'closed':True,'qualification':False,'missing_business_refused':True}
    calls,refs = verify.public_calls(folder,result)
    verify.require(calls[1]['response']==discovery and calls[4]['response']==measurement,
                   'replayed_original_product_blocks_changed')
    for i,(title,ref) in enumerate(refs.items(),2):
        receipt = closed_images[title]
        local = folder/f'{title}.png'
        verify.FRAME['NATIVE']['_check_attachment'](calls[i]['response'],ref,local,local.read_bytes(),receipt['sha256'])
    return {'closed':True,'qualification':False,'calls':len(calls),'original_public_read_refs':refs,
            'public_wire_verified':True,'same_bytes_from_real_common_read_images':True}


def run(root, receipt):
    binding = read(PRODUCT_BINDING)
    sys.path[:0] = [binding['dependency_root'], read(SEAL/'SHARED_DEPENDENCY.json')['dependency_root']]
    root.mkdir(parents=True,exist_ok=False)
    pins = {PRODUCT_BINDING}
    live_discovery = read(LIVE/'client/call_02/RESPONSE.json')['result']
    pins.add(LIVE/'client/call_02/RESPONSE.json')
    prior = archived_capture(pins,root/'old_QP_postclose_replay',live_discovery)
    discovery_producer = read(SEMANTIC/'discovery_PRODUCER.json')
    measurement = read(SEMANTIC/'measurement_MCP.json')
    measurement_producer = read(SEMANTIC/'measurement_PRODUCER.json')
    semantic = read(SEMANTIC/'PREFLIGHT.json')
    verify.require(semantic['closed'] is True and semantic['owned_Blender']==semantic['models']==0
                   and semantic['source_sha256']==binding['source_sha256']
                   and semantic['results']['measurement']['CLI']['passed'], 'actual_installed_replay_provenance_failed')
    measured = verify.PRODUCT['verify_measurement'](measurement,measurement_producer,discovery_producer['binding'])
    pins.update(SEMANTIC/name for name in ('PREFLIGHT.json','measurement_MCP.json','measurement_PRODUCER.json','discovery_PRODUCER.json'))
    complete = public_replay(root/'five_public_calls',live_discovery,measurement,prior['actual_discovery']['images'])
    missing = public_replay(root/'truncated_business',live_discovery,measurement,prior['actual_discovery']['images'],drop_measurement=True)
    save(receipt, {'passed':True,'Blender_starts':0,'models':0,'qualification_admitted':False,'old_QP':prior,
                   'installed_semantic_measurement':measured,'actual_recovery_diagnostic_replay':complete,
                   'actual_error_and_incomplete_business':missing,
                   'source_pins':[{'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)} for path in sorted(pins)]})


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,default=HERE/'PREFLIGHT.json')
    args = parser.parse_args()
    run(args.output.resolve(),args.receipt.resolve())
