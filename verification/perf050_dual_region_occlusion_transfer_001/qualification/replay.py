"""Exercise both dual-region diagnostic paths using the sealed Q1 geometry."""

import argparse
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
import sys
import time
from zipfile import ZipFile


NS = Path(__file__).resolve().parents[1]
ROOT = NS.parents[1]
OLD = NS.parent / 'm4_cross_scale_live_qualification_001'
ORIGINAL_SHA = '403b627419d158cee65d658571334ed66071a25e75b4be4be1a21294b4aec5c2'
CAPTURE_MEMBER = 'slots/Q1/INDEPENDENT_SCENE.json'
CAPTURE_SHA = 'a0f7816e83c852094acaa0c1424bf711c15aa467f1da14ac581d1c213c9392ad'
TOOL = 'human_eye_scene_observe'
THIN = NS / 'consumer/thin_stdio.py'
sys.path.insert(0, str(NS/'harness'))
from common import ASSET_SHA256, CATALOGUE, PRODUCT_BINDING, PRIOR, SEAL, SOURCE_SHA, load_retained


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def pin(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}


def frozen_capture():
    index_path = OLD/'RUNTIME_INDEX.json'
    index = read(index_path)
    archive = Path(index['archive']['path'])
    archive_pin = pin(archive)
    require(archive_pin == index['archive'] and archive_pin['sha256'] == ORIGINAL_SHA, 'old_Q1_archive_changed')
    members = {row['path']:row for row in index['files']}
    q1 = archive.parent/'slots/Q1'
    retained = [CAPTURE_MEMBER, 'slots/Q1/SLOT_RESULT.json','slots/Q1/SLOT_PUBLICATION.json',
                'slots/Q1/RUNTIME_CLOSE.json','slots/Q1/native/input.blend']
    with ZipFile(archive) as old:
        inputs = {name:old.read(name) for name in retained}
    for name, data in inputs.items():
        known = members[name]
        require(len(data)==known['bytes'] and sha256(data).hexdigest()==known['sha256']
                and data==(archive.parent/name).read_bytes(),'original_Q1_member_mismatch/'+name)
    raw = inputs[CAPTURE_MEMBER]
    original = read(q1/'SLOT_RESULT.json')
    publication = read(q1/'SLOT_PUBLICATION.json')
    closure = read(q1/'RUNTIME_CLOSE.json')
    source = original['source']
    require(members[CAPTURE_MEMBER]['sha256']==CAPTURE_SHA and original['status']==publication['status']=='completed'
            and publication['result_sha256']==members['slots/Q1/SLOT_RESULT.json']['sha256']
            and not original['errors'] and not closure['errors'] and original['model_consumers']==0
            and [source[k] for k in ('objects','vertices','triangles')]==[9,54,56]
            and source['asset_sha256']==members['slots/Q1/native/input.blend']['sha256']==ASSET_SHA256,
            'Q1_geometry_or_closure_binding_changed')
    return raw, {'archive':archive_pin,'member':members[CAPTURE_MEMBER],
        'source_pins':[pin(index_path),*(pin(archive.parent/name) for name in retained)]}


def replay_scene(raw):
    scene = deepcopy(json.loads(raw))
    offsets = [0]
    for row in scene['objects']:
        row['evaluated'] = {'vertices_world_m':row['vertices'],'triangles':row['triangles']}
        row['polygon_count'] = len(row['triangles'])
        row['visible_get'] = True
        offsets.append(offsets[-1]+len(row['triangles']))
    scene.update(source_ref='offline-replay-Q1:'+scene['source_ref'],source_face_offsets=offsets,
        display_object_mask=[True]*len(scene['objects']),
        offline_replay_display_scope='all archived Q1 meshes participate for the replay; effective live display is verified separately')
    return scene


