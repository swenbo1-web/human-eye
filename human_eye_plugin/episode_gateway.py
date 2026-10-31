"""One fixed-worker episode meter and native read helpers, never authority.

Only a trusted embedding may bind the immutable episode. The meter covers
registered helper entries, including bounded rollback; unavailable evidence
stays unknown. It neither sees arbitrary UI writers nor survives process loss.
This file uses only the standard library until the optional Blender render.
"""
from __future__ import annotations

import base64
import copy
from fractions import Fraction
import hashlib
import json
import math
import os
import re
import struct
import tempfile

PROTOCOL = 'owned-common-native-v1-20261031'
READONLY_EVIDENCE_PROTOCOL = 'owned-readonly-native-evidence-v1-20261031'
RENDER_AUDIT_PROTOCOL = 'owned-native-render-audit-v1-20261031'
MULTISCALE_PROTOCOL = 'owned-native-multiscale-v1-20261031'
SCHEMA = 'owned-episode-ledger-v1'
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
_LIMITS = {'max_setters': 8, 'max_step_translation_m': .001,
           'max_total_translation_m': .008}
_MAX_NATIVE_BYTES = 2 * 1024 * 1024
_MAX_STATE_BYTES = 40 * 1024 * 1024


class EpisodePrewriteRefused(ValueError):
    """No native assignment was entered by this invocation."""


class EpisodeUncertain(RuntimeError):
    """Episode evidence is incomplete or a physical invariant failed."""


def _require(condition, reason):
    if not condition:
        raise EpisodePrewriteRefused(reason)


def _json(value, cap=_MAX_STATE_BYTES):
    def plain(item, depth=0):
        _require(depth <= 24, 'episode_json_depth')
        if type(item) is dict:
            _require(all(type(k) is str for k in item), 'episode_json_keys')
            for child in item.values():plain(child, depth + 1)
        elif type(item) is list:
            for child in item:plain(child, depth + 1)
        elif type(item) in (int, float):
            _require(math.isfinite(item), 'episode_nonfinite')
        else:_require(item is None or type(item) in (str, bool), 'episode_plain_json_required')
    try:
        plain(value)
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                         allow_nan=False).encode('utf8')
        _require(len(raw) <= cap, 'episode_evidence_capacity')
        return raw
    except (OverflowError, RecursionError, TypeError) as exc:
        raise EpisodePrewriteRefused('episode_json_invalid') from exc


def _number(value):
    try:return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:return False


def _vector(value):
    _require(type(value) is list and len(value) == 3 and all(_number(x) for x in value),
             'episode_finite_vector_required')
    return [float(x) for x in value]


def _native(value):
    _require(type(value) is dict and value.get('unit') == 'm'
             and value.get('coordinate_frame') == 'world' and type(value.get('objects')) is list
             and 2 <= len(value['objects']) <= 256, 'episode_complete_native_required')
    _json(value, _MAX_NATIVE_BYTES)
    ids = set()
    for obj in value['objects']:
        _require(type(obj) is dict and type(obj.get('object_id')) is str
                 and obj['object_id'] not in ids, 'episode_native_object_identity')
        ids.add(obj['object_id'])
        matrix = obj.get('matrix')
        _require(type(matrix) is list and len(matrix) == 4 and all(type(row) is list
                 and len(row) == 4 and all(_number(x) for x in row) for row in matrix),
                 'episode_native_matrix_required')
        for key in ('local_vertices', 'world_vertices'):
            _require(type(obj.get(key)) is list and len(obj[key]) >= 3, 'episode_native_vertices_required')
            for point in obj[key]:_vector(point)
        _require(len(obj['local_vertices']) == len(obj['world_vertices'])
                 and type(obj.get('faces')) is list and bool(obj['faces']), 'episode_native_geometry_required')
    return copy.deepcopy(value)


def _binding(value):
    _require(type(value) is dict and set(value) == {
        'host_epoch', 'document_epoch', 'focal_id', 'reference_id', 'object_instances'},
        'episode_complete_binding_required')
    for key, length in [('host_epoch', 32), ('document_epoch', 64)]:
        _require(type(value[key]) is str and len(value[key]) == length
                 and all(c in '0123456789abcdef' for c in value[key]), 'episode_binding_epoch')
    instances = value['object_instances']
    _require(type(instances) is dict and 2 <= len(instances) <= 256
             and all(type(k) is str and type(v) is str and bool(k) and bool(v)
                     for k,v in instances.items()) and len(set(instances.values())) == len(instances),
             'episode_object_instances_required')
    _require(value['focal_id'] != value['reference_id'] and value['focal_id'] in instances
             and value['reference_id'] in instances, 'episode_original_pair_required')
    return copy.deepcopy(value)


def _limits(value):
    if value is None:value = {}
    _require(type(value) is dict and not set(value) - set(_LIMITS), 'episode_limits_invalid')
    result = {**_LIMITS, **value}
    _require(type(result['max_setters']) is int and 1 <= result['max_setters'] <= 8,
             'episode_setter_limit_invalid')
    for key in ('max_step_translation_m', 'max_total_translation_m'):
        _require(_number(result[key]) and 0 < result[key] <= _LIMITS[key], 'episode_motion_limit_invalid')
        result[key] = float(result[key])
    return result


def _record(store):
    _require(type(store) is dict and set(store) == {'schema_version', 'record'}
             and store['schema_version'] == SCHEMA and type(store['record']) is dict,
             'episode_not_bound_or_invalid')
    return store['record']


def _objects(native):return {obj['object_id']: obj for obj in native['objects']}


def _position(native, identity):
    try:return [float(_objects(native)[identity]['matrix'][i][3]) for i in range(3)]
    except (KeyError, TypeError, IndexError) as exc:raise EpisodePrewriteRefused('episode_focal_missing') from exc


def _path(record):
    return sum((Fraction(e['actual_translation_m']) for e in record['events']
                if e['state'] == 'confirmed'), Fraction())


def _floor(value):
    number = float(value)
    return math.nextafter(number, 0.) if Fraction(number) > value else number


def _freeze(record, reason):
    if record['frozen_reason'] is None:record['frozen_reason'] = str(reason)[:256]


