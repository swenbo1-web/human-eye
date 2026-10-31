"""Pure same-machine deadline protocol, without Blender or permission grants."""
import copy
from fractions import Fraction
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from human_eye_plugin import forward_deadline as deadline


def binding():
    return {'host_epoch':'a'*32,'document_epoch':'b'*64,'focal_id':'part','reference_id':'base',
            'object_instances':{'part':'instance-part','base':'instance-base'}}


def action():
    return {'focal_id':'part','reference_id':'base','translation':[0.,0.,-.0005],
            'rotation_euler_deg':[0.,0.,0.]}


class ForwardDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.binding=binding();self.action=action()
        self.base=deadline.make_deadline(100.,95.,goal_id='goal-1',binding=self.binding,process_id=123)
        self.args={'action':self.action,'expected_revision':'scene-1','expected_fingerprint':'c'*64,
                   'request_nonce':'d'*32}
        self.wire=deadline.bind_deadline(self.base,**self.args)

    def validate(self, wire=None, **changes):
        args={**self.args,'binding':self.binding,'process_id':123,'goal_id':'goal-1',**changes}
        return deadline.validate_deadline(self.wire if wire is None else wire,**args)

    def test_real_local_qpc_descriptor_is_explicit_and_guarded(self):
        value=deadline.counter_descriptor()
        self.assertEqual(value['source'],'windows_systemwide_qpc')
        self.assertEqual(value['unit'],'ns')
        self.assertEqual(value['implementation'],'QueryPerformanceCounter()')
        self.assertGreaterEqual(value['resolution_ns'],1)
        self.assertGreater(value['guard_ns'],value['resolution_ns'])

    def test_unsupported_platform_and_runtime_refuse(self):
        with patch.object(deadline.sys,'platform','linux'):
            with self.assertRaises(ValueError):deadline.counter_descriptor()
        with patch.object(deadline.sys,'version_info',(3,9,9)):
            with self.assertRaises(ValueError):deadline.counter_descriptor()
        with patch.object(deadline.sys,'implementation',NS(name='pypy')):
            with self.assertRaises(ValueError):deadline.counter_descriptor()

    def test_wrong_adjustable_or_nonmonotonic_clock_refuses(self):
        for changes in ({'implementation':'GetTickCount64()'}, {'monotonic':False},
                        {'adjustable':True}, {'resolution':0.}, {'resolution':math.inf}):
            values={'implementation':'QueryPerformanceCounter()','monotonic':True,'adjustable':False,'resolution':1e-7,**changes}
            with self.subTest(changes=changes),patch.object(deadline.time,'get_clock_info',return_value=NS(**values)):
                with self.assertRaises(ValueError):deadline.counter_descriptor()

    def test_deadline_conversion_rounds_down_exactly(self):
        value=1234.0000000015
        base=deadline.make_deadline(value,value,goal_id='g',binding=self.binding,process_id=1)
        exact=Fraction(value)*1_000_000_000
        self.assertEqual(base['parent_deadline_ns'],exact.numerator//exact.denominator)
        self.assertLessEqual(Fraction(base['parent_deadline_ns']),exact)

    def test_no_expansion_even_when_nanosecond_floor_matches(self):
        with self.assertRaises(ValueError):
            deadline.make_deadline(1.,math.nextafter(1.,math.inf),goal_id='g',binding=self.binding,process_id=1)

    def test_invalid_deadline_numbers_are_not_clamped(self):
        for value in (True,-1.,math.inf,math.nan,'100',None,1<<10000):
            with self.subTest(type=type(value).__name__),self.assertRaises(ValueError):
                deadline.make_deadline(value,value,goal_id='g',binding=self.binding,process_id=1)

    def test_integer_ns_schema_rejects_bool_float_or_overflow(self):
        for value in (True,1.,-1,1<<63):
            bad=copy.deepcopy(self.base);bad['forward_deadline_ns']=value
            with self.subTest(value=value),self.assertRaises(ValueError):deadline.validate_base(bad)

    def test_compact_binding_binds_every_object_without_transmitting_map(self):
        dense=binding()
        dense['object_instances'].update({f'object-{i}':f'instance-{i}' for i in range(254)})
        value=deadline.make_deadline(100.,95.,goal_id='g',binding=dense,process_id=1)
        self.assertNotIn('object_instances',value['binding'])
        self.assertEqual(len(value['binding']['object_instances_sha256']),64)
        self.assertLess(len(json.dumps(value)),1200)
        deadline.validate_base(value,binding=dense,process_id=1,goal_id='g')
        changed=copy.deepcopy(dense);changed['object_instances']['object-253']='new-incarnation'
        with self.assertRaises(ValueError):deadline.validate_base(value,binding=changed)

    def test_binding_dict_order_does_not_change_digest(self):
        other=binding();other['object_instances']=dict(reversed(list(other['object_instances'].items())))
        self.assertEqual(deadline.make_deadline(100.,95.,goal_id='goal-1',binding=other,process_id=123),self.base)

    def test_host_document_and_selected_roles_cannot_change(self):
        for field,value in (('host_epoch','e'*32),('document_epoch','e'*64),('focal_id','base')):
            other=binding();other[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.validate(binding=other)

    def test_process_and_goal_are_bound(self):
        for changes in ({'process_id':124},{'process_id':True},{'goal_id':'other-goal'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.validate(**changes)

    def test_malformed_incarnations_refuse(self):
        for instances in ({'part':'same','base':'same'},{'part':'only'}, {'part':1,'base':'base'},False):
            other=binding();other['object_instances']=instances
            with self.subTest(instances=instances),self.assertRaises(ValueError):
                deadline.make_deadline(100.,95.,goal_id='g',binding=other,process_id=1)

    def test_request_binding_is_detached_and_idempotent(self):
        again=deadline.bind_deadline(self.wire,**self.args)
        self.assertEqual(again,self.wire)
        again['binding']['document_epoch']='e'*64
        self.assertEqual(self.wire['binding']['document_epoch'],'b'*64)
        self.assertEqual(self.validate(),self.wire)

    def test_bound_request_never_rebinds(self):
        for changes in ({'request_nonce':'e'*32},{'expected_revision':'scene-2'},
                        {'expected_fingerprint':'e'*64},{'action':{**self.action,'translation':[0,0,-.0006]}}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.validate(**changes)

    def test_action_roles_and_nonfinite_vectors_refuse(self):
        for changes in ({'focal_id':'other'}, {'reference_id':'part'}, {'translation':[0,0,math.nan]},
                        {'translation':[0,0,True]}, {'translation':[0,0,1<<10000]}, {'code':'arbitrary'}):
            with self.subTest(field=list(changes)),self.assertRaises(ValueError):
                deadline.bind_deadline(self.base,**{**self.args,'action':{**self.action,**changes}})

    def test_tuple_and_list_actions_share_the_wire_json(self):
        tuples={**self.action,'translation':tuple(self.action['translation'])}
        self.assertEqual(deadline.bind_deadline(self.base,**{**self.args,'action':tuples}),self.wire)

    def test_protocol_and_clock_descriptor_cannot_be_forged(self):
        for field,value in (('protocol','other'),('clock',{**self.base['clock'],'guard_ns':0})):
            bad=copy.deepcopy(self.wire);bad[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.validate(bad)

    def test_unknown_envelope_fields_refuse(self):
        bad=copy.deepcopy(self.wire);bad['execution_authority']=True
        with self.assertRaises(ValueError):self.validate(bad)
        bad=copy.deepcopy(self.base);bad['binding']['object_instances']={'part':'p','base':'b'}
        with self.assertRaises(ValueError):deadline.validate_base(bad)

    def test_expiry_uses_guard_and_includes_equal_boundary(self):
        end=self.wire['forward_deadline_ns'];guard=self.wire['clock']['guard_ns']
        self.assertFalse(deadline.expired(self.wire,now_ns=end-guard-1))
        self.assertTrue(deadline.expired(self.wire,now_ns=end-guard))
        self.assertTrue(deadline.expired(self.wire,now_ns=end))
        self.assertTrue(deadline.expired(self.wire,now_ns=end+1_000_000))

    def test_default_expiry_reads_qpc_ns_after_validation(self):
        with patch.object(deadline.time,'perf_counter_ns',return_value=100_000_000_000) as clock:
            self.assertTrue(deadline.expired(self.wire))
        clock.assert_called_once_with()

    def test_expiry_rejects_invalid_current_time(self):
        for value in (True,95.,-1,1<<63):
            with self.subTest(value=value),self.assertRaises(ValueError):deadline.expired(self.wire,now_ns=value)

    def refusal(self, cancelled=False):
        return deadline.build_refusal(self.wire,checked_ns=95_000_000_000,
            cancelled_event_id=self.args['request_nonce']+':forward' if cancelled else None)

    def test_matched_zero_forward_refusal_requires_no_global_world_claim(self):
        for cancelled in (False,True):
            proof=deadline.validate_refusal(self.refusal(cancelled),forward_deadline=self.base,**self.args)
            self.assertFalse(proof['mutation_started']);self.assertFalse(proof['forward_setter_entered'])
            self.assertFalse(proof['retry_authorized'])
            self.assertNotIn('scene_unchanged',proof)
            self.assertEqual(proof['scope'],'bound_forward_request_only')

    def test_cannot_claim_refusal_before_expiry(self):
        with self.assertRaises(ValueError):deadline.build_refusal(self.wire,checked_ns=94_000_000_000)

    def test_cancellation_must_name_current_forward_reservation(self):
        for identity in ('different',self.args['request_nonce']+':rollback',False):
            with self.subTest(identity=identity),self.assertRaises(ValueError):
                deadline.build_refusal(self.wire,checked_ns=95_000_000_000,cancelled_event_id=identity)

    def test_refusal_cannot_conflict_with_bound_request(self):
        for changes in ({'request_nonce':'e'*32},{'expected_revision':'scene-2'},
                        {'expected_fingerprint':'e'*64},{'action':{**self.action,'translation':[0,0,-.0006]}}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                deadline.validate_refusal(self.refusal(),forward_deadline=self.base,**{**self.args,**changes})

    def test_refusal_extra_missing_and_boolean_fields_refuse(self):
        cases=[]
        for key,value in (('source','model'),('mutation_started',0),('checked_ns',True),
                          ('retry_authorized',True),('scope','all-world-writes')):
            case=self.refusal();case['rejection'][key]=value;cases.append(case)
        missing=self.refusal();missing['rejection'].pop('checked_ns');cases.append(missing)
        extra=self.refusal();extra['rejection']['scene_unchanged']=True;cases.append(extra)
        for case in cases:
            with self.subTest(fields=list(case['rejection'])),self.assertRaises(ValueError):
                deadline.validate_refusal(case,forward_deadline=self.wire,**self.args)

    def test_module_import_remains_standalone(self):
        path=Path(deadline.__file__).resolve()
        script='import runpy,sys;runpy.run_path(sys.argv[1]);assert not any(k in sys.modules for k in ("human_eye_plugin","numpy","PIL","bpy"))'
        result=subprocess.run([sys.executable,'-I','-B','-c',script,str(path)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
