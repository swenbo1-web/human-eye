"""Replay joint measurement with the frozen dense observation and its original images."""

import base64
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import runpy
import subprocess
import sys
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
RASTER = V / 'm4_dense_raster_cross_001'
BASE = RASTER / 'install/PRODUCT_RUN_BINDING.json'
CANDIDATE = NS / 'install/PRODUCT_RUN_BINDING.json'
INDEX = RASTER / 'RUNTIME_INDEX.json'
CAPTURE = V / 'm4_cross_scale_discovery_001/oracle/check_saved.py'
ARCHIVE_SHA = '692a05b0293cef88b8ace973a05331bce09d33cd6f7c9b7c21177f090cbcf179'
ORIGINAL = Path('D:/he_m4_dense_raster_cross_001')
SLOT = ORIGINAL / 'slots/B1'
OUTER = Path('D:/he_m5_global_observe_measure_qualification_001/slots/B/batch/rpc_03/RECEIPT.json')
QUERY = {'mode': 'task', 'objects': [{'name': 'M4_Far_00'}, {'name': 'M4_Near'}],
         'requested_facts': ['surface_proximity']}

sys.path.insert(0, str(HERE))
from offline_decode import decode_task, require
from live_wire_adapter import POLICY, replay


def digest(data):
    return sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def raw(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def pin(path):
    return {'path': str(path.resolve()), 'bytes': path.stat().st_size, 'sha256': digest(path.read_bytes())}


class DenseArchive:
    def __init__(self, archive, index):
        self.archive = archive
        self.files = {row['path']: row for row in index['files']}
        self.entries = []

    def member(self, path):
        name = path.relative_to(ORIGINAL).as_posix()
        record, saved = self.files[name], self.archive.read(name)
        require(digest(saved) == record['sha256'] and len(saved) == record['bytes'], 'archive_member_changed/' + name)
        self.entries.append(record)
        return saved

    def read(self, path, digest=None, within=None):
        require(within == SLOT and path.is_relative_to(SLOT) and digest is None, 'raw_wire_outside_dense_slot')
        return json.loads(self.member(path))

    check = staticmethod(require)


def source_inputs(install):
    index = read(INDEX)
    path = Path(index['archive']['path'])
    archive_pin = pin(path)
    require(archive_pin['sha256'] == ARCHIVE_SHA == index['archive']['sha256'] and
            archive_pin['bytes'] == index['archive']['bytes'], 'dense_archive_changed')
    with ZipFile(path) as zip_file:
        archive = DenseArchive(zip_file, index)
        producer = json.loads(archive.member(SLOT / 'product_full/call_001/SERVICE_RESULT.json'))
        public = json.loads(archive.member(SLOT / 'product_calls/call_001/RESPONSE.json'))['result']
        terminal = json.loads(archive.member(SLOT / 'TERMINAL_SOURCE.json'))
        helpers = runpy.run_path(str(CAPTURE))
        captures, _ = helpers['decode_captures'](SLOT, install, archive)
        capture = helpers['current_capture'](captures, producer['binding'], archive)
        helpers['source_binding_checks'](capture, producer['binding'], install, archive)
        current = capture['meshes']
        require((len(current), sum(len(mesh['faces']) for mesh in current)) == (14, 6148) and
                all(mesh['object_id'] == obj['object_id'] and mesh['name'] == obj['name'] and
                    mesh['vertices'] == obj['evaluated']['vertices_world_m'] and
                    mesh['faces'] == obj['evaluated']['triangles']
                    for mesh, obj in zip(current, terminal['objects'], strict=True)), 'dense_source_not_current')
        frames = []
        for frame in producer['constructed_frames']:
            row = {}
            for key, sha_key in (('image_path', 'image_sha256'), ('arrays_path', 'arrays_sha256')):
                artifact = Path(frame[key])
                saved = archive.member(artifact)
                require(digest(saved) == frame[sha_key] and artifact.read_bytes() == saved, 'dense_artifact_changed/' + key)
                row[key] = pin(artifact)
            frames.append(row)
        require(len(frames) == 2, 'dense_original_frame_count_changed')
    return producer, public, capture, frames, archive.entries, archive_pin


def measurement(producer, capture, install):
    from human_eye_plugin.active_observation import geometry
    from human_eye_plugin.active_observation_host import scene_from_capture
    from human_eye_plugin.active_observation_images import _meshes_from_objects
    from human_eye_plugin.live_service import LiveSpatialService, _validated_scene
    from human_eye_plugin.read_context import ReadContext
    from human_eye_plugin.task_query import task_result

    service = object.__new__(LiveSpatialService)
    service._identity = {'source_sha256': install['source_sha256']}
    parent = producer['binding']
    objects, _, _ = geometry(scene_from_capture(capture))
    aliases = tuple(mesh.object_id for mesh in _meshes_from_objects(objects))
    view, sources, work = service._prepare_observation_task_view(capture, QUERY)
    require(work['supplemental_capture_calls'] == 0 and len(sources) == 2, 'dense_offline_sources_not_complete')
    view = service._observation_task_view(view, sources, work, QUERY, parent, aliases)
    context = ReadContext()
    context.activate(view, 'observation_task', {'parent_binding_sha256': parent['binding_sha256'], 'task_query': QUERY})
    scene, meshes, fingerprint = context.normalized(
        lambda: _validated_scene(view, _observation_task_capture=True, _annotate_scene=False))
    task = task_result(scene, meshes, fingerprint, QUERY, context.scene_cache, lambda _: None)
    task['binding']['observation_source'] = {
        'schema': 'active-observation-task-source-v1', 'measurement_scope': 'whole_objects',
        'capture_scope': 'observation_task_objects', 'parent_binding_sha256': parent['binding_sha256'],
        'parent_source_binding_sha256': parent['source_binding_sha256'], 'parent_capture_scope': parent['capture_scope'],
        'capture_state': view['capture_state'], 'objects': sources,
    }
    service._bind_read_result(task, {'status': parent['source_status'], 'source_check_scope': parent['source_check_scope']})
    return task


def worker(binding_path):
    install = read(binding_path)
    sys.path[:0] = [install['install_root'], install['dependency_root']]
    from human_eye_plugin.live_spatial_mcp import _tool_result

    if binding_path == CANDIDATE:
        producer = json.load(sys.stdin)
        candidate = _tool_result(producer, is_error=False, response_detail='brief', observation_task_query=QUERY)
        print(raw(candidate))
        return
    producer, public, capture, frames, members, archive_pin = source_inputs(install)
    observation = _tool_result(producer, is_error=False, response_detail='brief')
    require(observation['isError'] == public['isError'] is False and
            json.loads(observation['content'][0]['text']) == json.loads(public['content'][0]['text']) and
            observation['content'][1:] == public['content'][1:], 'dense_observation_replay_changed')
    task = measurement(producer, capture, install)
    producer['task_result'] = task
    joint = _tool_result(producer, is_error=False, response_detail='brief')
    require(joint['content'][1:] == public['content'][1:], 'legacy_dense_joint_image_changed')
    print(raw({'producer': producer, 'joint': joint, 'frames': frames, 'members': members, 'archive_pin': archive_pin}))


def outer(value, template):
    frame_text = json.loads(template['content'][0]['text'])
    require(list(frame_text) == ['stdout', 'stderr', 'error'] and frame_text['stdout'].startswith('M5_GLOBAL_JOINT:') and
            frame_text['stderr'] == '' and frame_text['error'] is None and
            raw(frame_text) == template['content'][0]['text'], 'recorded_outer_envelope_changed')
    frame_text['stdout'] = 'M5_GLOBAL_JOINT:' + value['content'][0]['text'] + '\n'
    return {'content': [{'type': 'text', 'text': raw(frame_text)}, *value['content'][1:]], 'isError': False}


def main():
    def launch(path, payload=None):
        return json.loads(subprocess.check_output([sys.executable, '-I', '-B', str(Path(__file__).resolve()),
            '--worker', str(path)], input=payload, timeout=100))

    historic = launch(BASE)
    baseline = historic['joint']
    candidate = launch(CANDIDATE, raw(historic['producer']).encode())
    old_body, new_body = (json.loads(result['content'][0]['text']) for result in (baseline, candidate))
    new_task = decode_task(new_body)
    require(new_task == old_body.pop('task_result') == historic['producer']['task_result'] and
            {k: v for k, v in new_body.items() if k != 'task_result'} == old_body and
            candidate['content'][1:] == baseline['content'][1:], 'dense_joint_facts_or_images_changed')
    proximity = new_task['facts']['surface_proximity']['value']
    witness = proximity['nearest_witness']
    distance = Fraction(2138893713, 2147483648)
    require(Fraction(proximity['distance_m']) == distance and witness['direction_a_to_b'] == [-1., 0., 0.],
            'dense_whole_object_distance_or_orientation_changed')
    images = [digest(base64.b64decode(row['data'], validate=True)) for row in candidate['content'] if row['type'] == 'image']
    require(images == [frame['image_path']['sha256'] for frame in historic['frames']], 'dense_mcp_images_not_sealed_pngs')
    template = read(OUTER)['response']['result']
    old_outer, new_outer = (outer(result, template) for result in (baseline, candidate))
    sizes = [len(part['content'][0]['text'].encode()) for part in (baseline, old_outer, candidate, new_outer)]
    old_cli, new_cli, old_outer_cli, new_outer_cli = map(replay, (baseline, candidate, old_outer, new_outer))
    print('Dense old/new direct/outer:', sizes, flush=True)
    require(sizes[:2] == [11338, 12154] and old_cli['passed'] and not old_outer_cli['passed'] and
            all(not row['MCP_exact'] and not row['history_exact'] and row['PNG_exact'] for row in old_outer_cli['stages'])
            and new_cli['passed'] and new_outer_cli['passed'], 'dense_fixed_cli_boundary_not_reproduced')
    receipt = {'passed': True, 'dense': True, 'new_raster_attempts': 0, 'new_blender_slots': 0,
        'whole_object_distance_exact_m': str(distance), 'direction_a_to_b': witness['direction_a_to_b'],
        'raw_task_reconstituted_exactly': True, 'old_public_bytes': sizes[0], 'old_outer_bytes': sizes[1],
        'new_public_bytes': sizes[2], 'new_outer_bytes': sizes[3], 'old_public_replay': old_cli, 'old_outer_replay': old_outer_cli,
        'public_replay': new_cli, 'outer_replay': new_outer_cli, 'original_frames': historic['frames'],
        'source_archive_members': historic['members'], 'source_pins': [historic['archive_pin'],
            *[pin(path) for path in (BASE, CANDIDATE, INDEX, CAPTURE, OUTER, Path(__file__), HERE / 'offline_decode.py',
                                     HERE / 'live_wire_adapter.py', POLICY)],
            *[file for frame in historic['frames'] for file in frame.values()]]}
    with (HERE / 'DENSE_OFFLINE.json').open('xb') as output:
        output.write(json.dumps(receipt, indent=2, ensure_ascii=False, allow_nan=False).encode() + b'\n')


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_offline_interpreter_required')
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        worker(Path(sys.argv[2]))
    else:
        main()
