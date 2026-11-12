"""Project current scene evidence into descriptive, non-authorizing abilities.

The caller is the internal observation pipeline, after snapshot validation.
This module does not validate mesh contents again, run solid/pair kernels,
hash all vertices, cache evidence, contact a host, or change execution gates.
Supplied computed evidence must be bound to the caller's current revision and
fingerprint.  Those labels are checked for agreement, not independently
recomputed; this diagnostic is never a replacement for the action boundary.
"""
from __future__ import annotations

import copy
import re

from .measurement_presentation import finite_metric, valid_unrounded_measurement
from .rigid_frame import rigid_frame_status


SCENE_CAPABILITIES_REVISION = 'snapshot-capability-projection-v1-20261026'
_SHA256 = re.compile(r'^[a-f0-9]{64}$')
_STATES = frozenset({'supported', 'unsupported', 'unknown', 'not_evaluated'})
_SOLID_FAILURE_REASONS = frozenset({'geometry_resource_limit',
    'scene_solid_validation_resource_limit', 'unsupported_solid_geometry',
    'solid_support_evaluation_failed'})


def _capability(status, scope, basis, reasons=(), **fields):
    if status not in _STATES:
        raise ValueError('Unknown diagnostic capability state')
    return {'status': status, 'scope': scope, 'basis': list(basis),
            'reason_codes': list(dict.fromkeys(reasons)), 'execution_authority': False, **fields}


def _inventory(scene):
    if (not isinstance(scene, dict) or not isinstance(scene.get('revision'), str)
            or not scene['revision'].strip() or scene.get('unit') != 'm'
            or scene.get('coordinate_frame') != 'world'
            or not isinstance(scene.get('meshes'), list) or not 1 <= len(scene['meshes']) <= 256):
        raise ValueError('Capabilities require an identified world-metre scene inventory')
    result = {}
    for mesh in scene['meshes']:
        if (not isinstance(mesh, dict) or not isinstance(mesh.get('object_id'), str)
                or not mesh['object_id'] or mesh['object_id'] in result):
            raise ValueError('Capabilities require unique nonempty scene object identities')
        result[mesh['object_id']] = mesh
    return result


def _has_records(mesh):
    # Availability of represented data, not a second geometry-validation pass.
    try:
        return (not isinstance(mesh.get('vertices'), (str, bytes, dict))
                and not isinstance(mesh.get('faces'), (str, bytes, dict))
                and len(mesh['vertices']) > 0 and len(mesh['faces']) > 0)
    except (KeyError, TypeError):
        return False


def _host_declaration(scene, identities, require_host_execution):
    value = scene.get('host_execution')
    if value is None:
        return _capability('unknown', 'current_host_whole_scene_rigid_editability',
            [], ['host_execution_not_declared'], required_by_caller=require_host_execution), None
    valid = (isinstance(value, dict) and value.get('schema_version') == '1.0'
             and value.get('operation') == 'rigid_transform'
             and value.get('scope') == 'independent_static_rigid_meshes'
             and type(value.get('supported')) is bool and isinstance(value.get('reasons'), list))
    if valid:
        valid = all(isinstance(reason, dict) and isinstance(reason.get('object_id'), str)
                    and reason['object_id'] in identities
                    and isinstance(reason.get('object_name'), str)
                    and isinstance(reason.get('reason'), str) and bool(reason['reason'])
                    for reason in value['reasons'])
        valid = valid and value['supported'] == (not value['reasons'])
    if not valid:
        return _capability('unknown', 'current_host_whole_scene_rigid_editability',
            ['invalid_host_declaration'], ['host_execution_declaration_invalid'],
            required_by_caller=require_host_execution), None
    return _capability('supported' if value['supported'] else 'unsupported',
        'current_host_whole_scene_rigid_editability', ['captured_host_execution_declaration'],
        [reason['reason'] for reason in value['reasons']],
        required_by_caller=require_host_execution,
        blocking_objects=sorted({reason['object_id'] for reason in value['reasons']})), {
            field: copy.deepcopy(value[field]) for field in ('schema_version', 'operation', 'supported', 'scope', 'reasons')}