def begin_episode(store, *, episode_id, binding, initial_native, deadline_ns, now_ns,
                  read_only=False, limits=None):
    _require(type(store) is dict and type(episode_id) is str and _ID.fullmatch(episode_id),
             'episode_identity_required')
    bound = _binding(binding);native = _native(initial_native);caps = _limits(limits)
    _require(type(now_ns) is int and 0 <= now_ns < (1 << 63) and type(deadline_ns) is int
             and now_ns < deadline_ns <= now_ns + 180_000_000_000 and deadline_ns < (1 << 63),
             'episode_original_qpc_window_required')
    _require(type(read_only) is bool, 'episode_read_only_boolean')
    _require(set(_objects(native)) == set(bound['object_instances']), 'episode_complete_object_coverage')
    if store:
        record = _record(store)
        _require(record['episode_id'] == episode_id and record['binding'] == bound
                 and record['limits'] == caps and record['deadline_ns'] == deadline_ns
                 and record['read_only'] is read_only, 'episode_cannot_rebind_or_reset')
        return snapshot(store)
    candidate = {'schema_version': SCHEMA, 'record': {'episode_id': episode_id, 'binding': bound,
        'limits': caps, 'read_only': read_only, 'deadline_ns': deadline_ns, 'started_ns': now_ns,
        'last_seen_ns': now_ns, 'initial_native': native, 'last_native': copy.deepcopy(native),
        'frozen_reason': None, 'events': []}}
    _json(candidate);store.update(candidate)
    return snapshot(store)


def _check(record, binding, native, now_ns, *, rollback=False):
    _require(type(now_ns) is int and now_ns >= record['last_seen_ns'], 'episode_qpc_backwards')
    record['last_seen_ns'] = now_ns
    if _binding(binding) != record['binding']:
        _freeze(record, 'episode_binding_changed');raise EpisodeUncertain('episode_binding_changed')
    if native != record['last_native']:
        _freeze(record, 'episode_external_scene_change');raise EpisodeUncertain('episode_external_scene_change')
    if record['frozen_reason'] is not None and not rollback:
        raise EpisodeUncertain(record['frozen_reason'])
    _require(not record['read_only'], 'episode_read_only')
    if not rollback:_require(now_ns < record['deadline_ns'], 'episode_deadline_expired')


def preflight_setter(store, *, helper, object_id, requested_world, before_native, binding,
                     now_ns, kind='forward'):
    record = _record(store);native = _native(before_native);target = _vector(requested_world)
    _require(helper in ('_assign_translation', '_assign_matrix', 'native_transform')
             and kind in ('forward', 'rollback'), 'episode_setter_scope')
    _check(record, binding, native, now_ns, rollback=kind == 'rollback')
    _require(object_id == record['binding']['focal_id'], 'episode_wrong_object')
    _require(not any(e['state'] in ('reserved', 'unknown') for e in record['events']),
             'episode_unresolved_entry')
    current = _position(native, object_id)
    _require(current[:2] == target[:2], 'episode_world_z_only')
    distance = math.dist(current, target)
    caps = record['limits'];remaining = caps['max_setters'] - len(record['events'])
    path_left = Fraction(caps['max_total_translation_m']) - _path(record)
    _require(distance <= caps['max_step_translation_m'] and Fraction(distance) <= path_left,
             'episode_motion_cap')
    _require(remaining >= 1, 'episode_setter_cap')
    if kind == 'forward':
        _require(remaining >= 2 and 2 * Fraction(distance) <= path_left, 'episode_rollback_reserve')
    else:
        _require(record['frozen_reason'] is not None and record['events']
                 and record['events'][-1]['state'] == 'confirmed'
                 and record['events'][-1]['kind'] == 'forward'
                 and target == _position(record['events'][-1]['before_native'], object_id),
                 'episode_only_original_failed_return_allowed')
    return native, target


def reserve_setter(store, *, helper, object_id, requested_world, before_native, binding,
                    now_ns, kind='forward'):
    native, target = preflight_setter(store, helper=helper, object_id=object_id,
        requested_world=requested_world, before_native=before_native, binding=binding, now_ns=now_ns, kind=kind)
    record = _record(store)
    event = {'index': len(record['events']) + 1, 'helper': helper, 'kind': kind, 'state': 'reserved',
        'before_native': native, 'requested_world': target, 'after_native': None,
        'reserved_ns': now_ns, 'confirmed_ns': None, 'actual_translation_m': None}
    _json({**record, 'events': [*record['events'], event]})
    record['events'].append(event)
    return event['index']


def _event(record, index):
    _require(type(index) is int and 1 <= index <= len(record['events']), 'episode_unknown_event')
    return record['events'][index - 1]


def mark_unknown(store, event_index, reason='episode_setter_outcome_unknown'):
    record = _record(store);event = _event(record, event_index)
    if event['state'] == 'reserved':event['state'] = 'unknown'
    _freeze(record, reason)


def freeze_episode(store, reason='episode_host_verification_failed'):
    """A known host verification failure may need one bounded original return."""
    record = _record(store)
    _require(type(reason) is str and bool(reason), 'episode_freeze_reason_required')
    _freeze(record, reason)


def cancel_setter(store, event_index):
    record = _record(store);event = _event(record, event_index)
    _require(event['state'] == 'reserved', 'episode_cancel_requires_reserved')
    event.update(state='cancelled_before_entry', after_native=copy.deepcopy(event['before_native']),
                 confirmed_ns=event['reserved_ns'], actual_translation_m=0.)


def enter_setter(store, event_index, now_ns):
    """Lightweight final QPC sample adjacent to the native assignment."""
    record = _record(store);event = _event(record, event_index)
    _require(event['state'] == 'reserved' and type(now_ns) is int
             and now_ns >= record['last_seen_ns'], 'episode_entry_clock_invalid')
    record['last_seen_ns'] = now_ns
    if event['kind'] == 'forward' and now_ns >= record['deadline_ns']:
        cancel_setter(store, event_index)
        event['confirmed_ns'] = now_ns
        raise EpisodePrewriteRefused('episode_deadline_expired_before_entry')


def _invariants(before, after, focal_id):
    old, new = _objects(before), _objects(after)
    if set(old) != set(new):return False
    for identity, previous in old.items():
        current = new[identity]
        if identity != focal_id:
            if previous != current:return False
            continue
        if set(previous) != set(current):return False
        if any(previous[k] != current[k] for k in previous if k not in ('matrix', 'world_vertices')):return False
        if any(previous['matrix'][r][c] != current['matrix'][r][c]
               for r in range(4) for c in range(4) if c != 3 or r == 3):return False
        if previous['matrix'][0][3] != current['matrix'][0][3] or previous['matrix'][1][3] != current['matrix'][1][3]:return False
        if any(a[:2] != b[:2] for a,b in zip(previous['world_vertices'], current['world_vertices'])):return False
    return True


