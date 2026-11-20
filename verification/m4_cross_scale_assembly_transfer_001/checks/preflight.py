"""Validate the fixed transfer harness using original evidence and no live calls."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import runpy
import sys


NS = Path(__file__).resolve().parents[1]
V = NS.parent
FORMAL = V / 'm4_cross_scale_live_task_formal_001'
FORMAL_RUN = Path('D:/he_m4_cross_scale_live_task_formal_001')
RECOVERY_RUN = Path('D:/he_m4_cross_scale_live_task_recovery_001')
ASSEMBLY = Path('D:/he_m4_assembly_evidence_consumption_001/slots/A1')
PRODUCT_SHA = 'ea93acca1a4ba0bcd527f9702657e9180bac05e2cb126e10474fb525b7fa1ca7'
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
SOURCE_SHA = '81c84f4d7273cd9045702c7afb95b9c8fc21b02764106ff9d8289c7120e0964c'


def require(test, reason):
    if not test:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def save(path, record):
    with path.open('x', encoding='utf8', newline='\n') as out:
        json.dump(record, out, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        out.write('\n')


class Pinned:
    def __init__(self):
        self.files = {}

    def file(self, path, sha=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        pin = {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}
        require(sha in (None, pin['sha256']) and self.files.get(path, pin) == pin, 'changed_source/' + str(path))
        self.files[path] = pin
        return raw

    def json(self, path, sha=None):
        return json.loads(self.file(path, sha))


def source_control(pins):
    source_path = ASSEMBLY / 'TERMINAL_SOURCE.json'
    packet = pins.json(source_path, SOURCE_SHA)
    source = packet['source']
    outcome_path = ASSEMBLY / 'SLOT_RESULT.json'
    outcome = pins.json(outcome_path)
    receipt = outcome['terminal_source']
    publication = pins.json(ASSEMBLY / 'SLOT_PUBLICATION.json')
    asset = ASSEMBLY / 'native/input.blend'
    pins.file(asset, ASSET_SHA)
    require(outcome['status'] == publication['status'] == 'failed' and
            publication['result_sha256'] == pins.files[outcome_path.resolve()]['sha256'] and
            receipt['status'] == 'complete' and receipt['terminal'] is True and
            Path(receipt['path']).resolve() == source_path.resolve() and
            receipt['sha256'] == receipt['worker']['sha256'] == SOURCE_SHA and
            receipt['bytes'] == receipt['worker']['bytes'] == pins.files[source_path.resolve()]['bytes'] and
            Path(source['asset_copy']).resolve() == asset.resolve() and source['asset_sha256'] == ASSET_SHA and
            source['pid'] == receipt['worker']['pid'], 'historical_publication_or_terminal_identity_changed')
    worker_path = Path(receipt['worker_path']).resolve()
    require(worker_path.is_relative_to(ASSEMBLY.resolve()), 'terminal_worker_source_outside_own_slot')
    pins.file(worker_path, SOURCE_SHA)
    meshes = packet['objects']
    offsets = [0]
    for mesh in meshes:
        offsets.append(offsets[-1] + len(mesh['evaluated']['triangles']))
    counts = {'objects': len(meshes), 'vertices': sum(len(row['evaluated']['vertices_world_m']) for row in meshes),
              'triangles': offsets[-1]}
    require(counts == {'objects': 28, 'vertices': 416, 'triangles': 744} and
            len({m['name'] for m in meshes}) == len(meshes) and
            offsets == packet['source_face_offsets'] and
            packet['display_object_mask'] == [item['visible_get'] for item in meshes] and
            int(source['frame']) == source['frame'] == 1 and source['scale_length'] == 1 and
            source['subframe'] == 0, 'terminal_roster_arrays_or_coordinate_binding_changed')
    return {'historical_slot': outcome['status'], 'terminal_capture': receipt['status'], 'counts': counts,
            'asset_sha256': ASSET_SHA, 'terminal_sha256': SOURCE_SHA, 'sample_frame': source['frame'],
            'historical_source_keys': sorted(packet)}


def product_control(pins, common):
    binding = pins.json(common.PRODUCT_BINDING)
    install = Path(binding['install_root']).resolve()
    require(binding['source_sha256'] == common.SOURCE_SHA == PRODUCT_SHA and
            binding['preparation_git'] == '21e608db565cf20d21fca735f913ae780e231470' and
            install == Path('D:/he_m4_cross_scale_cold_frustum_001/install/product').resolve(),
            'wrong_accepted_installed_product')
    sources = binding['source_manifest']
    require(len(sources) == len({row['path'] for row in sources}) == 143, 'installed_source_denominator_changed')
    for row in sources:
        source = (install / row['path']).resolve()
        require(source.is_relative_to(install), 'illegal_install_source_path')
        pins.file(source, row['sha256'])
    previous = V / 'm4_cross_scale_cold_frustum_001'
    archive = Path('D:/he_m4_cross_scale_cold_frustum_001/slots/B1/INSTALLED_TOOLS.json')
    archived_tools = pins.json(archive)
    controls = pins.json(previous / 'install/BUILD_INSTALL.json')
    require(controls['passed'] and controls['tool_schema_matches_historical_actual_directory'] and
            controls['binding'] == binding and archived_tools == pins.json(previous / 'install/TOOLS_SCHEMA.json'),
            'accepted_live_installed_tool_catalogue_changed')
    [tool] = [row for row in archived_tools if row['name'] == 'human_eye_scene_observe']
    require(tool == pins.json(NS / 'inputs/PRODUCT_SCHEMA.json'), 'new_observe_tool_schema_differs_from_actual_install')
    return binding, {'runtime_source_sha256': PRODUCT_SHA, 'verified_sources': len(sources),
                     'actual_previous_tool_count': len(archived_tools), 'observe_tool_schema_equal': True}


def runtime_control(pins, common):
    runtime_path = NS / 'harness/runtime.py'
    require(pins.file(runtime_path) == pins.file(FORMAL / 'harness/runtime.py'), 'runtime_source_drift')
    current = common.load('_transfer_preflight_runtime', runtime_path)
    public_scope = current.Runtime._start_public_mcp.__globals__
    require(public_scope['SOURCE_SHA'] == PRODUCT_SHA and
            Path(public_scope['NS']).resolve() == NS and
            Path(public_scope['HERE']).resolve() == NS / 'harness' and
            current.SLOTS == {'QN': ('N', 'qualification'), 'QP': ('P', 'qualification'),
                              'N1': ('N', 'formal'), 'P1': ('P', 'formal')},
            'bound_runtime_scope_differs')
    native = common.load('_transfer_preflight_native', common.GENERIC_WORKER)
    received = {}

    def generic_start(**kwargs):
        received.update(kwargs)
        return {}

    current.start_generic_native(generic_start, blender=common.BLENDER, asset=ASSEMBLY / 'native/input.blend',
        workspace=NS, deadline_ns=1, condition='P', expected_asset_sha256=ASSET_SHA)
    require(set(received) == {'blender', 'asset', 'workspace', 'deadline_ns', 'condition', 'expected_asset_sha256',
                             'max_calls'} and received['max_calls'] == 48 and
            received['expected_asset_sha256'] == ASSET_SHA and hasattr(native.NativeSession, 'start'),
            'generic_native_start_keyword_or_limit_changed')
    for dependency in (common.GENERIC_WORKER, current.PREVIOUS, common.DISPLAY / 'harness/reused/stdio_checks.py',
                       common.PRIOR / 'harness/reused/verified_bootstrap.py', NS / 'harness/common.py',
                       NS / 'harness/budget.py', NS / 'harness/mcp_entry.py'):
        pins.file(dependency)
    return {'method_is_bound_to_new_product_and_namespace': True, 'generic_native_start_keys': sorted(received),
            'slots': {label: list(pair) for label, pair in current.SLOTS.items()}}


def argv_control(pins, scope, proof, temporary):
    result = {}
    # The two versions must match before spawning, modulo paths scoped to
    # this workspace and its thin transport. Do not run the CLI to do this.
    def normalize(args, slot, thin):
        for original, token in ((str(slot.resolve()), '<slot>'), (str(thin.resolve()), '<thin>')):
            escaped = original.replace('\\', '\\\\')
            args = [part.replace(escaped, token).replace(original, token) for part in args]
        return args

    actual_tools = proof['actual_tools_by_group']
    for label, group in [('N1', 'N'), ('P1', 'P')]:
        slot = temporary / label
        (slot / 'consumer').mkdir(parents=True)
        (slot / 'workspace').mkdir()
        cell = slot / 'consumer/cell.json'
        save(cell, {'endpoint': str(slot / 'ENDPOINT.json')})
        argv = scope['initial_argv'](proof['Python_path'], cell, slot / 'workspace',
                                     slot / 'consumer/final.txt', group)
        historical_slot = FORMAL_RUN / 'slots' / label
        historical = pins.json(historical_slot / 'consumer/ACTUAL_CONFIGURATION.json')
        expected = normalize(historical['requested_cli_overrides_and_argv'], historical_slot, FORMAL / 'thin_stdio.py')
        actual = normalize(argv, slot, NS / 'thin_stdio.py')
        require(actual == expected and len(list((slot / 'workspace').iterdir())) == 0,
                'isolated_CLI_launch_arguments_differ/' + label)
        result[label] = {'argv_matches_historical_after_path_substitution': True,
                         'normalized_argv_sha256': digest(json.dumps(actual, ensure_ascii=True).encode()),
                         'actual_tools': actual_tools[group], 'fresh_workspace_before_launch': True}
    require(set(actual_tools['P']) - set(actual_tools['N']) == {'human_eye_scene_observe'}
            and set(actual_tools['N']) < set(actual_tools['P']), 'ordinary_tool_parity_changed')
    return result


def archived_replays(pins, scope, work):
    work.mkdir()
    path = FORMAL / 'harness/preflight_formal_events.py'
    pins.file(path)
    replay = runpy.run_path(str(path))['replay']
    typed_path = FORMAL / 'checks/typed_diagnostic.py'
    pins.file(typed_path)
    pins.file(V / 'm4_cross_scale_live_qualification_001/checks/delivery.py')
    verify = runpy.run_path(str(typed_path))['verify_content']
    cases = {}
    for kind, label in (('ordinary', 'QN'), ('product', 'QP')):
        slot = RECOVERY_RUN / 'slots' / label
        cases[kind] = replay(work, kind, slot, scope)
        response = pins.json(slot / 'owner/tool_01/RESPONSE.json')
        method = 'ordinary' if kind == 'ordinary' else 'active_region_task'
        _, texts, images = verify(response, contract=method, fact_index=0)
        blocks = response['result']['content']
        swapped = copy.deepcopy(response)
        if kind == 'ordinary':
            # Exchange the real caption/image pairs in one controlled mismatch.
            control = swapped['result']['content']
            control[1]['text'], control[3]['text'] = control[3]['text'], control[1]['text']
        else:
            control = swapped['result']['content']
            control[1], control[2] = control[2], control[1]
        expected = {row['ref']: raw for row, raw in images}
        try:
            verify(swapped, contract=method, fact_index=0, expected_png=expected)
        except ValueError as error:
            rejected = str(error)
            require(rejected in {'image_bytes_do_not_match_bound_ref', 'product_image_sha256_or_order_changed'},
                    'typed_negative_control_failed_for_other_reason/' + kind)
        else:
            raise ValueError('typed_negative_control_accepted/' + kind)
        image_positions = [idx for idx, row in enumerate(blocks) if row['type'] == 'image']
        require(image_positions == [image[0]['content_index'] for image in images],
                'original_mixed_wire_positions_changed')
        cases[kind]['typed_delivery'] = {'texts': [{k: item[k] for k in ('content_index', 'type', 'UTF8_bytes')}
                                                  for item in texts],
                                          'ordered_images': [image[0] for image in images],
                                          'mismatch_rejected': rejected}

    consumer = ASSEMBLY / 'consumer/CONSUMER.json'
    error_events = [row for row in pins.json(consumer)['tool_calls']
                    if row['item'].get('tool') == 'human_eye_scene_observe' and row['item'].get('status') == 'failed']
    require(len(error_events) == 1, 'unique_real_previous_CLI_error_unavailable')
    cases['normal_error'] = replay(work, 'normal_error', ASSEMBLY, scope, raw_event=error_events[0])
    for entry in cases.values():
        for pin in entry['original_wire_pins']:
            pins.file(pin['path'], pin['sha256'])
    return cases


def main(runtime):
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_fixed_python_I_B')
    sys.path.insert(0, str(NS / 'harness'))
    import common

    require(runtime == common.EXTERNAL.resolve(), 'unregistered_transfer_runtime')
    work = runtime / 'preflight/harness_checks'
    work.mkdir(parents=True, exist_ok=False)
    pins = Pinned()
    source = source_control(pins)
    binding, product = product_control(pins, common)
    shared = pins.json(V / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json')
    sys.path[:0] = [str(NS), binding['dependency_root'], shared['dependency_root']]
    runtime_proof = runtime_control(pins, common)
    from consumer import consumer_adapter

    consume, proof, _ = consumer_adapter()
    require((proof['CLI_version'], proof['model'], proof['reasoning_effort'], proof['service_tier']) ==
            ('0.152.1', 'gpt-6.1-sol', 'medium', 'default') and proof['fresh_ephemeral'] and
            proof['business_tool_attempt_limit'] == 12, 'historical_registered_cli_scope_changed')
    pins.file(proof['CLI_path'], proof['CLI_sha256'])
    pins.file(proof['Python_path'], proof['Python_sha256'])
    for source_pin in proof['execution_sources']:
        pins.file(source_pin['path'], source_pin['sha256'])
    argv = argv_control(pins, consume.__globals__, proof, work / 'argv')
    cases = archived_replays(pins, consume.__globals__, work / 'replays')
    pins.file(Path(__file__))
    record = {'passed': True, 'actual_model_runs': 0, 'actual_Blender_processes': 0, 'actual_raster': 0,
              'source': source, 'product': product, 'runtime': runtime_proof, 'argv': argv, 'replays': cases,
              'source_pins': [pins.files[path] for path in sorted(pins.files)]}
    output = NS / 'checks/HARNESS_PREFLIGHT.json'
    save(output, record)
    print(output, digest(output.read_bytes()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    main(parser.parse_args().runtime.resolve())
