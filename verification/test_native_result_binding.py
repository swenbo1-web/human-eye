"""Batch integrity must precede native-baseline numerical/pixel scoring."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from verification.engineering_baseline_cases import cases
from verification import run_native_engineering_preflight as gate


def result(assets,*,pid=123,baseline='a'*64):
    rows=[]
    for asset in assets:
        value=dict(status='observed',damage='not_inferred',facts=copy.deepcopy(asset['expected']),images=[])
        rows.append(dict(case=asset['id'],value=value,error=None,preservation_passed=True,actual_mesh_sha256='b'*64,
            state_before_sha256='c'*64,state_after_sha256='c'*64,input_asset_sha256=asset['asset_task_sha256'],call_wall_ms=1.,scene_preparation_ms=1.))
    return dict(pid=pid,rows=rows,HE_modules_loaded=[],baseline_sha256=baseline,blender_version='5.2.1 LTS')


def corrupt(value,mode):
    if mode=='extra_tail':value['rows'].extend(copy.deepcopy(value['rows'][-1:])*2)
    elif mode=='missing':value['rows'].pop()
    elif mode=='duplicate':value['rows'][-1]=copy.deepcopy(value['rows'][0])
    elif mode=='wrong_id':value['rows'][0]['case']='unregistered'
    elif mode=='reordered':value['rows'].reverse()
    elif mode=='wrong_input':value['rows'][0]['input_asset_sha256']='0'*64
    elif mode=='wrong_input_tail':value['rows'][-1]['input_asset_sha256']='0'*64
    elif mode=='wrong_baseline':value['baseline_sha256']='0'*64
    elif mode=='wrong_pid':value['pid']+=1
    elif mode=='boolean_pid':value['pid']=True
    else:raise AssertionError(mode)
    return value


class NativeResultBindingTests(unittest.TestCase):
    def setUp(self):self.assets=cases()[:2]
    def validate(self,value):return gate.verified_worker_rows(self.assets,value,baseline_sha256='a'*64,pid=123)
    def test_registered_normal_batch_keeps_all_rows_and_quality_separate(self):
        value=result(self.assets);value['rows'][0]['preservation_passed']=False
        self.assertIs(self.validate(value),value['rows'])
        # Quality failure belongs to the unchanged quality gate, not source binding.
    def test_extra_tail_reproduces_the_old_zip_loss_then_is_rejected(self):
        value=corrupt(result(self.assets),'extra_tail')
        self.assertEqual(len(list(zip(self.assets,value['rows']))),len(self.assets))
        with self.assertRaisesRegex(ValueError,'row_count'):self.validate(value)
    def test_missing_rows_rejected_before_any_scoring(self):
        with self.assertRaisesRegex(ValueError,'row_count'):self.validate(corrupt(result(self.assets),'missing'))
    def test_duplicate_reordered_and_wrong_task_ids(self):
        for mode,reason in (('duplicate','duplicate_case'),('reordered','case_order_or_id'),('wrong_id','case_order_or_id')):
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,reason):self.validate(corrupt(result(self.assets),mode))
    def test_input_baseline_and_real_process_bindings(self):
        for mode,reason in (('wrong_input','asset_binding'),('wrong_input_tail','asset_binding'),('wrong_baseline','baseline_binding'),('wrong_pid','process_binding'),('boolean_pid','process_binding')):
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,reason):self.validate(corrupt(result(self.assets),mode))
    def test_registered_duplicate_task_is_rejected(self):
        public=[{k:c[k] for k in ('id','objects','task','asset_task_sha256')} for c in self.assets]
        public.append(copy.deepcopy(public[0]))
        with self.assertRaisesRegex(ValueError,'duplicate_id'):gate.verify_worker_assets(public)
    def test_wrong_registered_input_and_private_oracle_remain_rejected(self):
        public=[{k:copy.deepcopy(c[k]) for k in ('id','objects','task','asset_task_sha256')} for c in self.assets]
        public[0]['task']['object_id']='changed'
        with self.assertRaisesRegex(ValueError,'asset_task_changed'):gate.verify_worker_assets(public)
        public[0]['expected']=dict()
        with self.assertRaisesRegex(ValueError,'private_oracle'):gate.verify_worker_assets(public)
    def test_malformed_row_cannot_reach_downstream_field_access(self):
        value=result(self.assets);del value['rows'][0]['value']
        with self.assertRaisesRegex(ValueError,'row_fields'):self.validate(value)
        for bad in (True,float('nan'),-1):
            value=result(self.assets);value['rows'][0]['call_wall_ms']=bad
            with self.assertRaisesRegex(ValueError,'timing_shape'):self.validate(value)
    def test_HE_contamination_is_not_native_independence(self):
        value=result(self.assets);value['HE_modules_loaded']=['human_eye_plugin']
        with self.assertRaisesRegex(ValueError,'native_independence'):self.validate(value)

    def run_parent(self,mode):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);output=Path(temporary.name)/'new_preflight';launches=[]
        class Process:
            returncode=0
            def __init__(p,command,**kwargs):
                p.pid=1000+len(launches);launches.append(p)
                spec=json.loads(Path(command[-2]).read_text());folder=Path(command[-1]);value=result(self.assets,pid=p.pid,baseline=spec['baseline_sha256'])
                if mode is not None:corrupt(value,mode)
                p.raw=json.dumps(value);p.folder=folder
                (folder/'WORKER_RESULT.json').write_text(p.raw,encoding='utf8')
            def wait(p,timeout=None):return 0
            def poll(p):return 0
        with patch('verification.engineering_baseline_cases.cases',return_value=self.assets),patch.object(gate.subprocess,'Popen',side_effect=Process),\
             patch('verification.engineering_baseline_cases.validate_facts',return_value=True) as scoring,\
             patch.object(gate,'pixel_check',return_value=dict(status='not_scored',readable_pairs=None)) as pixels:
            passed=gate.parent(Path('unused-owned-Blender'),output,3)
        for process in launches:
            self.assertEqual((process.folder/'WORKER_RESULT.json').read_text(encoding='utf8'),process.raw)
            self.assertEqual((process.folder/'WORKER_RESULT_REJECTED.json').exists(),mode is not None)
        return passed,json.loads((output/'RESULT.json').read_text()),scoring.call_count,pixels.call_count

    def test_parent_quarantines_entire_malformed_batch_without_scoring(self):
        for mode in ('extra_tail','missing','duplicate','wrong_id','reordered','wrong_input','wrong_input_tail','wrong_baseline','wrong_pid'):
            with self.subTest(mode=mode):
                passed,value,numerical,pixels=self.run_parent(mode)
                self.assertFalse(passed);self.assertEqual(value['rows'],[]);self.assertEqual((numerical,pixels),(0,0))
                self.assertEqual(value['expected_task_denominator'],3*len(self.assets))
                self.assertTrue(all(p['result_integrity_error'] for p in value['processes']))
    def test_parent_normal_batch_still_runs_unchanged_quality_checks(self):
        passed,value,numerical,pixels=self.run_parent(None)
        self.assertTrue(passed);self.assertEqual(len(value['rows']),6);self.assertEqual((numerical,pixels),(6,6))
        self.assertTrue(all(p['result_integrity_passed'] for p in value['processes']))
        self.assertFalse(value['value_gate_passed']);self.assertFalse(value['release_gate_changed']);self.assertEqual(value['model_trials'],0)


if __name__=='__main__':unittest.main()
