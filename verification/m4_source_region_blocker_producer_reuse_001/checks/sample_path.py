"""Compare the existing sampled-PNG reference through both installed MCP endpoints."""

from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from types import SimpleNamespace


NS = Path(__file__).resolve().parents[1]
V = NS.parent
OLD_REPLAY = V / 'm1_sampled_image_path_producer_reuse_001/checks/positives.py'


def read(path):
    return json.loads(path.read_bytes())


def require(test, reason):
    if not test:
        raise ValueError(reason)


def worker(binding_path, producer_path):
    binding = read(binding_path)
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp, source_region
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.read_context import ReadContext
    from human_eye_plugin.runtime_identity import runtime_identity

    require(runtime_identity()['source_sha256'] == binding['source_sha256'], 'wrong_installed_source')
    value = read(producer_path)
    original = deepcopy(value)
    for key in ('runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope'):
        original['binding'].pop(key, None)

    class Replay:
        _source_region_sample_path = LiveSpatialService._source_region_sample_path
        _matching_source_region_producer = getattr(LiveSpatialService, '_matching_source_region_producer', None)
        _source_region_blocker_rows = getattr(LiveSpatialService, '_source_region_blocker_rows', None)

        def __init__(self):
            self._read_context = ReadContext()
            self.state_path = producer_path.parents[2] / 'product_state.json'
            self.calls = 0
            self.closed = False
            self.prepared = SimpleNamespace(binding=original['binding'], region_ref=original['region_ref'],
                                            observation=original)
            with self._read_context.lock:
                self._read_context.activate(value['binding'], 'source_region')
                self._read_context.prepared('source_regions', lambda: {
                    'regions': {self.prepared.region_ref['region_id']: self.prepared}})

        def observe(self, _session, *, include_image, **_kwargs):
            require(include_image is True, 'original_image_request_changed')
            self.calls += 1
            if self.calls == 1:
                return deepcopy(value)
            if self.calls == 3:
                with self._read_context.lock:
                    capture = deepcopy(value['binding'])
                    capture['capture_state']['revision'] += 1
                    self._read_context.activate(capture, 'source_region')
            reused = source_region.observe_region(self.prepared, None, include_image=True)
            require(reused['work']['frame_reuses'] == 1 and reused['work']['raster_attempts'] == 0,
                    'warm_route_no_longer_reuses_PNG')
            return {**reused, **{key: deepcopy(value[key]) for key in ('binding', 'task_result', 'session_id')}}

        def _check_request_budget(self, *_args, **_kwargs):
            pass

        def close(self):
            self.closed = True

    service = Replay()
    mcp._configure_utf8_stdio()
    mcp.run_stdio_mcp_server(service)
    require(service.calls == 3 and service.closed, 'installed_sample_replay_dispatch_or_EOF_failed')


def run(output):
    previous = run_path(str(OLD_REPLAY))
    png, path, pins = previous['frozen_media']()
    request = read(previous['REQ'])
    requests = [dict(request, id=case) for case in ('cold', 'retained', 'stale')]
    data = b''.join((json.dumps(raw)+'\n').encode() for raw in requests)
    output.mkdir(parents=True, exist_ok=False)
    (output/'TX.bin').write_bytes(data)
    responses = {}
    for arm, binding in {'A': V/'m4_source_region_blocker_brief_001/install/PRODUCT_RUN_BINDING.json',
                         'B': NS/'install/PRODUCT_RUN_BINDING.json'}.items():
        process = subprocess.run([sys.executable, '-IB', str(Path(__file__).resolve()), '--worker',
                                  str(binding), str(previous['SOURCE'])], input=data,
                                 capture_output=True, timeout=45)
        (output/f'{arm}_RX.bin').write_bytes(process.stdout)
        (output/f'{arm}_STDERR.bin').write_bytes(process.stderr)
        process.check_returncode()
        require(not process.stderr, 'MCP_stderr')
        responses[arm] = process.stdout
    require(responses['A'] == responses['B'], 'sampler_changed_public_wire')
    records = []
    for item, png_path in zip(responses['B'].splitlines(), (path.as_posix(), path.as_posix(), None), strict=True):
        response = json.loads(item)
        result = response['result']
        text, image = result['content']
        require(result['isError'] is False
                and json.loads(text['text'])['images'][0].get('local_image_path') == png_path
                and previous['base64'].b64decode(image['data'], validate=True) == png, 'sample_PNG_reference_changed')
        records.append({'case': response['id'], 'original_path': png_path, 'text_bytes': len(text['text'].encode())})
    (output/'RESULT.json').write_bytes((json.dumps({'passed': 3, 'planned': 3, 'cases': records,
                                                  'original_evidence': pins}, indent=2)+'\n').encode())
    print(json.dumps({'passed': 3, 'planned': 3, 'cases': records}))


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--worker':
        worker(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        run(Path(sys.argv[1]))