class ReplayRuntime:
    """Keep the genuine common APIs, replacing only their live capture source."""

    def __init__(self, folder, label, group, deadline, raw, public_dir):
        from frame_device import FrameDevice

        self.label, self.folder, self.deadline = label, folder, deadline
        self.product_tools = read(CATALOGUE)
        self.public_requests, self.public_input_pins = [], []
        self.public_dir = public_dir
        self.adopted_origins = []
        self.media_relocations = []
        self.device = FrameDevice(runroot=folder, asset_sha256=ASSET_SHA256, group=group, label=label,
                                  native_call=self.forbid_native, terminal_call=self.forbid_native, check=self.check,
                                  phase='qualification')
        self.device._scene = replay_scene(raw)
        self.buffers, self.cameras = self.device.buffers, self.device.cameras

    def check(self):
        if time.perf_counter_ns() >= self.deadline:
            raise TimeoutError('original_local_replay_deadline_expired')

    def forbid_native(self, *_args, **_kwargs):
        raise AssertionError('offline_replay_must_not_enter_Blender')

    def scene_data(self, selectors=None):
        return self.device.scene_data(selectors=selectors)

    def render_local(self, *args, **kwargs):
        return self.device.render_local(*args, **kwargs)

    def image_specification(self, ref):
        return self.device.image_specification(ref)

    def adopt_images(self, key, response):
        p = self.public_dir/(key+'_PRODUCER.json')
        self.public_input_pins.append(pin(p))
        producer = read(p)
        require(producer['result_kind']=='source_region' and len(producer['frames'])<=1
                and producer['binding']['runtime_source_sha256']==SOURCE_SHA,
                'replay_expected_source_region_public_frame_contract')
        parts = response['result']['content']
        require(parts and parts[0]['type']=='text','offline_installed_ordinary_json_required')
        images = [block for block in parts if block['type']=='image']
        require(len(images)==len(producer['frames']),'offline_installed_native_block_count_mismatch')
        if not images:
            return response
        frame, = producer['frames']
        image, = images
        require(image['mimeType']=='image/png' and base64.b64decode(image['data'],validate=True)==Path(frame['image_path']).read_bytes(),
                'offline_installed_image_block_not_original_png')
        document = json.loads(parts[0]['text'])
        if key=='Obj_02':
            row, = document['images']
            authored = Path(row['local_image_path'])
            require(authored==Path(frame['image_path']) and str(authored.resolve(strict=True))==str(authored)
                    and row['image_ref']==frame['image_ref'], 'brief_not_bound_to_actual_installed_canonical_path')
        target = self.folder/'installed_replay_frames'/key
        target.parent.mkdir(exist_ok=True)
        target.mkdir()
        relocations = {}
        for field, digest_field in (('image_path','image_sha256'), ('arrays_path','arrays_sha256')):
            original = Path(frame[field])
            row = pin(original)
            self.public_input_pins.append(row)
            require(row['sha256'] == frame[digest_field], 'offline_installed_asset_bytes_changed')
            copied = target/original.name
            copyfile(original, copied)
            frame[field] = str(copied)
            relocations[original.resolve(strict=True)] = copied
            self.media_relocations.append({'fixture':key,'field':field,'source':row,'copy':pin(copied)})
        self.adopted_origins.extend(self.device.adopt_product_result(producer,
            {'path':str(p),'scope':'derived installed product on saved captures; no live host'}))

        # Relocate only published media path strings. Archive the installed reply separately.
        def relocate(value):
            if isinstance(value,dict):
                for field,item in value.items():
                    if field in ('image_path','arrays_path','local_image_path') and isinstance(item,str):
                        original_path=Path(item)
                        replacement=relocations.get(original_path)
                        if replacement is not None:
                            value[field]=replacement.as_posix() if field=='local_image_path' else str(replacement)
                    else:
                        relocate(item)
            elif isinstance(value,list):
                for item in value:
                    relocate(item)
        relocate(document)
        parts[0]['text']=json.dumps(document,ensure_ascii=False,separators=(',',':'),allow_nan=False)
        return response

    def public_request(self, arguments):
        self.check()
        query = arguments['query']
        key = query['region']['object']['name']
        require(self.label=='QP' and key in ('Obj_02','Obj_06') and query=={
            'mode':'source_region','region':{'object':{'name':key},'source_triangle_indices':[0,1]},
            'reference':{'name':'Obj_03'},'requested_facts':['surface_proximity']}
            and arguments['include_image'] is True and (
                'response_detail' not in arguments if key=='Obj_02' else arguments.get('response_detail')=='full'),
            'wrong_replayed_dual_region_request')
        fixture_request = self.public_dir/(key+'_REQUEST.json')
        if fixture_request.is_file():
            self.public_input_pins.append(pin(fixture_request))
            require(read(fixture_request)['params']['arguments']==arguments,'installed_fixture_request_changed')
        p = self.public_dir/(key+'.json')
        response = read(p)
        self.public_input_pins.append(pin(p))
        response=self.adopt_images(key,response)
        self.public_requests.append({'request':{'params':{'name':TOOL,'arguments':deepcopy(arguments)}},
                                     'response':response, 'replayed_from':str(p),
                                     'layer':'derived installed producer/public response, with no live capture'})
        require(response['result']['isError'] is False, 'installed_product_replay_is_error')
        return response


