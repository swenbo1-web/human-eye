"""Requalify only the two historical replies offline under the repaired archive contract."""

import argparse
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import zipfile


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from typed_diagnostic import IMAGE_CHECK, digest, inspect_images, require, verify_content


NS = HERE.parent
ROOT = NS.parents[1]
OLD = ROOT / 'verification/m4_cross_scale_live_task_recovery_001'
ORIGINAL = Path('D:/he_m4_cross_scale_live_task_recovery_001')
FORMAL = Path('D:/he_m4_cross_scale_live_task_formal_001')
SOURCE = '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b'
ASSET = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
ORIGINS = {
    'FROZEN.json': 'dc10bc7ed44e5b3afe8a329cbe3ee031fba957954c828b4c8463f390293fd883',
    'QUALIFICATION.json': '8d15434785b3da2fda42bc48f71147efba331260b4284c1ee606054a103a2560',
    'RUNTIME_INDEX.json': 'b4d71c248243f7b224f837b98395c25337b1792cda2d937ccef7bf251dba62c9',
    'scoring/QUALITY.json': '48c3558e24500c68cbf1719bb0743266f04284e7c631eab449884fe3d1fe34d3',
    'qualify.py': '7c3cf71c854a18173c37f89d83e0a93806c62db8a07da4554d56ff436a1a76ba',
    'scoring/formal.py': '789ea8a7913d7c40ce1ecb0c9c27fbc1b5fef9aa03152dcf04bfefb54c3ce2cd',
    'CONTENT_MANIFEST.json': '0317d85d5de748a11b220b41da745878810ec4ebd1e46b37612db32067ea651f',
    'fixture/CURRENT_TRUTH.json': '376a31b5a5cfc0e979f6b43d43756d9837dbfae9c53b96c77f46cc329b2ba922',
    'checks/ORDINARY_DELIVERY_REPLAY.json': 'dfb664893c7c84e83b582ab5b7a7e757deaa8c14aa49a1dd0aa76025a4f9de1d',
}


def read(path):
    return json.loads(Path(path).read_bytes())


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Pins:
    def __init__(self):
        self.rows = {}

    def check(self, path, sha=None, size=None, parent=None):
        path = Path(path).resolve(strict=True)
        require(parent is None or path.is_relative_to(parent.resolve()), 'input_path_outside_registered_root')
        raw = path.read_bytes()
        actual = {'path': str(path), 'sha256': digest(raw), 'bytes': len(raw)}
        require((sha is None or actual['sha256'] == sha) and (size is None or len(raw) == size),
                'source_pin_changed/' + str(path))
        require(self.rows.setdefault(path, actual) == actual, 'same_source_pin_changed/' + str(path))
        return raw


def verify_originals(pins):
    for name, sha in ORIGINS.items():
        pins.check(OLD / name, sha)
    archive_index = read(OLD / 'RUNTIME_INDEX.json')
    archive = archive_index['archive']
    archived_bytes = pins.check(archive['path'], archive['sha256'], archive['bytes'], ORIGINAL)
    with zipfile.ZipFile(io.BytesIO(archived_bytes)) as bundle:
        rows = archive_index['files']
        require(len(rows) == archive_index['count'] and bundle.namelist() == [row['path'] for row in rows],
                'historical_runtime_archive_members_changed')
        for row in rows:
            actual = pins.check(ORIGINAL / row['path'], row['sha256'], row['bytes'], ORIGINAL)
            require(bundle.read(row['path']) == actual, 'historical_runtime_original_differs_from_zip')
    for row in read(OLD / 'FROZEN.json')['direct_inputs']:
        pins.check(row['path'], row['sha256'], row['bytes'])
    gate = read(OLD / 'QUALIFICATION.json')
    require(gate['passed'] is False and gate['freeze_sha256'] == ORIGINS['FROZEN.json'] and
            [(row['label'], row['original_status'], row['passed']) for row in gate['slots']] ==
            [('QN', 'failed', False), ('QP', 'completed', True)], 'old_qualification_outcome_changed')
    require(not any((ORIGINAL / 'slots' / label).exists() for label in ('N1', 'P1')),
            'old_formal_slots_are_still_unrun_required')
    return gate