def confirm_setter(store, event_index, *, after_native, now_ns, assignment_error=False):
    record = _record(store);event = _event(record, event_index)
    _require(event['state'] == 'reserved' and type(now_ns) is int
             and now_ns >= event['reserved_ns'] and type(assignment_error) is bool, 'episode_confirm_invalid')
    try:native = _native(after_native)
    except Exception:
        mark_unknown(store, event_index, 'episode_native_after_unavailable');raise EpisodeUncertain('episode_native_after_unavailable')
    amount = math.dist(_position(event['before_native'], record['binding']['focal_id']),
                       _position(native, record['binding']['focal_id']))
    event.update(state='confirmed', after_native=native, confirmed_ns=now_ns, actual_translation_m=amount)
    record['last_native'] = copy.deepcopy(native);record['last_seen_ns'] = max(record['last_seen_ns'], now_ns)
    valid = (_invariants(event['before_native'], native, record['binding']['focal_id'])
        and amount <= record['limits']['max_step_translation_m']
        and _path(record) <= Fraction(record['limits']['max_total_translation_m'])
        and math.dist(_position(native, record['binding']['focal_id']), event['requested_world']) <= 1e-6)
    if not valid:_freeze(record, 'episode_actual_setter_invariant_failed')
    if assignment_error:_freeze(record, 'episode_assignment_raised')
    if event['kind'] == 'forward' and now_ns >= record['deadline_ns']:_freeze(record, 'episode_late_setter')
    try:_json(store)
    except Exception:_freeze(record, 'episode_evidence_capacity_after_entry')
    if record['frozen_reason'] is not None and not (event['kind'] == 'rollback' and valid and not assignment_error):
        raise EpisodeUncertain(record['frozen_reason'])
    return snapshot(store)


def snapshot(store, after_event_count=0):
    record = _record(store)
    _require(type(after_event_count) is int and 0 <= after_event_count <= len(record['events']),
             'episode_event_cursor_invalid')
    events = record['events'];unknown = sum(e['state'] in ('reserved', 'unknown') for e in events)
    complete = not unknown and record['frozen_reason'] is None
    return copy.deepcopy({'schema_version': SCHEMA, 'protocol': PROTOCOL,
        'episode_id': record['episode_id'], 'binding': record['binding'], 'limits': record['limits'],
        'read_only': record['read_only'], 'deadline_ns': record['deadline_ns'], 'closed': False,
        'frozen_reason': record['frozen_reason'], 'actual_setter_count': sum(e['state'] == 'confirmed' for e in events),
        'reserved_event_count': len(events), 'unknown_event_count': unknown,
        'actual_cumulative_translation_m': float(_path(record)),
        'remaining_setters': max(0, record['limits']['max_setters'] - len(events)),
        'remaining_translation_m': max(0., _floor(Fraction(record['limits']['max_total_translation_m']) - _path(record))),
        'registered_events_complete': complete, 'all_channels_complete': complete,
        'count_semantics': 'confirmed lower bound; any unknown entry is not physical zero',
        'coverage': 'all legal setters only in negotiated fixed-owned-worker; not arbitrary UI/external writers',
        'history_durability': 'bounded worker memory only; process loss makes unavailable trace unknown',
        'execution_authority': False, 'events': events[after_event_count:],
        'initial_native': record['initial_native'], 'last_native': record['last_native']})


_RENDER_FIELDS = ('engine', 'resolution_x', 'resolution_y', 'resolution_percentage',
                  'filepath', 'film_transparent', 'pixel_aspect_x', 'pixel_aspect_y',
                  'use_border', 'use_crop_to_border', 'border_min_x', 'border_max_x',
                  'border_min_y', 'border_max_y')
_SHADING_FIELDS = ('light', 'color_type', 'background_type', 'background_color',
                   'show_shadows', 'show_cavity', 'show_object_outline')
_IMAGE_FIELDS = ('file_format', 'color_mode', 'color_depth', 'compression', 'quality',
                 'exr_codec', 'tiff_codec', 'jpeg2k_codec', 'use_jpeg2k_cinema_preset',
                 'use_jpeg2k_cinema_48', 'use_jpeg2k_ycc', 'use_cineon_log',
                 'color_management')
_VIEW_FIELDS = ('view_transform', 'look', 'exposure', 'gamma', 'use_curve_mapping',
                'use_hdr_view', 'white_balance_temperature', 'white_balance_tint',
                'use_white_balance')
_IMAGE_COLOR_CHILDREN = {'linear_colorspace_settings': ('name', 'is_data'),
                         'display_settings': ('display_device',),
                         'view_settings': _VIEW_FIELDS}


def _rna_identity(value):
    if value is None:return None
    name = str(getattr(value, 'name_full', getattr(value, 'name', '')))
    uid = getattr(value, 'session_uid', None)
    pointer = getattr(value, 'as_pointer', None)
    address = int(pointer()) if callable(pointer) else None
    return {'name': name, 'session_uid': uid if type(uid) is int else None,
            'pointer': address, 'identity_kind': 'blender_rna' if address is not None or type(uid) is int
                else 'injectable_test_object',
            'test_object_id': None if address is not None or type(uid) is int else id(value)}


def _scalar_value(value):
    if value is None or type(value) in (str, bool, int):return value
    if type(value) is float:
        _require(math.isfinite(value), 'native_render_state_nonfinite')
        return value
    if isinstance(value, set):return sorted(value)
    try:result = [_scalar_value(item) for item in value]
    except (TypeError, RecursionError) as exc:
        raise EpisodePrewriteRefused('native_render_state_scalar_required') from exc
    return result


def _scalar_state(value, fallback):
    """Writable RNA scalars include implicit format/view transform changes.

    Pointer/collection data are not assigned by this helper. The explicit
    fallback exists only for injectable host doubles without Blender RNA.
    """
    properties = getattr(getattr(value, 'bl_rna', None), 'properties', None)
    if properties is None:
        fields = [key for key in fallback if hasattr(value, key)]
    else:
        fields = [prop.identifier for prop in properties
            if prop.identifier != 'rna_type' and not prop.is_readonly
            and prop.type in ('BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM')]
    _require(len(fields) <= 256, 'native_render_state_property_bound')
    return {key: _scalar_value(getattr(value, key)) for key in sorted(fields)}


def _inventory(values, *, objects=False):
    rows=[]
    for item in values:
        row={'identity':_rna_identity(item)}
        if objects:
            row.update(type=str(getattr(item, 'type', '')),
                       data=_rna_identity(getattr(item, 'data', None)))
        rows.append(row)
    _require(len(rows) <= 10000, 'native_render_state_inventory_bound')
    return sorted(rows, key=lambda row: (row['identity']['name'], row['identity']['pointer'] or 0,
                                        row['identity']['session_uid'] or 0))