def assert_stdio(folder, close, names):
    require(close['confirmed'] is True and close['exit_code'] == 0, 'offline_stdio_stayed_open')
    bridge_folder, = list(folder.iterdir())
    exit_file = bridge_folder/'EXIT.json'
    end = read(exit_file)
    require(end['normal_exit'] is True and end['attempts'] == len(names), 'offline_thin_stdio_stream_incomplete')
    receipts, tool_names = [], []
    for wire in sorted(p for p in bridge_folder.iterdir() if p.is_dir()):
        tx = read(wire/'TX.bin')
        row = read(wire/'RECEIPT.json')
        if tx['method'] == 'tools/call':
            require(row['owner_TCP_attempted'] is True and row['flush_completed_ns'] is not None,
                    'offline_tool_not_flushed_to_stdio')
            response = read(wire/'RX.bin')
            require(response['id'] == tx['id'] and row['attempt'] == len(tool_names) + 1,
                    'offline_tool_attempt_or_reply_identity_mismatch')
            tool_names.append(tx['params']['name'])
        receipts.append(row)
    require([x['method'] for x in receipts[:3]] == ['initialize','notifications/initialized','tools/list']
            and end['requests'] == len(receipts) and tool_names == names, 'offline_stdio_sequence_not_retained')
    return {'exit':pin(exit_file), 'raw_receipts':receipts}


