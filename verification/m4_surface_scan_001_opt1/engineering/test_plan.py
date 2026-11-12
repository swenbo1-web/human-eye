"""Offline counterexamples for frozen-input checks and paired gate arithmetic."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from itertools import combinations
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from summarize import rows_from_sequences, summarize


def sequence(version, times=(100, 10, 100), life=1000):
    rows = []
    cold_pairs, edit_pairs = {}, {}
    public = []
    from verify_state import object_ids
    names = object_ids(json.loads((common.QUAL/'EDIT_SNAPSHOT.json').read_bytes()))
    moving = next(oid for oid,name in names.items() if name == 'Obj_008')
    others = sorted(oid for oid in names if oid != moving)
    for i, ids in enumerate(list(combinations(others,2))[:104]):
        pair = list(ids)
        key = json.dumps(pair, separators=(',', ':'))
        work = dict(surface_dependency_used=True, surface_dependency_cache_hit=False,
                    surface_dependency_key='same'+str(i))
        cold_pairs[key] = work
        edit_pairs[key] = dict(work, surface_dependency_cache_hit=True)
    for i in range(10):
        pair = sorted([moving,others[i]])
        key = json.dumps(pair, separators=(',', ':'))
        if i < 8:
            cold_pairs[key] = dict(surface_dependency_used=True,
                surface_dependency_cache_hit=False, surface_dependency_key='old'+str(i))
        edit_pairs[key] = dict(surface_dependency_used=True,
            surface_dependency_cache_hit=False, surface_dependency_key='new'+str(i))
        public.append(dict(objects=[dict(id=oid,name=names[oid]) for oid in pair]))
    expected = (112,0,114) if version == 'A' else (112,0,10)
    for state, value, calls in zip(('cold','repeat','edit'), times, expected):
        rows.append(dict(state=state, complete_client_request_ns=int(value*1e6),
            errors=[], verification=dict(passed=True), actual_host_RPC=1,
            body=dict(matches=public), diagnostics=dict(kernel_calls=calls,
                pairs=cold_pairs if state == 'cold' else edit_pairs,
                measurement_cache_after=dict(max_bytes=2*1024*1024,accounted_bytes=1024,measurement_entries=112),
                measurement_cache_max_measurements=256,
                acquisition_work=dict(residency_delta=dict(resource_vertices_read=0,world_vertices_transformed=8)))))
    return dict(passed=True, business=rows, session_wall_ns=int(life*1e6))


class PlanTests(unittest.TestCase):
    def test_qualification_checks_old_committed_promises(self):
        ready, values = common.qualification_binding()
        self.assertEqual(len(values), 9)
        self.assertEqual(ready['counts']['objects'], 24)
        original_sha = common.sha
        def replaced(path):
            return '0'*64 if Path(path).name == 'BASE_TRUTH.json' else original_sha(path)
        with patch.object(common, 'sha', replaced), self.assertRaises(AssertionError):
            common.qualification_binding()

    def test_missing_duplicate_and_failed_rows_keep_thirty_denominator(self):
        self.assertEqual(len(rows_from_sequences({})), 30)
        self.assertTrue(all(row['status'] == 'not_attempted' for row in rows_from_sequences({})))
        old = sequence('A')
        old['business'].append(copy.deepcopy(old['business'][0]))
        table = rows_from_sequences({(1,'A'):old})
        self.assertEqual(sum(row['status']=='duplicate' for row in table), 1)
        self.assertEqual(len(table), 30)
        old = sequence('A')
        old['business'][0]['errors'] = ['request failed']
        self.assertEqual(rows_from_sequences({(1,'A'):old})[0]['status'], 'failed')

    def test_pair_formulas_use_median_of_ratios_and_deltas(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            for i in range(1,6):
                for version in ('A','B'):
                    path = base/('pair_'+str(i).zfill(2))/version
                    path.mkdir(parents=True)
                    times = (100,10,100) if version == 'A' else (101,11,50)
                    value = sequence(version,times,1000 if version == 'A' else 1030)
                    order = ['AB','BA','AB','BA','AB'][i-1]
                    value['started_ns'] = i*10000+order.index(version)*1000
                    (path/'RESULTS.json').write_text(json.dumps(value))
            result = summarize(base)
            self.assertTrue(result['all_gates_passed'], result.get('mechanism_error'))
            self.assertEqual(result['gates']['edit']['limit'], .70)
            self.assertEqual(result['paired_request_costs']['edit']['median_ratio'], .5)
            self.assertEqual(result['gates']['cold']['limit'], 5.)
            self.assertEqual(result['gates']['repeat']['limit'], 2.)
            self.assertFalse(result['lifecycle_net_improvement'])
            path = base/'pair_01/B/RESULTS.json'
            value = json.loads(path.read_bytes())
            value['business'] = value['business'][:1]
            path.write_text(json.dumps(value))
            result = summarize(base)
            self.assertFalse(result['quality_passed'])
            self.assertEqual(result['missing'],2)
            self.assertEqual(result['planned_business_count'],30)

    def test_missing_sequence_returns_failed_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            result = summarize(Path(folder))
            self.assertEqual(result['missing'], 30)
            self.assertEqual(result['actual_business_rows'],0)
            self.assertFalse(result['all_gates_passed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