def _image_color_state(image_settings):
    # These readonly RNA pointers contain mutable scalar settings whose values
    # may be coerced indirectly by an image-format change. No arbitrary pointer
    # graph or data-block contents are traversed.
    return {name:_scalar_state(getattr(image_settings,name),fallback)
        for name,fallback in _IMAGE_COLOR_CHILDREN.items() if hasattr(image_settings,name)}


def native_render_state(bpy, scene, view_layer):
    """Owner-private readback of the entire state surface changed by look.

    Render Result image caches are output resources, not scene/camera assets,
    and are outside this state contract. No permissions are granted here.
    """
    camera=scene.camera
    camera_state=None
    if camera is not None:
        camera_state={'identity':_rna_identity(camera), 'data':_rna_identity(camera.data),
            'matrix_world':[[float(camera.matrix_world[r][c]) for c in range(4)] for r in range(4)],
            'data_settings':_scalar_state(camera.data, ('type','lens','ortho_scale','clip_start','clip_end',
                'shift_x','shift_y','sensor_width','sensor_height','sensor_fit'))}
    data=getattr(bpy, 'data', None)
    objects=list(scene.objects)
    state={'schema_version':'native-render-state-v1',
        'scope':'render-helper-assigned-and-implicitly-dependent-scalars-camera-assets-selection',
        'scene_camera':camera_state,
        'scene_objects':_inventory(objects, objects=True),
        'global_objects':_inventory(getattr(data, 'objects', objects), objects=True),
        'camera_datablocks':_inventory(getattr(data, 'cameras', [])),
        'active_object':_rna_identity(view_layer.objects.active),
        'selection':[{'object':_rna_identity(obj), 'selected':bool(obj.select_get())}
            for obj in sorted(objects, key=lambda obj: str(getattr(obj, 'name_full', obj.name)))],
        'render':{key:_scalar_value(getattr(scene.render,key)) for key in _RENDER_FIELDS},
        'shading':{key:_scalar_value(getattr(scene.display.shading,key)) for key in _SHADING_FIELDS},
        'image_settings':_scalar_state(scene.render.image_settings, _IMAGE_FIELDS),
        'image_color_management':_image_color_state(scene.render.image_settings),
        'view_settings':_scalar_state(scene.view_settings, _VIEW_FIELDS),
        'scene_display_settings':_scalar_state(scene.display_settings, ('display_device',))
            if hasattr(scene,'display_settings') else {},
        'execution_authority':False}
    _json(state, _MAX_NATIVE_BYTES)
    return state


def _restore_scalar_state(target, values, errors, *, first=()):
    ordered=[key for key in first if key in values]+[key for key in values if key not in first]
    properties=getattr(getattr(target, 'bl_rna', None), 'properties', None)
    for key in ordered:
        try:
            if _scalar_value(getattr(target, key)) == values[key]:continue
            value=values[key]
            prop=properties.get(key) if properties is not None else None
            if prop is not None and prop.type=='ENUM' and prop.is_enum_flag:value=set(value)
            setattr(target,key,value)
        except BaseException as exc:errors.append('scalar:'+key+':'+type(exc).__name__)


def _native_view_frame(initial_native, view, unit_scale):
    """Plan a square orthographic view in host units from SI geometry.

    Subtract the center in Python double precision before projection. Camera
    placement and clipping follow the complete depth interval rather than a
    fixed distance. This is framing, not proof of pixel-level readability.
    """
    _require(view in ('XY', 'XZ', 'SCENE'), 'native_view_invalid')
    _require(_number(unit_scale) and unit_scale > 0, 'native_view_unit_scale_invalid')
    _require(type(initial_native) is dict and type(initial_native.get('objects')) is list,
             'native_view_geometry_required')
    vertices=[]
    for obj in initial_native['objects']:
        _require(type(obj) is dict and type(obj.get('world_vertices')) is list and bool(obj['world_vertices']),
                 'native_view_geometry_required')
        vertices.extend(_vector(point) for point in obj['world_vertices'])
        _require(len(vertices) <= 100000, 'native_view_geometry_capacity')
    _require(bool(vertices), 'native_view_geometry_required')
    low=[min(point[k] for point in vertices) for k in range(3)]
    high=[max(point[k] for point in vertices) for k in range(3)]
    center=[low[k]/2 + high[k]/2 for k in range(3)]
    raw={'XY':(0.,0.,1.), 'XZ':(0.,-1.,0.), 'SCENE':(1.,-1.,.75)}[view]
    length=math.hypot(*raw);direction=[x/length for x in raw]
    # Blender to_track_quat('-Z','Y') at this exact axial direction retains a
    # 180-degree roll. Match that established pixel orientation; do not change
    # the actual quaternion/Euler assignment used by the legacy native view.
    right=[-direction[1], direction[0], 0.] if view != 'XY' else [-1.,0.,0.]
    length=math.hypot(*right);right=[x/length for x in right]
    up=[direction[1]*right[2]-direction[2]*right[1],
        direction[2]*right[0]-direction[0]*right[2],
        direction[0]*right[1]-direction[1]*right[0]]
    local=[[(point[k]-center[k])/unit_scale for k in range(3)] for point in vertices]
    _require(all(_number(x) for point in local for x in point), 'native_view_frame_unrepresentable')
    projected=[[math.fsum(point[k]*axis[k] for k in range(3))
                for axis in (right,up,direction)] for point in local]
    span=max(max(point[k] for point in projected)-min(point[k] for point in projected) for k in (0,1))
    # The projected bounding box need not be centered on the world AABB center.
    extent=max(abs(point[k]) for point in projected for k in (0,1))
    near_depth=min(point[2] for point in projected);far_depth=max(point[2] for point in projected)
    margin=max(span,far_depth-near_depth)*.125
    _require(span > 0 and margin > 0, 'native_view_frame_degenerate')
    distance=far_depth+margin
    center_bu=[x/unit_scale for x in center]
    frame={'center_bu':center_bu,'direction':direction,'right':right,'up':up,
        'camera_location_bu':[math.fsum((center_bu[k],direction[k]*distance)) for k in range(3)],
        'ortho_scale_bu':2*extent*1.25,'clip_start_bu':margin*.25,
        'clip_end_bu':distance-near_depth+margin}
    try:
        values=[*center_bu,*frame['camera_location_bu'],frame['ortho_scale_bu'],
                frame['clip_start_bu'],frame['clip_end_bu']]
        _require(all(_number(x) and math.isfinite(struct.unpack('>f',struct.pack('>f',x))[0]) for x in values),
                 'native_view_frame_unrepresentable')
    except (OverflowError,struct.error) as exc:
        raise EpisodePrewriteRefused('native_view_frame_unrepresentable') from exc
    return frame


