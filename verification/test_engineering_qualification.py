"""Qualification contract negatives; synthetic rows are not physical evidence."""
import base64,copy,hashlib,io,json,struct,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from verification import engineering_qualification as q
from verification.engineering_task_contract import bootstrap
from verification.engineering_evidence import ArchiveCursor,check_images
from verification.engineering_baseline_cases import cases
from verification.test_mesh_structure_runtime import raw_case,identity
from human_eye_plugin import mesh_structure as m


def he_value(name='dense1808'):
    case=next(c for c in cases() if c['id']==name);obj=case['objects'][0]
    raw=raw_case(dict(vertices=obj['world_vertices'],edges=obj.get('edges',[]),polygons=obj['faces']))
    raw['vertices']=[[struct.unpack('<f',struct.pack('<f',x))[0] for x in p] for p in raw['vertices']]
    result=m.analyze_raw(raw,identity(),task_id='test',categories=q.CATEGORIES,region_summaries=True)
    value=dict(diagnostic=result,patch_refs=[dict(category=p['category'],cluster_ordinal=p['cluster_ordinal'],patch_ref=str(i).zfill(32))
        for i,p in enumerate(result['patches'])])
    return case,value


def matrix():
    n=[dict(case=c,round=r,task=t,quality=dict(common_contract_checks_passed=True),lifecycle_passed=True,complete_task_ms=100.)
       for c in q.ASSETS for r in range(3) for t in range(3)]
    h=[dict(case=c,round=0,task=0,quality=dict(common_contract_checks_passed=True),lifecycle_passed=True) for c in q.ASSETS]
    p=[dict(arm=arm,case=c,round=r,host_exit=0,mcp_exit=0,source_unchanged=True,display_restored=True)
       for arm,count in [('native',3),('he',1)] for c in q.ASSETS for r in range(count)]
    return n,h,p


class EligibilityTests(unittest.TestCase):
    def test_complete_bounded_matrix_only_allows_registration(self):
        result=q.eligibility(*matrix());self.assertTrue(result['A2_may_be_registered'])
        for name in ('A2_started','old_global_members_gate_passed','old_release_cost_gate_passed','model_trials_permitted',
                     'strict_full_guarantee_speed_claim_permitted'):self.assertIs(result[name],False)

    def test_missing_duplicate_and_wrong_case_stay_in_denominator(self):
        for change in ('missing','duplicate','other'):
            n,h,p=matrix()
            if change=='missing':n.pop()
            elif change=='duplicate':n[-1]=copy.deepcopy(n[0])
            else:h[0]['case']='not_registered'
            self.assertFalse(q.eligibility(n,h,p)['A2_may_be_registered'])

    def test_first_and_warm_cost_failures_cannot_be_averaged_away(self):
        for task,limit in ((0,3390),(1,2000)):
            n,h,p=matrix();row=next(r for r in n if r['task']==task);row['complete_task_ms']=limit+.001
            self.assertFalse(q.eligibility(n,h,p)['native_cost_reference_passed'])

    def test_invalid_timing_and_lifecycle_refuse(self):
        for value in (True,float('nan'),float('inf'),-1,None):
            n,h,p=matrix();n[0]['complete_task_ms']=value
            self.assertFalse(q.eligibility(n,h,p)['A2_may_be_registered'])
        n,h,p=matrix();h[0]['lifecycle_passed']=False
        self.assertFalse(q.eligibility(n,h,p)['A2_may_be_registered'])

    def test_process_exit_state_and_missing_process_refuse(self):
        for field,value in (('host_exit',1),('mcp_exit',False),('source_unchanged',False),('display_restored',False)):
            n,h,p=matrix();p[0][field]=value
            self.assertFalse(q.eligibility(n,h,p)['process_and_state_passed'])
        n,h,p=matrix();p.pop();self.assertFalse(q.eligibility(n,h,p)['A2_may_be_registered'])

    def test_unknown_quality_is_not_success(self):
        n,h,p=matrix();h[0]['quality']={};self.assertFalse(q.eligibility(n,h,p)['common_contract_checks_passed'])


class PublicTaskTests(unittest.TestCase):
    def test_summary_repairs_positions_without_repairing_legacy_members(self):
        case,value=he_value();norm=q.normalize(value,'he');selected=q.select(norm,[0.,0.,0.])
        result=q.quality(case,norm,selected,dict(status='scored',readable_pairs=12,false_visible=0),2)
        self.assertTrue(result['common_contract_checks_passed']);self.assertFalse(result['old_all_members_passed'])
        self.assertEqual(norm['published_members']['boundary_edges'],8)

    def test_wrong_world_position_cannot_pass_posthoc_source_check(self):
        case,value=he_value();norm=q.normalize(value,'he');norm['regions'][0]['bounds'][0][0]-=1
        with self.assertRaisesRegex(ValueError,'public_positions'):q.quality(case,norm,q.select(norm,[0,0,0]),None,0)

    def test_selected_oversize_and_summary_never_become_renderable(self):
        _,value=he_value();norm=q.normalize(value,'he');remote=next(r for r in norm['regions'] if r['selection_only'])
        anchor=[sum(x)/2 for x in zip(*remote['bounds'])]
        self.assertEqual(q.select(norm,anchor)['status'],'not_localizable')
        remote.update(selection_only=False,patch_ref='a',members=[[i,i+1] for i in range(120)])
        self.assertEqual(q.select(norm,anchor)['status'],'not_localizable')

    def test_pixel_floor_and_false_visible_fail_even_when_counts_are_correct(self):
        case,value=he_value();norm=q.normalize(value,'he');selected=q.select(norm,[0,0,0])
        for pixels in (None,dict(status='scored',readable_pairs=11,false_visible=0),dict(status='scored',readable_pairs=12,false_visible=1)):
            with self.assertRaises(ValueError):q.quality(case,norm,selected,pixels,2)

    def test_blocked_area_cannot_claim_detail(self):
        case,value=he_value('feature_blocked');norm=q.normalize(value,'he')
        with self.assertRaisesRegex(ValueError,'occluded_detail'):
            q.quality(case,norm,q.select(norm,[0,0,0]),dict(status='scored',readable_pairs=0,false_visible=0),2)

    def test_old_protocol_and_duplicate_members_refused(self):
        _,value=he_value();value['diagnostic']['protocol']='raw-mesh-structure-v2'
        with self.assertRaises(ValueError):q.normalize(value,'he')
        with self.assertRaises(ValueError):q.canonical([[0,1],[1,0]],'boundary_edges')


