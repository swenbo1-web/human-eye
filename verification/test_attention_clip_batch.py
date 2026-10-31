"""Independent boundary and ordering checks for batched face classification."""
import unittest
from unittest.mock import patch
import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import attention_raster as raster
from human_eye_plugin.scene_rendering import _projection


class BatchedClipTests(unittest.TestCase):
    def setUp(self):
        self.projection=_projection('orthographic',1,.08,10)

    def mesh(self,triangles,oid='m',color=(150,100,70)):
        ndc=np.asarray(triangles,dtype=float).reshape(-1,3)
        inv=np.linalg.inv(self.projection)
        vertices=(np.c_[ndc,np.ones(len(ndc))]@inv.T)[:,:3]
        return MeshEntity3D(oid,'#'+oid,oid,vertices,
            np.arange(len(vertices)).reshape(-1,3),None,color,False)

    def test_each_common_outside_plane_rejects_before_shading_or_clipping(self):
        triangles=[]
        for axis in range(3):
            for sign in (-1,1):
                t=np.array([[-.2,-.2,0],[.2,-.2,0],[0,.2,0]])
                t[:,axis]=sign*2
                triangles.append(t)
        with (patch.object(raster,'_clip_polygon',side_effect=AssertionError('outside face clipped')),
                patch.object(raster,'_raster_triangle',side_effect=AssertionError('outside face rasterized'))):
            color,depth,owner=raster.rasterize_attention([self.mesh(triangles)],np.eye(4),self.projection,64,return_owner=True)
        self.assertTrue(np.all(np.isinf(depth)))
        self.assertTrue(np.all(owner==-1))
        self.assertTrue(np.all(color==(18,22,30)))

    def test_faces_outside_different_planes_are_clipped_not_rejected(self):
        # Every vertex is outside, but they share no outside plane. The middle
        # of this triangle still covers the viewport and must not disappear.
        mesh=self.mesh([[[-3,-2,0],[3,-2,0],[0,3,0]]])
        with patch.object(raster,'_clip_polygon',wraps=raster._clip_polygon) as clipped:
            _,depth,owner=raster.rasterize_attention([mesh],np.eye(4),self.projection,64,return_owner=True)
        self.assertEqual(clipped.call_count,1)
        self.assertTrue(np.isfinite(depth[31,31]))
        self.assertEqual(owner[31,31],0)

    def test_exact_clip_plane_equalities_stay_inside(self):
        self.projection=np.diag([1.,1.,-1.,1.])
        triangles=[]
        for z in (-1.,1.):
            triangles.append([[-1,-1,z],[1,-1,z],[0,1,z]])
        with patch.object(raster,'_clip_polygon',side_effect=AssertionError('inside boundary clipped')):
            _,depth=raster.rasterize_attention([self.mesh(triangles)],np.eye(4),self.projection,64)
        self.assertEqual(depth[31,31],1.)

    def test_equal_depth_owner_keeps_original_mesh_enumeration(self):
        t=[[[-1,-1,0],[1,-1,0],[0,1,0]]]
        a,b=self.mesh(t,'a',(240,0,0)),self.mesh(t,'b',(0,0,240))
        color,_,owner=raster.rasterize_attention([a,b],np.eye(4),self.projection,64,return_owner=True)
        self.assertEqual(owner[31,31],0)
        self.assertGreater(color[31,31,0],0)
        self.assertEqual(color[31,31,2],0)
        reverse,_,_=raster.rasterize_attention([b,a],np.eye(4),self.projection,64,return_owner=True)
        self.assertGreater(reverse[31,31,2],0)
        self.assertEqual(reverse[31,31,0],0)

    def test_inside_faces_still_charge_existing_pixel_budget(self):
        mesh=self.mesh([[[-1,-1,0],[1,-1,0],[0,1,0]]])
        with patch.object(raster,'MAX_PIXEL_SAMPLES',1):
            with self.assertRaisesRegex(ValueError,'pixel work budget exceeded'):
                raster.rasterize_attention([mesh],np.eye(4),self.projection,64)


if __name__=='__main__':unittest.main()
