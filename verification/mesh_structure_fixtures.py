"""Hand-authored M1 oracles, independent of the future diagnostic algorithm.

Indices refer to input vertices/polygons. Edge witnesses use endpoint pairs;
the Blender reader must resolve them to actual source edge indices. No welding.
Only the categories listed in each oracle are scored; missing is NOT normal.
"""
from __future__ import annotations

from copy import deepcopy

CATEGORIES = (
    'boundary_edges', 'nonmanifold_edges', 'nonmanifold_vertices',
    'isolated_vertices', 'loose_edges', 'duplicate_positions',
    'degenerate_polygons', 'duplicate_polygons', 'winding_conflicts',
)
NOT_CHECKED = ('self_intersection', 'near_coincident_surfaces', 'surface_damage',
               'rig_pose', 'skin_deformation')


def fixtures():
    def case(name, vertices, polygons, expected, edges=()):
        return dict(id=name, vertices=vertices, edges=list(edges), polygons=polygons,
                    expected=expected, damage_truth='not_inferable_from_structure')

    quad = [[0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.]]
    ring = [[0, 1], [1, 2], [2, 3], [0, 3]]
    cases = [
        case('closed_tetra', [[0,0,0],[1,0,0],[0,1,0],[0,0,1]],
             [[0,2,1],[0,1,3],[1,2,3],[2,0,3]], {c: [] for c in CATEGORIES}),
        case('legal_open_quad', quad, [[0,1,2,3]],
             {**{c: [] for c in CATEGORIES}, 'boundary_edges': [ring]}),
        case('two_open_components', quad + [[x+3,y,z] for x,y,z in quad],
             [[0,1,2,3],[4,5,6,7]],
             {**{c: [] for c in CATEGORIES},
              'boundary_edges': [ring, [[4,5],[5,6],[6,7],[4,7]]]}),
        case('bow_tie_vertex', [[0,0,0],[1,0,0],[0,1,0],[-1,0,0],[0,-1,0]],
             [[0,1,2],[0,3,4]],
             {'boundary_edges': [[[0,1],[1,2],[0,2],[0,3],[3,4],[0,4]]],
              'nonmanifold_edges': [], 'nonmanifold_vertices': [[0]]}),
        case('three_faces_one_edge', [[0,0,0],[1,0,0],[0,1,0],[0,-1,0],[0,0,1]],
             [[0,1,2],[1,0,3],[0,1,4]],
             {'nonmanifold_edges': [[[0,1]]], 'nonmanifold_vertices': [[0,1]]}),
        case('isolated_vertex', quad + [[9,9,9]], [[0,1,2,3]],
             {'isolated_vertices': [[4]], 'loose_edges': [], 'boundary_edges': [ring]}),
        case('loose_edge', quad + [[2,0,0],[3,0,0]], [[0,1,2,3]],
             {'loose_edges': [[[4,5]]], 'isolated_vertices': [], 'boundary_edges': [ring]},
             edges=[[4,5]]),
        case('unwelded_duplicate_position', [[0,0,0],[1,0,0],[0,1,0],
                                          [0,0,0],[-1,0,0],[0,-1,0]],
             [[0,1,2],[3,4,5]],
             {'duplicate_positions': [[0,3]], 'nonmanifold_vertices': [],
              'boundary_edges': [[[0,1],[1,2],[0,2]],[[3,4],[4,5],[3,5]]]}),
        case('zero_area_triangle', [[0,0,0],[1,0,0],[2,0,0]], [[0,1,2]],
             {'degenerate_polygons': [[0]]}),
        case('duplicate_polygon', [[0,0,0],[1,0,0],[0,1,0]], [[0,1,2],[0,1,2]],
             {'duplicate_polygons': [[0,1]], 'boundary_edges': [],
              'winding_conflicts': [[[0,1],[1,2],[0,2]]]}),
        case('winding_conflict', quad, [[0,1,2],[0,3,2]],
             {'winding_conflicts': [[[0,2]]], 'nonmanifold_edges': []}),
        case('concave_ngon', [[0,0,0],[2,0,0],[2,2,0],[1,1,0],[0,2,0]],
             [[0,1,2,3,4]], {'boundary_edges': [[[0,1],[1,2],[2,3],[3,4],[0,4]]],
                               'degenerate_polygons': []}),
        case('vertices_only', [[0,0,0],[1,0,0]], [],
             {'isolated_vertices': [[0],[1]], 'boundary_edges': [], 'loose_edges': []}),
        case('empty_mesh', [], [], {c: [] for c in CATEGORIES}),
    ]
    return deepcopy(cases)


def grid(n):
    """Open analytic sheet for read-cost gradients, not an algorithm oracle."""
    return dict(id=f'grid_{n}',
                vertices=[[i/n, j/n, 0.] for j in range(n+1) for i in range(n+1)],
                polygons=[[j*(n+1)+i, j*(n+1)+i+1,
                           (j+1)*(n+1)+i+1, (j+1)*(n+1)+i]
                          for j in range(n) for i in range(n)], edges=[])
