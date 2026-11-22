"""Preflight the isolated recorder, actual owner and CLI stdio without live Blender."""

import base64
import json
from pathlib import Path
import runpy
import sys
import time
from types import FunctionType, SimpleNamespace


NS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NS / 'harness'))
import common
from common import CATALOGUE, PRODUCT_BINDING, SEAL, read, save, sha


ARCHIVED = Path('D:/he_m1_source_region_task_entry_holdout_001/slots/A1/owner/tool_04')
TOOL = 'human_eye_scene_observe'


def require(test, error):
    if not test:
        raise ValueError(error)


def recorder(root, args):
    # Reuse every validation in the real recorder, with only the offline run root changed.
    common.EXTERNAL = root
    sys.argv = [str(NS / 'harness/mcp_entry.py'), *args]
    runpy.run_path(sys.argv[0], run_name='__main__')


def request(identifier, method, **params):
    return {'jsonrpc': '2.0', 'id': identifier, 'method': method, 'params': params}


def arm(root, label, programme, archived, startup, transport):
    from bridge import Owner
    from frame_device import FrameDevice
    from runtime import Runtime

    group = label[-1]
    folder = root / 'slots' / label
    folder.mkdir(parents=True)
    deadline = time.perf_counter_ns() + 45_000_000_000
    class RuntimeReplay:
        def __init__(self):
            self.folder, self.label, self.phase, self.task_deadline = folder, label, 'qualification', deadline
            self.product_tools, self.public_requests, self.client = [], [], None
            self.native = SimpleNamespace(host='127.0.0.1', port=1)
            self.budget = SimpleNamespace(root=root / 'budget')
            self.device = FrameDevice(runroot=folder, asset_sha256=common.ASSET_SHA256, group=group, label=label,
                                      native_call=self.no_blender, terminal_call=self.no_blender, phase='qualification')
            self.cameras, self.buffers = self.device.cameras, self.device.buffers

        def no_blender(self, *args, **kwargs):
            raise AssertionError('offline_preflight_attempted_Blender')

        def _retain(self, process, filename):
            save(folder / filename, {'process_live': process.poll() is None, 'pid': process.pid})
            return process

        def public_request(self, args):
            tx = request('stock-observe', 'tools/call', name=TOOL, arguments=args)
            if args == programme:
                response = archived
            else:
                response = self.client.call(tx)
            self.public_requests.append({'request': tx, 'response': response})
            return response

    runtime = RuntimeReplay()
    png_bytes, = [base64.b64decode(block['data'], validate=True) for block in archived['result']['content']
                  if block['type'] == 'image']
    png = folder / 'replayed_original.png'
    png.write_bytes(png_bytes)
    image_ref = 'preflight-archived-image'
    runtime.device.by_ref[image_ref] = {'PNG':str(png), 'PNG_sha256':sha(png), 'size_px':[512,512], 'origin':'archive'}
    runtime.image_specification = runtime.device.image_specification
    real_client = transport.StdioClient

    def start_offline_recorder(command, *args):
        require(Path(command[5]) == NS / 'harness/mcp_entry.py', 'actual_startup_recorder_changed')
        wrapper = [*command[:5], str(Path(__file__).resolve()), '--recorder', str(root), *command[6:]]
        return real_client(wrapper, *args)

    def load_startup(name, path):
        return SimpleNamespace(StdioClient=start_offline_recorder)

    if group == 'P':
        FunctionType(startup.__code__, dict(startup.__globals__, load=load_startup))(runtime, PRODUCT_BINDING, read(PRODUCT_BINDING))
        require(runtime.product_tools == read(CATALOGUE), 'actual_catalogue_changed')
    owner = Owner(runtime, {'label': label, 'group': group, 'phase': 'qualification',
                            'worker_deadline_ns': deadline, 'output': str(folder / 'owner')})
    client = None
    try:
        endpoint = owner.start(folder / 'ENDPOINT.json')
        client = real_client([sys.executable, '-IB', '-X', 'utf8', str(NS / 'consumer/thin_stdio.py'),
                              '--endpoint', str(endpoint), '--audit', str(folder / 'attachments')],
                             folder, folder / 'outer', deadline)
        hello = client.call(request('initialize', 'initialize', protocolVersion='2025-03-26', capabilities={},
                                    clientInfo={'name':'dense-micro-preflight', 'version':'1'}))
        require('result' in hello, 'actual_owner_initialize_failed')
        client.call({'jsonrpc':'2.0', 'method':'notifications/initialized'})
        catalogue = client.call(request('tools', 'tools/list'))['result']['tools']
        require(catalogue == owner.tools, 'actual_outer_catalogue_changed')
        def invoke(name, arguments):
            return client.call(request(len(client.records), 'tools/call', name=name, arguments=arguments))['result']

        require(invoke('render_local', {'direction':'SCENE'})['isError'] is True, 'bad_ordinary_arguments_not_rejected')
        require(invoke('execute_python', {'code':'preflight_value = 19'})['isError'] is False,
                'ordinary_after_error_failed')
        normal = invoke('execute_python', {'code':'print(preflight_value + 23)'})
        require(normal['isError'] is False and json.loads(normal['content'][0]['text'])['stdout'].strip() == '42',
                'ordinary_recovery_or_persistent_state_lost')
        original = invoke('read_images', {'refs':[image_ref]})
        caption, image = original['content']
        declaration = json.loads(caption['text'].split('\n', 1)[1])
        require(not original['isError'] and caption['type']=='text' and image['type']=='image' and
                Path(declaration['local_image_path']) == png and declaration['image_sha256']==sha(png) and
                base64.b64decode(image['data'], validate=True)==png_bytes, 'ordinary_original_caption_path_or_image_changed')
        if group == 'P':
            bad = {**programme, 'response_detail':'invalid'}
            require(invoke(TOOL, bad)['isError'] is True and runtime.public_requests[-1]['request']['params']['arguments'] == bad,
                    'actual_installed_invalid_argument_not_rejected')
            current = invoke(TOOL, programme)
            require(current == archived['result'] and runtime.public_requests[-1]['request']['params']['arguments'] == programme,
                    'archive_product_mixed_reply_or_arguments_changed_in_bridge')
            require(any(block['type']=='image' and base64.b64decode(block['data'], validate=True).startswith(b'\x89PNG\r\n\x1a\n')
                        for block in current['content']), 'retained_product_image_missing')
            save(folder / 'MIXED_RESPONSES.json', current)
    finally:
        outer = client.finish() if client is not None else None
        ordinary = owner.close()
        inner = runtime.client.finish() if runtime.client is not None else None
        save(folder / 'PREFLIGHT_CLOSE.json', {'outer':outer, 'owner':ordinary, 'inner':inner})
        require(outer and outer['confirmed'] and outer['exit_code'] == 0 and ordinary['confirmed']
                and not ordinary['errors'] and not ordinary['transport_errors'] and
                (group == 'N' or (inner and inner['confirmed'] and inner['exit_code'] == 0)), 'offline_bridges_failed_to_close')
    return catalogue


