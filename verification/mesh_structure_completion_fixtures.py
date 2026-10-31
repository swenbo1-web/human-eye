"""Independent literal oracles frozen before M1-02 category completion.

Winding unknown witnesses are endpoint pairs, resolved to actual raw edge IDs
by the verifier. Face and vertex groups retain original indices. No welding.
"""
from copy import deepcopy


def fixtures():
    def c(name,vertices,polygons,expected,unknown=None):
        return dict(id=name,vertices=vertices,edges=[],polygons=polygons,
                    expected=expected,unknown=unknown or {})
    quad=[[0,0,0],[1,0,0],[1,1,0],[0,1,0]]
    ring=[[0,1],[1,2],[2,3],[0,3]]
    tetra=[[0,2,1],[0,1,3],[1,2,3],[2,0,3]]
    return deepcopy([
        c('signed_zero_and_equal_numeric_groups',[[0.,0,0],[-0.,0.,0],[1,2,3],[1.,2.,3.],[0,0,2.**-20]],[],
          {'duplicate_positions':[[0,1],[2,3]],'duplicate_polygons':[],'winding_conflicts':[]}),
        c('near_positions_stay_distinct',[[0,0,0],[2.**-20,0,0]],[],{'duplicate_positions':[]}),
        c('rotated_same_direction_duplicate',quad,[[0,1,2,3],[2,3,0,1]],
          {'duplicate_positions':[],'duplicate_polygons':[[0,1]],'winding_conflicts':[ring]}),
        c('reversed_duplicate',quad,[[0,1,2,3],[0,3,2,1]],
          {'duplicate_polygons':[[0,1]],'winding_conflicts':[]}),
        c('three_equivalent_polygons',quad,[[0,1,2,3],[2,3,0,1],[0,3,2,1]],
          {'duplicate_polygons':[[0,1,2]],'winding_conflicts':[]},unknown={'winding_conflicts':ring}),
        c('same_vertex_set_different_cycle',quad,[[0,1,2,3],[0,2,1,3]],
          {'duplicate_polygons':[],'winding_conflicts':[[[0,3]]]}),
        c('coincident_disjoint_indices',quad+quad,[[0,1,2,3],[4,5,6,7]],
          {'duplicate_positions':[[0,4],[1,5],[2,6],[3,7]],'duplicate_polygons':[],'winding_conflicts':[]}),
        c('distinct_duplicate_classes_share_edge',[[0,0,0],[1,0,0],[0,1,0],[0,-1,0]],
          [[0,1,2],[1,2,0],[0,1,3],[3,0,1]],
          {'duplicate_polygons':[[0,1],[2,3]],'winding_conflicts':[[[1,2],[0,2],[1,3],[0,3]]]},
          unknown={'winding_conflicts':[[0,1]]}),
        c('two_disconnected_winding_clusters',quad+[[x+3,y,z] for x,y,z in quad],
          [[0,1,2],[0,3,2],[4,5,6],[4,7,6]],
          {'winding_conflicts':[[[0,2]],[[4,6]]],'duplicate_polygons':[]}),
        c('connected_winding_edges',[[0,0,0],[1,0,0],[1,1,0],[0,1,0],[-1,1,0]],
          [[0,1,2],[0,3,2],[0,3,4]],{'winding_conflicts':[[[0,2],[0,3]]]}),
        c('nonmanifold_orientation_unknown',[[0,0,0],[1,0,0],[0,1,0],[0,-1,0],[0,0,1]],
          [[0,1,2],[1,0,3],[0,1,4]],{'winding_conflicts':[]},unknown={'winding_conflicts':[[0,1]]}),
        c('globally_reversed_closed_shell',[[0,0,0],[1,0,0],[0,1,0],[0,0,1]],
          [p[::-1] for p in tetra],{'winding_conflicts':[],'duplicate_polygons':[]}),
        c('one_reversed_face_closed_shell',[[0,0,0],[1,0,0],[0,1,0],[0,0,1]],
          [tetra[0][::-1]]+tetra[1:],{'winding_conflicts':[[[0,1],[0,2],[1,2]]]}),
        c('empty_completion',[],[],{'duplicate_positions':[],'duplicate_polygons':[],'winding_conflicts':[]}),
    ])
