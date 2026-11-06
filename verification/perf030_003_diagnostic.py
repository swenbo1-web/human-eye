"""QA-only exclusive-stage instrumentation of the frozen 326 convex function.

The builder runs only inside the granted diagnostic window. Its clone keeps
the original statements and conditions, adding removable QA observations.
"""
from __future__ import annotations

import ast
from contextlib import contextmanager
import copy
import hashlib
import marshal
from pathlib import Path
import statistics
import sys
import time


RECORDER_NAME = '_perf030_003_recorder'
STAGES = ('token_cache', 'closure', 'topology_components',
          'numeric_certification', 'direction_index', 'other')
SOURCE_PATH = 'human_eye_module1_operators/submodule_1_4_spatial_sniffer.py'

# This literal is an AST anchor, never an executable alternative. The actual
# diagnostic function is copied from SourceGuard's original frozen bytes.
EXPECTED_FUNCTION = '''\
def _convex_shells(mesh: MeshEntity3D):
    """Return certified convex connected shells, or None for unsupported solids.

    This is a conservative exact path for boxes and disconnected convex parts
    such as the existing U/L fixtures.  A connected concave or open surface is
    not silently replaced with its convex hull.  Cache only the current mesh.
    """
    token = mesh._compute_full_crc_token()
    cached = getattr(mesh, "_certified_convex_shells", None)
    if cached is not None and cached[0] == token:
        return cached[1]
    faces = np.asarray(mesh.faces, dtype=np.int64)
    verts = np.asarray(mesh.vertices, dtype=np.float64)
    result = None
    try:
        if len(faces) < 4 or not mesh.is_closed_hull:
            raise ValueError("open_or_empty")
        parents = np.arange(len(faces))
        def find(i):
            while parents[i] != i:
                parents[i] = parents[parents[i]]
                i = parents[i]
            return int(i)
        edge_faces = {}
        oriented = {}
        for i, face in enumerate(faces):
            for a, b in zip(face, np.roll(face, -1)):
                key = (min(int(a), int(b)), max(int(a), int(b)))
                edge_faces.setdefault(key, []).append(i)
                oriented[key] = oriented.get(key, 0) + (1 if a < b else -1)
        if any(len(v) != 2 or oriented[e] != 0 for e, v in edge_faces.items()):
            raise ValueError("non_manifold_or_inconsistent_winding")
        for left, right in edge_faces.values():
            parents[find(left)] = find(right)
        groups = {}
        for i in range(len(faces)):
            groups.setdefault(find(i), []).append(i)
        result = []
        winding_sign = None
        for group in groups.values():
            ids = np.asarray(group)
            triangles = verts[faces[ids]]
            raw = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
            lengths = np.linalg.norm(raw, axis=1)
            if (lengths <= 1e-12).any():
                raise ValueError("degenerate_face")
            points = verts[np.unique(faces[ids])]
            origin = points.mean(axis=0)
            volume6 = float(np.sum(np.einsum("ij,ij->i", triangles[:, 0]-origin, raw)))
            if abs(volume6) <= 1e-12:
                raise ValueError("zero_volume")
            sign = 1 if volume6 > 0 else -1
            if winding_sign is not None and sign != winding_sign:
                raise ValueError("mixed_shell_winding_or_cavity")
            winding_sign = sign
            normals = raw / lengths[:, None] * (1 if volume6 > 0 else -1)
            offsets = np.einsum("ij,ij->i", normals, triangles[:, 0])
            _, keep = np.unique(np.round(np.c_[normals, offsets], 10), axis=0, return_index=True)
            tolerance = max(1e-9, float(np.ptp(points, axis=0).max()) * 1e-9)
            if np.max(points @ normals[keep].T - offsets[keep]) > tolerance:
                raise ValueError("connected_concave_shell")
            global_normals = dict(zip(ids.tolist(), normals))
            directions = []
            for (a, b), incident in edge_faces.items():
                if incident[0] not in global_normals:
                    continue
                if abs(float(global_normals[incident[0]] @ global_normals[incident[1]])) < 1-1e-9:
                    directions.append(verts[b]-verts[a])
            edge_axes = _unique_unit_axes(np.asarray(directions))
            if len(edge_axes) > 128:
                raise ValueError("exact_sat_budget")
            result.append((points, _unique_unit_axes(normals[keep]), edge_axes))
    except (ValueError, IndexError, FloatingPointError):
        result = None
    mesh._certified_convex_shells = (token, result)
    return result
'''