def run(root):
    from runtime import Runtime, previous

    root.mkdir(parents=True, exist_ok=False)
    binding = read(PRODUCT_BINDING)
    programme = read(ARCHIVED / 'PRODUCT_ARGUMENTS.json')
    archived = read(ARCHIVED / 'PRODUCT_RESPONSE.json')
    data = {}
    for label in ('QN', 'QP'):
        data[label] = arm(root, label, programme, archived, Runtime._start_public_mcp, previous.transport)
    require(data['QP'][:-1] == data['QN'] and data['QP'][-1]['name'] == TOOL, 'only_installed_observe_may_differ')
    paths = [ARCHIVED / 'PRODUCT_ARGUMENTS.json', ARCHIVED / 'PRODUCT_RESPONSE.json']
    save(root / 'PREFLIGHT.json', {'passed': True, 'model_starts': 0, 'Blender_starts': 0,
         'actual_product_recorder': True, 'actual_installed_catalogue_and_invalid_argument': True,
         'ordinary_persistent_and_rejection_recovery': True, 'unchanged_archived_mixed_product_reply': True,
        'same_slot_read_images_caption_and_png_both_arms': True,
         'catalogues': data, 'source_pins': [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in paths]})


if __name__ == '__main__':
    if sys.argv[1] == '--recorder':
        recorder(Path(sys.argv[2]), sys.argv[3:])
    else:
        binding = read(PRODUCT_BINDING)
        sys.path[:0] = [binding['dependency_root'], read(SEAL / 'SHARED_DEPENDENCY.json')['dependency_root']]
        run(Path(sys.argv[1]).resolve())
