"""Independent lossless segment presentation contracts, using frozen real wires.

These tests never create a service, connect to a host, read a PNG, or modify a
scene/configuration. The reference decoder is deliberately local to this file;
it does not import the product's JSON parsing, deduplication, or expansion code.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from human_eye_plugin.live_spatial_mcp import (
    LIVE_MCP_TOOLS_SCHEMA, LiveSpatialMCPServer, _tool_result,
)
from human_eye_plugin.task_brief import project_segment_brief


BASELINE = Path(__file__).resolve().parent / 'fixes' / '20261030_v1_agent_entry'
WIRE_SHA256 = {
    'FIRST_SEGMENT_WIRE.json': 'ecc0bfcfb1f60acfb703b7e24a061872be1c614399f07a536e2856931c655ffd',
    'RESUMED_SEGMENT_WIRE.json': '82abb05b9ddcb6684b7a3765bb424c365df40c38a540bf9bca5f9e135c0e5411',
}
REVISION = 'segment-endpoint-references-v1-20261030'


def exact(value):
    """JSON equality that distinguishes false/0 and rejects nonfinite values."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':'))


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result

    def constant(value):
        raise ValueError('nonfinite constant: ' + value)

    value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    exact(value)  # Includes exponent overflow, which parse_constant cannot catch.
    return value


def text_metadata(wire):
    text = [block['text'] for block in wire['content'] if block['type'] == 'text']
    if len(text) != 1:
        raise AssertionError('one native metadata text block required')
    return strict_json(text[0])