class Recorder:
    """One entry's sequential calls, with disjoint original-function stages."""

    def __init__(self):
        self.calls = []
        self.current = None
        self.active_stage = None
        self.clock_reads = 0
        self.recording_windows_ns = 0
        self.clock_calibration = None

    def reset(self):
        if self.current is not None:
            raise RuntimeError('diagnostic_reset_during_call')
        self.calls = []
        self.active_stage = None
        self.clock_reads = 0
        self.recording_windows_ns = 0
        started = time.perf_counter_ns()
        gaps = []
        for _ in range(16):
            left = time.perf_counter_ns()
            right = time.perf_counter_ns()
            gaps.append(right - left)
        elapsed = time.perf_counter_ns() - started
        self.clock_calibration = {
            'pairs': 16, 'clock_reads': 34, 'pair_gap_ns': gaps,
            'median_pair_gap_ns': statistics.median(gaps), 'elapsed_ns': elapsed,
            'scope': 'bare consecutive-clock gaps including measurement overhead',
        }

    def _clock(self):
        self.clock_reads += 1
        return time.perf_counter_ns()

    @contextmanager
    def call(self, mesh):
        if self.current is not None:
            raise RuntimeError('diagnostic_unexpected_nested_convex_call')
        bookkeeping = self._clock()
        frame = {'input_faces': len(mesh.faces), 'input_vertices': len(mesh.vertices),
                 'input_edge_hints': len(mesh.edges), 'association_edges': None,
                 'topology_components': None, 'certified_components': None,
                 'cache': None, 'negative_cache_hit': False,
                 'topology_counter_complete': False, 'direction_counter_groups': 0,
                 'counts': {}, 'stages_ns': dict.fromkeys(STAGES, 0),
                 'stage_entries': dict.fromkeys(STAGES, 0)}
        self.current = frame
        started = self._clock()
        self.recording_windows_ns += started - bookkeeping
        try:
            yield
        finally:
            ended = self._clock()
            if self.active_stage is not None:
                raise RuntimeError('diagnostic_unclosed_stage')
            frame['function_total_ns'] = ended - started
            covered = sum(frame['stages_ns'].values())
            frame['stages_ns']['other'] = frame['function_total_ns'] - covered
            if frame['stages_ns']['other'] < 0:
                raise RuntimeError('diagnostic_overlapping_stages')
            self.calls.append(frame)
            self.current = None
            self.recording_windows_ns += self._clock() - ended

    @contextmanager
    def span(self, stage):
        bookkeeping = self._clock()
        if self.current is None or self.active_stage is not None or stage == 'other':
            raise RuntimeError('diagnostic_overlapping_or_unknown_stage')
        if stage not in STAGES:
            raise RuntimeError('diagnostic_unknown_stage')
        self.active_stage = stage
        self.current['stage_entries'][stage] += 1
        started = self._clock()
        self.recording_windows_ns += started - bookkeeping
        try:
            yield
        finally:
            ended = self._clock()
            self.current['stages_ns'][stage] += ended - started
            self.active_stage = None
            self.recording_windows_ns += self._clock() - ended

    def topology_complete(self, faces, edges, components):
        """Count completed original loops without observing individual edges."""
        started = self._clock()
        frame = self.current
        frame['association_edges'] = edges
        frame['topology_components'] = components
        frame['topology_counter_complete'] = True
        frame['counts'].update({
            'np_roll_calls': faces, 'face_rows': faces, 'directed_edge_keys': 3 * faces,
            'edge_faces_setdefault': 3 * faces, 'incident_appends': 3 * faces,
            'oriented_get': 3 * faces, 'oriented_set': 3 * faces,
            'manifold_edge_visits': edges, 'manifold_oriented_reads': edges,
            'union_edge_visits': edges, 'union_parent_writes': edges,
            'group_setdefault': faces, 'group_appends': faces,
            'find_calls_derived': 2 * edges + faces,
        })
        self.recording_windows_ns += self._clock() - started

    def direction_complete(self, edges, group_faces, directions):
        """Use the completed closed-triangle component's exact edge incidence."""
        started = self._clock()
        frame = self.current
        frame['direction_counter_groups'] += 1
        own_edges = 3 * group_faces // 2
        updates = {'component_all_edge_visits': edges, 'component_membership_checks': edges,
                   'global_normal_entries': group_faces, 'direction_angle_tests_derived': own_edges,
                   'global_normal_reads_derived': 2 * own_edges, 'direction_appends': directions}
        for name, value in updates.items():
            frame['counts'][name] = frame['counts'].get(name, 0) + value
        self.recording_windows_ns += self._clock() - started

    def cache_hit(self, value):
        started = self._clock()
        frame = self.current
        frame['cache'] = 'hit'
        frame['negative_cache_hit'] = value is None
        frame['counts']['cache_hits'] = 1
        frame['certified_components'] = None if value is None else len(value)
        frame['return_kind'] = 'negative' if value is None else 'components'
        self.recording_windows_ns += self._clock() - started

    def cache_miss(self):
        started = self._clock()
        self.current['cache'] = 'miss'
        self.current['counts']['cache_misses'] = 1
        self.recording_windows_ns += self._clock() - started

    def result(self, value):
        started = self._clock()
        self.current['certified_components'] = None if value is None else len(value)
        self.current['return_kind'] = 'negative' if value is None else 'components'
        self.recording_windows_ns += self._clock() - started

    def snapshot(self):
        if self.current is not None:
            raise RuntimeError('diagnostic_snapshot_during_call')
        calls = copy.deepcopy(self.calls)
        totals = {}
        for frame in calls:
            counts = frame['counts']
            entries = frame['stage_entries']
            topology = ('complete' if frame['topology_counter_complete'] else
                        'incomplete' if entries['topology_components'] else 'not_entered')
            direction = ('complete' if frame['direction_counter_groups'] == entries['direction_index'] else
                         'incomplete') if entries['direction_index'] else 'not_entered'
            frame['counter_coverage'] = {'topology': topology, 'direction': direction}
            frame['counts_incomplete'] = topology == 'incomplete' or direction == 'incomplete'
            frame['unmeasured_counts'] = ['find_path_compression_iterations',
                                          'find_parent_array_reads', 'find_parent_array_writes']
            for name, value in counts.items():
                totals[name] = totals.get(name, 0) + value
        return {
            'calls': calls, 'call_count': len(calls), 'counts': totals,
            'counts_complete': all(not row['counts_incomplete'] for row in calls),
            'stages_ns': {stage: sum(row['stages_ns'][stage] for row in calls) for stage in STAGES},
            'function_total_ns': sum(row['function_total_ns'] for row in calls),
            'instrumentation': {
                'trace_clock_reads': self.clock_reads,
                'clock_calibration': copy.deepcopy(self.clock_calibration),
                'measured_bookkeeping_windows_ns': self.recording_windows_ns,
                'window_scope': 'overlapping stage time, partial recorder windows and clock cost',
                'unmeasured_tax': 'argument construction, generator/context dispatch and some final updates',
                'rtt_correction_applied': False,
            },
        }


