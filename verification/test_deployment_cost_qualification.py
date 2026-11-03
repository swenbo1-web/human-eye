"""Independent bookkeeping guards for the finite deployment experiment."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('deployment_cost',Path(__file__).with_name('run_deployment_cost_qualification.py'))
cost=importlib.util.module_from_spec(spec)
spec.loader.exec_module(cost)


class CostBookkeepingTests(unittest.TestCase):
    def test_nearest_rank_small_sample_is_maximum(self):
        self.assertEqual(cost.nearest_rank(list(range(1,9))),8)
        self.assertEqual(cost.nearest_rank(list(range(1,25))),23)
        with self.assertRaises(ValueError):cost.nearest_rank([])

    def test_finite_balanced_interleaving(self):
        orders=[cost.order(i) for i in range(cost.PAIRS)]
        self.assertEqual(orders.count(('old','candidate')),4)
        self.assertEqual(orders.count(('candidate','old')),4)

    def test_strict_wire_rejects_duplicate_and_nonfinite(self):
        for raw in ('{"id":1,"id":2}','{"n":NaN}','{"n":Infinity}'):
            with self.assertRaises(ValueError):cost.strict_loads(raw)

    def test_stopped_attempt_not_success_latency(self):
        rows=[dict(arm='old',pair=0,lane='tcp',status='stopped',full_ns=99),
              dict(arm='old',pair=1,lane='tcp',status='completed',full_ns=10),
              dict(arm='candidate',pair=1,lane='tcp',status='completed',full_ns=13)]
        metric=cost.summarize(rows)['tcp.full_ns']
        self.assertEqual(metric['old']['n'],1)
        self.assertEqual(metric['paired']['delta_median_ns'],3)
        self.assertAlmostEqual(metric['paired']['relative_median_percent'],30)
        self.assertEqual(len(rows),3)

    def test_identity_count_and_source_kind_both_pinned(self):
        identity=dict(source_sha256=cost.ARMS['candidate']['sha'],source_file_count=124,
                      source_kind='installed_distribution')
        cost.validate_identity(identity,'candidate')
        for key,value in [('source_sha256','x'),('source_file_count',78),('source_kind','checkout')]:
            changed={**identity,key:value}
            with self.assertRaises(ValueError):cost.validate_identity(changed,'candidate')

    def test_full_manifest_and_summary_both_bind_count(self):
        identity=dict(source_sha256=cost.ARMS['old']['sha'],source_files=[{}]*78,
                      source_kind='installed_distribution')
        cost.validate_identity(identity,'old')
        with self.assertRaises(ValueError):
            cost.validate_identity({**identity,'source_file_count':124},'old')

    def test_native_projection_cannot_pass_native_lane(self):
        import json
        identity=dict(source_sha256=cost.ARMS['old']['sha'],source_file_count=78,
                      source_kind='installed_distribution')
        metadata=dict(runtime_identity=identity,status='observed',signed_clearance_m=.004,
                      visual_delivery=dict(source='analytical_projection',status='delivered'))
        response=dict(result=dict(isError=False,content=[dict(type='text',text=json.dumps(metadata))]))
        self.assertEqual(cost.check_tool(response,'old','cold_native')[0],'unsupported_native_image')
        self.assertEqual(cost.check_tool(response,'old','ordinary_gap_text')[0],'passed')


if __name__=='__main__':unittest.main()
