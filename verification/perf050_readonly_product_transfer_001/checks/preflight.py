"""Verify the two image routes and both product task schemas without a live slot."""

import base64
import json
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile


sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import (F, HERE, INSTALL_PATH, LEGACY, NS, ORACLE, PIXELS, REGION_QUERY, SET, TERMINAL, V, checked,
                      frame_geometry, library, measure_body, pin, read, same_geometry)


OLD_FORMAL = V / 'm4_cross_scale_live_task_formal_001'
OLD_RECOVERY = V / 'm4_cross_scale_live_task_recovery_001'
DECODE = V / 'm4_cross_scale_discovery_001/oracle/check_saved.py'
HISTORICAL_INSTALL = V / 'm4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'


class Sealed:
    def __init__(self, index, expected):
        self.source = [pin(index)]
        record = read(index)
        archive = Path(record['archive']['path'])
        bound = pin(archive)
        checked(bound['sha256'] == record['archive']['sha256'] == expected
                and bound['bytes'] == record['archive']['bytes'], 'historical_runtime_zip_changed')
        self.source.append(bound)
        self.root = archive.parent.resolve()
        self.index = {row['path']: row for row in record['files']}
        self.zip = ZipFile(archive)
        checked(set(self.zip.namelist()) == self.index.keys(), 'historical_runtime_files_changed')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.zip.close()

    def member(self, path, expected=None):
        path = Path(path).resolve()
        row = self.index[path.relative_to(self.root).as_posix()]
        actual = pin(path)
        data = path.read_bytes()
        checked(actual['sha256'] == row['sha256'] and actual['bytes'] == row['bytes']
                and (expected is None or actual['sha256'] == expected) and self.zip.read(row['path']) == data,
                'archived_original_changed/' + row['path'])
        self.source.append(actual)
        return data

    def read(self, path, digest=None, within=None):
        checked(within is None or Path(path).resolve().is_relative_to(Path(within).resolve()), 'wrong_source_namespace')
        return json.loads(self.member(path, digest))

    check = staticmethod(checked)


def original_frame(archive, slot, expected_origin):
    evidence = archive.read(slot / 'DEVICE_EVIDENCE.json')
    terminal = archive.read(slot / 'TERMINAL_SOURCE.json', evidence['terminal_source']['sha256'])
    same_geometry(None, terminal)
    row, = [r for r in evidence['frames'] if r['origin'] == expected_origin and r['view'] == 'LEFT'
            and r['pose']['target_world_m'][0] == -2]
    png = archive.member(row['PNG'], row['PNG_sha256'])
    arrays = archive.member(row['NPZ'], row['NPZ_sha256'])
    proof = frame_geometry(row, terminal, png, arrays, read(NS / 'truth/TRUTH.json'))
    checked(evidence['asset_sha256'] == ORACLE['ASSET_SHA'] and proof['qualifies'], 'old_real_frame_not_a_complete_witness')
    closed = archive.read(slot / 'SLOT_RESULT.json')['closure_verification']
    checked(closed['passed'] and closed['status'] == 'ready_closed', 'prior_real_frame_without_real_close')
    return {'frame': row['ref'], 'PNG': pin(Path(row['PNG'])), 'NPZ': pin(Path(row['NPZ'])),
            'closure': closed, 'view': proof}