def _qa_call(method, *arguments):
    return ast.Call(func=ast.Attribute(value=ast.Name(id=RECORDER_NAME, ctx=ast.Load()),
                                       attr=method, ctx=ast.Load()),
                    args=[ast.Constant(value) if isinstance(value, str) else value
                          for value in arguments], keywords=[])


def _event(method, *arguments):
    return ast.Expr(value=_qa_call(method, *arguments))


def _length(name):
    return ast.Call(func=ast.Name(id='len', ctx=ast.Load()),
                    args=[ast.Name(id=name, ctx=ast.Load())], keywords=[])


def _span(stage, statements):
    return ast.With(items=[ast.withitem(context_expr=_qa_call('span', stage), optional_vars=None)],
                    body=statements, type_comment=None)


class StripInstrumentation(ast.NodeTransformer):
    """Remove only declared recorder syntax, independently of phase selection."""

    @staticmethod
    def _recorder_method(node):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == RECORDER_NAME):
            return node.func.attr
        return None

    def visit_With(self, node):
        if (len(node.items) == 1 and node.items[0].optional_vars is None
                and self._recorder_method(node.items[0].context_expr) in ('call', 'span')):
            statements = []
            for statement in node.body:
                value = self.visit(statement)
                if isinstance(value, list):
                    statements.extend(value)
                elif value is not None:
                    statements.append(value)
            return statements
        return self.generic_visit(node)

    def visit_Expr(self, node):
        if self._recorder_method(node.value) in (
                'topology_complete', 'direction_complete', 'cache_hit', 'cache_miss', 'result'):
            return None
        return self.generic_visit(node)


