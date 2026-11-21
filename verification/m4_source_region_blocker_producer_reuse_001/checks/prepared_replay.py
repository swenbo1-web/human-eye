"""Restore existing source-region producer state without any host or raster calls."""

from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from zipfile import ZipFile


V = Path(__file__).resolve().parents[2]
TRUTH = V / 'm4_source_region_blocker_brief_001/checks/blocker_truth.py'
OVERLAYS = ('runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


@lru_cache
def frozen_capture():
    truth = run_path(str(TRUTH))
    run = truth['RUN']
    archive_path = run / 'ORIGINAL_RUNTIME.zip'
    index = json.loads(truth['INDEX'].read_bytes())
    require(sha256(archive_path.read_bytes()).hexdigest() == index['archive']['sha256'] == truth['ARCHIVE_SHA'],
            'frozen_source_archive_changed')
    with ZipFile(archive_path) as archive:
        evidence = truth['ArchivedRun'](run, index, archive)
        capture, meshes = truth['native_capture'](evidence)
        producer = evidence.document('product_full/call_004/SERVICE_RESULT.json')
        require(len(meshes) == 9 and sum(len(mesh[3]) for mesh in meshes) == 56
                and capture['capture_state'] == producer['binding']['capture_state'], 'source_capture_identity_changed')
        for item, (identity, name, points, faces) in zip(capture['meshes'], meshes, strict=True):
            require(item['object_id'] == identity and item['name'] == name, 'source_mesh_order_changed')
            item.pop('_scene_resource')
            item['vertices'] = [list(map(float, vertex)) for vertex in points]
            item['faces'] = faces
        return capture, list(evidence.checked.values())


def original_binding(binding):
    return {key: value for key, value in binding.items() if key not in OVERLAYS}


def original_observation(producer):
    value = {key: deepcopy(item) for key, item in producer.items()
             if key not in ('task_result', 'session_id', 'request_trace')}
    value['binding'] = original_binding(value['binding'])
    return value


def prepare(source_region, active_host, capture, request):
    query = request['params']['arguments']['query']
    binding = active_host.source_binding(capture)
    ordered_geometry = source_region.ordered_geometry_identity(capture, binding)
    display = source_region.display_state(capture, binding)
    selected = {'binding': binding, 'ordered_geometry_sha256': ordered_geometry,
                'display_identity': display['identity'], 'display_status': display['status']}
    prepared = source_region.prepare_region(capture, query, _binding=binding,
                                            _ordered_geometry_sha256=ordered_geometry)
    return prepared, selected


def register(context, capture, selected, prepared, observation):
    prepared.observation = observation
    if observation is not None and observation['frames']:
        prepared.images = SimpleNamespace(output_directory=Path(observation['frames'][0]['image_path']).parent)
    with context.lock:
        context.activate(capture, 'source_region', selected)
        context.prepared('source_regions', lambda: {
            'regions': {prepared.region_ref['region_id']: prepared}, 'aliases': {}})
    return prepared


def restore(source_region, active_host, context, request, producer, *, retained=None):
    capture = deepcopy(frozen_capture()[0])
    prepared, selected = prepare(source_region, active_host, capture, request)
    require(prepared.region_ref == producer['region_ref']
            and prepared.binding == original_binding(producer['binding'])
            and prepared.region_facts == producer['facts']['region']
            and len(prepared.meshes[2].faces) == 2 and len(prepared.meshes[8].faces) == 12,
            'restored_prepared_record_does_not_match_current_archived_producer')
    return register(context, capture, selected, prepared,
                    original_observation(producer if retained is None else retained))