def _check_native_view_frame(camera, camera_data, initial_native, unit_scale, frame,
                             *, screen_coverage='all_native_vertices', render=None, view=None):
    """Read real RNA back: clamp/quantization must not silently crop geometry."""
    for key,expected in [('ortho_scale',frame['ortho_scale_bu']),
                         ('clip_start',frame['clip_start_bu']),('clip_end',frame['clip_end_bu'])]:
        actual=float(getattr(camera_data,key))
        _require(_number(actual) and actual > 0 and abs(actual-expected) <= expected*1e-5,
                 'native_view_camera_parameter_clamped')
    matrix=camera.matrix_world
    location=[float(matrix[k][3]) for k in range(3)]
    axes=[[float(matrix[k][column]) for k in range(3)] for column in range(3)]
    _require(screen_coverage in ('all_native_vertices','intentional_local_window'), 'native_view_coverage_invalid')
    half=float(camera_data.ortho_scale)/2
    maximum=[0.,0.];depths=[]
    for obj in initial_native['objects']:
        for point in obj['world_vertices']:
            delta=[point[k]/unit_scale-location[k] for k in range(3)]
            x,y,z=[math.fsum(delta[k]*axis[k] for k in range(3)) for axis in axes]
            _require(all(_number(value) for value in (x,y,z))
                     and (screen_coverage=='intentional_local_window' or abs(x) <= half and abs(y) <= half)
                     and float(camera_data.clip_start) <= -z <= float(camera_data.clip_end),
                     'native_view_actual_frustum_incomplete')
            if render is not None:
                maximum=[max(maximum[0],abs(x)),max(maximum[1],abs(y))];depths.append(-z)
    if render is None:return None
    for actual,expected in zip(axes,(frame['right'],frame['up'],frame['direction'])):
        _require(all(_number(x) and abs(x-y)<=1e-5 for x,y in zip(actual,expected)),
                 'native_view_actual_orientation_changed')
    center=[frame['center_bu'][k]-location[k] for k in range(3)]
    center_ndc=[math.fsum(center[k]*axis[k] for k in range(3))/half for axis in axes[:2]]
    _require(all(_number(value) and abs(value)<=.02 for value in center_ndc), 'native_view_center_quantized_outside_window')
    _require(render.resolution_x==render.resolution_y==384 and render.resolution_percentage==100
        and render.pixel_aspect_x==render.pixel_aspect_y==1.,'native_view_actual_pixel_geometry_invalid')
    return {'schema_version':'native-render-frustum-v1','view':view,'unit_scale_m':unit_scale,
        'camera_matrix_host_units':[[float(matrix[r][c]) for c in range(4)] for r in range(4)],
        'ortho_scale_bu':float(camera_data.ortho_scale),'clip_start_bu':float(camera_data.clip_start),
        'clip_end_bu':float(camera_data.clip_end),'resolution_px':[384,384],'pixel_aspect':[1.,1.],
        'screen_coverage':screen_coverage,'depth_coverage':'all_native_vertices',
        'depth_vertex_count':len(depths),'screen_vertex_count':len(depths) if screen_coverage=='all_native_vertices' else 1,
        'checked_center_world_m':[x*unit_scale for x in frame['center_bu']], 'center_ndc':center_ndc,
        'max_abs_screen_bu':maximum,'min_depth_bu':min(depths),'max_depth_bu':max(depths)}


def _public_view_frame(frame, unit_scale, coverage):
    return {'center_world_m':[x*unit_scale for x in frame['center_bu']],
        'right_world':list(frame['right']),'up_world':list(frame['up']),
        'eye_direction_world':list(frame['direction']),'span_m':frame['ortho_scale_bu']*unit_scale,
        'screen_coverage':coverage,'depth_coverage':'all_native_vertices'}


def _central_focal_sample(native, center, frame, focal_id):
    """One bounded floating orthographic sample, never a visibility certificate."""
    if sum(len(obj.get('faces',[])) for obj in native['objects'])>4096:return 'budget_exceeded'
    projected={}
    for obj in native['objects']:
        if any(type(face) is not list or len(face)!=3 for face in obj.get('faces',[])):
            return 'budget_exceeded'
        projected[obj['object_id']]=[[math.fsum((point[k]-center[k])*axis[k] for k in range(3))
             for axis in (frame['right'],frame['up'],frame['direction'])] for point in obj['world_vertices']]
    hits=[];uncertain=False
    for obj in native['objects']:
        points=projected[obj['object_id']]
        for face in obj['faces']:
            a,b,c=[points[index] for index in face]
            if max(a[0],b[0],c[0])<0 or min(a[0],b[0],c[0])>0 or max(a[1],b[1],c[1])<0 or min(a[1],b[1],c[1])>0:continue
            ab=[b[k]-a[k] for k in (0,1)];ac=[c[k]-a[k] for k in (0,1)]
            denominator=ab[0]*ac[1]-ab[1]*ac[0]
            if denominator==0:continue
            if abs(denominator)<=1e-12*max(abs(ab[0]*ac[1]),abs(ab[1]*ac[0])):
                uncertain=True;continue
            v=(-a[0]*ac[1]+a[1]*ac[0])/denominator
            w=(-ab[0]*a[1]+ab[1]*a[0])/denominator;u=1-v-w
            if min(u,v,w)<-1e-12:continue
            depth=math.fsum((u*a[2],v*b[2],w*c[2]))
            if not _number(depth):return 'other_or_uncertain'
            hits.append((depth,obj['object_id']))
    if uncertain or not hits:return 'other_or_uncertain'
    nearest=max(depth for depth,_ in hits)
    tolerance=1e-9*max(1.,abs(nearest),max(depth for depth,_ in hits)-min(depth for depth,_ in hits))
    identities={identity for depth,identity in hits if nearest-depth<=tolerance}
    return 'focal_first' if identities=={focal_id} else 'other_or_uncertain'