def _bound_evidence(scene, fingerprint, evidence, identities):
    if evidence is None:
        return None, ['computed_evidence_not_supplied']
    if not isinstance(evidence, dict):
        return None, ['computed_evidence_invalid']
    if (fingerprint is None or evidence.get('scene_revision') != scene['revision']
            or evidence.get('scene_fingerprint') != fingerprint):
        return None, ['computed_evidence_binding_mismatch']
    support = evidence.get('solid_support', {})
    pairs = evidence.get('pair_measurements', [])
    if (not isinstance(support, dict) or not set(support).issubset(identities)
            or not isinstance(pairs, list) or len(pairs) > len(identities) ** 2):
        return None, ['computed_evidence_namespace_invalid']
    for pair in pairs:
        if (not isinstance(pair, dict) or not isinstance(pair.get('focal_id'), str)
                or not isinstance(pair.get('reference_id'), str)
                or pair['focal_id'] not in identities or pair['reference_id'] not in identities
                or pair['focal_id'] == pair['reference_id']):
            return None, ['computed_pair_namespace_invalid']
    return evidence, []


def _solid(evidence, identity, evidence_reasons):
    record = None if evidence is None else evidence.get('solid_support', {}).get(identity)
    scope = 'represented_mesh_solid_domain_not_pair_collision_or_path'
    if not isinstance(record, dict) or type(record.get('supported')) is not bool:
        return _capability('unknown', scope, [], evidence_reasons or ['solid_support_not_supplied'])
    reason = record.get('reason')
    budget = record.get('work_budget')
    if (budget is not None and not isinstance(budget, dict)
            or isinstance(budget, dict) and 'within_budget' in budget
            and type(budget['within_budget']) is not bool
            or reason is not None and not isinstance(reason, str)):
        return _capability('unknown', scope, ['malformed_computed_solid_support'], ['solid_support_evidence_invalid'])
    record_codes = record.get('reason_codes', [])
    budget_codes = (budget or {}).get('reason_codes', [])
    error_type = record.get('error_type')
    if (any(not isinstance(codes, list)
            or any(not isinstance(code, str) or not code for code in codes)
            for codes in (record_codes, budget_codes))
            or error_type is not None and (not isinstance(error_type, str) or not error_type)):
        return _capability('unknown', scope, ['malformed_computed_solid_support'], ['solid_support_evidence_invalid'])
    method = record.get('support_method')
    method = method if isinstance(method, str) and method else 'engine_solid_classifier'
    # Classifier reasons may also be descriptive. Only explicit failure markers
    # contradict success; work-budget reason codes denote admission failures.
    failures = [code for code in [reason, *record_codes] if code in _SOLID_FAILURE_REASONS]
    failures.extend(budget_codes)
    if error_type is not None:
        failures.append('solid_support_evaluation_failed')
    if record['supported'] is True:
        if failures:
            return _capability('unknown', scope, ['conflicting_computed_solid_support'],
                ['solid_support_evidence_contradictory', *failures], support_method=method)
        # AABB availability and a success flag cannot replace positive evidence
        # that the existing classifier was admitted within its work budget.
        if budget is None or 'within_budget' not in budget:
            return _capability('unknown', scope, ['current_computed_solid_support'],
                ['solid_support_budget_not_supplied'], support_method=method)
        if budget['within_budget'] is False:
            return _capability('unknown', scope, ['conflicting_computed_solid_support'],
                ['solid_support_evidence_contradictory', 'solid_support_budget_exceeded'],
                support_method=method)
        return _capability('supported', scope, ['current_computed_solid_support'],
            support_method=method)
    # Failure to finish a classifier is unknown; its explicit unsupported-domain
    # result is different from a resource rejection or an evaluation error.
    status = ('unsupported' if reason == 'unsupported_solid_geometry'
              and (budget or {}).get('within_budget') is not False
              and not budget_codes and error_type is None else 'unknown')
    return _capability(status, scope, ['current_computed_solid_support'],
        [reason] if isinstance(reason, str) and reason else ['solid_support_unresolved'],
        support_method=method)