def same_original_wires(slot, original, response, request):
    rpc = slot / 'client/transport/rpc_04'
    owner = slot / 'owner/tool_01'
    thin, = list((slot / 'client/attachments').glob('bridge_*/004'))
    exact = {}
    for direction, name, structured in (('TX', 'REQUEST.json', request), ('RX', 'RESPONSE.json', response)):
        raw = (rpc / (direction + '.bin')).read_bytes()
        require((thin / (direction + '.bin')).read_bytes() == (owner / name).read_bytes() == raw and
                json.loads(raw) == structured, 'original_owner_thin_and_diagnostic_wire_differ/' + direction)
        exact[direction] = {'sha256': digest(raw), 'bytes': len(raw)}
    client_receipt = read(rpc / 'RECEIPT.json')
    wire_receipt = read(thin / 'RECEIPT.json')
    owner_receipt = read(owner / 'RECEIPT.json')
    require(exact['RX']['sha256'] == client_receipt['RX_sha256'] and not client_receipt['error'] and
            exact['RX']['bytes'] == client_receipt['RX_bytes'] == wire_receipt['response_bytes'] == owner_receipt['response_bytes'] and
            exact['TX']['bytes'] == client_receipt['TX_bytes'] == wire_receipt['request_bytes'] and wire_receipt['origin'] == 'owner' and
            request['id'] == response['id'] == owner_receipt['RPC_id'] == wire_receipt['RPC_id'] == client_receipt['id'] and
            original['slot'] in ('QN', 'QP') and owner_receipt['status'] == 'returned' and owner_receipt['is_error'] is False,
            'original_transport_receipt_identity_unbound')
    return exact, owner_receipt


def actual_frame_bytes(slot):
    import numpy as np
    from PIL import Image
    rows = read(slot / 'DEVICE_EVIDENCE.json')['frames']
    frames = {}
    for row in rows:
        png, npz = (Path(row[key]).resolve(strict=True) for key in ('PNG', 'NPZ'))
        require(png.is_relative_to(slot.resolve()) and npz.is_relative_to(slot.resolve()), 'frame_outside_original_slot')
        raw, archive = png.read_bytes(), npz.read_bytes()
        require((len(raw), digest(raw)) == (row['PNG_bytes'], row['PNG_sha256']) and
                (len(archive), digest(archive)) == (row['NPZ_bytes'], row['NPZ_sha256']), 'frame_artifact_identity_mismatch')
        with np.load(io.BytesIO(archive), allow_pickle=False) as arrays, Image.open(io.BytesIO(raw)) as image:
            require(image.format == 'PNG' and image.mode == 'RGB' and image.size == (512, 512) and
                    np.array_equal(np.asarray(image), arrays['color']) and arrays['owners'].shape == (512, 512) and
                    arrays['triangle_ids'].shape == (512, 512) and arrays['depth'].shape == (512, 512),
                    'original_PNG_NPZ_and_pixel_owner_contract_mismatch')
        require(row['ref'] not in frames and row['pose']['direction_rational'] == row['direction_rational'],
                'frame_identity_or_direction_unbound')
        frames[row['ref']] = raw
    return frames


