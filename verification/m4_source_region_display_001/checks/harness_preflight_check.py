"""Offline fixture protocol and admission checks with synthetic in-memory state."""

import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent / 'harness'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def review():
    checks = []
    pins = []

    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    def rejects(action, name):
        try:
            action()
        except (ValueError, RuntimeError, FileExistsError):
            checks.append(name)
        else:
            raise AssertionError(name)

    trees = {}
    for path in sorted(HARNESS.rglob('*.py')):
        raw = path.read_bytes()
        trees[path.name] = ast.parse(raw, filename=str(path))
        pins.append(dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    check(bool(trees), 'all_harness_python_parsed')
    native = load('_display_preflight_native', HARNESS / 'state_owned_native.py')
    budget_module = load('_display_preflight_budget', HARNESS / 'budget.py')
    runner = load('_display_preflight_runner', HARNESS / 'run_slot.py')
    check(budget_module.LIMITS == dict(Blender_start_attempts=2, all_rasters=8,
          consumer_tasks=0, rasters_by_slot=dict(main=1, state=7)), 'fixed_budget_limits')
    with tempfile.TemporaryDirectory(prefix='m4-display-budget-') as temporary:
        budget = budget_module.Budget(temporary)
        budget.reserve('Blender_start', 'main')
        budget.reserve('Blender_start', 'state')
        rejects(lambda: budget.reserve('Blender_start', 'state'), 'third_owned_attempt_rejected')
        rejects(lambda: budget.reserve('consumer_task', 'main'), 'model_consumer_rejected')
        rejects(lambda: budget.reserve('raster_attempt', 'other'), 'unregistered_raster_slot_rejected')
        budget.reserve('raster_attempt', 'main')
        rejects(lambda: budget.reserve('raster_attempt', 'main'), 'second_main_raster_rejected')
        for _ in range(7):
            budget.reserve('raster_attempt', 'state')
        rejects(lambda: budget.reserve('raster_attempt', 'state'), 'ninth_total_raster_rejected')
        reopened = budget_module.Budget(temporary).snapshot()['counts']
        check(reopened['all_raster_upper'] == 8 and reopened['pending_raster_reservations'] == 8
              and reopened['Blender_start_attempts'] == 2, 'unresolved_admissions_retained_after_reopen')

    selection = dict(object=native.DISPLAY_TARGET, source_triangle_ids=[8, 2, 7])
    actual_public_ref = dict(region_id='synthetic-returned-public-reference', capture_generation='opaque-generation')
    arguments = runner.arguments(selection)
    check(arguments['query']['region']['source_triangle_indices'] == [2, 7, 8]
          and arguments['query']['reference'] == {'name': 'Cube'}
          and arguments['include_image'] is True, 'fresh_request_uses_fixed_source_selection_and_Cube')
    repeated = runner.arguments(selection, actual_public_ref, full=True)
    check(repeated['query']['region_ref'] == actual_public_ref
          and 'region' not in repeated['query'] and repeated['response_detail'] == 'full',
          'repeat_passes_returned_public_ref_without_generation_assumptions')
    repeated['query']['region_ref']['region_id'] = 'changed-local-copy'
    check(actual_public_ref['region_id'] == 'synthetic-returned-public-reference', 'public_ref_is_copied')

    flag_defaults = dict(hide_viewport=False, hide_select=False, display_type='TEXTURED',
                         show_in_front=False, show_instancer_for_viewport=True,
                         show_instancer_for_render=True, materials=[], collections=['Collection'], parent=None,
                         type='MESH')
    initial = dict(objects=[], view_layer=dict(name='ViewLayer', scene_name='Scene'),
                   collections=[], unit_scale=1.0, frame_number=1, subframe=0.0)
    for name, hidden, render, matrix, vertex_count, face_count in (
        ('Cube', True, True, native.DISPLAY_CUBE_MATRIX, 8, 6),
        (native.DISPLAY_TARGET, False, False, native.DISPLAY_TARGET_MATRIX, 27304, 29073),
    ):
        initial['objects'].append(dict(flag_defaults, name=name, hide_get=hidden,
            visible_get=not hidden, hide_render=render, matrix_world=copy.deepcopy(matrix),
            vertices=[None] * vertex_count, polygons=[None] * face_count, edges=[]))
    native._validate_display_initial(initial)
    check(native.DISPLAY_TARGET_MATRIX[1][2] == 4.371138828673793e-08,
          'fixed_original_small_matrix_coefficient_retained')
    bad = copy.deepcopy(initial)
    bad['objects'][1]['matrix_world'][1][2] = 0.0
    rejects(lambda: native._validate_display_initial(bad), 'rounded_original_matrix_rejected')
    bad = copy.deepcopy(initial)
    bad['objects'][0]['hide_render'] = False
    rejects(lambda: native._validate_display_initial(bad), 'changed_original_render_flag_rejected')

    state = copy.deepcopy(initial)
    writes = []

    class FixtureObject:
        type = 'MESH'

        def __init__(self, name):
            self.name = name

        def hide_set(self, hidden, *, view_layer):
            writes.append((self.name, hidden, view_layer))
            row = next(row for row in state['objects'] if row['name'] == self.name)
            row['hide_get'] = hidden
            row['visible_get'] = not hidden

    layer = SimpleNamespace(update=lambda: None)
    bpy = SimpleNamespace(context=SimpleNamespace(view_layer=layer), data=SimpleNamespace(
        objects={row['name']: FixtureObject(row['name']) for row in initial['objects']}))
    original_reader = native._scene_state
    native._scene_state = lambda _bpy: copy.deepcopy(state)
    try:
        for stage in range(1, 5):
            receipt = native._apply_display_step(bpy, stage, initial)
            check(receipt['stage'] == stage and receipt['fixture_hide_set_setters'] == 1
                  and receipt['product_setters'] == 0, 'fixed_fixture_step_' + str(stage))
        check(state == initial and len(writes) == 4, 'four_setters_restore_complete_original_state')
        check([(name, hidden) for name, hidden, _ in writes]
              == [(step[1], step[2]) for step in native.DISPLAY_STEPS], 'exact_fixed_fixture_write_sequence')
        state['objects'][0]['hide_render'] = False
        rejects(lambda: native._apply_display_step(bpy, 1, initial), 'unrelated_display_mutation_rejected_before_setter')
        check(len(writes) == 4, 'rejected_fixture_performs_zero_additional_setters')
    finally:
        native._scene_state = original_reader

    original_protection = native.protected_files_intact
    native.protected_files_intact = lambda _config: True
    try:
        with tempfile.TemporaryDirectory(prefix='m4-display-protocol-') as temporary:
            client = native.NativeSession()
            client.process = None
            client.workspace = Path(temporary)
            client.config = dict(display_steps_enabled=False, asset_sha256=native.DISPLAY_ASSET_SHA256,
                helper_sha256=hashlib.sha256((HARNESS / 'state_owned_native.py').read_bytes()).hexdigest(),
                deadline_ns=time.perf_counter_ns() + 30_000_000_000)
            calls = []

            def exchange(request, _timeout):
                calls.append(request)
                stage = next(index for index, step in enumerate(native.DISPLAY_STEPS, 1)
                             if step[0] == request['type'])
                operation, name, hidden = native.DISPLAY_STEPS[stage - 1]
                return dict(status='success', result=dict(operation=operation, stage=stage,
                    target_name=name, hidden=hidden, fixture_hide_set_setters=1))

            client._exchange = exchange
            rejects(lambda: client.display_step(native.DISPLAY_STEPS[0][0]), 'main_session_fixture_disabled')
            client.config['display_steps_enabled'] = True
            rejects(lambda: client.display_step('arbitrary_setter'), 'unknown_fixture_operation_rejected')
            rejects(lambda: client.display_step(native.DISPLAY_STEPS[1][0]), 'out_of_order_fixture_rejected')
            for operation, _, _ in native.DISPLAY_STEPS:
                client.display_step(operation)
                rejects(lambda: client.display_step(operation), 'confirmed_step_cannot_replay_' + operation)
            check(len(calls) == 4 and all(call['params'] == {} for call in calls),
                  'client_sends_four_parameterless_fixed_operations')
        with tempfile.TemporaryDirectory(prefix='m4-display-unknown-') as temporary:
            client.workspace = Path(temporary)

            def unknown_exchange(_request, _timeout):
                raise OSError('synthetic response loss after possible fixture entry')

            client._exchange = unknown_exchange
            try:
                client.display_step(native.DISPLAY_STEPS[0][0])
            except OSError:
                pass
            else:
                raise AssertionError('unknown_fixture_transport_must_fail')
            check((client.workspace / 'POISONED.json').is_file()
                  and (client.workspace / 'DISPLAY_1_ATTEMPT.json').is_file()
                  and not (client.workspace / 'DISPLAY_1_RECEIPT.json').exists(),
                  'unknown_fixture_attempt_retained_and_session_poisoned')
            rejects(lambda: client.display_step(native.DISPLAY_STEPS[0][0]),
                    'unknown_fixture_cannot_replay_or_consume_extra_setter')
    finally:
        native.protected_files_intact = original_protection

    setter_calls = [node for node in ast.walk(trees['state_owned_native.py'])
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'hide_set']
    check(len(setter_calls) == 1, 'only_fixed_fixture_has_hide_set_call')
    check(not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.name in ('qa_advance', 'm5_matrix_step', '_apply_qa_vertex_patch', '_apply_m5_matrix')
                  for node in ast.walk(trees['state_owned_native.py'])), 'legacy_geometry_mutation_protocols_removed')
    for filename in ('export_source.py', 'state_owned_native.py'):
        visible_reads = [node for node in ast.walk(trees[filename]) if isinstance(node, ast.Call)
                         and isinstance(node.func, ast.Attribute) and node.func.attr == 'visible_get']
        check(bool(visible_reads) and all(any(key.arg == 'view_layer' for key in node.keywords)
                                        for node in visible_reads), filename + '_explicit_active_view_layer_visible_get')
    return dict(schema='m4-source-region-display-harness-preflight-v1', status='passed',
        checks=checks, input_pins=pins, synthetic_fixture_setters=4,
        operations=dict(Blender_starts=0, actual_rasters=0, model_calls=0, paid_calls=0),
        scope='Python syntax, synthetic admission ledgers and in-memory fixture state. Actual Blender execution remains unrun.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = review()
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(status=result['status'], checks=len(result['checks']))))


if __name__ == '__main__':
    main()