def plan_native_multiscale(native, focal_id, view, unit_scale, *, focal_hidden_render=False):
    """Public-geometry opportunity and one-sample gate for at most one detail."""
    overview=_native_view_frame(native,view,unit_scale)
    plan={'schema_version':'native-multiscale-plan-v1','view':view,'scene_revision':native['revision'],
        'focal_id':focal_id,'unit':'m','coordinate_frame':'world','image_size':[384,384],
        'max_images':2,'max_total_pixels':2*384*384,'budget_scope':'per_call_original_episode_deadline',
        'image_count':1,'detail_included':False,
        'reason_code':'overview_sufficient','overview':_public_view_frame(overview,unit_scale,'all_native_vertices'),
        'detail':None,'feature':{'method':'projected_min_edge_normal_width','width_m':None,
            'overview_px':None,'detail_px':None,'zoom':None},
        'visibility':{'method':'single_orthographic_central_ray','status':'not_checked',
            'scope':'one_sample_not_complete_visibility'},'execution_authority':False}
    focal=next((obj for obj in native['objects'] if obj['object_id']==focal_id),None)
    _require(focal is not None,'native_multiscale_focal_missing')
    points=focal['world_vertices'];faces=focal.get('faces',[])
    if not (3<=len(points)<=64 and 1<=len(faces)<=128 and all(type(face) is list and len(face)==3 for face in faces)):
        plan['reason_code']='focus_budget_exceeded';return plan,overview,None
    center=[min(point[k] for point in points)/2+max(point[k] for point in points)/2 for k in range(3)]
    projected=[[math.fsum((point[k]-center[k])*axis[k] for k in range(3))
        for axis in (overview['right'],overview['up'])] for point in points]
    widths=[]
    for face in faces:
        for ia,ib in zip(face,face[1:]+face[:1]):
            a,b=projected[ia],projected[ib];dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
            if length==0:continue
            values=[(-dy*point[0]+dx*point[1])/length for point in projected]
            widths.append(max(values)-min(values))
    width=min(widths) if widths else 0.
    if not _number(width) or width<=0:
        plan['reason_code']='degenerate_projected_focus';return plan,overview,None
    span=plan['overview']['span_m'];detail_span=max(4*width,span/4096.)
    feature=plan['feature'];feature.update(width_m=width,overview_px=384*width/span,
        detail_px=384*width/detail_span,zoom=span/detail_span)
    if feature['overview_px']>=12:return plan,overview,None
    if feature['zoom']<2:
        plan['reason_code']='gain_below_threshold';return plan,overview,None
    if feature['detail_px']<32:
        plan['reason_code']='detail_insufficient_at_zoom_cap';return plan,overview,None
    if focal_hidden_render:
        plan['reason_code']='focal_not_renderable';plan['visibility']['status']='focal_hidden_render'
        return plan,overview,None
    visibility=_central_focal_sample(native,center,overview,focal_id);plan['visibility']['status']=visibility
    if visibility!='focal_first':
        plan['reason_code']='occlusion_budget_exceeded' if visibility=='budget_exceeded' else 'central_ray_occluded_or_unknown'
        return plan,overview,None
    # Only screen coverage narrows. Every represented vertex still contributes
    # to depth placement and clipping, including every potential occluder.
    center_bu=[x/unit_scale for x in center]
    depths=[math.fsum((point[k]/unit_scale-center_bu[k])*overview['direction'][k] for k in range(3))
        for obj in native['objects'] for point in obj['world_vertices']]
    side=detail_span/unit_scale;margin=max(side,max(depths)-min(depths))*.125
    distance=max(depths)+margin
    detail={**copy.deepcopy(overview),'center_bu':center_bu,
        'camera_location_bu':[math.fsum((center_bu[k],overview['direction'][k]*distance)) for k in range(3)],
        'ortho_scale_bu':side,'clip_start_bu':margin*.25,'clip_end_bu':distance-min(depths)+margin}
    plan.update(detail=_public_view_frame(detail,unit_scale,'intentional_local_window'),
        detail_included=True,image_count=2,reason_code='projected_detail_gain')
    _json(plan,_MAX_NATIVE_BYTES)
    return plan,overview,detail


def _task_gap_box_bounds(obj):
    """Strict tiny closed axis box, not an arbitrary AABB approximation."""
    points=obj.get('world_vertices',[]);faces=obj.get('faces',[])
    if (len(points)!=8 or len(faces)!=12 or any(not isinstance(p,list) or len(p)!=3
            or not all(_number(x) for x in p) for p in points)):
        return None
    low=[min(p[k] for p in points) for k in range(3)]
    high=[max(p[k] for p in points) for k in range(3)]
    if any(not low[k]<high[k] for k in range(3)):return None
    if {tuple(p) for p in points}!={(x,y,z) for x in (low[0],high[0])
            for y in (low[1],high[1]) for z in (low[2],high[2])}:return None
    directed={};planes={};triangles=set()
    for face in faces:
        if (type(face) is not list or len(face)!=3 or any(type(i) is not int or not 0<=i<8 for i in face)
                or len(set(face))!=3 or tuple(sorted(face)) in triangles):return None
        triangles.add(tuple(sorted(face)))
        plane=[(k,points[face[0]][k]) for k in range(3)
            if points[face[0]][k]==points[face[1]][k]==points[face[2]][k]]
        if len(plane)!=1:return None
        axis,level=plane[0];a,b,c=[points[i] for i in face]
        u=[b[k]-a[k] for k in range(3)];v=[c[k]-a[k] for k in range(3)]
        normal=(u[(axis+1)%3]*v[(axis+2)%3]-u[(axis+2)%3]*v[(axis+1)%3])
        if not _number(normal) or not (normal<0 if level==low[axis] else normal>0):return None
        planes[plane[0]]=planes.get(plane[0],0)+1
        for a,b in zip(face,face[1:]+face[:1]):directed[a,b]=directed.get((a,b),0)+1
    if (planes!={(k,v):2 for k in range(3) for v in (low[k],high[k])}
            or any(count!=1 or directed.get((b,a))!=1 for (a,b),count in directed.items())):return None
    return low,high


def _task_gap_witness(native,focal_id,reference_id):
    pair=[next((o for o in native['objects'] if o['object_id']==identity),None)
        for identity in (focal_id,reference_id)]
    if any(obj is None for obj in pair) or focal_id==reference_id:return None
    bounds=[_task_gap_box_bounds(obj) for obj in pair]
    if any(value is None for value in bounds):return None
    (fl,fh),(rl,rh)=bounds;separated=[];overlap={}
    for k in range(3):
        if fh[k]<rl[k]:separated.append((k,fh[k],rl[k],-1))
        elif rh[k]<fl[k]:separated.append((k,fl[k],rh[k],1))
        else:
            a,b=max(fl[k],rl[k]),min(fh[k],rh[k])
            if not a<b:return None
            overlap[k]=(a,b)
    if len(separated)!=1:return None
    axis,f,r,sign=separated[0];gap=abs(f-r)
    if not _number(gap) or gap<=0:return None
    # A full central image stripe must lie within both transverse overlaps.
    if any(b-a<4*gap for a,b in overlap.values()):return None
    center=[(overlap[k][0]/2+overlap[k][1]/2) if k!=axis else f/2+r/2 for k in range(3)]
    fp=list(center);rp=list(center);fp[axis]=f;rp[axis]=r
    fs=list(fp);rs=list(rp)
    fs[axis]+=sign*min(gap,(fh[axis]-fl[axis])/4)
    rs[axis]-=sign*min(gap,(rh[axis]-rl[axis])/4)
    # World offsets cannot enlarge the task-local coordinate tolerance.
    # If binary64 cannot represent the narrow witness reliably, retain V1.
    precision=gap*1e-8
    if precision<=0 or any(math.ulp(float(x))>precision/8 for p in (center,fp,rp,fs,rs) for x in p):return None
    return {'reference_id':reference_id,'gap_axis':axis,'gap_m':gap,'center_world_m':center,
        'witness_focal_world_m':fp,'witness_reference_world_m':rp,
        'sample_points_world_m':[fs,rs,list(center)],'detail_view':'XZ' if axis==2 else 'XY'}