def _pair_kind(record):
    if valid_unrounded_measurement(record):
        return 'certified_penetration' if record.get('is_penetrating') is True or record['signed_clearance_m'] < 0 else 'exact'
    if (record.get('numeric_bound_valid') is True
            and finite_metric(record.get('clearance_lower_bound_m'))
            and record['clearance_lower_bound_m'] >= 0):
        return 'lower_bound'
    return 'unknown'


def _measurement_summaries(evidence, identities, evidence_reasons):
    kinds = {identity: {} for identity in identities}
    if evidence is not None:
        for record in evidence.get('pair_measurements', []):
            left, right = record['focal_id'], record['reference_id']
            key = tuple(sorted((left, right)))
            kind = _pair_kind(record)
            metric = (record.get('clearance_lower_bound_m') if kind == 'lower_bound'
                      else record.get('signed_clearance_m') if kind != 'unknown' else None)
            signature = (kind, metric, record.get('is_penetrating') if kind != 'unknown' else None)
            # Identical pair aliases need not inflate counts.  Conflicting
            # precision aliases cannot promote an unresolved pair to exact.
            for identity in (left, right):
                old = kinds[identity].get(key)
                kinds[identity][key] = signature if old is None or old == signature else ('unknown', None, None)
    summaries = {}
    for identity, returned in kinds.items():
        counts = {kind: sum(value[0] == kind for value in returned.values())
                  for kind in ('exact', 'certified_penetration', 'lower_bound', 'unknown')}
        resolved = bool(returned) and not counts['unknown']
        summaries[identity] = _capability('supported' if resolved else 'unknown',
            'only_returned_represented_mesh_pair_measurements_not_all_object_pairs',
            ['current_computed_pair_measurements'] if returned else [],
            ([] if resolved else ['returned_pair_measurement_unknown'] if returned
             else evidence_reasons or ['pair_measurement_not_supplied']),
            pair_count=len(returned), precision_counts=counts,
            all_returned_pairs_resolved=resolved, all_scene_pairs_evaluated=False)
    return summaries


def _aggregate(capabilities, scope):
    states = [value['status'] for value in capabilities]
    status = ('unsupported' if 'unsupported' in states else 'unknown' if 'unknown' in states
              else 'not_evaluated' if 'not_evaluated' in states else 'supported')
    return _capability(status, scope, ['all_current_scene_objects'],
        [reason for value in capabilities for reason in value['reason_codes']])