def build_diagnostic(module, source_blob):
    """Return (clone, AST/code/source proof, recorder) from guarded 326 bytes."""
    guards = [finder for finder in sys.meta_path
              if getattr(finder, 'protocol', None) == 'human-eye-verified-source-v1']
    if len(guards) != 1:
        raise ValueError('diagnostic_requires_one_source_guard')
    guard = guards[0]
    if (Path(module.__file__).resolve() != guard.root / SOURCE_PATH
            or guard.sources.get(SOURCE_PATH) != source_blob
            or guard._executed.get(id(module)) != (module, SOURCE_PATH)):
        raise ValueError('diagnostic_source_binding')
    if RECORDER_NAME in module.__dict__:
        raise ValueError('diagnostic_recorder_name_collision')
    tree = ast.parse(source_blob, filename=str(guard.root / SOURCE_PATH))
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_convex_shells']
    if len(matches) != 1:
        raise ValueError('diagnostic_function_anchor')
    original = matches[0]
    original_dump = ast.dump(original, include_attributes=False)
    expected = ast.parse(EXPECTED_FUNCTION).body[0]
    if original_dump != ast.dump(expected, include_attributes=False):
        raise ValueError('diagnostic_unexpected_original_ast')
    clone_node = copy.deepcopy(original)
    docstring, token, cached, hit, faces, vertices, result, body_try, cache_write, returned = clone_node.body
    hit.body.insert(0, _event('cache_hit', copy.deepcopy(hit.body[0].value)))
    closure_check, parents, find, edges, oriented, face_loop, manifold, union, groups, grouping, result_list, winding, components = body_try.body

    numeric = components.body[:17]
    direction = components.body[17:20]
    remaining_numeric = components.body[20:]
    components.body = [_span('numeric_certification', numeric),
                       _span('direction_index', direction),
                       _event('direction_complete', _length('edge_faces'),
                              _length('ids'), _length('directions')),
                       _span('numeric_certification', remaining_numeric)]
    body_try.body = [
        _span('closure', [closure_check]),
        _span('topology_components', [parents, find, edges, oriented, face_loop,
              manifold, union, groups, grouping, result_list, winding]),
        _event('topology_complete', _length('faces'), _length('edge_faces'), _length('groups')),
        components,
    ]
    call_body = [_span('token_cache', [token, cached, hit]), _event('cache_miss'),
                 _span('closure', [faces, vertices, result]), body_try, cache_write,
                 _event('result', ast.Name(id='result', ctx=ast.Load())), returned]
    clone_node.body = [docstring, ast.With(items=[ast.withitem(
        context_expr=_qa_call('call', ast.Name(id='mesh', ctx=ast.Load())), optional_vars=None)],
        body=call_body, type_comment=None)]
    stripped = StripInstrumentation().visit(copy.deepcopy(clone_node))
    stripped_dump = ast.dump(stripped, include_attributes=False)
    if stripped_dump != original_dump:
        raise ValueError('diagnostic_strip_ast_mismatch')
    recorder = Recorder()
    namespace = dict(module.__dict__)
    namespace[RECORDER_NAME] = recorder
    futures = [copy.deepcopy(node) for node in tree.body
               if isinstance(node, ast.ImportFrom) and node.module == '__future__']
    generated = ast.fix_missing_locations(ast.Module(body=futures + [clone_node], type_ignores=[]))
    filename = str(guard.root / SOURCE_PATH) + ':PERF030_003_QA_DIAGNOSTIC'
    exec(compile(generated, filename, 'exec', dont_inherit=True), namespace)
    clone = namespace['_convex_shells']
    proof = {
        'source_path': SOURCE_PATH, 'source_sha256': hashlib.sha256(source_blob).hexdigest(),
        'original_function_ast_sha256': hashlib.sha256(original_dump.encode()).hexdigest(),
        'stripped_function_ast_sha256': hashlib.sha256(stripped_dump.encode()).hexdigest(),
        'strip_ast_equal': True,
        'diagnostic_ast_sha256': hashlib.sha256(ast.dump(clone_node, include_attributes=False).encode()).hexdigest(),
        'diagnostic_code_sha256': hashlib.sha256(marshal.dumps(clone.__code__)).hexdigest(),
        'diagnostic_filename': filename, 'stage_names': list(STAGES),
        'direction_mixed_numerical_selection': True,
        'gate_credit_scope': 'topology_components_only',
        'counter_basis': 'completed original loops and closed triangular-manifold incidence',
        'counter_event_scope': 'one event after full topology and one after each completed direction group',
        'find_path_compression_iterations': 'not_measured',
        'stage_scope': {
            'token_cache': 'full token, cached lookup, cached decision/return',
            'closure': 'faces/vertices array preparation, result seed, is_closed_hull guard',
            'topology_components': 'parents/find, oriented incidence/manifold, union and groups',
            'numeric_certification': 'per-group ids through convex test, edge axes and result append',
            'direction_index': 'global_normals/directions, full-edge scan including retained dot/threshold/vector work',
            'other': 'exclusive remainder, including loop dispatch, catch and cache publication',
        },
        'instrumentation_scope': 'QA clone with original statements/conditions and removable recorder calls',
        'calibration_per_reset': {'pairs': 16, 'clock_reads': 34},
    }
    return clone, proof, recorder
