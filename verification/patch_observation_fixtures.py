"""Independent finite aperture observation fixtures; not a runtime planner.

An open planar ring has two raw boundary components. The inner four edges are
the requested feature. Analytic opaque rectangles give sample visibility truth
without consulting engine rays, triangulation or a candidate view selector.
"""
from copy import deepcopy


def fixtures():
    common=dict(center=[.5,0.,0.],half=[.02,.1],far=True,
                feature_edges=[[4,5],[5,6],[6,7],[4,7]])
    rows=[
        dict(id='clear_small_feature',blocker=None,visible_samples=12,object_center_visible=True,patch_center_blocked=False,want_detail=True),
        dict(id='object_center_blocked_feature_visible',blocker=[-.1,.1,-.15,.15,.1,.3],visible_samples=12,object_center_visible=False,patch_center_blocked=False,want_detail=True),
        dict(id='patch_center_blocked_edges_visible',blocker=[.494,.506,-.15,.15,.1,.3],visible_samples=10,object_center_visible=True,patch_center_blocked=False,want_detail=True),
        dict(id='object_visible_feature_blocked',blocker=[.46,.54,-.14,.14,.1,.3],visible_samples=0,object_center_visible=True,patch_center_blocked=True,want_detail=False),
        dict(id='fully_blocked',blocker=[-1.2,1.2,-1.2,1.2,.1,.3],visible_samples=0,object_center_visible=False,patch_center_blocked=True,want_detail=False),
        dict(id='overview_already_readable',blocker=None,visible_samples=12,object_center_visible=True,patch_center_blocked=False,want_detail=False,
             half=[.2,.2],far=False),
    ]
    # Explicit correction of the literal named-case center property before this
    # file is frozen: the center strip blocks the hole center, not its edges.
    rows[2]['patch_center_blocked']=True
    return deepcopy([{**common,**row} for row in rows])


def ring(case):
    x,y,z=case['center'];a,b=case['half']
    return dict(vertices=[[-1.,-1.,z],[1.,-1.,z],[1.,1.,z],[-1.,1.,z],
                          [x-a,y-b,z],[x+a,y-b,z],[x+a,y+b,z],[x-a,y+b,z]],
                polygons=[[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]],edges=[])


def edge_samples(case):
    x,y,z=case['center'];a,b=case['half'];result=[]
    for t in (.25,.5,.75):
        result.extend([
            dict(point=[x-a,y-b+2*b*t,z],outside=[-1.,0.,0.]),
            dict(point=[x+a,y-b+2*b*t,z],outside=[1.,0.,0.]),
            dict(point=[x-a+2*a*t,y-b,z],outside=[0.,-1.,0.]),
            dict(point=[x-a+2*a*t,y+b,z],outside=[0.,1.,0.])])
    return result


def analytically_visible(case, point):
    """XY opaque-box projection for these fixed fixtures only."""
    block=case['blocker']
    return not (block is not None and block[0]<=point[0]<=block[1]
                and block[2]<=point[1]<=block[3] and block[5]>point[2])