class AdmissionTests(unittest.TestCase):
    def spec(self,root):
        path=root/'registration.json';path.write_text(json.dumps(q.registration()))
        return dict(qualification_registration=str(path),qualification_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            purpose='native_reference',arm='native',case_id='dense1808',asset_task_sha256=q.ASSETS['dense1808'],
            helpers={str(q.ROOT/'verification'/n):hashlib.sha256((q.ROOT/'verification'/n).read_bytes()).hexdigest() for n in q.HELPERS})

    def test_exact_registration_and_fixed_helpers_admit(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(q.admit(self.spec(Path(temporary)))['engine_build'],q.BUILD)

    def test_wrong_purpose_arm_asset_or_helper_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            original=self.spec(Path(temporary))
            for field,value in (('purpose','HE_cost_trial'),('arm','he'),('case_id','unknown'),('asset_task_sha256','0'*64)):
                spec=copy.deepcopy(original);spec[field]=value
                with self.assertRaises(ValueError):q.admit(spec)
            spec=copy.deepcopy(original);key=next(iter(spec['helpers']));spec['helpers'][key]='0'*64
            with self.assertRaisesRegex(ValueError,'helper_changed'):q.admit(spec)

    def test_cannot_relax_costs_even_after_rehashing_registration(self):
        with tempfile.TemporaryDirectory() as temporary:
            spec=self.spec(Path(temporary));path=Path(spec['qualification_registration']);value=json.loads(path.read_text())
            value['first_limit_ms']=100000;path.write_text(json.dumps(value));spec['qualification_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'contract_changed'):q.admit(spec)

    def test_unknown_baseline_fails_before_loading_entry(self):
        with patch('verification.engineering_task_contract.importlib.util.spec_from_file_location',side_effect=AssertionError('unexpected')):
            with self.assertRaisesRegex(ValueError,'unknown_fixed_baseline'):bootstrap('nonexistent',baseline='latest')


class EvidenceTests(unittest.TestCase):
    def image(self):
        from PIL import Image
        stream=io.BytesIO();Image.new('RGBA',(384,384),(0,30,200,255)).save(stream,format='PNG')
        raw=stream.getvalue();data=base64.b64encode(raw).decode();matrix=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
        frame=dict(data=data,sha256=hashlib.sha256(raw).hexdigest(),camera_matrix=matrix,actual_ortho_scale=1.,span=1.,
            right=[1.,0.,0.],up=[0.,1.,0.],direction=[0.,0.,1.],location=[0.,0.,0.])
        return dict(content=[dict(type='image',mimeType='image/png',data=data)]),[dict(native=dict(images=[frame]))]

    def test_cursor_reads_each_new_outer_reply_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'WIRE_0.json').write_text('{"first":1}');cursor=ArchiveCursor(root)
            self.assertEqual(cursor.collect(),[dict(first=1)]);self.assertEqual(cursor.collect(),[])
            (root/'WIRE_1.json').write_text('{"second":2}')
            self.assertEqual(cursor.collect(),[dict(second=2)]);self.assertEqual(cursor.next,2)

    def test_native_original_pixels_and_actual_camera_checked(self):
        reply,wires=self.image();case=next(c for c in cases() if c['id']=='closed_torus')
        with tempfile.TemporaryDirectory() as temporary:
            result=check_images(case,'native',reply,wires,Path(temporary)/'images');self.assertEqual(result['images'],1)
        wires[0]['native']['images'][0]['right']=[0,1,0]
        with tempfile.TemporaryDirectory() as temporary,self.assertRaises(ValueError):
            check_images(case,'native',reply,wires,Path(temporary)/'images')

    def test_native_image_count_hash_and_pixels_tamper_rejected(self):
        case=next(c for c in cases() if c['id']=='closed_torus')
        for change in ('count','hash','pixels'):
            reply,wires=self.image()
            if change=='count':reply['content']=[]
            elif change=='hash':wires[0]['native']['images'][0]['sha256']='0'*64
            else:
                from PIL import Image
                stream=io.BytesIO();Image.new('RGBA',(384,384),(200,0,0,255)).save(stream,format='PNG')
                reply['content'][0]['data']=base64.b64encode(stream.getvalue()).decode()
            with tempfile.TemporaryDirectory() as temporary,self.assertRaises(ValueError):
                check_images(case,'native',reply,wires,Path(temporary)/'images')


if __name__=='__main__':unittest.main()
