"""Independent static source/AST audit only; does not import candidate code."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path

AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE = AUTHOR / 'verification/m4_triangulation_invariant_discovery_001'
HERE = Path(__file__).resolve().parent
INPUTS = []
CHECKS = []


def source(path):
    raw = path.read_bytes()
    INPUTS.append({'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    return raw.decode('utf-8-sig')


def check(name, passed, evidence=None):
    CHECKS.append({'name': name, 'passed': bool(passed), 'evidence': evidence})


def calls(fn, name):
    return [n for n in ast.walk(fn) if isinstance(n, ast.Call) and ast.unparse(n.func) == name]


def work_increments(fn):
    result = Counter()
    for n in ast.walk(fn):
        if (isinstance(n, ast.AugAssign) and isinstance(n.op, ast.Add)
                and isinstance(n.target, ast.Subscript) and ast.unparse(n.target.value) == 'work'
                and isinstance(n.target.slice, ast.Constant) and isinstance(n.value, ast.Constant)
                and type(n.value.value) is int):
            result[n.target.slice.value] += n.value.value
    return dict(result)


text = source(BASE / 'discovery.py')
core = source(AUTHOR / 'verification/m4_active_coverage_001/coverage.py')
engineering = source(BASE / 'engineering.py')
source(BASE / 'SIMPLIFICATION_REVIEW.md')
source(BASE / 'review/DISCOVERY_STATIC_SELF_REVIEW.md')
tree = ast.parse(text)
fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
core_fns = {n.name: n for n in ast.parse(core).body if isinstance(n, ast.FunctionDef)}
check('candidate_source_sha', INPUTS[0]['sha256'] == 'd048852ffaa114d67eccc0b42451eebef7e00bbe8760d108574ae9eaa5439fe7')
check('old_core_sha', INPUTS[1]['sha256'] == '2561ecaf2f2df98ec7c03ed48cb95dd08c34f10ce73c1e9ecc2e32f31c41daf4')
check('engineering_source_sha', INPUTS[2]['sha256'] == '739648f76fe603b4857dcf30c73f06c10a98e6af32207c1daa091afa19017583')
check('parse_uses_geometry_once', len(calls(fns['parse_geometry'], 'legacy.geometry')) == 1)
check('top_entry_parses_once', len(calls(fns['build_index'], 'parse_geometry')) == 1)
check('top_entry_builds_from_parsed_once', len(calls(fns['build_index'], 'build_from_parsed')) == 1)
check('parsed_entry_discovers_once', len(calls(fns['build_from_parsed'], 'regions_from_objects')) == 1)
check('parsed_entry_covers_once', len(calls(fns['build_from_parsed'], 'build_index_from_parsed')) == 1)
check('parsed_entry_no_legacy_geometry', not calls(fns['build_from_parsed'], 'legacy.geometry'))
for name in ('regions_from_objects', 'build_from_parsed', 'build_index'):
    fn = fns[name]
    defaults = {arg.arg: ast.literal_eval(value) for arg, value in zip(fn.args.args[-len(fn.args.defaults):], fn.args.defaults)}
    check(name + ':explicit_reference_default', defaults.get('discovery_variant') == 'reference', defaults)
clone = fns['build_index_from_parsed']
rebindings = {}
for node in ast.walk(clone):
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Subscript) and ast.unparse(target.value) == 'namespace':
                rebindings[ast.literal_eval(target.slice)] = ast.unparse(node.value)
check('private_globals_only_geometry_regions', set(rebindings) == {'geometry', 'regions_from_objects'}, rebindings)
check('private_globals_copied', len(calls(clone, 'legacy.build_index.__globals__.copy')) == 1)
ctor = calls(clone, 'types.FunctionType')
check('same_old_code_ctor', len(ctor) == 1 and ast.unparse(ctor[0].args[0]) == 'legacy.build_index.__code__')
check('same_old_defaults_closure', [ast.unparse(n) for n in ctor[0].args[3:]] == ['legacy.build_index.__defaults__', 'legacy.build_index.__closure__'])
entry = calls(clone, 'entry')
check('one_optimized_entry', len(entry) == 1 and {k.arg: ast.literal_eval(k.value) for k in entry[0].keywords} == {'variant': 'optimized'})
check('entry_receives_no_scene_to_reparse', ast.literal_eval(entry[0].args[0]) is None)
check('legacy_geometry_and_regions_sites_single', len(calls(core_fns['build_index'], 'geometry')) == len(calls(core_fns['build_index'], 'regions_from_objects')) == 1)

reference = fns['_reference_area']
candidate = fns['_candidate_area']
ri, ci = work_increments(reference), work_increments(candidate)
for key, expected in [('area_rational_multiply_calls', 9), ('area_rational_subtract_calls', 9), ('area_rational_add_calls', 6)]:
    check('reference_counter:' + key, ri.get(key) == expected)
for key, expected in [('area_rational_multiply_calls', 2), ('area_rational_subtract_calls', 5), ('area_rational_add_calls', 1)]:
    check('candidate_counter:' + key, ci.get(key) == expected)
check('reference_cross_dot_once_per_face', len(calls(reference, 'cross')) == len(calls(reference, 'dot')) == 1)
check('candidate_no_full_cross_or_dot_in_area', not calls(candidate, 'cross') and not calls(candidate, 'dot'))
check('cyclic_axis_pairs', '((1, 2), (2, 0), (0, 1))[axis]' in ast.unparse(candidate))
check('candidate_sign_relative_to_plane', '(signed_area > 0) != positive_front' in ast.unparse(candidate))
check('candidate_nonzero_axis_selected', 'next((index for index, value in enumerate(plane_normal) if value))' in ast.unparse(candidate))
discover = fns['regions_from_objects']
try_node = next(n for n in ast.walk(discover) if isinstance(n, ast.Try))
area_branch = try_node.body[1]
check('topology_precedes_selected_area_then_boundary',
      isinstance(try_node.body[0], ast.Assign) and ast.unparse(try_node.body[0].value.func) == '_topology'
      and isinstance(area_branch, ast.If)
      and ast.unparse(area_branch.body[0].value.func) == '_reference_area'
      and ast.unparse(area_branch.orelse[0].value.func) == '_candidate_area'
      and isinstance(try_node.body[2], ast.Assign) and ast.unparse(try_node.body[2].value.func) == '_rectangle_boundary')
check('full_source_face_indices_preserved', 'tuple(range(len(faces)))' in ast.unparse(discover))
check('same_ROI_fingerprint', "'roi_' + legacy.fingerprint(quad)[:24]" in ast.unparse(discover))
check('candidate_expected_area_scalar', '2 * normal[axis]' in ast.unparse(discover))
check('reference_expected_area_vector', 'tuple((2 * value for value in normal))' in ast.unparse(discover))
check('input_domain_not_rectangle_errors_rejected', len([n for n in ast.walk(discover) if isinstance(n, ast.ExceptHandler) and ast.unparse(n.type) == '_NotRectangle']) == 1)
check('global_ROI_sort_present', len(calls(discover, 'regions.sort')) == 1)
check('work_created_without_stats_gate', any(isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and ast.unparse(n.value.func) == '_work' for n in ast.walk(discover)))
check('engineering_explicit_parse_and_discover', engineering.count('discovery.parse_geometry(scene, stats=stats)') == 1 and engineering.count('discovery.regions_from_objects(objects, discovery_variant=variant, stats=stats)') == 1)

manual = [
    {'topic': 'rectangle_tiling', 'verdict': 'valid_in_declared_domain',
     'basis': 'Internal directed index edges cancel. Every accepted coplanar triangle has the same positive orientation. The one simplified boundary is exactly the rectangle. Thus interior coverage multiplicity is its winding number (one inside, zero outside), excluding positive-area holes/overlaps. Connectivity and boundary-cycle constraints additionally reject disconnected/holed topology.'},
    {'topic': '2D_component_equivalence', 'verdict': 'valid',
     'basis': 'After exact coplanarity each triangle normal is parallel to the nonzero seed normal. Selecting any nonzero seed component preserves zero/nonzero and relative orientation. Summing that component equals the corresponding full-vector area criterion because all summands and the boundary normal lie on the same one-dimensional normal subspace.'},
    {'topic': 'boundary_identity', 'verdict': 'valid',
     'basis': 'Only same-direction collinear internal boundary points are removed; no corner or backtracking point is removed. Lexicographic rotation preserves directed winding. ROI hash and boundary normal use the same canonical quad as the old contract. Geometry identity still changes with real mesh representation.'},
    {'topic': 'complexity', 'verdict': 'bounded_claim',
     'basis': 'Per-object incidence/connectivity/boundary and area are expected O(V+F+B) dictionary/set work. The final R-region sort is O(R log R). Fraction bit costs and old geometry/index sorting remain; no linear whole-index guarantee.'},
    {'topic': 'cost_instrumentation', 'verdict': 'disclose_not_block',
     'basis': 'work dict increments, bit-length collection and clocks remain even when stats=None. Reference/candidate execute different instrumentation in the area loop. The measured wrapper includes this cost; observed wall-time gain cannot be uniquely attributed to arithmetic reduction. This is a concrete productization simplification opportunity, not an error in retained measurements.'},
]
result = {'candidate_commit': 'b638c499c049604902415965f500f50a9947d34f',
          'scope': 'Independent static AST/source audit and mathematical review; no candidate import or business execution.',
          'check_count': len(CHECKS), 'passed': sum(c['passed'] for c in CHECKS),
          'failed': [c for c in CHECKS if not c['passed']], 'checks': CHECKS,
          'reference_area_counter_increments': ri, 'candidate_area_counter_increments': ci,
          'manual_findings': manual, 'candidate_function_calls': 0,
          'new_model_CLI_actor_Blender_raster_calls': 0,
          'author_matrix_or_timing_reruns': 0,
          'offline_static_parser_runs': 2,
          'parser_note': 'Both static runs passed; second made the control-flow ordering assertion inspect direct Try/If execution structure instead of AST traversal ordering.',
          'AL_binding': 'own child handle bound; parent_read_only'}
for name, value in [('INPUTS.json', INPUTS), ('RESULTS.json', result)]:
    (HERE / name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
print(json.dumps({k: result[k] for k in ('check_count','passed','failed','candidate_function_calls')}, ensure_ascii=False))