def run_arm(label, output, raw, public_dir):
    from bridge import Owner
    from diagnostic import run_diagnostic

    group = label[-1]
    folder = output/label
    folder.mkdir()
    initial = folder/'initial_capture/TERMINAL_SOURCE.json'
    initial.parent.mkdir()
    write(initial,replay_scene(raw))
    deadline = time.perf_counter_ns() + 60_000_000_000
    runtime = ReplayRuntime(folder, label, group, deadline, raw, public_dir)
    owner = Owner(runtime, {'label':label, 'group':group, 'phase':'qualification',
                           'worker_deadline_ns':deadline, 'output':str(folder/'owner')})
    endpoint = owner.start(folder/'ENDPOINT.json')
    result = {'diagnostic_calls':[]}
    try:
        run_diagnostic(folder, endpoint, deadline, group, owner, result)
    finally:
        close = owner.close()
    require(close['confirmed'] and not close['errors'] and not close['transport_errors'], 'replay_owner_close_failed')
    names = ['execute_python','execute_python','render_local']
    if group == 'P':
        names += [TOOL]*2 + ['read_images']
        require(len(runtime.public_requests)==2 and len(runtime.adopted_origins)>=1,'offline_public_contracts_incomplete')
    require([row['name'] for row in result['diagnostic_calls']] == names and result['qualification']['passed'],
            'real_run_diagnostic_incomplete')
    stdio = assert_stdio(folder/'client/attachments', result['diagnostic_close'], names)
    start = read(folder/'client/transport/START.json')
    require(Path(start['cwd']) == folder and Path(start['command'][0]) == Path(sys.executable)
            and str(THIN) in start['command'], 'local_replay_not_using_actual_diagnostic_child')
    images = {k: result['qualification'][k] for k in ('common_image','product_image') if result['qualification'][k]}
    for image in images.values():
        path = Path(image['path'])
        require(pin(path)['sha256'] == image['sha256'] and path.is_relative_to(folder), 'offline_replay_image_lost_after_close')
    result.update(scope='actual diagnostic and bridge on archived scene plus installed product replay',
                  bridge_owner_closed=close, thin_stdio=stdio, public_input_pins=runtime.public_input_pins,
                  media_path_relocations=runtime.media_relocations, derived_initial_display=pin(initial),
                  reopened_images=images, host_process_started=False, model_process_started=False)
    write(folder/'LOCAL_REPLAY_RESULT.json',result)
    return {'receipt':pin(folder/'LOCAL_REPLAY_RESULT.json'), 'exact_calls':names,
            'stdout_original':pin(folder/'client/transport/stdout.raw.bin'),
            'owner_original':pin(folder/'owner/BRIDGE_RESULT.json'), 'transport_start':pin(folder/'client/transport/START.json'),
            'source_pins':runtime.public_input_pins, 'post_EOF_images':images,
            'public_responses':len(runtime.public_requests), 'passed':True}


