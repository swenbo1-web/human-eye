"""Independent pixel regressions for bounded scanline coordinates."""
import unittest
import warnings

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.scene_rendering import _SceneRasterizer,_raster_with_owners


SIZE=256
FACES=[[0,3,2],[0,2,1],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
       [1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]]
REAL_VIEW=np.array([[.8,.6,0.,-8.601554071931687e-18],
    [-.3086974532565159,.41159660434202117,.8574929257125441,-.008146182532327554],
    [.5144957554275265,-.6859943405700353,.5144957554275265,-.25987480549024633],
    [0.,0.,0.,1.]])
REAL_PROJECTION=np.array([[2.460747202960564,0.,0.,0.],[0.,2.460747202960564,0.,0.],
    [0.,0.,-1.493442150576139,-.19947537204609112],[0.,0.,-1.,0.]])

def mesh(identity,vertices,faces,color=(128,128,128)):
    return MeshEntity3D.from_dict({'object_id':identity,'mark_label':identity,'name':identity,
        'vertices':vertices,'faces':faces,'color_rgb':color,'local_axes':np.eye(3).tolist()})

def box(identity,x,y,z0,z1,color):
    return mesh(identity,[[-x,-y,z0],[x,-y,z0],[x,y,z0],[-x,y,z0],
        [-x,-y,z1],[x,-y,z1],[x,y,z1],[-x,y,z1]],FACES,color)

def real_meshes():
    # Exact captured numeric values, kept self-contained for installed tests.
    return [box('blue',.019999999552965164,.014999999664723873,
                .004000000189989805,.028999999165534973,(13,64,229)),
            box('base',.05999999865889549,.04500000178813934,
                -.009999999776482582,0.,(128,128,128))]

def projected_triangle(points,identity='triangle'):
    return mesh(identity,[[2*x/(SIZE-1)-1,1-2*y/(SIZE-1),-1.] for x,y in points],[[0,1,2]])

def render(values,view=None,projection=None):
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter('always')
        color,depth,owners=_raster_with_owners(_SceneRasterizer(SIZE),values,
            np.eye(4) if view is None else view,np.eye(4) if projection is None else projection,SIZE)
    return color,depth,owners,[str(item.message) for item in recorded if issubclass(item.category,RuntimeWarning)]

def reference(values,view=None,projection=None):
    """Full-triangle barycentric raster; no scanline division or int32 cast."""
    view=np.eye(4) if view is None else view
    projection=np.eye(4) if projection is None else projection
    depth=np.full((SIZE,SIZE),np.inf);owner=np.full((SIZE,SIZE),-1,dtype=np.int32)
    for index,value in enumerate(values):
        camera=np.c_[value.vertices,np.ones(len(value.vertices))]@view.T
        clip=camera@projection.T
        screen=np.c_[(clip[:,0]/clip[:,3]+1)*(SIZE-1)/2,
                     (1-clip[:,1]/clip[:,3])*(SIZE-1)/2]
        for face in value.faces:
            a,b,c=screen[face]
            denominator=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(denominator)<1e-4:continue
            low=np.maximum(np.floor(np.minimum(np.minimum(a,b),c)).astype(np.int64),0)
            high=np.minimum(np.ceil(np.maximum(np.maximum(a,b),c)).astype(np.int64),SIZE-1)
            if np.any(low>high):continue
            x,y=np.meshgrid(np.arange(low[0],high[0]+1)+.5,np.arange(low[1],high[1]+1)+.5)
            l0=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denominator
            l1=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denominator
            l2=1-l0-l1
            inside=(l0>=-1e-5)&(l1>=-1e-5)&(l2>=-1e-5)
            w=clip[face,3];z=-camera[face,2]
            reciprocal=l0/w[0]+l1/w[1]+l2/w[2]
            candidate=(l0*z[0]/w[0]+l1*z[1]/w[1]+l2*z[2]/w[2])/np.where(abs(reciprocal)>1e-30,reciprocal,1.)
            target=depth[low[1]:high[1]+1,low[0]:high[0]+1]
            wins=inside&(candidate<target-1e-12)
            target[wins]=candidate[wins]
            owner[low[1]:high[1]+1,low[0]:high[0]+1][wins]=index
    return depth,owner

class RasterRowBoundTests(unittest.TestCase):
    def assert_reference(self,values,view=None,projection=None):
        _,actual,owners,messages=render(values,view,projection)
        expected,expected_owners=reference(values,view,projection)
        self.assertEqual(messages,[],'Finite screen geometry must not emit numeric cast warnings')
        np.testing.assert_array_equal(np.isfinite(actual),np.isfinite(expected))
        visible=np.isfinite(expected)
        np.testing.assert_allclose(actual[visible],expected[visible],atol=1e-12,rtol=0)
        np.testing.assert_array_equal(owners,expected_owners)

    def test_real_four_interior_base_pixels_are_present(self):
        _,depth,owners,_=render(real_meshes(),REAL_VIEW,REAL_PROJECTION)
        for x,y in [(107,99),(105,100),(103,101),(101,102)]:
            with self.subTest(pixel=(x,y)):
                self.assertTrue(np.isfinite(depth[y,x]),'Original supplied base surface must be rendered')
                self.assertEqual(owners[y,x],1)

    def test_real_captured_scene_matches_independent_full_triangle_reference(self):
        self.assert_reference(real_meshes(),REAL_VIEW,REAL_PROJECTION)

    def test_positive_and_negative_nearly_horizontal_edges_beyond_int32(self):
        for slope in (1e-5,-1e-5):
            for mirror_x in (False,True):
                for mirror_y in (False,True):
                    with self.subTest(slope=slope,mirror_x=mirror_x,mirror_y=mirror_y):
                        points=[(32.,48.),(224.,48.+slope),(128.,220.)]
                        points=[(255-x if mirror_x else x,255-y if mirror_y else y) for x,y in points]
                        self.assert_reference([projected_triangle(points)])

    def test_tiny_coefficients_on_both_sides_of_near_zero_gate(self):
        for slope in (1e-7,-1e-7,1e-9,-1e-9):
            with self.subTest(slope=slope):
                self.assert_reference([projected_triangle([(32.,48.),(224.,48.+slope),(128.,220.)])])

    def test_regular_triangle_depth_and_coverage_are_unchanged(self):
        self.assert_reference([projected_triangle([(25.,35.),(222.,56.),(63.,221.)])])

    def test_half_pixel_edge_inclusion_is_preserved(self):
        self.assert_reference([projected_triangle([(32.5,32.5),(220.5,32.5),(32.5,220.5)])])

    def test_screen_edge_sentinels_do_not_wrap_or_expand_coverage(self):
        for points in [[(-70.,30.),(320.,30.+1e-5),(128.,220.)],
                       [(30.,-60.),(30.+1e-5,310.),(220.,128.)]]:
            with self.subTest(points=points):self.assert_reference([projected_triangle(points)])

    def test_equal_depth_keeps_first_object_owner(self):
        points=[(25.,35.),(222.,56.),(63.,221.)]
        self.assert_reference([projected_triangle(points,'first'),projected_triangle(points,'second')])

if __name__=='__main__':unittest.main()
