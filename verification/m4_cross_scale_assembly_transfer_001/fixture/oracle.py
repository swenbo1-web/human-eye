"""Bind the previous real terminal export and recompute the assembly task truth."""

from fractions import Fraction as F
from hashlib import sha256
import json
from math import sqrt
from pathlib import Path
import runpy


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
RUN = Path('D:/he_m4_assembly_evidence_consumption_001')
ORIGIN = V / 'm4_assembly_evidence_consumption_001'
CONTROLS = V / 'm4_cross_scale_cold_frustum_001/checks/frustum_controls.py'
PREVIOUS_ORACLE = V / 'm4_cross_scale_live_task_001/fixture/oracle.py'
ASSET = RUN / 'slots/A1/native/input.blend'
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
TERMINAL = RUN / 'slots/A1/TERMINAL_SOURCE.json'
TERMINAL_SHA = '81c84f4d7273cd9045702c7afb95b9c8fc21b02764106ff9d8289c7120e0964c'
COUNTS = {'objects': 28, 'vertices': 416, 'triangles': 744}
MINIMUM, MAXIMUM, MIN_NZ = F(1, 40), F(1, 20), F(3, 4)
COMPLETE = {'N10': ('TOP',), 'N11': (), 'N22': ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write(name, value):
    with (HERE / name).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def union_area(polygons):
    """Exact union of the clipped 2D fronts using slabs at all line crossings."""
    # Projected triangles can share edges and overlap. Their individual areas
    # cannot be summed to decide whether any open target surface remains.
    cuts = {p[0] for poly in polygons for p in poly}
    edge_sets = []
    for poly in polygons:
        edges = []
        for a, b in zip(poly, poly[1:] + poly[:1], strict=True):
            if a[0] == b[0]:
                continue
            slope = (b[1] - a[1]) / (b[0] - a[0])
            edges.append((min(a[0], b[0]), max(a[0], b[0]), slope, a[1] - slope * a[0]))
        edge_sets.append(edges)
    edges = [edge for group in edge_sets for edge in group]
    for i, (a, b, m, c) in enumerate(edges):
        for d, e, n, f in edges[:i]:
            if m != n:
                cross_x = (f - c) / (m - n)
                if max(a, d) < cross_x < min(b, e):
                    cuts.add(cross_x)
    xs = sorted(cuts)
    total = F(0)
    for left, right in zip(xs, xs[1:]):
        midpoint = (left + right) / 2
        spans = []
        for group in edge_sets:
            values = [slope * midpoint + intercept for low, high, slope, intercept in group
                      if low < midpoint < high]
            if values:
                spans.append((min(values), max(values)))
        covered_y = F(0)
        end = F(0)
        for low, high in sorted(spans):
            covered_y += max(F(0), high - max(end, low))
            end = max(end, high)
        total += (right - left) * covered_y
    return total


def determine(scene, topology, geometry, occluders):
    objects = [dict(name=row['name'], vertices=[tuple(map(F, point)) for point in row['vertices']],
                    triangles=row['triangles']) for row in scene['objects']]
    components = [row for mesh in objects for row in
                  topology['component_analysis'](mesh['name'], mesh['vertices'], mesh['triangles'])]
    for row in components:
        nx, ny, nz = row['plane_normal_integer']
        row['area_in_domain'] = MINIMUM ** 2 <= row['area_squared_m4'] <= MAXIMUM ** 2
        row['normal_nz_in_domain'] = nz > 0 and nz ** 2 >= MIN_NZ ** 2 * (nx ** 2 + ny ** 2 + nz ** 2)
        row['eligible'] = row['rectangle_supported'] and row['area_in_domain'] and row['normal_nz_in_domain']
    chosen = sorted((row for row in components if row['eligible']), key=lambda row: row['object_name'])
    require(tuple(row['object_name'] for row in chosen) == tuple(COMPLETE), 'independent_eligible_set_differs')
    for row in chosen:
        name = row['object_name']
        require(row['source_triangle_indices'] == [10, 11], 'independent_source_rows_differ/' + name)
        proofs = {}
        for label, direction in topology['VIEWS'].items():
            hits = occluders(objects, row, direction, geometry)
            coverage = union_area([[tuple(map(F, point)) for point in hit['clipped_normalized_polygon']]
                                   for hit in hits])
            require(0 <= coverage <= 1 and bool(hits) == bool(coverage), 'exact_shadow_union_invalid')
            proofs[label] = {'direction': direction, 'tested_other_triangles': COUNTS['triangles'] - 2,
                             'whole_region_clear': not hits, 'positive_area_occluders': hits,
                             'union_blocked_area_fraction': str(coverage),
                             'geometric_coverage': 'clear' if not hits else
                                 'full_positive_depth_shadow' if coverage == 1 else 'partial_positive_depth_shadow'}
        require(tuple(label for label, proof in proofs.items() if proof['whole_region_clear']) == COMPLETE[name],
                'independent_finite_visibility_set_differs/' + name)
        norm = sqrt(sum(x ** 2 for x in row['plane_normal_integer']))
        row.update(area_m2=sqrt(row['area_squared_m4']), unit_normal=[x / norm for x in row['plane_normal_integer']],
                   finite_direction_proofs=proofs, eligible_complete_views=list(COMPLETE[name]),
                   expected_unknown_reason=None if COMPLETE[name] else 'positive_area_occlusion_all_front_views')
    return components, chosen


def main():
    controls = runpy.run_path(str(CONTROLS))
    earlier = runpy.run_path(str(PREVIOUS_ORACLE))
    topology, geometry = earlier['helpers']()
    pins = controls['Pins']()
    for source in (CONTROLS, PREVIOUS_ORACLE, *(V / path for path in earlier['SOURCES'])):
        pins.bytes(source)
    pins.bytes(TERMINAL, TERMINAL_SHA)
    scene, receipt, bound = controls['sealed_capture'](pins, RUN, ORIGIN, ASSET_SHA, (28, 416, 744, 188))
    terminal = bound('TERMINAL_SOURCE.json')
    require('m4-live-assembly-terminal-source-v1' == terminal['schema'] and
            len(terminal['display_object_mask']) == COUNTS['objects'] and all(terminal['display_object_mask']),
            'wrong_geometry_domain_or_display')
    components, chosen = determine(scene, topology, geometry, earlier['occluders'])
    rectangles = sum(row['rectangle_supported'] for row in components)
    require(rectangles == 188, 'independent_rectangle_denominator_differs')
    source_pins = sorted(pins.entries.values(), key=lambda pin: pin['path'])
    binding = {'schema': 'm4-assembly-transfer-original-asset-v1',
               'asset_path': str(ASSET.resolve()), 'asset_sha256': ASSET_SHA, 'counts': COUNTS,
               'archived_terminal': {'path': str(TERMINAL.resolve()), 'sha256': TERMINAL_SHA,
                                     'bytes': TERMINAL.stat().st_size},
               'terminal_provenance': receipt, 'source_pins': source_pins}
    truth = {'schema': 'm4-assembly-transfer-exact-current-truth-v1',
             'passed': True, 'current_blender_evaluated_readback': True,
             'asset_path': binding['asset_path'], 'asset_sha256': ASSET_SHA, 'terminal_source_sha256': TERMINAL_SHA,
             'counts': COUNTS, 'component_count': len(components), 'rectangles': rectangles,
             'directions': topology['VIEWS'], 'eligible': topology['rational_json'](chosen),
             'conditions': {'area_min_m2': 0.025, 'area_max_m2': 0.05, 'normal_z_min': 0.75},
             'geometry_scope': 'Exact entire captured geometry and positive-depth projected overlap; pixel evidence uses actual current frames.',
             'source_pins': source_pins}
    write('ASSET_BINDING.json', binding)
    write('CURRENT_TRUTH.json', truth)
    print(json.dumps({row['object_name']: {
        'center': [str(v) for v in row['center_world_m']], 'area': row['area_m2'],
        'normal': row['unit_normal'], 'clear': row['eligible_complete_views'],
        'blocked': {k: proof['union_blocked_area_fraction'] for k, proof in row['finite_direction_proofs'].items()}}
        for row in chosen}, sort_keys=True))


if __name__ == '__main__':
    main()