def refusal_recovery(output, raw, public_dir):
    from bridge import Owner
    from runtime import previous

    class WrongRouteOnce(Owner):
        def handle(self, request, attempt=None):
            if request.get('id') == 'deliberate-wrong-carrier-id':
                require(attempt == 1 and request['method'] == 'tools/call', 'invalid_refusal_trigger')
                return {'jsonrpc':'2.0','id':'wrong-response-id','result':{'isError':False,'content':[]}}
            return super().handle(request, attempt)

    folder = output/'REFUSAL'
    folder.mkdir()
    deadline = time.perf_counter_ns() + 30_000_000_000
    owner = WrongRouteOnce(ReplayRuntime(folder,'QN','N',deadline,raw,public_dir),
        {'label':'QN','group':'N','phase':'qualification', 'worker_deadline_ns':deadline,'output':str(folder/'owner')})
    endpoint = owner.start(folder/'ENDPOINT.json')
    client = previous.transport.StdioClient([sys.executable,'-I','-B','-X','utf8',str(THIN),
        '--endpoint',str(endpoint),'--audit',str(folder/'thin')],folder,folder/'transport',deadline)
    try:
        req = {'jsonrpc':'2.0','id':'init','method':'initialize','params':{'protocolVersion':'2025-03-26'}}
        client.call(req)
        client.call({'jsonrpc':'2.0','method':'notifications/initialized'})
        require(client.call({'jsonrpc':'2.0','id':'tools','method':'tools/list'})['result']['tools'] == owner.tools,
                'unexpected_catalogue_after_stdio_initialize')
        req = {'jsonrpc':'2.0','id':'deliberate-wrong-carrier-id','method':'tools/call',
               'params':{'name':'execute_python','arguments':{'code':'print(123)'}}}
        rejected = client.call(req)
        require(rejected['result'] == {'isError':True,'content':[{'type':'text',
                'text':'ValueError: owner_RPC_response_identity'}]}, 'thin_did_not_use_retained_error_formatter')
        accepted = client.call({**req,'id':'next-valid-business'})
        require(accepted['result']['isError'] is False
                and json.loads(accepted['result']['content'][0]['text'])['stdout'] == '123\n',
                'same_thin_process_failed_next_business_after_refusal')
    finally:
        close = client.finish()
        owner_close = owner.close()
    require(owner_close['confirmed'] and not owner_close['errors'] and not owner_close['transport_errors'],
            'refusal_control_owner_close_failed')
    audit = assert_stdio(folder/'thin',close,['execute_python','execute_python'])
    require([r['origin'] for r in audit['raw_receipts'][-2:]] == ['transport_failure','owner']
            and [r['attempt'] for r in audit['raw_receipts'][-2:]] == [1,2], 'wrong_recovery_wire_attempt_chain')
    return {'passed':True,'deliberate_carrier_rejection':rejected,'next_valid':accepted,'thin_stdio':audit,
            'transport_start':pin(folder/'transport/START.json'),'close':close}


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned_interpreter_requires_I_B')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--public-dir',required=True,type=Path)
    parser.add_argument('--only-arm',choices=['QN','QP','refusal'])
    args = parser.parse_args()
    settings = read(PRODUCT_BINDING)
    shared = read(SEAL/'SHARED_DEPENDENCY.json')
    sys.path[:0] = [str(NS), settings['dependency_root'], shared['dependency_root'], str(NS/'qualification')]
    bootstrap = load_retained('_dual_replay_verified_product',PRIOR/'harness/reused/verified_bootstrap.py')
    bootstrap.bootstrap(settings)
    from human_eye_plugin.runtime_identity import runtime_identity
    from bridge import TOOL_NAMES

    identity = runtime_identity()
    require(identity['source_kind'] == 'installed_distribution' and identity['source_sha256'] == SOURCE_SHA,
            'offline_replay_did_not_load_fixed_install')
    raw, provenance = frozen_capture()
    output = args.output_dir.resolve()
    output.mkdir(parents=True,exist_ok=False)
    public = args.public_dir.resolve()
    runs = {}
    for name in ('QN','QP','refusal'):
        if args.only_arm is None or args.only_arm == name:
            runs[name] = refusal_recovery(output,raw,public) if name == 'refusal' else run_arm(name,output,raw,public)
    actual_catalogue = None
    if 'QN' in runs and 'QP' in runs:
        native, plugin = (read(output/f'{label}/client/TOOLS.json')['result']['tools'] for label in ('QN','QP'))
        fixed, = [tool for tool in read(CATALOGUE) if tool['name'] == TOOL]
        require(plugin == [*native, fixed], 'actual_tools_common_schema_changed')
        actual_catalogue = {'full_common_schemas_equal':True,'installed_schema_exact':True,
                            'catalogues':[pin(output/f'{label}/client/TOOLS.json') for label in ('QN','QP')]}
    provenance['source_pins'].extend([pin(Path(__file__)), pin(PRODUCT_BINDING), pin(CATALOGUE),
        pin(NS/'harness/bridge.py'),pin(NS/'harness/runtime.py'),pin(NS/'qualification/diagnostic.py'),pin(THIN), pin(Path(sys.executable))])
    write(output/'DIAGNOSTIC_REPLAY.json',{'passed':True,'full_both_arm_preflight':set(runs)=={'QN','QP','refusal'},
        'qualification_runs':runs,'runtime_source':identity['source_sha256'],'registered_original_asset':ASSET_SHA256,
        'common_tools':sorted(TOOL_NAMES['N']), 'plugin_only_tools':sorted(TOOL_NAMES['P']-TOOL_NAMES['N']),
        'actual_catalogue_comparison':actual_catalogue,
        'original_qualification_source':provenance, 'controller_cwd':str(Path.cwd()), 'repository':str(ROOT),
        'offline_common_raster_builds':sum(name in runs for name in ('QN','QP')), 'live_Blender_launches':0,
        'provider_model_launches':0,'actual_formal_slots':0,
        'scope':'offline replay with the real run_diagnostic and thin stdio, never a substitute for new owned qualification'})
    print(json.dumps({'status':'passed','runs':list(runs),'receipt':pin(output/'DIAGNOSTIC_REPLAY.json')}))


if __name__ == '__main__':
    main()
