"""Isolated first eligible request treatment; never edits a product response.

The caller records original and forwarded arguments and owns producer/source
correlation. ``known_current_refs`` must contain only complete refs learned from
successful current producers, invalidated by the caller on source change.

The first locally valid semantic match reserves the sole attempt immediately
before dispatch. A failed dispatch remains that attempt, with no replacement.
"""

from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys


INSTALL_ROOT = Path('D:/he_m4_source_region_blocker_frame_list_001/candidate_install/product')
DEPENDENCY_ROOT = Path('D:/he_anchor_001/venv/Lib/site-packages')
SOURCE_SHA256 = '65bd1ec8009f8024e85ef1cd30c1229957cceb1c1766c8e5b62f2ef2489ce48c'
VALIDATOR_PINS = {
    'live_spatial_mcp': 'b4d89dc4c0a8ada7e5c883c6ff19357f085cb7662a22244e1ddf08c58ed1565c',
    'query_policy': 'b1175635785d3819466f618892a77701f8c9afd3b173950257e24d485ecb170d',
}


def _product_validation():
    """Use the actual installed entry validators, with no service or host."""
    original_path = sys.path[:]
    try:
        sys.path[:0] = [str(INSTALL_ROOT), str(DEPENDENCY_ROOT)]
        modules = {
            name: importlib.import_module('human_eye_plugin.' + name)
            for name in VALIDATOR_PINS
        }
    finally:
        sys.path[:] = original_path
    for name, module in modules.items():
        expected = (INSTALL_ROOT / 'human_eye_plugin' / (name + '.py')).resolve(strict=True)
        if (Path(module.__file__).resolve(strict=True) != expected
                or hashlib.sha256(expected.read_bytes()).hexdigest() != VALIDATOR_PINS[name]):
            raise ValueError('first_packet_validation_requires_pinned_installed_product')
    return modules['live_spatial_mcp']._validate_arguments, modules['query_policy'].validate_query


class Treatment:
    """Replace only response_detail on the first valid matching request."""

    def __init__(self, detail, target_host_id, reference_host_id):
        if detail not in ('full', 'brief') or type(detail) is not str:
            raise ValueError('first_packet_detail_must_be_full_or_brief')
        if any(type(value) is not str or not value for value in (target_host_id, reference_host_id)):
            raise ValueError('first_packet_current_host_ids_required')
        if target_host_id == reference_host_id:
            raise ValueError('first_packet_distinct_objects_required')
        self.detail = detail
        self.target_host_id = target_host_id
        self.reference_host_id = reference_host_id
        self.used = False
        self._pending = None
        self._completed = False
        self._validate = self._normalize = None

    def _validators(self):
        if self._validate is None:
            self._validate, self._normalize = _product_validation()
        return self._validate, self._normalize

    def arguments(self, original, known_current_refs=()):
        """Return an independent forwarded value plus a serializable decision."""
        forwarded = deepcopy(original)
        verdict = {
            'schema': 'source-region-first-packet-treatment-v1',
            'matched': False, 'applied': False, 'attempt': None,
            'detail': self.detail, 'reason': 'not_source_region',
        }
        if self.used:
            verdict['reason'] = 'first_match_already_dispatched'
            return forwarded, verdict
        if (type(original) is not dict or type(original.get('query')) is not dict
                or original['query'].get('mode') != 'source_region'):
            return forwarded, verdict

        validate, normalize = self._validators()
        try:
            validate('human_eye_scene_observe', original)
            query = normalize(original['query'])
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            verdict.update(reason='invalid_arguments', validation_error_type=type(error).__name__)
            return forwarded, verdict
        if original.get('include_image', True) is not True:
            verdict['reason'] = 'image_not_requested'
            return forwarded, verdict
        if query['requested_facts'] != ['surface_proximity']:
            verdict['reason'] = 'different_facts'
            return forwarded, verdict
        reference = query['reference']
        if reference not in ({'name': 'Obj_04'}, {'id': self.reference_host_id}):
            verdict['reason'] = 'different_reference'
            return forwarded, verdict

        if 'region' in query:
            region = query['region']
            if (region['object'] not in ({'name': 'Obj_09'}, {'id': self.target_host_id})
                    or region['source_triangle_indices'] != [0, 1]):
                verdict['reason'] = 'different_selection'
                return forwarded, verdict
            selection_kind = 'explicit_current_triangle_rows'
        else:
            ref = query['region_ref']
            if (ref['host_id'] != self.target_host_id or ref['source_triangle_indices'] != [0, 1]
                    or type(known_current_refs) not in (list, tuple)
                    or not any(type(known) is dict and ref == known for known in known_current_refs)):
                verdict['reason'] = 'reference_not_proven_current_exact_selection'
                return forwarded, verdict
            selection_kind = 'known_current_full_reference'

        forwarded['response_detail'] = self.detail
        verdict.update(matched=True, applied=True, attempt=1, reason='first_valid_matching_dispatch',
                       selection_kind=selection_kind)
        self.used = True
        self._pending = {'verdict': deepcopy(verdict), 'query': deepcopy(query)}
        return forwarded, verdict

    def accept(self, verdict, response):
        """Record outcome without releasing or substituting a dispatched match.

        ``response_valid`` is only a transport/scope observation. It does not
        grade geometry, distance, readability, final delivery, or model usage.
        No response bytes or references are created or changed by this method.
        """
        if (not self._pending or self._completed or verdict != self._pending['verdict']):
            return {'consumed': False, 'attempt_used': self.used, 'reason': 'not_pending_matching_dispatch'}
        self._completed = True
        outcome = {
            'consumed': True, 'attempt_used': True, 'response_valid': False,
            'reason': 'missing_response', 'product_error': False,
        }
        if type(response) is not dict:
            return outcome
        result = response.get('result')
        if 'error' in response or type(result) is not dict or result.get('isError') is not False:
            outcome.update(reason='product_or_rpc_error', product_error=True)
            return outcome
        content = result.get('content')
        if (type(content) is not list or not content or type(content[0]) is not dict
                or content[0].get('type') != 'text' or type(content[0].get('text')) is not str):
            outcome['reason'] = 'missing_public_json'
            return outcome
        try:
            value = json.loads(content[0]['text'])
            query = self._pending['query']
            ref = value['region_ref']
            _, normalize = self._validators()
            normalize({'mode': 'source_region', 'region_ref': ref,
                       'reference': {'id': self.reference_host_id}, 'requested_facts': ['surface_proximity']})
            valid = (
                value['result_kind'] == 'source_region' and value['read_only'] is True
                and value['execution_authority'] is False
                and ref['host_id'] == self.target_host_id and ref['source_triangle_indices'] == [0, 1]
                and ('region_ref' not in query or ref == query['region_ref'])
                and value['task_result']['reference']['object_id'] == self.reference_host_id
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            outcome['reason'] = 'unverifiable_response_scope'
            return outcome
        outcome.update(response_valid=valid,
                       reason='matching_public_response' if valid else 'response_scope_mismatch',
                       response_status=value.get('status'),
                       observation_status=value.get('observation_status'),
                       native_image_block_count=sum(
                           type(item) is dict and item.get('type') == 'image' for item in content))
        return outcome