def _task_gap_sample_hits(native,point,frame):
    """Nearest surface depth relative to one sample; no complete visibility claim."""
    hits=[];uncertain=False
    for obj in native['objects']:
        projected=[[math.fsum((p[k]-point[k])*axis[k] for k in range(3))
            for axis in (frame['right'],frame['up'],frame['direction'])] for p in obj['world_vertices']]
        for face in obj['faces']:
            a,b,c=[projected[i] for i in face]
            if max(a[0],b[0],c[0])<0 or min(a[0],b[0],c[0])>0 or max(a[1],b[1],c[1])<0 or min(a[1],b[1],c[1])>0:continue
            ab=[b[k]-a[k] for k in (0,1)];ac=[c[k]-a[k] for k in (0,1)]
            den=ab[0]*ac[1]-ab[1]*ac[0]
            if den==0:uncertain=True;continue
            if abs(den)<=1e-12*max(abs(ab[0]*ac[1]),abs(ab[1]*ac[0])):uncertain=True;continue
            v=(-a[0]*ac[1]+a[1]*ac[0])/den;w=(-ab[0]*a[1]+ab[1]*a[0])/den;u=1-v-w
            if min(u,v,w)<-1e-12:continue
            depth=math.fsum((u*a[2],v*b[2],w*c[2]))
            if not _number(depth):uncertain=True;continue
            hits.append((depth,obj['object_id']))
    if uncertain:return None
    scale=max([1.]+[abs(d) for d,_ in hits])
    tolerance=1e-9*scale
    nearest=max((d for d,_ in hits),default=None)
    identities={identity for d,identity in hits if nearest-d<=tolerance} if hits else set()
    return nearest,identities,tolerance


def plan_readonly_task_gap(native,focal_id,reference_id,view,unit_scale,*,
                           focal_hidden_render=False,reference_hidden_render=False):
    """Finite subpixel pair-gap opportunity; legacy V1 planning stays intact.

    V2 is used only for an added cross-view task window. Three bounded samples
    never establish complete ROI visibility or image measurement precision.
    """
    original=plan_native_multiscale(native,focal_id,view,unit_scale,
        focal_hidden_render=focal_hidden_render)
    plan,overview,existing_detail=original
    if existing_detail is not None or plan['reason_code']!='overview_sufficient':return original
    witness=_task_gap_witness(native,focal_id,reference_id)
    if witness is None:return original
    gap=witness['gap_m'];span=plan['overview']['span_m'];canonical_px=384*gap/span
    if not _number(canonical_px) or not 0<canonical_px<1:return original
    detail_span=max(4*gap,span/4096.);detail_px=384*gap/detail_span;zoom=span/detail_span
    if detail_px<32 or not 2<=zoom<=4096 or focal_hidden_render or reference_hidden_render:return original
    triangle_count=sum(len(o.get('faces',[])) for o in native['objects'])
    vertex_count=sum(len(o.get('world_vertices',[])) for o in native['objects'])
    if (6*triangle_count>4096 or vertex_count>4096
            or any(type(f) is not list or len(f)!=3 for o in native['objects'] for f in o.get('faces',[]))):return original
    direction,right,up=([0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]) if witness['detail_view']=='XZ' else ([0.,0.,1.],[-1.,0.,0.],[0.,-1.,0.])
    basis={'direction':direction,'right':right,'up':up}
    samples=[_task_gap_sample_hits(native,p,basis) for p in witness['sample_points_world_m']]
    if any(sample is None for sample in samples):return original
    for sample,identity in zip(samples[:2],(focal_id,reference_id)):
        nearest,identities,tolerance=sample
        if identities!={identity} or nearest is None or nearest<-tolerance:return original
    # Background behind the gap is allowed. Surface at/before it is not.
    nearest,_,tolerance=samples[2]
    if nearest is not None and nearest>=-tolerance:return original
    center=witness['center_world_m'];center_bu=[x/unit_scale for x in center]
    depths=[math.fsum((p[k]/unit_scale-center_bu[k])*direction[k] for k in range(3))
        for obj in native['objects'] for p in obj['world_vertices']]
    side=detail_span/unit_scale;margin=max(side,max(depths)-min(depths))*.125;distance=max(depths)+margin
    detail={**basis,'center_bu':center_bu,
        'camera_location_bu':[math.fsum((center_bu[k],direction[k]*distance)) for k in range(3)],
        'ortho_scale_bu':side,'clip_start_bu':margin*.25,'clip_end_bu':distance-min(depths)+margin}
    # This new ROI must not turn a usable overview into a predictable RNA
    # precision failure. Actual camera/RNA validation remains mandatory.
    try:
        location32=[struct.unpack('>f',struct.pack('>f',x))[0] for x in detail['camera_location_bu']]
        side32=struct.unpack('>f',struct.pack('>f',side))[0]
        if (not all(_number(x) for x in location32) or not _number(side32) or side32<=0
                or abs(side32-side)>side*1e-5):return original
        location_error=[location32[k]-detail['camera_location_bu'][k] for k in range(3)]
        if any(abs(math.fsum(location_error[k]*axis[k] for k in range(3)))>side*.005
                for axis in (right,up)):return original
    except (OverflowError,struct.error):return original
    delta=[witness['witness_focal_world_m'][k]-witness['witness_reference_world_m'][k] for k in range(3)]
    projected=math.hypot(*[math.fsum(delta[k]*axis[k] for k in range(3)) for axis in (overview['right'],overview['up'])])
    task={**witness,'method':'strict_axis_box_single_axis_gap','requested_gap_projection_px':384*projected/span,
        'canonical_gap_px':canonical_px,'detail_gap_px':detail_px,'zoom':zoom,
        'quality_scope':'geometric_opportunity_three_samples_not_complete_visibility','execution_authority':False}
    result=copy.deepcopy(plan)
    result.update(schema_version='native-task-gap-plan-v2',detail_included=True,image_count=2,
        reason_code='task_gap_detail_gain',detail=_public_view_frame(detail,unit_scale,'intentional_local_window'),
        task_feature=task,visibility={'method':'three_orthographic_samples',
            'status':'pair_surfaces_first_and_gap_clear_to_sample','scope':'three_samples_not_complete_visibility',
            'triangle_tests':3*triangle_count,'max_triangle_tests':4096,'scene_vertex_count':vertex_count,
            'consumer_triangle_tests':3*triangle_count,'total_triangle_tests':6*triangle_count,
            'max_total_triangle_tests':4096,'work_scope':'producer_plus_independent_consumer'})
    _json(result,_MAX_NATIVE_BYTES)
    return result,overview,detail