def build_scene_capabilities(scene, *, require_host_execution=False,
                             scene_fingerprint=None, computed_evidence=None, object_ids=None):
    """Return compact diagnostics without granting or changing action eligibility.

    ``object_ids`` filters detailed output only. All scene objects and host
    restrictions still contribute to the scene-wide summary. ``computed_evidence``
    is internal, current pipeline output with scene_revision, scene_fingerprint,
    solid_support keyed by object ID, and explicit focal/reference pair_measurements.
    Missing/stale evidence remains unknown. Do not accept this projection back
    from an Agent as an execution gate or as a cached action permission.
    """
    if type(require_host_execution) is not bool:
        raise ValueError('require_host_execution must be boolean')
    if scene_fingerprint is not None and (not isinstance(scene_fingerprint, str)
                                         or not _SHA256.fullmatch(scene_fingerprint)):
        raise ValueError('scene_fingerprint must be a lower-case SHA256 digest or None')
    inventory = _inventory(scene)
    identities = set(inventory)
    if object_ids is None:
        selected = list(inventory)
    else:
        if (not isinstance(object_ids, (list, tuple))
                or any(not isinstance(identity, str) or identity not in identities for identity in object_ids)
                or len(set(object_ids)) != len(object_ids)):
            raise ValueError('object_ids must be a unique subset of captured identities')
        selected = list(object_ids)
    host, declaration = _host_declaration(scene, identities, require_host_execution)
    evidence, evidence_reasons = _bound_evidence(scene, scene_fingerprint, computed_evidence, identities)
    solids = {identity: _solid(evidence, identity, evidence_reasons) for identity in inventory}
    captures = {identity: _capability('supported' if _has_records(mesh) else 'unknown',
        'represented_mesh_record_available_in_input_not_geometry_validation',
        ['input_snapshot_inventory'], [] if _has_records(mesh) else ['mesh_records_unavailable'])
        for identity, mesh in inventory.items()}
    capture_scene = _aggregate(list(captures.values()), 'all_input_mesh_records_available_not_geometry_validation')
    solid_scene = _aggregate(list(solids.values()), 'all_current_scene_meshes_solid_domain')
    motion_scene = _aggregate([host, solid_scene, capture_scene],
        'current_whole_scene_host_and_solid_prerequisites_not_candidate_execution')
    motion_scene['remaining_checks'] = ['current_target_reference_frames', 'fresh_pair_and_scene_work_budget',
                                        'fresh_candidate_endpoint_geometry',
                                        'host_commit_precision_and_revision', 'actual_readback']
    measurements = _measurement_summaries(evidence, identities, evidence_reasons)
    detailed = []
    for identity in selected:
        mesh = inventory[identity]
        frame = rigid_frame_status(mesh)
        frame_cap = _capability('supported' if frame['valid'] else 'unsupported',
            frame['scope'], ['provided_host_frame_fields'], frame['reason_codes'])
        movable = _aggregate([motion_scene, frame_cap],
            'current_rigid_transform_prerequisites_not_an_allowed_action')
        movable.update(candidate_checked=False, fresh_execution_required=True,
                       remaining_checks=list(motion_scene['remaining_checks']))
        reasons = ([] if declaration is None else
                   [reason for reason in declaration['reasons'] if reason['object_id'] == identity])
        detailed.append({'object_id': identity,
            'capture': captures[identity],
            'represented_mesh_measurement': measurements[identity],
            'obstacle_geometry': solids[identity],
            'host_rigid_frame': frame_cap,
            'host_object_restrictions': copy.deepcopy(reasons),
            'movable': movable})
    host_identity = scene.get('host_identity')
    complete = (isinstance(host_identity, dict)
                and host_identity.get('schema_version') == '1.0'
                and isinstance(host_identity.get('document_epoch'), str)
                and bool(host_identity['document_epoch'].strip())
                and host_identity.get('capture_scope') == 'complete_scene_meshes'
                and isinstance(host_identity.get('object_instances'), dict)
                and set(host_identity['object_instances']) == identities
                and all(isinstance(value, str) and value for value in host_identity['object_instances'].values())
                and len(set(host_identity['object_instances'].values())) == len(identities))
    return {'schema_version': '1.0', 'contract_revision': SCENE_CAPABILITIES_REVISION,
        'scene_revision': scene['revision'], 'scene_fingerprint': scene_fingerprint,
        'scope': 'current_snapshot_diagnostics_not_execution_authorization',
        'execution_authority': False, 'changes_existing_gates': False,
        'evidence_binding': _capability('supported' if evidence is not None else 'unknown',
            'caller_supplied_current_revision_and_fingerprint_agreement_not_recomputed_content',
            ['internal_observation_pipeline'] if evidence is not None else [], evidence_reasons),
        'host_execution_declaration': declaration,
        'scene': {'captured_object_count': len(inventory),
            'detailed_object_count': len(selected), 'details_filtered': len(selected) != len(inventory),
            'capture_record_availability': capture_scene,
            'capture_completeness': _capability('supported' if complete else 'unknown',
                'host_declared_mesh_capture_scope_not_unrepresented_objects',
                ['captured_host_identity'] if complete else [],
                [] if complete else ['complete_capture_not_declared']),
            'host_editability_gate': host, 'solid_obstacle_domain': solid_scene,
            'current_motion_prerequisites': motion_scene,
            'unresolved_solid_object_ids': [identity for identity in inventory if solids[identity]['status'] != 'supported'],
            'candidate_endpoint': _capability('not_evaluated', 'current_action_candidate', [], ['no_candidate_checked']),
            'swept_path': _capability('not_evaluated', 'continuous_motion_path', [], ['path_not_certified'])},
        'objects': detailed}


__all__ = ['SCENE_CAPABILITIES_REVISION', 'build_scene_capabilities']
