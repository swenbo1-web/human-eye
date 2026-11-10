"""Pure grouping/authorization tests; never prepare or run a consumer/backend."""
import copy
import importlib.util
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('_consumption_group_driver',HERE/'driver.py')
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)


def plan_fixture():
    installed={profile:{'source_sha256':source,'source_count':137,
        'commit':driver.COMMIT_BY_PROFILE[profile],'dependency_python':'synthetic-common-python'}
        for profile,source in driver.SOURCE_BY_PROFILE.items()}
    return {'cycle_id':driver.CYCLE,'batch':driver.CYCLE,
        'installation_ready':installed['P0'],'installations':installed,
        'arms':{'N':{'actor_group':'N','installation_profile':'P0','source_sha256':None},
            'P0':{'actor_group':'P','installation_profile':'P0','source_sha256':driver.SOURCE_BY_PROFILE['P0']},
            'P1':{'actor_group':'P','installation_profile':'P1','source_sha256':driver.SOURCE_BY_PROFILE['P1']}},
        'image_count':1,'new_images':0,'sequence':[
            {'cell':'lrc'+str(index+1).zfill(2),'round':index//3+1,'task':'T1','group':group}
            for index,group in enumerate(driver.GROUP_ORDER)]}


class GroupContractTests(unittest.TestCase):
    def setUp(self):
        self.forbidden_attempts=[]
        def forbidden(*args,**kwargs):
            self.forbidden_attempts.append('process_system_or_network')
            raise AssertionError('synthetic grouping tests forbid external operations')
        for owner,name in ((driver.subprocess,'Popen'),(driver.os,'system'),
                           (socket,'socket'),(socket,'create_connection')):
            guard=patch.object(owner,name,side_effect=forbidden)
            guard.start();self.addCleanup(guard.stop)

    def tearDown(self):
        self.assertEqual(self.forbidden_attempts,[])

    def test_three_external_arms_map_to_two_internal_profiles_without_mutating_slots(self):
        plan=plan_fixture()
        for slot in plan['sequence']:
            original=copy.deepcopy(slot)
            internal,ready,profile=driver.arm_runtime(plan,slot)
            self.assertEqual(slot,original)
            self.assertIsNot(slot,internal)
            self.assertEqual(internal['group'],'N' if slot['group']=='N' else 'P')
            self.assertEqual(internal['external_group'],slot['group'])
            self.assertEqual(profile,'P1' if slot['group']=='P1' else 'P0')
            self.assertEqual(ready['source_sha256'],driver.SOURCE_BY_PROFILE[profile])

    def test_nine_slot_GO_is_bound_to_new_cycle_and_frozen_order(self):
        plan=plan_fixture();digest='a'*64
        go={'task':driver.CYCLE,'authorized':True,'plan_sha256':digest,'max_consumers':9}
        driver.go_contract(go,plan,digest)
        for changes in ({'task':'M4-OBSERVATION-BASELINE-001','max_consumers':6},
                        {'max_consumers':6},{'plan_sha256':'b'*64}):
            with self.subTest(changes=changes),self.assertRaises(AssertionError):
                driver.go_contract({**go,**changes},plan,digest)
        reordered=copy.deepcopy(plan)
        reordered['sequence'][0]['group'],reordered['sequence'][1]['group']='P0','N'
        with self.assertRaises(AssertionError):driver.go_contract(go,reordered,digest)

    def test_source_and_common_dependency_drift_are_rejected(self):
        plan=plan_fixture();slot=plan['sequence'][2]
        bad=copy.deepcopy(plan);bad['arms']['P1']['source_sha256']=driver.SOURCE_BY_PROFILE['P0']
        with self.assertRaises(AssertionError):driver.arm_runtime(bad,slot)
        bad=copy.deepcopy(plan);bad['installations']['P1']['dependency_python']='different-synthetic-python'
        with self.assertRaises(AssertionError):driver.arm_runtime(bad,slot)
        bad=copy.deepcopy(plan);bad['arms']['P1']['actor_group']='N'
        with self.assertRaises(AssertionError):driver.arm_runtime(bad,slot)


if __name__=='__main__':unittest.main(verbosity=2)
