"""Run the fixed installed MCP server against sealed producers without a Blender host."""

import argparse
import base64
import copy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from zipfile import ZipFile


V = Path(__file__).resolve().parents[1]
FORMAL = 'perf050_dense_micro_surface_holdout_recovery_001'
PREDICTION = 'm4_cross_scale_projected_bounds_001'
TARGET = 'perf050_dense_pair_transfer_001'
INSTALL = V/'m4_source_region_blocker_frame_list_001/install'
SOURCE = '65bd1ec8009f8024e85ef1cd30c1229957cceb1c1766c8e5b62f2ef2489ce48c'
WHEEL = '97053290d96270fefeff95d681efaf5222a64ef136a084267be5d7c707d6813d'
GIT = '8cf3fabc1a735b7ff5849b3c63c49cf932df4b6b'
TOOL = 'human_eye_scene_observe'
WORKSPACE = Path('D:/he_m1_region_task_brief_client_profile_001')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def compact(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pin(path):
    path = path.resolve(strict=True)
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': digest(data)}


def save(path, value):
    with path.open('xb') as stream:
        stream.write(compact(value) + b'\n')


@lru_cache
def archive_scope(batch):
    runtime = Path('D:/he_' + batch)
    if batch == FORMAL:
        source = V/batch/'RAW_INDEX.json'
        index = read(source)
        archive = V/batch/index['archive']['name']
        members, prefix = index['members'], 'runtime/'
    else:
        source = V/batch/'RUNTIME_INDEX.json'
        index = read(source)
        archive = Path(index['archive']['path'])
        members = {row['path']: row for row in index['files']}
        prefix = ''
    actual = pin(archive)
    require(actual['bytes'] == index['archive']['bytes'] and actual['sha256'] == index['archive']['sha256'],
            'original_archive_changed/' + batch)
    return runtime, archive, members, prefix, (pin(source), actual)


def archived_bytes(batch, *parts):
    runtime, archive, members, prefix, _ = archive_scope(batch)
    relative = Path(*parts)
    name = prefix + relative.as_posix()
    path = runtime/relative
    actual = pin(path)
    expected = members[name]
    require(actual['bytes'] == expected['bytes'] and actual['sha256'] == expected['sha256'],
            'old_disk_member_differs_from_sealed_original/' + name)
    with ZipFile(archive) as package:
        data = package.read(name)
    require(digest(data) == actual['sha256'], 'old_zip_member_differs_from_disk/' + name)
    return data, actual


def archived(batch, *parts):
    data, actual = archived_bytes(batch, *parts)
    return json.loads(data), actual


def historic_order(value, public):
    """Use the original public key order without changing any archived producer value."""
    if isinstance(value, dict) and isinstance(public, dict):
        keys = [key for key in public if key in value] + [key for key in value if key not in public]
        return {key: historic_order(value[key], public.get(key)) for key in keys}
    if isinstance(value, list) and isinstance(public, list) and len(value) == len(public):
        return [historic_order(item, old) for item, old in zip(value, public, strict=True)]
    return value


@lru_cache
def fixture(batch, slot, ordinal):
    call = f'call_{ordinal:03d}'
    producer, producer_pin = archived(batch, 'slots', slot, 'product_full', call, 'SERVICE_RESULT.json')
    request, request_pin = archived(batch, 'slots', slot, 'product_calls', call, 'REQUEST.json')
    response, response_pin = archived(batch, 'slots', slot, 'product_calls', call, 'RESPONSE.json')
    require(request['params']['name'] == TOOL and request['id'] == response['id'] and
            response['result']['isError'] is False and response['result']['content'][0]['type'] == 'text',
            'archived_original_product_pairs_mismatch/' + slot + '/' + call)
    text = response['result']['content'][0]['text']
    public = json.loads(text)
    ordered = historic_order(producer, public) if request['params']['arguments'].get('response_detail') == 'full' else producer
    require(ordered == producer, 'historic_key_order_changed_producer_values')
    image_pins = []
    blocks = [block for block in response['result']['content'] if block['type']=='image']
    require(len(blocks)==len(producer['frames']), 'archive_producer_and_public_image_counts_differ')
    for frame, block in zip(producer['frames'], blocks, strict=True):
        path = Path(frame['image_path']).resolve(strict=True)
        relative = path.relative_to(archive_scope(batch)[0].resolve(strict=True))
        data, actual = archived_bytes(batch, *relative.parts)
        require(digest(data)==frame['image_sha256'] and len(data)==frame['PNG_bytes']
                and block['mimeType']=='image/png' and base64.b64decode(block['data'], validate=True)==data,
                'archive_original_PNG_binding_changed')
        image_pins.append(actual)
    return {'case': f'{batch}/{slot}/{call}', 'producer': ordered, 'public': public,
            'request': request['params']['arguments'], 'response': response,
            'pins': [producer_pin, request_pin, response_pin, *image_pins]}


def fixtures(slot):
    require(slot in ('P2', 'P3'), 'expected_fixed_P2_or_P3_archive')
    return {'discovery': fixture(FORMAL, slot, 1), 'source_measurement': fixture(FORMAL, 'P1', 2),
            'source_unknown': fixture(FORMAL, 'P3', 2), 'no_image_prediction': fixture(PREDICTION, 'B1', 2),
            'other_observation': fixture(TARGET, 'P1', 1)}


def requests(slot):
    cases = fixtures(slot)
    discover = cases['discovery']['request']
    measurement = cases['source_measurement']['request']
    return {'discover_full': copy.deepcopy(discover), 'discover_brief': {**copy.deepcopy(discover), 'response_detail': 'brief'},
            'discover_omitted': {k: copy.deepcopy(v) for k, v in discover.items() if k != 'response_detail'},
            'source_region_full': copy.deepcopy(measurement), 'source_region_no_image': {**copy.deepcopy(measurement), 'response_detail': 'brief'},
            'source_region_unknown': copy.deepcopy(cases['source_unknown']['request']),
            'discover_no_image': {**copy.deepcopy(cases['no_image_prediction']['request']), 'response_detail': 'brief'},
            'active_other': copy.deepcopy(cases['other_observation']['request'])}


def installed_binding():
    binding = read(INSTALL/'PRODUCT_RUN_BINDING.json')
    require(binding['preparation_git'] == GIT and binding['source_sha256'] == SOURCE and
            binding['wheel_sha256'] == WHEEL and len(binding['source_manifest']) == 143,
            'unexpected_fixed_installed_product')
    return binding


def worker(root, slot, request_budget_s):
    binding = installed_binding()
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.query_policy import validate_query
    from human_eye_plugin.runtime_identity import runtime_identity

    require(runtime_identity(mode='live')['source_sha256'] == SOURCE and
            Path(mcp.__file__).resolve().is_relative_to(Path(binding['install_root'])), 'loaded_actual_product_differs')
    catalogue = read(INSTALL/'TOOLS_SCHEMA.json')
    require(catalogue == mcp.LIVE_MCP_TOOLS_SCHEMA, 'fixed_installed_tools_differ')
    registered = fixtures(slot)
    lookup = {(compact(validate_query(record['request']['query'])), record['request']['include_image']): record
              for record in registered.values()}
    require(len(lookup) == len(registered), 'ambiguous_archived_observe_shape')

    terminal, terminal_pin = archived(FORMAL, 'slots', 'P3', 'TERMINAL_SOURCE.json')
    source_arrays = {x['object_id']: x for x in terminal['objects']}
    unknown = registered['source_unknown']
    unk_bind = unknown['producer']['binding']
    require(len(unk_bind['objects']) == len(source_arrays) == 21, 'unknown_original_mesh_count_changed')
    counts = []
    for original in unk_bind['objects']:
        native = source_arrays[original['host_id']]
        require((native['name'], native['instance_id']) == (original['object_name'], original['instance_id']),
                'unknown_original_mesh_identity_changed')
        counts.append(len(native['evaluated']['triangles']))

    # Keep replay output entirely below the isolated batch directory.
    root = root.resolve()
    require(root != WORKSPACE and root.is_relative_to(WORKSPACE), 'replay_output_outside_trial_workspace')
    root.mkdir(parents=True, exist_ok=False)
    config = root/'PRODUCT_CONFIG.json'
    save(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                  'project_root': binding['install_root'], 'state_file': str(root/'product_state.json'),
                  'audit_file': str(root/'product_audit.jsonl'), 'request_budget_s': request_budget_s,
                  'expected_identity': {'source_sha256': SOURCE}})
    source_pins = {row['path']: row for record in registered.values() for row in record['pins']}
    for row in (*archive_scope(FORMAL)[4], *archive_scope(PREDICTION)[4], *archive_scope(TARGET)[4], terminal_pin,
                pin(INSTALL/'PRODUCT_RUN_BINDING.json'), pin(INSTALL/'TOOLS_SCHEMA.json'), pin(Path(mcp.__file__)),
                pin(Path(binding['wheel_path']))):
        source_pins[row['path']] = row
    require(source_pins[str(Path(binding['wheel_path']).resolve())]['sha256']==WHEEL, 'installed_wheel_bytes_changed')
    save(root/'INPUTS.json', {'slot': slot, 'source_pins': list(source_pins.values()),
        'fixtures': {key: {'archive_case': r['case'], 'producer_source_sha256': r['producer']['binding']['runtime_source_sha256']}
                     for key, r in registered.items()}})

    class NoHost:
        attempts = 0

        def __getattr__(self, name):
            if name in ('runtime_identity', 'runtime_manifest', 'verify_readonly_source', 'package_identity', 'source_identity'):
                raise AttributeError(name)
            self.attempts += 1
            raise AssertionError('no_Blender_host_in_replay/' + name)

    class Replay(LiveSpatialService):
        def __init__(self):
            super().__init__(config, host=NoHost())
            self.dispatches = 0
            self.codec_events = []

        def _archived_observe(self, query, include_image):
            key = (compact(validate_query(query)), include_image)
            record = lookup.get(key)
            if record is None:
                raise ValueError('archived_fixture_for_exact_validated_query_required')
            original = record['producer']
            value = copy.deepcopy(original)
            self.dispatches += 1
            if record is unknown:
                # Rehydrate just the private display lookup using original identity, frame,
                # per-object face counts and observed classifications. The production reader
                # still decides whether its original six blocker addresses can be published.
                rid = value['region_ref']['region_id']
                selected = value['facts']['region']['host_id']
                index, = [i for i, obj in enumerate(value['binding']['objects']) if obj['host_id'] == selected]
                context = self._read_context
                context.activate(value['binding'], 'source_region', query)
                private = SimpleNamespace(region_ref=value['region_ref'], observation=value, binding=value['binding'],
                    meshes=[SimpleNamespace(faces=range(size)) for size in counts], object_index=index,
                    source_triangle_indices=value['region_ref']['source_triangle_indices'])
                context.prepared('source_regions', lambda: {'regions': {rid: private}})
            with (root/'PRODUCER_CALLS.jsonl').open('ab') as stream:
                stream.write(compact({'index': self.dispatches, 'source': record['case'], 'query': query,
                    'include_image': include_image, 'started_ns': time.perf_counter_ns(),
                    'archived_producer_sha256': record['pins'][0]['sha256']}) + b'\n')
            return value

        def _observe_active_observation(self, session_id, *, include_image, selector, task_query, region_task):
            query = {'mode': 'active_observation'}
            if selector is not None:
                query['objects'] = [selector]
            if task_query is not None:
                query['task_query'] = task_query
            if region_task is not None:
                query['region_task'] = region_task
            return self._archived_observe(query, include_image)

        def _observe_source_region(self, session_id, query, *, include_image):
            return self._archived_observe(query, include_image)

        def record_event(self, event, **fields):
            if event in ('active_observation_mcp_content', 'source_region_mcp_content'):
                self.codec_events.append({'event': event, **fields})

        def close(self):
            save(root/'EOF.json', {'closed': True, 'observe_dispatches': self.dispatches, 'host_attempts': self.host.attempts,
                 'new_rasters': 0, 'source_sha256': SOURCE, 'encoder_events': self.codec_events})

    mcp._configure_utf8_stdio()
    mcp.run_stdio_mcp_server(Replay())


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'registered_isolated_worker_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', nargs=2, metavar=('ROOT','SLOT'), required=True)
    parser.add_argument('--request-budget-s', type=float, default=30)
    args = parser.parse_args()
    worker(Path(args.worker[0]), args.worker[1], args.request_budget_s)
