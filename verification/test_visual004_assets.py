"""Independent analytic certificates; no Blender, renderer or Human Eye call."""
import copy,math,tempfile,unittest
from pathlib import Path
from verification import visual004_assets as a

def distance2d(point,left,right):
    vx,vy=right[0]-left[0],right[1]-left[1]
    t=max(0.,min(1.,((point[0]-left[0])*vx+(point[1]-left[1])*vy)/(vx*vx+vy*vy)))
    return math.hypot(point[0]-left[0]-t*vx,point[1]-left[1]-t*vy)

def segments_distance(p,q,r,s):
    def orient(x,y,z):return (y[0]-x[0])*(z[1]-x[1])-(y[1]-x[1])*(z[0]-x[0])
    if orient(p,q,r)*orient(p,q,s)<0 and orient(r,s,p)*orient(r,s,q)<0:return 0.
    return min(distance2d(p,r,s),distance2d(q,r,s),distance2d(r,p,q),distance2d(s,p,q))

def polygon_minimum(first,second):
    return min(segments_distance(first[i],first[(i+1)%len(first)],second[j],second[(j+1)%len(second)])
        for i in range(len(first)) for j in range(len(second)))

class AssetContractTests(unittest.TestCase):
    def setUp(self):self.cases={case['case_id']:case for case in a.cases()}
    def role(self,case,role):return next(obj for obj in self.cases[case]['objects'] if obj['private_role']==role)
    def test_exact_six_fixed_strata_and_no_public_answer_names_or_values(self):
        self.assertEqual(list(self.cases),['V01','V02','V03','V04','V05','V06'])
        for case in self.cases.values():
            public=case['public'];truth=case['private_truth']
            self.assertEqual(set(public['required_roles']),set(truth['expected_objects']))
            self.assertEqual(set(public['required_fact_ids']),set(truth['facts']))
            self.assertFalse(any(name in public['question'] for name in truth['expected_objects'].values()))
            self.assertTrue(all(obj['name'].startswith('Object_') for obj in case['objects']))
            self.assertEqual(len({obj['name'] for obj in case['objects']}),len(case['objects']))
            self.assertGreaterEqual(len(case['objects']),10)
            self.assertNotIn('expected_objects',public)
    def test_deterministic_complete_geometry_seed_and_neutral_names(self):
        self.assertEqual(a.blob(a.cases()),a.blob(a.cases()))
        for index,case in enumerate(self.cases.values()):self.assertEqual(case['seed'],a.SEED+index)
    def test_L_to_U_gap_is_complete_polygon_boundary_minimum(self):
        target=self.role('V01','target');reference=self.role('V01','reference')
        first=[p[:2] for p in target['vertices'][:6]];second=[p[:2] for p in reference['vertices'][:8]]
        self.assertAlmostEqual(polygon_minimum(first,second),.0015,places=12)
    def test_projected_overlap_has_y_plane_separation(self):
        first=self.role('V02','target')['vertices'];second=self.role('V02','reference')['vertices']
        self.assertAlmostEqual(min(p[1] for p in second)-max(p[1] for p in first),.04,places=12)
        # Frozen witness is in both XZ footprints, giving an attainable lower
        # bound from the strictly separated parallel Y slabs.
        witness=self.cases['V02']['private_truth']['analytic_certificate']['closest_points']
        self.assertEqual(witness[0][::2],witness[1][::2])
        self.assertTrue(.35<witness[0][2]<.6)
    def test_annulus_all_inner_walls_strictly_contain_pin_and_unique_minimum(self):
        target=self.role('V03','target')['vertices'];center=(.4,.1)
        clearances=[]
        for index in range(16):
            normal=(math.cos(index*2*math.pi/16),math.sin(index*2*math.pi/16))
            support=max(normal[0]*(p[0]-center[0])+normal[1]*(p[1]-center[1]) for p in target)
            clearances.append(.09-support)
        self.assertTrue(all(value>0 for value in clearances))
        self.assertAlmostEqual(min(clearances),.003,places=12)
        self.assertEqual([i for i,value in enumerate(clearances) if abs(value-.003)<1e-12],[0])
        expected=self.cases['V03']['private_truth']['analytic_certificate']['all_wall_support_clearances_m']
        for actual,wanted in zip(clearances,expected):self.assertAlmostEqual(actual,wanted,places=12)
    def test_octagon_U_full_edge_set_microgap_and_opposite_gap(self):
        target=[p[:2] for p in self.role('V04','target')['vertices'][:8]]
        reference=[p[:2] for p in self.role('V04','reference')['vertices'][:8]]
        self.assertAlmostEqual(polygon_minimum(target,reference),.0008,places=12)
        self.assertAlmostEqual(.104-max(p[0] for p in target),.004,places=12)
        edge_distances=[min(segments_distance(target[i],target[(i+1)%8],reference[j],reference[(j+1)%8]) for i in range(8)) for j in range(8)]
        self.assertEqual([i for i,value in enumerate(edge_distances) if abs(value-.0008)<1e-12],[5])
    def test_overview_aabb_direction_and_vertical_clearance(self):
        def bounds(role):
            points=self.role('V05',role)['vertices']
            return [min(p[k] for p in points) for k in range(3)],[max(p[k] for p in points) for k in range(3)]
        lo,hi=bounds('target');rlo,rhi=bounds('reference');third_lo,_=bounds('third')
        signs=['+' if (lo[k]+hi[k])>(rlo[k]+rhi[k]) else '-' for k in range(3)]
        self.assertEqual(signs,['+','-','-']);self.assertAlmostEqual(third_lo[2]-hi[2],.55,places=12)
        self.assertGreater(third_lo[0]-hi[0],0.)
    def test_enclosed_core_complete_geometry_answer_not_forced_unknown(self):
        target=self.role('V06','target')['vertices'];lo=[-.5,-.5,.2];hi=[.5,.5,.8]
        self.assertTrue(all(all(lo[k]<p[k]<hi[k] for k in range(3)) for p in target))
        margins=[min(min(p[k]-lo[k] for p in target),min(hi[k]-p[k] for p in target)) for k in range(3)]
        self.assertAlmostEqual(min(margins),.02,places=12)
        truth=self.cases['V06']['private_truth']
        self.assertIsNone(truth['unknown_by_modality']['external_images_only']['gap'])
        self.assertTrue(truth['unknown_by_modality']['complete_mesh']['full_answer'])
    def test_all_meshes_closed_edges_and_no_private_metadata_in_object_names(self):
        for case in [*self.cases.values(),a.calibration_spec()]:
            for obj in case['objects']:
                edges={}
                for face in obj['faces']:
                    self.assertGreaterEqual(len(face),3)
                    for first,second in zip(face,face[1:]+face[:1]):
                        key=tuple(sorted((first,second)));edges[key]=edges.get(key,0)+1
                self.assertTrue(all(value==2 for value in edges.values()),obj['name'])
    def test_freeze_cannot_overwrite_or_ignore_parameter_change(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);a.freeze(root);self.assertEqual(a.verify(root)['case_ids'],list(self.cases))
            with self.assertRaises(FileExistsError):a.freeze(root)
            path=root/'V03/SCENE_SPEC.json';path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'case_member_changed'):a.verify(root)
    def test_calibration_not_a_formal_question_or_private_target(self):
        calibration=a.calibration_spec();self.assertEqual(len(calibration['objects']),4)
        self.assertNotIn('public',calibration);self.assertNotIn('private_truth',calibration)

if __name__=='__main__':unittest.main()
