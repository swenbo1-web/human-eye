"""Independent adequacy gates must reject easy false positive baselines."""
import ast
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from verification.engineering_baseline_cases import cases,digest,validate_facts
from verification.run_native_engineering_preflight import verify_worker_asset,complete_preflight,pixel_check


class NativeEngineeringPreflightTests(unittest.TestCase):
    def setUp(self):
        self.cases=cases();self.case=next(c for c in self.cases if c['id']=='nonplanar_clear')
        self.value=dict(status='observed',damage='not_inferred',facts=copy.deepcopy(self.case['expected']))

    def test_eight_assets_are_stable_and_task_bound(self):
        self.assertEqual(len(self.cases),8)
        self.assertEqual(digest(self.cases),digest(cases()))
        for case in self.cases:
            verify_worker_asset({k:case[k] for k in ('id','objects','task','asset_task_sha256')})

    def test_exact_source_facts_pass_but_missing_member_fails(self):
        self.assertTrue(validate_facts(self.case,self.value))
        self.value['facts']['boundary_edges'][0].pop()
        with self.assertRaisesRegex(ValueError,'source_members'):validate_facts(self.case,self.value)

    def test_component_merge_does_not_pass_matching_total(self):
        groups=self.value['facts']['boundary_edges'];self.value['facts']['boundary_edges']=[groups[0]+groups[1]]
        with self.assertRaisesRegex(ValueError,'components'):validate_facts(self.case,self.value)

    def test_unknown_and_missing_are_not_zero(self):
        for mutation in ('missing','unknown','none'):
            value=copy.deepcopy(self.value)
            if mutation=='missing':del value['facts']['loose_edges']
            elif mutation=='unknown':value['facts']['loose_edges']=None
            else:value=None
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):validate_facts(self.case,value)

    def test_boolean_and_float_source_indices_are_not_integers(self):
        for fake in (True,0.):
            value=copy.deepcopy(self.value);value['facts']['boundary_edges'][0][0][0]=fake
            with self.subTest(index=fake),self.assertRaises(ValueError):validate_facts(self.case,value)

    def test_damage_inference_cannot_pass_structural_truth(self):
        self.value['damage']='detected'
        with self.assertRaisesRegex(ValueError,'facts'):validate_facts(self.case,self.value)

    def test_input_hash_and_private_truth_rejected(self):
        value={k:copy.deepcopy(self.case[k]) for k in ('id','objects','task','asset_task_sha256')}
        value['task']['anchor_world_bu'][0]+=1
        with self.assertRaisesRegex(ValueError,'changed'):verify_worker_asset(value)
        value={k:self.case[k] for k in ('id','objects','task','asset_task_sha256')};value['expected']=self.case['expected']
        with self.assertRaisesRegex(ValueError,'private_oracle'):verify_worker_asset(value)

    def test_unknown_duplicate_and_missing_task_stay_in_denominator(self):
        rows=[dict(round=r,case=c['id'],quality_passed=True) for r in range(3) for c in self.cases]
        processes=[dict(exit_code=0,reaped=True,timed_out=False) for _ in range(3)]
        self.assertTrue(complete_preflight(self.cases,rows,processes,3))
        missing=rows[:-1];self.assertFalse(complete_preflight(self.cases,missing,processes,3))
        duplicate=copy.deepcopy(rows);duplicate[-1]=copy.deepcopy(rows[0])
        self.assertFalse(complete_preflight(self.cases,duplicate,processes,3))
        unknown=copy.deepcopy(rows);unknown[0]['quality_passed']=None
        self.assertFalse(complete_preflight(self.cases,unknown,processes,3))
        self.assertFalse(complete_preflight(self.cases,rows[:8],processes[:1],1))

    def test_native_program_has_no_HE_or_fixture_imports(self):
        source=Path(__file__).with_name('native_engineering_baseline.py').read_text()
        names=[]
        for node in ast.walk(ast.parse(source)):
            if isinstance(node,ast.Import):names.extend(alias.name for alias in node.names)
            elif isinstance(node,ast.ImportFrom):names.append(node.module or '')
        self.assertTrue({'bpy','bmesh','mathutils'}<=set(names))
        self.assertFalse(any(name.startswith(('human_eye','verification')) for name in names))

    def test_all_blue_pixels_do_not_prove_an_opening(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'flat.png';Image.new('RGBA',(384,384),(10,40,210,255)).save(path)
            frame=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                actual_ortho_scale=.25,span=.25,location=[1.,0.,0.],right=[0.,0.,-1.],up=[0.,1.,0.],direction=[1.,0.,0.],
                camera_matrix=[[0.,0.,1.,1.],[0.,1.,0.,0.],[-1.,0.,0.,0.],[0.,0.,0.,1.]])
            value={'images':[frame]}
            self.assertEqual(pixel_check(self.case,value)['readable_pairs'],0)
            frame['camera_matrix'][0][0]=1.
            with self.assertRaisesRegex(ValueError,'basis'):pixel_check(self.case,value)

    def test_missing_occluder_is_detected_as_false_visible(self):
        from PIL import Image,ImageDraw
        case=next(c for c in self.cases if c['id']=='center_blocked')
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'missing_occluder.png';picture=Image.new('RGBA',(384,384),(10,40,210,255))
            ImageDraw.Draw(picture).rectangle((161,38,222,345),fill=(0,0,0,255));picture.save(path)
            frame=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                actual_ortho_scale=.25,span=.25,location=[1.,0.,0.],right=[0.,0.,-1.],up=[0.,1.,0.],direction=[1.,0.,0.],
                camera_matrix=[[0.,0.,1.,1.],[0.,1.,0.,0.],[-1.,0.,0.,0.],[0.,0.,0.,1.]])
            result=pixel_check(case,dict(images=[frame]))
            self.assertEqual(result['readable_pairs'],12)
            self.assertEqual(result['false_visible'],2)


if __name__=='__main__':unittest.main()