def candidate(capture):
    from human_eye_plugin.live_spatial_mcp import _tool_result
    from human_eye_plugin.live_service import _validated_scene
    from human_eye_plugin.scene_cache import SpatialSceneCache
    from human_eye_plugin.source_region import measure_region, observe_region, prepare_region
    from human_eye_plugin.task_query import task_result, validate_task_query

    prepared = prepare_region(capture, REGION_QUERY)
    with TemporaryDirectory(prefix='human_eye_transfer_source_') as root:
        image_root = Path(root).resolve()
        views = []
        result = observe_region(prepared, image_root / ('0' * 32), include_image=True,
                                construction_callback=views.append)
        install = read(INSTALL_PATH)
        status = {'source_status': 'verified', 'disk_status': 'verified',
                  'source_check_scope': 'offline_replay_current_capture', 'runtime_source_sha256': install['source_sha256']}
        result['binding'].update(status)
        result['session_id'] = 'mcp-00000000-0000-0000-0000-000000000000'
        result['task_result'] = measure_region(prepared, REGION_QUERY['reference'], None)
        result['task_result']['binding'].update(status)
        public = _tool_result(result, is_error=False, response_detail='brief', source_region_image_root=image_root)
        text, png = public['content']
        parsed = json.loads(text['text'])
        frame, = result['frames']
        metrics = PIXELS['frame_metrics'](frame, result)
        image, = parsed['images']
        source = parsed['region_ref']
        checked(not public['isError'] and metrics['view_name'] in ('LEFT', 'BACK') and
                metrics['corners_inside_clip'] and metrics['visible_source_ids'] == [0, 1] and
                (metrics['surface'], metrics['contrast']) == (146797, 1530) and
                source['source_triangle_indices'] == [0, 1] and image['image_block_index'] == 1 and
                png['mimeType'] == 'image/png' and
                Path(image['local_image_path']).read_bytes() == base64.b64decode(png['data'], validate=True) and
                image['image_sha256'] == metrics['PNG_sha256'], 'actual_installed_candidate_image_route_failed')
        cli = PIXELS['replay_cli'](public)
        checked(cli['passed'], 'actual_installed_candidate_source_region_brief_not_preserved')
        image_route = {'views_constructed': views, 'schema': parsed['schema'], 'PNG_sha256': metrics['PNG_sha256'],
                       'surface_pixels': metrics['surface'], 'contrasting_boundary_pixels': metrics['contrast'],
                       'reference_binds_actual_png': True, 'CLI_replay': cli}

    scene, meshes, fingerprint = _validated_scene(capture)
    source = same_geometry(capture, read(TERMINAL))
    measured = []
    for query in (LEGACY, SET):
        canonical = validate_task_query(query)
        proof = task_result(scene, meshes, fingerprint, canonical, SpatialSceneCache(), lambda _: None)
        if query is SET:
            checked(proof['pairs'][0]['facts']['spatial_relation']['value'] == 'separated',
                    'registered_task_set_did_not_confirm_separation')
        wire = _tool_result(proof, is_error=False, response_detail='brief')
        checked(wire['isError'] is False and len(wire['content']) == 1, 'whole_task_query_envelope_not_text')
        measured.append(measure_body(json.loads(wire['content'][0]['text']), source))
    return {'image': image_route, 'whole_measurement_entries': measured}


def qualify():
    install = library(product=True)
    checked(install['preparation_git'] == '470a36f111cd5e96845569c258f464d4bbcf2824' and
            install['source_sha256'] == '5b2e2ff21b068936b8ab951be585272d9b871a896d7a0a882dfed020896298c7'
            and len(install['source_manifest']) == 143, 'candidate_not_frozen_product')
    decode = runpy.run_path(str(DECODE))
    with Sealed(OLD_FORMAL / 'RUNTIME_INDEX.json',
                '38be66d67b301524de5594acab12158342da7c31e2aa75629109e2fe4ff8a89d') as archive:
        slot = archive.root / 'slots/P1'
        producer = archive.read(slot / 'product_full/call_001/SERVICE_RESULT.json')
        captures, commands = decode['decode_captures'](slot, read(HISTORICAL_INSTALL), archive)
        capture = decode['current_capture'](captures, producer['binding'], archive)
        checked(len(capture['meshes']) == 21, 'replay_capture_does_not_cover_source')
        same_geometry(capture, read(TERMINAL))
        orig_product = original_frame(archive, slot, 'product')
        pins = list(archive.source)

    with Sealed(OLD_RECOVERY / 'RUNTIME_INDEX.json',
                '721a454beadcb5104a6866b50e05f9e7f3335da57767cb6119d4888fbb14bf65') as archive:
        native = original_frame(archive, archive.root / 'slots/QN', 'common_native')
        pins.extend(archive.source)
    for path in (INSTALL_PATH, HISTORICAL_INSTALL, DECODE, NS / 'truth/TRUTH.json', Path(__file__),
                 HERE / 'evidence.py', OLD_FORMAL / 'scoring/formal.py'):
        pins.append(pin(path))
    replay = candidate(capture)
    return {'schema': 'perf050-readonly-product-transfer-source-preflight-v1', 'passed': True,
            'source_pins': list({row['path']: row for row in pins}.values()), 'native_original': native,
            'prior_product_original': orig_product, 'actual_installed_product_offline_replay': replay,
            'native_whole_mesh_independent_exact_proof': ORACLE['compute']()['measurement'],
            'current_common_path_contract': 'see harness/HOST_PREFLIGHT.json',
            'new_blender_launches': 0, 'new_model_launches': 0, 'archived_native_commands': len(commands)}


if __name__ == '__main__':
    value = qualify()
    ORACLE['write'](HERE / 'PREFLIGHT.json', value)
    print(json.dumps({'passed': value['passed'], 'native_view': value['native_original']['view']['camera'],
                      'product_view': value['actual_installed_product_offline_replay']['image']['views_constructed']}))