def load_wire(name):
    data = (BASELINE / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != WIRE_SHA256[name]:
        raise AssertionError('immutable baseline changed: ' + name)
    return strict_json(data.decode('utf-8'))


def service_value(wire):
    """Restore the already captured native image as a service-shaped value."""
    value = text_metadata(wire)
    pictures = [block for block in wire['content'] if block['type'] == 'image']
    if len(pictures) != 1:
        raise AssertionError('frozen segment must have exactly one native image')
    value['routing']['image'] = copy.deepcopy(pictures[0])
    return value


def child_path(path, key):
    return path + '/' + str(key).replace('~', '~0').replace('/', '~1')


def expand_references(document):
    """Expand only documented, backward, physical dictionary references.

    An object_id sibling is additive. A reference cannot override a target key,
    point outside this metadata, point through serialized text, or form a cycle.
    """
    positions = {}
    refs = []

    def inventory(value, path):
        positions[path] = len(positions)
        if isinstance(value, dict):
            for key, item in value.items():
                inventory(item, child_path(path, key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                inventory(item, child_path(path, index))

    inventory(document, '#')

    def resolve(pointer):
        if not isinstance(pointer, str) or not pointer.startswith('#/'):
            raise AssertionError('reference must be local')
        value = document
        for raw in pointer[2:].split('/'):
            if re.search(r'~(?![01])', raw):
                raise AssertionError('invalid JSON Pointer escape')
            key = raw.replace('~1', '/').replace('~0', '~')
            if isinstance(value, list):
                if not re.fullmatch(r'0|[1-9][0-9]*', key):
                    raise AssertionError('invalid array index')
                try:
                    value = value[int(key)]
                except IndexError as exc:
                    raise AssertionError('missing array target') from exc
            elif isinstance(value, dict) and key in value:
                value = value[key]
            else:
                raise AssertionError('missing or nonphysical pointer target')
        if not isinstance(value, dict):
            raise AssertionError('only dictionaries may be referenced')
        return value

    def walk(value, path, active=()):
        if isinstance(value, dict):
            if '$ref' in value:
                if not (path.startswith('#/endpoint_observation/')
                        or path.startswith('#/routing/')):
                    raise AssertionError('receipt/header references are forbidden')
                if set(value) not in ({'$ref'}, {'$ref', 'object_id'}):
                    raise AssertionError('unknown reference overlay')
                target = value['$ref']
                resolved = resolve(target)
                if target in active or target not in positions or positions[target] >= positions[path]:
                    raise AssertionError('cyclic or forward reference')
                expanded = walk(resolved, target, (*active, target))
                if 'object_id' in value:
                    if 'object_id' in expanded:
                        raise AssertionError('object_id overlay must not override')
                    expanded['object_id'] = copy.deepcopy(value['object_id'])
                refs.append((path, target, copy.deepcopy(value)))
                return expanded
            return {key: walk(item, child_path(path, key), active)
                    for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item, child_path(path, index), active)
                    for index, item in enumerate(value)]
        return copy.deepcopy(value)

    return walk(document, '#'), refs


class SegmentBriefProjectionIndependentTests(unittest.TestCase):
    def setUp(self):
        self.first_wire = load_wire('FIRST_SEGMENT_WIRE.json')
        self.resumed_wire = load_wire('RESUMED_SEGMENT_WIRE.json')
        self.full = text_metadata(self.first_wire)

    def assert_lossless(self, full, brief):
        self.assertIsInstance(brief, dict)
        self.assertEqual(brief['response_detail'], 'brief')
        header = brief['segment_brief']
        self.assertEqual(header['revision'], REVISION)
        self.assertEqual(header['reference_encoding'], 'local_pointer_with_object_id')
        self.assertEqual(header['reference_base'], 'this_same_tool_result_metadata')
        self.assertEqual(header['scope'], 'exact_value_transport_only_no_geometry_or_authority_change')
        self.assertIs(header['execution_authority'], False)
        self.assertEqual(header['omitted_diagnostics'], [])
        self.assertLess(list(brief).index('endpoint_observation'), list(brief).index('routing'))
        self.assertEqual(brief['routing']['context_observation_ref'], '#/endpoint_observation')
        self.assertNotIn('context_text', brief['routing'])
        self.assertEqual(set(brief), set(full) | {'response_detail', 'segment_brief', 'endpoint_observation'})
        # Do not expand receipt fields: the original values must stay directly readable.
        for key in set(full) - {'routing'}:
            self.assertEqual(exact(brief[key]), exact(full[key]), key)
        expanded, refs = expand_references(brief)
        original_route = copy.deepcopy(full['routing'])
        endpoint = strict_json(original_route.pop('context_text'))
        expanded_route = expanded['routing']
        expanded_route.pop('context_observation_ref')
        self.assertEqual(exact(expanded['endpoint_observation']), exact(endpoint))
        self.assertEqual(exact(expanded_route), exact(original_route))
        return expanded, refs

    def assert_fallback(self, value):
        before = copy.deepcopy(value)
        self.assertIsNone(project_segment_brief(value))
        self.assertEqual(exact(value), exact(before))

    def replace_facts(self, value, **changes):
        facts = strict_json(value['routing']['context_text'])
        facts.update(changes)
        value['routing']['context_text'] = json.dumps(facts, ensure_ascii=False, allow_nan=False)
        return facts

    def test_pinned_real_inputs_represent_distinct_review_and_satisfied_states(self):
        self.assertEqual(self.full['status'], 'review_required')
        self.assertEqual(text_metadata(self.resumed_wire)['status'], 'satisfied')
        self.assertFalse(self.full['task_succeeded'])
        self.assertTrue(text_metadata(self.resumed_wire)['task_succeeded'])

    def test_first_real_receipt_reconstructs_every_endpoint_route_and_receipt_fact(self):
        _, refs = self.assert_lossless(self.full, project_segment_brief(self.full))
        self.assertGreater(len(refs), 0)

    def test_resumed_real_receipt_reconstructs_every_endpoint_route_and_receipt_fact(self):
        full = text_metadata(self.resumed_wire)
        _, refs = self.assert_lossless(full, project_segment_brief(full))
        self.assertGreater(len(refs), 0)

    def test_every_camera_cache_and_attention_diagnostic_survives(self):
        expanded, _ = self.assert_lossless(self.full, project_segment_brief(self.full))
        original = strict_json(self.full['routing']['context_text'])
        for key in ('canvas', 'attention', 'measurement_cache', 'scene_memory', 'label_presentation'):
            self.assertEqual(exact(expanded['endpoint_observation'][key]), exact(original[key]), key)
        self.assertIn('view_matrix', expanded['endpoint_observation']['canvas']['views'][0])

    def test_unknown_fields_missing_null_false_and_zero_are_preserved(self):
        distinctions = {'null': None, 'false': False, 'zero': 0, 'negative_zero': -0.0,
                        'empty': {}, 'missing_is_absent': [], 'future_risk': 'unknown'}
        self.full['future_receipt'] = copy.deepcopy(distinctions)
        self.full['routing']['future_route'] = copy.deepcopy(distinctions)
        self.replace_facts(self.full, future_endpoint=copy.deepcopy(distinctions))
        expanded, _ = self.assert_lossless(self.full, project_segment_brief(self.full))
        for value in (expanded['future_receipt'], expanded['routing']['future_route'],
                      expanded['endpoint_observation']['future_endpoint']):
            self.assertIs(value['null'], None)
            self.assertIs(value['false'], False)
            self.assertIs(type(value['zero']), int)
            self.assertNotIn('not_present', value)

    def test_returned_projection_is_detached_from_all_original_regions(self):
        before = exact(self.full)
        brief = project_segment_brief(self.full)
        self.assert_lossless(self.full, brief)
        brief['steps'][0]['result']['receipt']['source'] = 'changed'
        brief['endpoint_observation']['measurement']['signed_clearance_m'] = 999
        brief['routing']['reason_codes'].append('changed')
        brief['segment_brief']['omitted_diagnostics'].append('changed')
        self.assertEqual(exact(self.full), before)

    def test_dictionary_references_escape_physical_unicode_and_tilde_slash_keys(self):
        shared = {'large': '\u6d4b\u8bd5' * 200, 'false': False, 'zero': 0, 'null': None}
        self.replace_facts(self.full, **{'\u51e0\u4f55~/path': shared, 'future_duplicate': copy.deepcopy(shared)})
        _, refs = self.assert_lossless(self.full, project_segment_brief(self.full))
        self.assertTrue(any(target == '#/endpoint_observation/\u51e0\u4f55~0~1path'
                            for _, target, _ in refs))

    def test_object_id_reference_sibling_is_additive_and_lossless(self):
        shared = {'long_future_evidence': 'evidence-' * 60, 'applicable': None}
        self.replace_facts(self.full, future_objects=[shared, dict(shared, object_id='future-object')])
        _, refs = self.assert_lossless(self.full, project_segment_brief(self.full))
        self.assertTrue(any(ref.get('object_id') == 'future-object' for _, _, ref in refs))

    def test_json_whitespace_is_not_required_for_decoded_fact_equivalence(self):
        facts = strict_json(self.full['routing']['context_text'])
        self.full['routing']['context_text'] = json.dumps(facts, indent=3, ensure_ascii=True)
        self.assert_lossless(self.full, project_segment_brief(self.full))

    def test_routing_container_stays_physical_when_endpoint_duplicates_its_fields(self):
        original_route = copy.deepcopy(self.full['routing'])
        original_route.pop('context_text')
        self.replace_facts(self.full, future_route_copy=original_route)
        brief = project_segment_brief(self.full)
        self.assert_lossless(self.full, brief)
        self.assertNotIn('$ref', brief['routing'])

    def test_unrecognized_or_malformed_receipt_contracts_keep_full(self):
        for value in (None, False, 0, [], {}, {'status': 'satisfied'}):
            with self.subTest(value=value):
                self.assert_fallback(value)
        changes = [('schema_version', 'future'), ('status', []),
                   ('replayed', None), ('historical_receipt', 0),
                   ('execution_authority', 0), ('swept_path_certified', None),
                   ('retry_authorized', True), ('execution_scope', 'swept_path'),
                   ('executed', None), ('execution_status', 'execution_uncertain'),
                   ('presentation_scope', 'current_scene'),
                   ('request', []), ('steps', None), ('residual', [])]
        for field, bad in changes:
            with self.subTest(field=field, bad=bad):
                value = copy.deepcopy(self.full)
                value[field] = bad
                self.assert_fallback(value)

    def test_malformed_or_nonobject_context_falls_back(self):
        for raw in ('gap=0.1m', '{', '[]', 'null', 'true', '0', '"text"', '', None, {}):
            with self.subTest(raw=raw):
                value = copy.deepcopy(self.full)
                value['routing']['context_text'] = raw
                self.assert_fallback(value)

    def test_duplicate_json_keys_at_any_depth_fall_back(self):
        original = self.full['routing']['context_text']
        for extra in ('"scene_revision":"first","scene_revision":"second"',
                      '"future":{"same":0,"same":false}'):
            with self.subTest(extra=extra):
                value = copy.deepcopy(self.full)
                value['routing']['context_text'] = '{' + extra + ',' + original.lstrip()[1:]
                self.assert_fallback(value)

    def test_nonfinite_constants_and_exponent_overflow_fall_back(self):
        original = self.full['routing']['context_text']
        for constant in ('NaN', 'Infinity', '-Infinity', '1e9999', '-1e9999'):
            with self.subTest(constant=constant):
                value = copy.deepcopy(self.full)
                value['routing']['context_text'] = '{"future":' + constant + ',' + original.lstrip()[1:]
                self.assert_fallback(value)

    def test_reserved_reference_keys_anywhere_in_original_fall_back(self):
        for region in ('receipt', 'route', 'endpoint'):
            with self.subTest(region=region):
                value = copy.deepcopy(self.full)
                reserved = {'nested': [{'opaque': {'$ref': '#/not-a-codec-reference'}}]}
                if region == 'receipt':
                    value['future'] = reserved
                elif region == 'route':
                    value['routing']['future'] = reserved
                else:
                    self.replace_facts(value, future=reserved)
                self.assert_fallback(value)

    def test_existing_projection_fields_are_never_overwritten(self):
        for field in ('endpoint_observation', 'response_detail', 'segment_brief', 'segment_projection',
                      'capability_reference_encoding', 'support_plane_reference_encoding',
                      'support_plane_value_encoding'):
            for prior in (None, False, 0, {}, 'future'):
                with self.subTest(field=field, prior=prior):
                    value = copy.deepcopy(self.full)
                    value[field] = prior
                    self.assert_fallback(value)
        value = copy.deepcopy(self.full)
        value['routing']['context_observation_ref'] = None
        self.assert_fallback(value)

    def test_unknown_source_unit_or_coordinate_frame_falls_back(self):
        for field, bad in (('source', 'future_source'), ('source', []), ('source', False),
                           ('unit', 'mm'), ('unit', 0), ('coordinate_frame', 'camera'),
                           ('coordinate_frame', {})):
            with self.subTest(field=field, bad=bad):
                value = copy.deepcopy(self.full)
                self.replace_facts(value, **{field: bad})
                self.assert_fallback(value)

    def test_scene_revision_conflicts_with_endpoint_or_terminal_receipt_fall_back(self):
        value = copy.deepcopy(self.full)
        self.replace_facts(value, scene_revision='different-endpoint')
        self.assert_fallback(value)
        value = copy.deepcopy(self.full)
        value['end_revision'] = 'different-terminal-receipt'
        self.assert_fallback(value)

    def test_conflicting_frame_unit_and_capabilities_fall_back(self):
        for field, bad in (('unit', 'mm'), ('coordinate_frame', 'camera'),
                           ('scene_capabilities', {'execution_authority': True}),
                           ('rigid_frame', {'valid': False})):
            with self.subTest(field=field):
                value = copy.deepcopy(self.full)
                value['routing'][field] = bad
                self.assert_fallback(value)

    def test_conflicting_scoped_evidence_and_false_zero_are_not_merged(self):
        for field in ('query_result', 'scene_assessment', 'scene_capabilities'):
            for region in ('route', 'receipt'):
                with self.subTest(field=field, region=region):
                    value = copy.deepcopy(self.full)
                    facts = strict_json(value['routing']['context_text'])
                    facts[field]['future_count'] = False
                    value['routing'][field] = copy.deepcopy(facts[field])
                    if region == 'route':
                        value['routing'][field]['future_count'] = 0
                    else:
                        value[field] = copy.deepcopy(facts[field])
                        value[field]['future_count'] = 0
                    value['routing']['context_text'] = json.dumps(facts)
                    self.assert_fallback(value)

    def test_conflicting_pair_bindings_step_receipts_and_residual_frames_keep_full(self):
        for change in ('selection_pair', 'step_pair', 'step_executed', 'step_verified',
                       'step_execution_verified', 'residual_unit', 'residual_frame', 'residual_fingerprint'):
            with self.subTest(change=change):
                value = copy.deepcopy(self.full)
                if change == 'selection_pair':
                    value['request']['selection_binding']['focal_id'] = 'different-part'
                elif change == 'step_pair':
                    value['steps'][0]['action']['focal_id'] = 'different-part'
                elif change.startswith('step_'):
                    field = change.removeprefix('step_')
                    value['steps'][0]['result'][field] = False
                elif change == 'residual_unit':
                    value['residual']['unit'] = 'mm'
                elif change == 'residual_frame':
                    value['residual']['coordinate_frame'] = 'camera'
                else:
                    value['residual']['scene_fingerprint'] = '0' * 64
                self.assert_fallback(value)

    def test_historical_and_replayed_receipts_keep_full_without_current_claim(self):
        for field in ('historical_receipt', 'replayed'):
            value = copy.deepcopy(self.full)
            value[field] = True
            with self.subTest(field=field):
                self.assert_fallback(value)

    def test_uncertain_blocked_and_error_receipts_keep_full(self):
        for status in ('execution_uncertain', 'blocked', 'error', 'host_quarantined'):
            value = copy.deepcopy(self.full)
            value['status'] = status
            value['executed'] = None
            with self.subTest(status=status):
                self.assert_fallback(value)

    def test_interrupted_and_other_results_without_valid_routing_keep_full(self):
        for status in ('segment_interrupted', 'preview', 'review_required', 'satisfied'):
            for route in (None, {}, {'context_text': 'historical unavailable'}):
                value = copy.deepcopy(self.full)
                value['status'] = status
                value['routing'] = route
                with self.subTest(status=status, route=route):
                    self.assert_fallback(value)

    def test_independent_decoder_rejects_invalid_reference_shapes(self):
        for ref in ({'$ref': 'https://example.invalid/x'}, {'$ref': '#/missing'},
                    {'$ref': '#/endpoint_observation/text'},
                    {'$ref': '#/endpoint_observation/base', 'unexpected': 1},
                    {'$ref': '#/endpoint_observation/base', 'object_id': 'override'}):
            document = {'endpoint_observation': {'base': {'object_id': 'original'}, 'text': '{}',
                                                  'copy': ref}, 'routing': {}}
            with self.subTest(ref=ref), self.assertRaises(AssertionError):
                expand_references(document)
        for document in (
            {'endpoint_observation': {'first': {'$ref': '#/endpoint_observation/later'},
                                      'later': {'value': 1}}, 'routing': {}},
            {'endpoint_observation': {'self': {'$ref': '#/endpoint_observation/self'}}, 'routing': {}},
        ):
            with self.subTest(document=document), self.assertRaises(AssertionError):
                expand_references(document)


class CapturedSegmentService:
    """An immutable captured return value, with no geometry or host facilities."""
    def __init__(self, value):
        self.value = value
        self.calls = []

    def run_clearance_segment(self, session_id, request_id, request, **options):
        self.calls.append((session_id, request_id, copy.deepcopy(request), copy.deepcopy(options)))
        return self.value


class SegmentBriefTransportIndependentTests(unittest.TestCase):
    def setUp(self):
        self.wire = load_wire('FIRST_SEGMENT_WIRE.json')
        self.value = service_value(self.wire)
        self.service = CapturedSegmentService(self.value)
        self.server = LiveSpatialMCPServer(self.service, default_session_id='segment-independent')
        self.arguments = {'request_id': 'captured-return-only', 'request': {
            'focal_id': 'part', 'reference_id': 'base', 'axis': '+z',
            'target_clearance_m': .001, 'clearance_tolerance_m': 1e-6},
            'execute': False, 'include_image': True}

    def call(self, arguments):
        return self.server.handle_jsonrpc_message({'jsonrpc': '2.0', 'id': 9,
            'method': 'tools/call', 'params': {'name': 'human_eye_clearance_segment',
                                              'arguments': arguments}})['result']

    def test_schema_advertises_detail_only_for_observe_and_segment(self):
        for tool in LIVE_MCP_TOOLS_SCHEMA:
            options = tool['inputSchema']['properties']
            with self.subTest(tool=tool['name']):
                if tool['name'] in ('human_eye_scene_observe', 'human_eye_clearance_segment'):
                    self.assertEqual(options['response_detail']['enum'], ['full', 'brief'])
                    self.assertNotIn('response_detail', tool['inputSchema'].get('required', []))
                else:
                    self.assertNotIn('response_detail', options)

    def test_default_and_explicit_full_are_exact_frozen_wire(self):
        implicit = self.call(self.arguments)
        explicit = self.call(dict(self.arguments, response_detail='full'))
        self.assertEqual(implicit, self.wire)
        self.assertEqual(explicit, self.wire)
        self.assertEqual(self.service.calls[0], self.service.calls[1])

    def test_invalid_detail_never_calls_service(self):
        for detail in (None, False, True, 0, 1, '', 'short', 'FULL', [], {}, ['brief']):
            with self.subTest(detail=detail):
                self.assertTrue(self.call(dict(self.arguments, response_detail=detail))['isError'])
        self.assertEqual(self.service.calls, [])

    def test_presentation_argument_is_detached_and_never_forwarded(self):
        arguments = dict(self.arguments, response_detail='brief')
        before = copy.deepcopy(arguments)
        original_value = exact(self.value)
        result = self.call(arguments)
        self.assertFalse(result['isError'])
        self.assertEqual(arguments, before)
        self.assertEqual(exact(self.value), original_value)
        self.assertEqual(self.service.calls, [('segment-independent', 'captured-return-only',
            self.arguments['request'], {'execute': False, 'include_image': True})])

    def test_real_brief_saves_twenty_percent_and_preserves_native_png_bytes(self):
        checker = SegmentBriefProjectionIndependentTests()
        for name in WIRE_SHA256:
            with self.subTest(name=name):
                wire = load_wire(name)
                value = service_value(wire)
                full = _tool_result(value, is_error=False)
                brief = _tool_result(value, is_error=False, response_detail='brief', segment_brief=True)
                self.assertEqual(full, wire)
                checker.assert_lossless(text_metadata(full), text_metadata(brief))
                full_images = [item for item in full['content'] if item['type'] == 'image']
                brief_images = [item for item in brief['content'] if item['type'] == 'image']
                self.assertEqual(full_images, brief_images)
                self.assertEqual(len(brief_images), 1)
                self.assertEqual(base64.b64decode(full_images[0]['data'], validate=True),
                                 base64.b64decode(brief_images[0]['data'], validate=True))
                self.assertNotIn(brief_images[0]['data'], brief['content'][0]['text'])
                full_size = len(full['content'][0]['text'].encode('utf-8'))
                brief_size = len(brief['content'][0]['text'].encode('utf-8'))
                self.assertLessEqual(brief_size, full_size * .8)

    def test_failed_or_unencodable_segment_projector_retains_exact_full(self):
        full = _tool_result(self.value, is_error=False)
        for candidate in ({'unsupported': {1, 2}}, {'not_finite': float('nan')}, object()):
            with self.subTest(candidate_type=type(candidate).__name__):
                with patch('human_eye_plugin.live_spatial_mcp.project_segment_brief', return_value=candidate):
                    result = _tool_result(self.value, is_error=False, response_detail='brief', segment_brief=True)
                self.assertEqual(result, full)
        with patch('human_eye_plugin.live_spatial_mcp.project_segment_brief', side_effect=RuntimeError('presentation')):
            self.assertEqual(_tool_result(self.value, is_error=False, response_detail='brief', segment_brief=True), full)

    def test_projection_without_required_gain_retains_exact_full(self):
        full = _tool_result(self.value, is_error=False)
        original = text_metadata(full)
        for candidate in (original, dict(original, future_noise='x' * 100_000)):
            with self.subTest(extra_noise='future_noise' in candidate):
                with patch('human_eye_plugin.live_spatial_mcp.project_segment_brief', return_value=candidate):
                    result = _tool_result(self.value, is_error=False, response_detail='brief', segment_brief=True)
                self.assertEqual(result, full)
        # Separate the absolute and proportional savings conditions.
        small = {'status': 'preview', 'future_evidence': 'x' * 300}
        candidate = dict(small, future_evidence='x' * 240)
        small_full = _tool_result(small, is_error=False)
        with patch('human_eye_plugin.live_spatial_mcp.project_segment_brief', return_value=candidate):
            self.assertEqual(_tool_result(small, is_error=False, response_detail='brief', segment_brief=True), small_full)
        candidate = copy.deepcopy(original)
        candidate['future_reference'] = 'x' * 300
        candidate.pop('runtime_identity')
        full_bytes = len(full['content'][0]['text'].encode('utf-8'))
        candidate_bytes = len(json.dumps(candidate, ensure_ascii=False, allow_nan=False,
                                        separators=(',', ':')).encode('utf-8'))
        self.assertGreaterEqual(full_bytes - candidate_bytes, 256)
        self.assertGreater(candidate_bytes, full_bytes * .9)
        with patch('human_eye_plugin.live_spatial_mcp.project_segment_brief', return_value=candidate):
            self.assertEqual(_tool_result(self.value, is_error=False, response_detail='brief', segment_brief=True), full)

    def test_errors_and_nonsegment_boundary_never_invoke_segment_projector(self):
        with patch('human_eye_plugin.live_spatial_mcp.project_segment_brief',
                   side_effect=AssertionError('must not project')) as projector:
            full_error = _tool_result(self.value, is_error=True)
            brief_error = _tool_result(self.value, is_error=True, response_detail='brief', segment_brief=True)
            full_other = _tool_result(self.value, is_error=False)
            brief_other = _tool_result(self.value, is_error=False, response_detail='brief')
        projector.assert_not_called()
        self.assertEqual(brief_error, full_error)
        self.assertEqual(brief_other, full_other)

    def test_invalid_original_json_and_native_png_are_not_swallowed_by_projection(self):
        with patch('human_eye_plugin.live_spatial_mcp.project_segment_brief') as projector:
            nonfinite = copy.deepcopy(self.value)
            nonfinite['actual_fact'] = float('inf')
            with self.assertRaises(ValueError):
                _tool_result(nonfinite, is_error=False, response_detail='brief', segment_brief=True)
            invalid_image = copy.deepcopy(self.value)
            invalid_image['routing']['image']['data'] = '%%%not-base64%%%'
            with self.assertRaises(ValueError):
                _tool_result(invalid_image, is_error=False, response_detail='brief', segment_brief=True)
        projector.assert_not_called()

    def test_historical_fallback_does_not_refetch_or_add_native_content(self):
        self.value['historical_receipt'] = True
        self.value['replayed'] = True
        full = _tool_result(self.value, is_error=False)
        result = self.call(dict(self.arguments, response_detail='brief'))
        self.assertEqual(result, full)
        self.assertEqual(len(self.service.calls), 1)
        self.assertNotIn('endpoint_observation', text_metadata(result))


if __name__ == '__main__':
    unittest.main()
