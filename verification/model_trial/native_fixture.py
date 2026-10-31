"""Finite owned Blender 5.2 gateway, run by native_client.OwnedFixture.

This is a protocol gate around a factory scene, not a Python or bpy sandbox.
Only an installed production capture/apply template has an execution path.
Every actual native/plugin assignment (including rollback) shares one meter.
"""
from pathlib import Path
import ast
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
import secrets
import socket
import socketserver
import struct
import sys
import time
import traceback


BUILD_ID = 'sha256:71c5bb2ecab267d6d055b20ee3105493296e58d1d82fa109df90f789dded5225'
SOURCE_SHA256 = '539adfc6b6640f2d2226d89e623cbabe073ef2280f9b8b978a56d94c9d1dbb4b'
CAP, TOTAL, STEPS = .001, .008, 8
CASES = {'floor', 'tilted', 'dense', 'occluded', 'readonly', 'readonly_occluded',
         'open_focal', 'open_reference'}
SIGNS = [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
FACES = [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
         (2,3,7),(2,7,6),(1,2,6),(1,6,5),(3,0,4),(3,4,7)]


class Refusal(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def require(value, code, message):
    if not value:
        raise Refusal(code, message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def loads(raw):
    def constant(_):
        raise ValueError('Nonfinite JSON constant')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    value = json.loads(raw, parse_constant=constant, object_pairs_hook=pairs)
    # Python's float parser also accepts overflowing exponents as infinity.
    json.dumps(value, allow_nan=False)
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


class OwnedGateway:
    def __init__(self, folder, bpy):
        self.bpy = bpy
        self.folder = Path(folder).resolve()
        self.config = loads((self.folder / 'config.json').read_bytes())
        self.started = time.monotonic()
        self.episode_started = None
        self.episode_deadline = None
        self.bound_episode_window = None
        self.quarantined = False
        self.reason = None
        self.write_events = []
        self.planned_motion = 0.
        self.actual_motion = 0.
        self.counts = dict(host_capture_calls=0, host_apply_calls=0, matrix_assignments=0,
                           translation_assignments=0, host_write_events=0, capture_requests=0,
                           apply_requests=0, rejected_requests=0, truth_queries=0,
                           native_transform_actions=0, action_requests=0, look_requests=0)
        self._validate_config()
        self._verify_source()
        self.template = Path(self.config['template_path']).read_text(encoding='utf-8').split('\n')
        self.source = os.path.normcase(os.path.abspath(self.config['source_path']))
        spec = importlib.util.spec_from_file_location('_trial_owned_ids', self.config['source_path'])
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self._create_scene()
        self.initial = self.truth()
        self.save('INITIAL_NATIVE.json', self.initial)

    def save(self, name, value):
        with (self.folder / name).open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write('\n')

    def publish_startup(self, value):
        """Publish a complete startup record once, on this Windows host.

        The polling owner must never observe a partially written final file.
        Windows os.rename refuses an existing destination; it does not replace
        a previously published startup record.
        """
        destination = self.folder / 'startup.json'
        pending = self.folder / ('.startup.' + secrets.token_hex(16) + '.pending')
        created = False
        try:
            with pending.open('x', encoding='utf-8', newline='\n') as stream:
                created = True
                json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
                stream.write('\n')
            if destination.exists():
                raise FileExistsError('Startup record has already been published')
            os.rename(pending, destination)
        finally:
            # Only the private pending path created by this call is removable.
            if created and pending.exists():
                pending.unlink()

    def append(self, name, value):
        with (self.folder / name).open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':')) + '\n')
            stream.flush()

    def _validate_config(self):
        c = self.config
        require(c['runtime_build_id'] == BUILD_ID, 'runtime_identity', 'Expected frozen installed v21')
        require(c['source_sha256'] == SOURCE_SHA256, 'runtime_identity', 'Unexpected production helper bytes')
        require(c['case'] in CASES, 'invalid_case', 'Unknown fixture case')
        require(finite(c['angle_deg']) and -30 <= c['angle_deg'] <= 30, 'invalid_angle', 'Invalid angle')
        require(finite(c['gap_m']) and 0 <= c['gap_m'] <= .1, 'invalid_gap', 'Invalid gap')
        require(isinstance(c['origin'], list) and len(c['origin']) == 3 and all(
            finite(v) and abs(v) <= .1 for v in c['origin']), 'invalid_origin', 'Invalid origin')
        require(type(c['readonly']) is bool, 'invalid_readonly', 'Readonly must be boolean')
        require(c['lifetime_s'] == 360 and c['episode_s'] == 180, 'invalid_lifetime', 'Expected 360s lifetime and 180s episode')
        require(isinstance(c['token'], str) and len(c['token']) == 64, 'invalid_token', 'Invalid owner token')

    def _verify_source(self):
        require(sha(self.config['source_path']) == self.config['source_sha256'],
                'source_changed', 'Production helper bytes changed')
        require(sha(self.config['template_path']) == self.config['template_sha256'],
                'template_changed', 'Fixed runtime template bytes changed')

    def _box(self, name, size, center, color, angle, opened=False):
        mesh = self.bpy.data.meshes.new(name + '_mesh')
        # Negative fixtures remain explicit open surfaces: remove the top face.
        faces = [face for i, face in enumerate(FACES) if not opened or i not in (2, 3)]
        mesh.from_pydata([[s[k] * size[k] / 2 for k in range(3)] for s in SIGNS], [], faces)
        mesh.update()
        obj = self.bpy.data.objects.new(name, mesh)
        self.scene.collection.objects.link(obj)
        obj.location = center
        obj.rotation_euler[1] = angle
        obj.color = (*color, 1.)
        return obj

    def _create_scene(self):
        bpy, c = self.bpy, self.config
        require(bpy.app.version[:2] == (5, 2), 'blender_version', 'Expected Blender 5.2')
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = bpy.context.scene
        self.scene.name = 'HE_20261030_MODEL_TRIAL_NEW_OWNED'
        self.scene.unit_settings.system = 'METRIC'
        self.scene.unit_settings.scale_length = 1.
        angle = math.radians(0. if c['case'] == 'floor' else c['angle_deg'])
        self.normal = [math.sin(angle), 0., math.cos(angle)]
        self.reference = self._box('GreyBase', [.2,.2,.2], c['origin'], (.45,.48,.50), angle,
                                  opened=c['case'] == 'open_reference')
        center = [c['origin'][k] + self.normal[k] * (.15 + c['gap_m']) for k in range(3)]
        self.focal = self._box('BluePart', [.06,.06,.1], center, (.12,.40,.85), angle,
                              opened=c['case'] == 'open_focal')
        if c['case'] in {'occluded', 'readonly_occluded'}:
            # The common SCENE view is orthographic along this fixed direction.
            # The blocker is in front of the focal silhouette, but separated
            # along Y from both the pair and its permitted world-Z trajectory.
            # Other common views can recover the same unmodified geometry.
            length = math.sqrt(1. + 1. + .75*.75)
            direction = [1./length, -1./length, .75/length]
            blocker_center = [center[k] + .30*direction[k] for k in range(3)]
            self._box('FixedOccluder', [.14,.14,.14], blocker_center, (.62,.31,.16), 0.)
        if c['case'] == 'dense':
            for i in range(24):
                center = [c['origin'][0] + .3 + .025 * (i % 6),
                          c['origin'][1] - .05 + .025 * (i // 6), c['origin'][2] + .03]
                self._box('Distractor_%02d' % i, [.01,.01,.01], center, (.6,.45,.25), 0.)
        for obj in self.scene.objects:
            obj.select_set(False)
        self.focal.select_set(True)
        bpy.context.view_layer.objects.active = self.focal
        bpy.context.view_layer.update()
        self.focal_id = self.module.BlenderSceneHost.object_id(self.focal)
        self.reference_id = self.module.BlenderSceneHost.object_id(self.reference)

    def _objects(self):
        self.bpy.context.view_layer.update()
        return {obj.name: {
            'object_id': self.module.BlenderSceneHost.object_id(obj), 'name': obj.name,
            'matrix': [list(row) for row in obj.matrix_world],
            'local_vertices': [list(v.co) for v in obj.data.vertices],
            'world_vertices': [list(obj.matrix_world @ v.co) for v in obj.data.vertices],
            'faces': [list(p.vertices) for p in obj.data.polygons], 'color': list(obj.color),
            'parent': obj.parent.name if obj.parent else None,
            'location': list(obj.location), 'rotation_euler': list(obj.rotation_euler),
            'rotation_mode': obj.rotation_mode, 'rotation_quaternion': list(obj.rotation_quaternion),
            'scale': list(obj.scale), 'delta_location': list(obj.delta_location),
            'delta_rotation_euler': list(obj.delta_rotation_euler), 'delta_scale': list(obj.delta_scale)}
            for obj in sorted(self.scene.objects, key=lambda obj: obj.name) if obj.type == 'MESH'}

    def query(self):
        fields = ('object_id', 'name', 'local_vertices', 'world_vertices', 'faces', 'matrix', 'color')
        objects = [{key: obj[key] for key in fields} for obj in self._objects().values()]
        return {'unit': 'm', 'coordinate_frame': 'world', 'revision': 'native:' + digest(objects), 'objects': objects}

    def truth(self):
        objects = self._objects()
        return {'pid': os.getpid(), 'normal': self.normal, 'origin': self.config['origin'],
            'gap_m': self.config['gap_m'], 'case': self.config['case'],
            'angle_deg': self.config['angle_deg'], 'readonly': self.config['readonly'] or self.config['case'] in {'readonly','readonly_occluded'},
            'allow_apply': not self.config['readonly'] and self.config['case'] not in {'readonly','readonly_occluded','open_focal','open_reference'},
            'focal_id': self.focal_id, 'reference_id': self.reference_id, 'objects': objects,
            'revision': self.query()['revision'], 'counts': dict(self.counts),
            'native_cumulative_translation_m': self.actual_motion,
            'planned_cumulative_translation_m': self.planned_motion, 'host_write_events': list(self.write_events),
            'quarantined': self.quarantined, 'loaded_file': self.bpy.data.filepath,
            'user_file_loaded_or_saved': False, 'runtime_build_id': BUILD_ID,
            'scene_state': {'selection': sorted(o.name for o in self.bpy.context.selected_objects),
                            'active': self.bpy.context.view_layer.objects.active.name if self.bpy.context.view_layer.objects.active else None,
                            'object_types': {o.name:o.type for o in self.scene.objects},
                            'unit_scale_m': self.scene.unit_settings.scale_length,
                            'private_render_state':self._render_state()},
            'source_path': self.config['source_path'], 'source_sha256': self.config['source_sha256']}

    def _render_state(self):
        """Owner evidence of every persistent property the look path changes."""
        scene=self.scene;render=scene.render;shade=scene.display.shading
        render_keys=('engine','resolution_x','resolution_y','resolution_percentage','filepath','film_transparent')
        shading_keys=('light','color_type','background_type','background_color','show_shadows','show_cavity','show_object_outline')
        return {'camera':scene.camera.name if scene.camera else None,
            'render':{key:getattr(render,key) for key in render_keys},
            'shading':{key:list(getattr(shade,key)) if key=='background_color' else getattr(shade,key) for key in shading_keys},
            'image_file_format':render.image_settings.file_format,
            'view_transform':scene.view_settings.view_transform,
            'mesh_hide_render':{obj.name:bool(obj.hide_render) for obj in scene.objects if obj.type=='MESH'}}

    def _write_permission(self):
        require(not self.quarantined, 'quarantined', 'Owned fixture is quarantined')
        require(self.episode_started is not None, 'episode_not_started', 'Owner must begin the episode')
        require(time.monotonic() < self.episode_deadline, 'episode_expired', 'Owned episode expired')
        require(time.monotonic() - self.started < self.config['lifetime_s'], 'fixture_expired', 'Owned fixture expired')
        require(not self.config['readonly'] and self.config['case'] not in {'readonly','readonly_occluded'}, 'read_only', 'Scene is read only')
        require(self.config['case'] not in {'open_focal','open_reference'}, 'unsupported_open_geometry',
                'Open focal or reference geometry is outside the writable domain')

    def _delta(self, delta):
        require(isinstance(delta, list) and len(delta) == 3 and all(finite(v) for v in delta),
                'invalid_delta', 'delta_world_m must contain three finite numbers')
        require(delta[0] == 0 and delta[1] == 0, 'world_z_only', 'Only world Z translation is permitted')
        require(abs(delta[2]) <= CAP, 'step_limit', 'Requested translation exceeds 1mm')

    def _claim_action(self):
        # Rejected attempts spend the outer tool-call budget, never a physical
        # setter slot. Only assign() limits the eight actual helper invocations.
        self.counts['action_requests'] += 1

    def quarantine(self, why):
        if not self.quarantined:
            self.quarantined = True
            self.reason = 'quarantine'
            self.save('QUARANTINE.json', {'reason': why, 'state': self.truth()})
            (self.folder / 'quarantine.flag').touch(exist_ok=False)

    def assign(self, helper, original, obj, target):
        """One meter at every physical setter, even during plugin rollback."""
        self._write_permission()
        require(helper != '_assign_matrix', 'matrix_write_forbidden', 'Matrix writes are forbidden')
        require(self.module._same_rna(obj, self.focal), 'wrong_object', 'Only BluePart may be assigned')
        require(isinstance(target, (list, tuple)) and len(target) == 3 and all(finite(v) for v in target),
                'invalid_target', 'Assignment target must contain three finite numbers')
        before = self.truth()
        old = list(obj.location)
        planned_delta = [target[k] - old[k] for k in range(3)]
        self._delta(planned_delta)
        planned = math.hypot(*planned_delta)
        rounded_delta = [f32(target[k]) - old[k] for k in range(3)]
        self._delta(rounded_delta)
        expected_actual = math.hypot(*rounded_delta)
        require(self.counts['host_write_events'] < STEPS, 'write_limit', 'Eight helper assignments exhausted')
        require(self.planned_motion + planned <= TOTAL and self.actual_motion + expected_actual <= TOTAL,
                'motion_limit', 'Cumulative translation exceeds 8mm')
        event = {'index': self.counts['host_write_events'] + 1, 'helper': helper,
                 'planned_delta_world_m': planned_delta, 'predicted_float32_delta_world_m': rounded_delta,
                 'returned_normally': False}
        self.append('write_states.jsonl', {'phase': 'before', 'index': event['index'], 'state': before})
        self.counts['host_write_events'] += 1
        self.counts['translation_assignments'] += 1
        self.planned_motion += planned
        self.write_events.append(event)
        caught = None
        result = None
        try:
            result = original(obj, target)
            event['returned_normally'] = True
        except BaseException as exc:
            caught = exc
        finally:
            # Read actual storage after *every* assignment, before any rollback.
            after_objects = self._objects()
            old_objects = before['objects']
            delta = [after_objects['BluePart']['matrix'][k][3] - old_objects['BluePart']['matrix'][k][3] for k in range(3)]
            actual = math.hypot(*delta)
            self.actual_motion += actual
            event.update(actual_delta_world_m=delta, actual_motion_m=actual,
                         actual_cumulative_translation_m=self.actual_motion,
                         planned_cumulative_translation_m=self.planned_motion)
            unchanged = set(after_objects) == set(old_objects)
            if unchanged:
                unchanged = all(value == after_objects[name] for name, value in old_objects.items() if name != 'BluePart')
            if unchanged:
                previous, current = old_objects['BluePart'], after_objects['BluePart']
                unchanged = all(previous[key] == current[key] for key in previous if key not in {'matrix','world_vertices','location'})
                unchanged = unchanged and previous['location'][:2] == current['location'][:2]
                unchanged = unchanged and all(previous['matrix'][r][c] == current['matrix'][r][c]
                    for r in range(4) for c in range(4) if c != 3 or r == 3)
            valid = (unchanged and all(finite(v) for v in delta) and delta[0] == 0 and delta[1] == 0
                     and actual <= CAP and self.actual_motion <= TOTAL
                     and self.counts['host_write_events'] <= STEPS)
            if not valid or caught is not None:
                self.quarantine('Actual helper readback violated invariants or assignment raised')
            after = self.truth()
            self.append('write_states.jsonl', {'phase': 'after', 'index': event['index'], 'state': after})
            self.append('write_snapshots.jsonl', {'index':event['index'], 'helper':helper, 'before':before, 'after':after})
        if self.quarantined:
            raise Refusal('quarantined', 'Actual helper write failed verification; fixture quarantined') from caught
        return result

    def install_guards(self, host):
        if getattr(host, '_trial_assignment_guards', False):
            return
        host._trial_assignment_guards = True
        for helper in ('_assign_matrix', '_assign_translation'):
            original = getattr(host, helper)
            def guarded(obj, values, _helper=helper, _original=original):
                return self.assign(_helper, _original, obj, values)
            setattr(host, helper, guarded)

    def profile(self, frame, event, arg):
        if event == 'call' and os.path.normcase(os.path.abspath(frame.f_code.co_filename)) == self.source:
            if frame.f_code.co_name == 'capture_scene':
                self.counts['host_capture_calls'] += 1
            elif frame.f_code.co_name == 'apply_transform':
                self.counts['host_apply_calls'] += 1
                self.install_guards(frame.f_locals['self'])

    def validate_template(self, code):
        require(isinstance(code, str), 'invalid_code', 'Code must be text')
        lines = code.split('\n')
        require(len(lines) == len(self.template) and lines[0] == self.template[0] and lines[2:] == self.template[2:],
                'template_mismatch', 'Only the byte fixed installed capture/apply template is accepted')
        prefix = '_request = _json.loads('
        require(lines[1].startswith(prefix) and lines[1].endswith(')'), 'invalid_request_line', 'Invalid bound request line')
        inner = loads(ast.literal_eval(lines[1][len(prefix):-1]))
        require(isinstance(inner, dict) and set(inner) == {'id','command','params'}, 'invalid_host_request', 'Invalid host request')
        nonce, params = inner['id'], inner['params']
        require(isinstance(nonce, str) and len(nonce) == 32 and all(c in '0123456789abcdef' for c in nonce),
                'invalid_nonce', 'Invalid request nonce')
        if inner['command'] == 'capture':
            require(params == {}, 'invalid_capture', 'Capture parameters must be empty')
        else:
            require(inner['command'] == 'apply', 'invalid_command', 'Unknown fixed host command')
            self._write_permission()
            require(isinstance(params, dict) and {'action','expected_revision'} <= set(params)
                    and set(params) <= {'action','expected_revision','expected_fingerprint','request_nonce'},
                    'invalid_apply', 'Invalid apply parameters')
            action = params['action']
            require(isinstance(action, dict) and {'focal_id','translation'} <= set(action)
                    and set(action) <= {'focal_id','reference_id','translation','rotation_euler_deg'},
                    'invalid_action', 'Invalid host action')
            require(action['focal_id'] == self.focal_id and action.get('reference_id') in (None,self.reference_id),
                    'wrong_object', 'Only owned BluePart may move relative to GreyBase')
            self._delta(action['translation'])
            require(action.get('rotation_euler_deg', [0,0,0]) == [0,0,0], 'rotation_forbidden', 'Rotation is forbidden')
            require(isinstance(params['expected_revision'], str) and params['expected_revision'], 'invalid_revision', 'Revision is required')
            self._claim_action()
        return inner

    def plugin(self, request):
        require(set(request) == {'type','params'} and isinstance(request['params'], dict)
                and set(request['params']) == {'code'}, 'invalid_plugin_request', 'Invalid fixed host envelope')
        code = request['params']['code']
        inner = self.validate_template(code)
        self.counts[inner['command'] + '_requests'] += 1
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(compile(code, '<trial-runtime-fixed-host>', 'exec'),
                 {'__builtins__': __builtins__, '__name__':'__main__', 'bpy': self.bpy})
        require(not self.quarantined, 'quarantined', 'Fixture was quarantined during host execution')
        return {'status':'success', 'result':{'executed':True, 'result':output.getvalue()}}

    def _native_one(self, action):
        self._write_permission()
        require(isinstance(action, dict) and set(action) == {'object_id','delta_world_m'},
                'invalid_action', 'Native action must contain object_id and delta_world_m')
        require(action['object_id'] == self.focal_id, 'wrong_object', 'Only BluePart may move')
        self._delta(action['delta_world_m'])
        self._claim_action()
        self.counts['native_transform_actions'] += 1
        target = [float(self.focal.location[k]) + action['delta_world_m'][k] for k in range(3)]
        def assign_location(obj, values):
            obj.location = values
        self.assign('native_transform', assign_location, self.focal, target)
        query = self.query()
        return {'applied':True, 'object_id':self.focal_id, 'revision':query['revision'],
                'delta_world_m':self.write_events[-1]['actual_delta_world_m'], 'scene':query}

    def transform(self, params):
        self._write_permission()
        require(isinstance(params, dict), 'invalid_params', 'Native transform params must be an object')
        require(isinstance(params.get('expected_revision'), str), 'invalid_revision', 'expected_revision is required')
        require(params['expected_revision'] == self.query()['revision'], 'stale_revision', 'Scene revision changed')
        if 'actions' not in params:
            require(set(params) == {'object_id','delta_world_m','expected_revision'}, 'invalid_params', 'Unexpected transform fields')
            return self._native_one({key:params[key] for key in ('object_id','delta_world_m')})
        require(set(params) == {'actions','expected_revision'} and isinstance(params['actions'], list)
                and 1 <= len(params['actions']) <= STEPS, 'invalid_batch', 'Batch must contain one to eight explicit actions')
        results = []
        stopped = False
        for action in params['actions']:
            try:
                results.append(self._native_one(action))
            except Exception as exc:
                results.append({'applied':False, 'error':{'code':getattr(exc,'code','native_failure'), 'message':str(exc)}})
                stopped = True
                break
        require(not self.quarantined, 'quarantined', 'Actual batch write failed verification; fixture quarantined')
        return {'results':results, 'stopped':stopped, 'revision':self.query()['revision']}

    def _camera_recipe(self, view):
        """The camera depends only on the complete initial represented scene."""
        from mathutils import Vector
        initial_vertices = [v for obj in self.initial['objects'].values() for v in obj['world_vertices']]
        center = Vector([(min(v[k] for v in initial_vertices) + max(v[k] for v in initial_vertices))/2 for k in range(3)])
        direction = Vector({'XY':(0,0,1), 'XZ':(0,-1,0), 'SCENE':(1,-1,.75)}[view]).normalized()
        rotation = (-direction).to_track_quat('-Z','Y')
        inverse = rotation.inverted()
        projected = [inverse @ (Vector(v)-center) for v in initial_vertices]
        span = max(max(v[k] for v in projected)-min(v[k] for v in projected) for k in (0,1))
        return center,direction,rotation,span*1.25+.04

    def _camera_metadata(self, view):
        from mathutils import Vector
        center,direction,rotation,scale = self._camera_recipe(view)
        return {'center_world':list(center), 'direction_world':list(direction),
                'center':list(center), 'eye_direction':list(direction),
                'eye':list(center+direction*3.),'ortho_scale':scale,
                'camera_right':list(rotation @ Vector((1,0,0))),
                'camera_up':list(rotation @ Vector((0,1,0))),
                'width':384,'height':384,'projection':'orthographic',
                'frame_source':'complete_initial_native_vertices'}

    def look(self, params, *, _diagnostic=None, _isolated=False):
        require(set(params) == {'view'} and params['view'] in {'XY','XZ','SCENE'}, 'invalid_view', 'view must be XY, XZ or SCENE')
        bpy, scene = self.bpy, self.scene
        center,direction,rotation,ortho_scale = self._camera_recipe(params['view'])
        render = scene.render
        shade = scene.display.shading
        render_keys = ('engine','resolution_x','resolution_y','resolution_percentage','filepath','film_transparent')
        shading_keys = ('light','color_type','background_type','background_color','show_shadows','show_cavity','show_object_outline')
        before_render = {key:getattr(render,key) for key in render_keys}
        before_shading = {key: tuple(getattr(shade,key)) if key == 'background_color' else getattr(shade,key) for key in shading_keys}
        before_camera = scene.camera
        before_format = render.image_settings.file_format
        before_view = scene.view_settings.view_transform
        before_objects = {obj:(tuple(obj.color),obj.hide_render) for obj in scene.objects if obj.type=='MESH'} if _diagnostic is not None else {}
        camera_data = bpy.data.cameras.new('_trial_temp_camera_data')
        camera = bpy.data.objects.new('_trial_temp_camera', camera_data)
        scene.collection.objects.link(camera)
        camera.location = center + direction * 3.
        camera.rotation_euler = rotation.to_euler()
        camera_data.type = 'ORTHO'
        camera_data.ortho_scale = ortho_scale
        path = self.folder / (_diagnostic if _diagnostic is not None else 'native_look_%04d.png' % self.counts['look_requests'])
        try:
            scene.camera = camera
            render.engine = 'BLENDER_WORKBENCH'
            render.resolution_x = render.resolution_y = 384
            render.resolution_percentage = 100
            render.film_transparent = False
            render.filepath = str(path)
            render.image_settings.file_format = 'PNG'
            scene.view_settings.view_transform = 'Standard'
            shade.light = 'STUDIO'
            shade.color_type = 'OBJECT'
            shade.background_type = 'VIEWPORT'
            shade.background_color = (.92,.92,.92)
            shade.show_shadows = True
            shade.show_cavity = False
            shade.show_object_outline = True
            if _diagnostic is not None:
                shade.light = 'FLAT'
                shade.background_color = (0.,0.,0.)
                shade.show_shadows = False
                shade.show_object_outline = False
                for obj in before_objects:
                    obj.color = (1.,0.,0.,1.) if obj == self.focal else (0.,0.,0.,1.)
                    obj.hide_render = bool(_isolated and obj != self.focal)
            bpy.ops.render.render(write_still=True)
            png = path.read_bytes()
            require(png[:8] == b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',png[16:24]) == (384,384),
                    'native_look_not_ready', 'Native render did not return the required PNG')
            result = {'mime_type':'image/png', 'image_base64':base64.b64encode(png).decode('ascii'),
                      'width':384, 'height':384, 'view':params['view']}
            if _diagnostic is not None:
                from array import array
                image = bpy.data.images.load(str(path),check_existing=False)
                try:
                    buffer = array('f',[0.]) * (384*384*4)
                    image.pixels.foreach_get(buffer)
                    result['red_pixels_linear'] = sum(1 for i in range(0,len(buffer),4)
                        if buffer[i]>.5 and buffer[i+1]<.25 and buffer[i+2]<.25 and buffer[i+3]>.5)
                finally:
                    bpy.data.images.remove(image)
                result['png_sha256'] = hashlib.sha256(png).hexdigest()
                result['camera'] = self._camera_metadata(params['view'])
                # Match the actual represented render camera, including its
                # float32 RNA property/Euler conversion, rather than a merely
                # algebraically equivalent ideal camera.
                result['camera'].update(eye=list(camera.matrix_world.translation),
                    ortho_scale=float(camera_data.ortho_scale),
                    camera_right=[float(camera.matrix_world[k][0]) for k in range(3)],
                    camera_up=[float(camera.matrix_world[k][1]) for k in range(3)],
                    direction_world=[float(camera.matrix_world[k][2]) for k in range(3)],
                    eye_direction=[float(camera.matrix_world[k][2]) for k in range(3)])
            return result
        except Exception as exc:
            raise Refusal('native_look_not_ready', 'Blender native rendering is not ready') from exc
        finally:
            scene.camera = before_camera
            bpy.data.objects.remove(camera, do_unlink=True)
            bpy.data.cameras.remove(camera_data)
            for key,value in before_render.items():
                setattr(render,key,value)
            for key,value in before_shading.items():
                setattr(shade,key,value)
            render.image_settings.file_format = before_format
            scene.view_settings.view_transform = before_view
            for obj,(color,hidden) in before_objects.items():
                obj.color = color
                obj.hide_render = hidden
            bpy.context.view_layer.update()

    def visibility(self, params):
        """Owner-only native segmentation evidence; never model tool output."""
        require(set(params)=={'view'} and params['view'] in {'XY','XZ','SCENE'},
                'invalid_view','view must be XY, XZ or SCENE')
        before = self.query()
        self._visibility_index = getattr(self,'_visibility_index',0)+1
        stem = 'private_visibility_%04d_%s' % (self._visibility_index,params['view'])
        visible = self.look(params,_diagnostic=stem+'_full.png')
        isolated = self.look(params,_diagnostic=stem+'_isolated.png',_isolated=True)
        require(self.query()==before,'visibility_mutated_scene','Private visibility changed mesh state')
        nvisible,nisolated = visible['red_pixels_linear'],isolated['red_pixels_linear']
        require(nisolated>0 and nvisible<=nisolated,'visibility_mask_invalid','Invalid private target masks')
        return {'view':params['view'],'camera':visible['camera'],
            'full_scene_png_base64':visible['image_base64'],
            'focal_only_png_base64':isolated['image_base64'],
            'visible_mask_png_sha256':visible['png_sha256'],
            'isolated_mask_png_sha256':isolated['png_sha256'],
            'mask':{'visible_pixels':nvisible,'isolated_pixels':nisolated,
                    'occluded_pixels':nisolated-nvisible,'visible_fraction':nvisible/nisolated,
                    'pixel_rule':'linear RGBA red>0.5 green<0.25 blue<0.25 alpha>0.5'},
            'state_restored':True,'scene_unchanged':True,'scope':'private native diagnostic, not model observation'}

    def dispatch(self, request):
        self._verify_source()
        require(not self.quarantined, 'quarantined', 'Fixture is quarantined')
        require(isinstance(request, dict), 'invalid_request', 'Request must be an object')
        if self.episode_deadline is not None:
            require(time.monotonic() < self.episode_deadline, 'episode_expired', 'Owned episode expired')
        if request.get('type') == 'execute_code':
            value = self.plugin(request)
            if self.episode_deadline is not None:
                require(time.monotonic() < self.episode_deadline, 'episode_expired', 'Owned episode expired')
            return value
        require(set(request) == {'type','params','token'} and isinstance(request['params'], dict),
                'invalid_request', 'Invalid native envelope')
        require(isinstance(request['token'], str) and secrets.compare_digest(request['token'],self.config['token']),
                'owner_token', 'Invalid owner capability')
        name, params = request['type'], request['params']
        if name == 'owner_truth':
            require(params == {}, 'invalid_params', 'Owner truth has no parameters')
            self.counts['truth_queries'] += 1
            value = self.truth()
        elif name == 'owner_visibility':
            value = self.visibility(params)
        elif name == 'owner_begin_episode':
            self.begin_episode(params)
            value = {'episode_started':True, 'max_wall_s':180, 'max_assignments':STEPS,
                     'max_step_m':CAP, 'max_cumulative_m':TOTAL,
                     'started_monotonic':self.episode_started,
                     'deadline_monotonic':self.episode_deadline}
        elif name == 'native_scene_query':
            require(params == {}, 'invalid_params', 'Scene query has no parameters')
            value = self.query()
        elif name == 'native_transform':
            value = self.transform(params)
        elif name == 'native_look':
            self.counts['look_requests'] += 1
            before = self.query()
            value = self.look(params)
            if self.query() != before:
                self.quarantine('Native look changed mesh state')
                raise Refusal('quarantined', 'Native look changed mesh state')
        else:
            raise Refusal('unsupported_command', 'Unsupported native command')
        if self.episode_deadline is not None:
            require(time.monotonic() < self.episode_deadline, 'episode_expired', 'Owned episode expired')
        return {'status':'success', 'result':value}

    def begin_episode(self, params):
        """Owner-only binding; a second call never grants a new180 seconds."""
        now = time.monotonic()
        if params == {}:
            if self.episode_started is None:
                self.episode_started = now
                self.episode_deadline = now + 180
            return
        require(set(params) == {'started_monotonic','deadline_monotonic'},
                'invalid_params','Begin episode requires one complete absolute window')
        start, end = params['started_monotonic'], params['deadline_monotonic']
        require(finite(start) and finite(end) and 0 < end-start <= 180,
                'invalid_deadline','Episode window must be positive and at most180 seconds')
        require(start <= now and now < end, 'episode_expired','Owner window is not currently active')
        window = (start,end)
        if self.bound_episode_window is not None:
            require(window == self.bound_episode_window,'deadline_rebind','Episode window cannot be replaced')
            return
        # A legacy owner may already have begun a finite episode. Tighten it;
        # never renew that initial lifetime by adding a later formal binding.
        self.episode_started = min(self.episode_started,start) if self.episode_started is not None else start
        self.episode_deadline = min(self.episode_deadline,end) if self.episode_deadline is not None else end
        self.bound_episode_window = window


class PrivateTCPServer(socketserver.TCPServer):
    allow_reuse_address = False
    request_queue_size = 4

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        gateway = self.server.gateway
        event = {'wall_ns':time.time_ns(), 'before_counts':dict(gateway.counts)}
        try:
            self.request.settimeout(5)
            raw = bytearray()
            deadline = time.monotonic() + 5
            while True:
                require(time.monotonic() < deadline, 'request_timeout', 'Request deadline exceeded')
                remaining = deadline - time.monotonic()
                if gateway.episode_deadline is not None:
                    remaining = min(remaining,gateway.episode_deadline-time.monotonic())
                require(remaining > 0,'episode_expired','Owned episode expired')
                self.request.settimeout(remaining)
                block = self.request.recv(65536)
                require(bool(block), 'incomplete_request', 'Request ended before complete JSON')
                raw.extend(block)
                require(len(raw) <= 32768, 'request_limit', 'Request exceeds 32KiB')
                try:
                    request = loads(raw)
                except json.JSONDecodeError:
                    continue
                break
            # Raw production requests remain owner evidence; capabilities are never logged.
            event['request'] = {key:value for key,value in request.items() if key != 'token'} if isinstance(request,dict) else request
            response = gateway.dispatch(request)
            event['accepted'] = True
        except Exception as exc:
            gateway.counts['rejected_requests'] += 1
            event.update(accepted=False, exception_type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())
            response = {'status':'error', 'error':{'code':getattr(exc,'code','invalid_request'),
                'message':str(exc) if isinstance(exc,Refusal) else 'Native request rejected', 'quarantined':gateway.quarantined}}
        event['after_counts'] = dict(gateway.counts)
        event['quarantined'] = gateway.quarantined
        gateway.append('requests.jsonl', event)
        try:
            remaining = 5.
            if gateway.episode_deadline is not None:
                remaining = min(remaining,gateway.episode_deadline-time.monotonic())
            require(remaining > 0,'episode_expired','Owned episode expired')
            self.request.settimeout(remaining)
            self.request.sendall(json.dumps(response,allow_nan=False,separators=(',', ':')).encode('utf-8'))
        except (OSError, Refusal):
            # A lost apply reply is ambiguous, and the owner client must not retry.
            if gateway.counts['host_write_events'] != event['before_counts']['host_write_events']:
                gateway.quarantine('Write response transport failed')


def main():
    import bpy
    if sys.flags.optimize:
        raise RuntimeError('Fixture requires assertions enabled')
    gateway = OwnedGateway(sys.argv[sys.argv.index('--')+1], bpy)
    sys.setprofile(gateway.profile)
    failure = None
    try:
        # Bind directly to port 0. No reserve-close-bind race and no known service port.
        with PrivateTCPServer(('127.0.0.1',0), Handler) as server:
            server.gateway = gateway
            server.timeout = .2
            gateway.publish_startup({'pid':os.getpid(), 'port':server.server_address[1],
                'blender_version':bpy.app.version_string, 'runtime_build_id':BUILD_ID,
                'factory_startup':True, 'background':True, 'private_loopback':True,
                'lifetime_limit_s':gateway.config['lifetime_s'], 'episode_limit_s':180, 'user_file_loaded_or_saved':False})
            while time.monotonic() - gateway.started < gateway.config['lifetime_s']:
                if gateway.quarantined:
                    break
                if (gateway.folder / 'stop.flag').exists():
                    gateway.reason = 'owner_stop_flag'
                    break
                server.handle_request()
            else:
                gateway.reason = 'maximum_lifetime'
    except BaseException as exc:
        failure = {'type':type(exc).__name__, 'message':str(exc), 'traceback':traceback.format_exc()}
        gateway.save('FAILURE.json', failure)
        raise
    finally:
        sys.setprofile(None)
        gateway.save('FINAL_NATIVE.json',gateway.truth())
        gateway.save('shutdown.json', {'pid':os.getpid(), 'reason':gateway.reason, 'failure':failure,
            'counts':gateway.counts, 'quarantined':gateway.quarantined,
            'elapsed_s':time.monotonic()-gateway.started, 'user_file_loaded_or_saved':False})


if __name__ == '__main__':
    main()