def check_installed(slot, diagnostic_request, diagnostic_response):
    identity = read(slot / 'MCP_IDENTITY.json')
    require(identity['source_sha256'] == SOURCE and identity['source_file_count'] == 143 and
            identity['source_kind'] == 'installed_distribution', 'actual_plugin_installed_source_unbound')
    one, = [json.loads(line) for line in (slot / 'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines()]
    owner = slot / 'owner/tool_01'
    rpc = slot / 'mcp' / f"rpc_{one['receipt']['index']:02d}"
    tx, rx = ((rpc / (direction + '.bin')).read_bytes() for direction in ('TX', 'RX'))
    require(json.loads(tx) == read(owner / 'PRODUCT_REQUEST.json') == one['request'] and
            json.loads(rx) == read(owner / 'PRODUCT_RESPONSE.json') == one['response'] and
            read(rpc / 'RECEIPT.json') == one['receipt'] and digest(rx) == one['receipt']['RX_sha256'] and
            diagnostic_request['params'] == one['request']['params'] and
            diagnostic_response['result'] == one['response']['result'], 'installed_product_RPC_did_not_match_actual_diagnostic')
    return {'source_sha256': identity['source_sha256'], 'source_file_count': identity['source_file_count'],
            'TX_sha256': digest(tx), 'RX_sha256': digest(rx), 'TX_bytes': len(tx), 'RX_bytes': len(rx)}


def replay_slot(label, qualification, qualify, scoring, truth, output):
    slot = ORIGINAL / 'slots' / label
    result_path = slot / 'SLOT_RESULT.json'
    original = read(result_path)
    public = read(slot / 'SLOT_PUBLICATION.json')
    result_sha = digest(result_path.read_bytes())
    require(public['result_sha256'] == result_sha == qualification['result_sha256'] and
            public['status'] == original['status'] == qualification['original_status'] and
            original['freeze_sha256'] == ORIGINS['FROZEN.json'] and not original['actual_model_admitted'] and
            original['model_consumers'] == 0 and original['paid_API_calls'] == 0 and
            original['closure_verification']['passed'] and original['independent_before_after']['passed'] and
            original['diagnostic_close']['confirmed'] and original['owner_close']['confirmed'],
            'historical_worker_result_geometry_or_cleanup_unbound')
    response_path = slot / 'client/call_01/RESPONSE.json'
    request_path = response_path.with_name('REQUEST.json')
    response, request = read(response_path), read(request_path)
    entry, = original['diagnostic_calls']
    response_sha = digest(response_path.read_bytes())
    require(entry['request_sha256'] == digest(request_path.read_bytes()) and entry['response_sha256'] == response_sha and
            entry['tool_error'] is False, 'historical_diagnostic_original_unbound')
    wires, owner = same_original_wires(slot, original, response, request)
    output_bytes = actual_frame_bytes(slot)
    terminal, detailed_guard = scoring.terminal(slot, original, ASSET)
    require(len(terminal['objects']) == detailed_guard['verified_object_count'] == 21, 'clinical_complete_geometry_binding_required')
    readbacks = qualify.readbacks(slot, original)
    model_content = response['result']
    if label == 'QN':
        require(request['params'] == read(OLD / 'inputs/DIAGNOSTIC_N.json')['calls'][0], 'historical_native_diagnostic_arguments_changed')
        errors = original['errors']
        require(len(errors) == 1 and errors[0]['type'] == 'JSONDecodeError' and
                errors[0]['stage'] == 'qualification' and 'transport.inspect_images' in errors[0]['traceback'] and
                'reused/stdio_checks.py' in errors[0]['traceback'].replace('\\', '/'), 'original_native_sole_archive_fault_required')
        evidence = qualify.native(slot, truth, model_content)
        refs = [row['ref'] for row in evidence['regions'].values() if row['status'] == 'covered']
        require([r['ref'] for r in owner['image_attachments']] == refs and
                all(r['delivery_ready'] and r['PNG_sha256'] == digest(output_bytes[r['ref']])
                    for r in owner['image_attachments']), 'ordinary_attachment_context_and_ref_changed')
        profile = {'contract': 'ordinary', 'fact_index': 0, 'expected_refs': refs, 'expected_png': output_bytes}
        content = response['result']['content']
        fault_index = next(i for i, row in enumerate(content) if row['type'] == 'text' and row['text'].startswith('native-image:'))
        try:
            json.loads(content[fault_index]['text'])
        except json.JSONDecodeError as error:
            require(str(error) == errors[0]['message'], 'original_decode_failure_not_exactly_reproduced')
        else:
            raise ValueError('original_plain_caption_did_not_reproduce_failure')
        installed = None
    else:
        require(request['params']['name'] == 'human_eye_scene_observe' and not original['errors'], 'expected_original_product_success')
        installed = check_installed(slot, request, response)
        evidence = qualify.product(slot, truth, model_content)
        require(evidence == qualification['evidence'], 'new_product_replay_differs_from_frozen_actual_qualification')
        profile = {'contract': 'active_region_task', 'fact_index': 0, 'expected_png': output_bytes}
        fault_index = None
    require(evidence['CLI']['passed'] and evidence['regions']['M09'].get('direction', evidence['regions']['M09'].get('view'))
            in ('LEFT', 'BACK') and evidence['regions']['M06']['status'] == 'unknown', 'geometry_rotation_unknown_or_CLI_not_revalidated')
    archive = inspect_images(response, output / label, **profile)
    require([row['PNG_bytes'] for row in archive['images']] == evidence['image_bytes'] and
            archive['PNG_bytes'] == owner['content_metrics']['PNG_bytes'] and
            sum(row['UTF8_bytes'] for row in archive['text_blocks']) == owner['content_metrics']['text_UTF8_bytes'],
            'corrected_archive_no_longer_matches_actual_delivery_sizes')
    return {'label': label, 'passed': True, 'original_status': original['status'], 'result_sha256': result_sha,
            'response_sha256': response_sha, 'response_path': str(response_path), 'result_path': str(result_path),
            'original_caption_fault_content_index': fault_index, 'owner_thin_client_original_wire': wires,
            'installed_product_wire': installed, 'before_after': readbacks, 'closure': detailed_guard,
            'geometry_passed': True, 'CLI_preservation_passed': True, 'evidence': evidence,
            'corrected_archive_path': str(output / label / 'READBACK.json'),
            'corrected_archive_sha256': digest((output / label / 'READBACK.json').read_bytes())}, response, profile


def controls(native, product):
    results = []

    def rejected(name, item, mutate, reason):
        source, profile = item
        changed = copy.deepcopy(source)
        mutate(changed['result']['content'])
        try:
            verify_content(changed, **profile)
        except (ValueError, OSError, KeyError) as error:
            require(reason in str(error), 'negative_failed_for_another_reason/' + name + '/' + str(error))
            results.append({'name': name, 'passed': True, 'observed': str(error)})
        else:
            raise ValueError('negative_control_accepted/' + name)

    rejected('native_bad_caption', native, lambda c: c[1].update(text='unbound caption'), 'caption_required')
    rejected('native_ref_mismatch', native, lambda c: c[1].update(text=c[3]['text']), 'bound_ref')
    rejected('native_wrong_PNG_for_caption', native, lambda c: c[2].update(data=c[4]['data']), 'bound_ref')
    rejected('native_missing_image', native, lambda c: c.pop(), 'orphan_image_caption')
    rejected('native_full_image_pair_order_swap', native, lambda c: c.__setitem__(slice(1, 5), c[3:5] + c[1:3]), 'reference_order')
    rejected('native_invalid_fact_JSON', native, lambda c: c[0].update(text='{bad'), 'invalid_JSON')
    rejected('product_PNG_order_swap', product, lambda c: c[1].update(data=c[2]['data']), 'product_image_sha256')
    rejected('product_invalid_fact_JSON', product, lambda c: c[0].update(text='{bad'), 'invalid_JSON')
    rejected('product_unregistered_caption', product, lambda c: c.insert(1, {'type': 'text', 'text': 'caption'}), 'single_product_fact')
    ordinary = {'result': {'isError': False, 'content': [{'type': 'text', 'text': item}
                 for item in ('first plain text', '{"ordinary":"opaque"}', 'last plain text')]}}
    original = copy.deepcopy(ordinary)
    fact, text, images = verify_content(ordinary)
    require(ordinary == original and fact is None and not images and
            [item['text'] for item in text] == [item['text'] for item in ordinary['result']['content']],
            'normal_multiple_text_blocks_were_reparsed_or_changed')
    results.append({'name': 'ordinary_no_image_multi_text_keeps_original_order', 'passed': True})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-output', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=HERE / 'OFFLINE_EVIDENCE.json')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_pinned_python_I_B')
    require(args.archive_output.resolve().is_relative_to(FORMAL.resolve()) and
            args.output.resolve().is_relative_to(NS.resolve()), 'new_formal_archive_paths_required')
    started = time.perf_counter_ns()
    pins = Pins()
    gate = verify_originals(pins)
    for source in (Path(__file__), HERE / 'typed_diagnostic.py', IMAGE_CHECK):
        pins.check(source)
    qualify = load('_actual_recovery_qualification', OLD / 'qualify.py')
    scoring = load('_actual_recovery_formal_scoring', OLD / 'scoring/formal.py')
    sys.path.insert(0, read(qualify.BINDING)['dependency_root'])
    truth = {row['object_name']: row for row in scoring.truth()['eligible']}
    results = [replay_slot(row['label'], row, qualify, scoring, truth, args.archive_output) for row in gate['slots']]
    negatives = controls(*(row[1:] for row in results))
    for row, _, _ in results:
        pins.check(row['corrected_archive_path'], row['corrected_archive_sha256'], parent=FORMAL)
        for image in read(row['corrected_archive_path'])['images']:
            pins.check(image['path'], image['PNG_sha256'], image['PNG_bytes'], FORMAL)
    receipt = {'schema': 'm4-cross-scale-formal-typed-archive-offline-evidence-v1', 'passed': True,
               'original_freeze_sha256': ORIGINS['FROZEN.json'], 'original_qualification_sha256': ORIGINS['QUALIFICATION.json'],
               'original_qualification_passed': False, 'original_formal_slots': {'N1': 'unrun', 'P1': 'unrun'},
               'original_archive_sha256': read(OLD / 'RUNTIME_INDEX.json')['archive']['sha256'],
               'slots': [row[0] for row in results], 'geometry_arms_passed': True, 'CLI_preservation_passed': True,
               'negative_controls_passed': True, 'controls': negatives, 'source_pins': list(pins.rows.values()),
               'started_ns': started, 'closed_ns': time.perf_counter_ns(), 'new_Blender_starts': 0,
               'new_raster_attempts': 0, 'new_model_consumers': 0}
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(receipt, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
    print('Offline derived admission evidence passed', len(receipt['source_pins']), 'pins', len(negatives), 'controls')


if __name__ == '__main__':
    main()