def native_look(bpy, scene, view_layer, initial_native, view, *, _frame=None,
                _screen_coverage='all_native_vertices', _frustum_sink=None):
    """True Workbench384 render; restore every property changed by this helper."""
    _require(view in ('XY', 'XZ', 'SCENE'), 'native_view_invalid')
    # Blender5.2 may crash inside Workbench when every layer is disabled.
    # Known invalid input is refused before creating assets or entering render.
    _require(any(bool(getattr(layer,'use',True)) for layer in getattr(scene,'view_layers',(view_layer,))),
             'native_view_layer_unavailable')
    unit_scale=float(scene.unit_settings.scale_length)
    frame=_native_view_frame(initial_native,view,unit_scale) if _frame is None else _frame
    from mathutils import Vector
    direction=Vector(frame['direction'])
    rotation = (-direction).to_track_quat('-Z', 'Y')
    render, shade = scene.render, scene.display.shading
    render_keys = _RENDER_FIELDS
    shading_keys = _SHADING_FIELDS
    saved_render = {k: getattr(render, k) for k in render_keys}
    saved_shading = {k: tuple(getattr(shade,k)) if k == 'background_color' else getattr(shade,k) for k in shading_keys}
    saved_camera = scene.camera
    saved_image = _scalar_state(render.image_settings, _IMAGE_FIELDS)
    saved_image_color = _image_color_state(render.image_settings)
    saved_view = _scalar_state(scene.view_settings, _VIEW_FIELDS)
    saved_display = _scalar_state(scene.display_settings, ('display_device',)) if hasattr(scene,'display_settings') else {}
    selected = {obj: obj.select_get() for obj in scene.objects};active = view_layer.objects.active
    camera_data = camera = None
    descriptor, path = tempfile.mkstemp(prefix='human-eye-owned-native-', suffix='.png');os.close(descriptor)
    try:
        camera_data = bpy.data.cameras.new('_human_eye_common_camera_data')
        camera = bpy.data.objects.new('_human_eye_common_camera', camera_data);scene.collection.objects.link(camera)
        camera.location=frame['camera_location_bu'];camera.rotation_euler = rotation.to_euler()
        camera_data.type = 'ORTHO';camera_data.ortho_scale=frame['ortho_scale_bu']
        camera_data.clip_start=frame['clip_start_bu'];camera_data.clip_end=frame['clip_end_bu']
        scene.camera = camera;render.engine = 'BLENDER_WORKBENCH';render.resolution_x = render.resolution_y = 384
        render.resolution_percentage = 100;render.film_transparent = False;render.filepath = path
        render.pixel_aspect_x=render.pixel_aspect_y=1.
        render.use_border=False;render.use_crop_to_border=False
        if render.image_settings.file_format != 'PNG':render.image_settings.file_format = 'PNG'
        scene.view_settings.view_transform = 'Standard'
        shade.light = 'STUDIO';shade.color_type = 'OBJECT';shade.background_type = 'VIEWPORT'
        shade.background_color = (.92,.92,.92);shade.show_shadows = True;shade.show_cavity = False;shade.show_object_outline = True
        view_layer.update()
        proof=_check_native_view_frame(camera,camera_data,initial_native,unit_scale,frame,
            screen_coverage=_screen_coverage,render=render if _frustum_sink is not None else None,view=view)
        if _frustum_sink is not None:_frustum_sink.append(proof)
        bpy.ops.render.render(write_still=True)
        with open(path, 'rb') as stream:png = stream.read(8 * 1024 * 1024 + 1)
        _require(len(png) <= 8 * 1024 * 1024 and png[:8] == b'\x89PNG\r\n\x1a\n'
                 and struct.unpack('>II', png[16:24]) == (384,384), 'native_png_unavailable')
        return {'mime_type': 'image/png', 'image_base64': base64.b64encode(png).decode('ascii'),
                'width': 384, 'height': 384, 'view': view, 'source': 'blender_workbench_native_render'}
    finally:
        # One restoration error cannot skip the remaining state or asset cleanup.
        errors=[]
        def restore(label, operation):
            try:operation()
            except BaseException as exc:errors.append(label+':'+type(exc).__name__)
        restore('scene_camera', lambda:setattr(scene,'camera',saved_camera))
        if camera is not None:restore('temporary_camera_object',lambda:bpy.data.objects.remove(camera,do_unlink=True))
        if camera_data is not None:restore('temporary_camera_data',lambda:bpy.data.cameras.remove(camera_data))
        for k,v in saved_render.items():restore('render:'+k,lambda k=k,v=v:setattr(render,k,v))
        for k,v in saved_shading.items():restore('shading:'+k,lambda k=k,v=v:setattr(shade,k,v))
        if saved_display:_restore_scalar_state(scene.display_settings,saved_display,errors,first=('display_device',))
        _restore_scalar_state(scene.view_settings,saved_view,errors,first=('view_transform','look'))
        _restore_scalar_state(render.image_settings,saved_image,errors,first=('file_format','color_management'))
        for name,values in saved_image_color.items():
            try:
                _restore_scalar_state(getattr(render.image_settings,name),values,errors,first=('view_transform','look'))
            except BaseException as exc:errors.append('image_color:'+name+':'+type(exc).__name__)
        for obj, flag in selected.items():restore('selection',lambda obj=obj,flag=flag:obj.select_set(flag))
        restore('active_object',lambda:setattr(view_layer.objects,'active',active))
        restore('view_layer_update',view_layer.update)
        if os.path.exists(path):restore('owned_temporary_png',lambda:os.unlink(path))
        if errors:raise EpisodeUncertain('native_render_restore_failed:'+','.join(errors)[:1500])
