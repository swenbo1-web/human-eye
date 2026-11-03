"""Offline entry tests. No product, Blender or model is invoked."""
import ast
import copy
import io
import json
from pathlib import Path
import types
import unittest
from unittest.mock import patch


def legacy_reproductions():
    from verification import region_witness_pilot as old
    tree = ast.parse(Path(old.__file__).read_text(encoding='utf8'))
    dispatch = compile(ast.Module(body=[tree.body[-1]], type_ignores=[]), str(old.__file__), 'exec')
    records = []
    task = {'task': 'offline-original-dispatch'}
    task_sha = old.digest(task)
    base = dict(task_sha256=task_sha, anchors={'f1': 'chosen-one', 'f2': 'chosen-two'}, native_supplement=False)
    cases = [(stage, action) for stage in (1, 2) for action in ('final', 'abstain')]
    cases += [(2, 'empty'), (1, 'early_native')]
    for stage, action in cases:
        response = dict(task_sha256=task_sha, action=action)
        if action == 'empty': response = dict(task_sha256=task_sha, triangle_indices=[])
        if action == 'early_native': response = dict(base, native_supplement=True)
        events = []; writes = {}; calls = []

        def load(path):
            name = Path(path).name
            events.append(['load', name])
            if name == 'PRIVATE_MAPPING.json': return {'anonymous': 'A'}
            if name == 'PHASE%d_RESPONSE.json' % stage: return copy.deepcopy(response)
            if name == 'TASK.json': return copy.deepcopy(task)
            if name in ('BUDGET.json', 'BUDGET_AFTER1.json'):
                return dict(directories=2, facts=0 if stage == 1 else 2, native_supplements=0, stages=stage-1)
            if name == 'MODEL_STARTED.json': return {'unix_ns': 0}
            if name == 'PHASE1_FROZEN.json': return copy.deepcopy(base)
            raise AssertionError('unexpected legacy read: ' + name)

        def save(path, value):
            writes[Path(path).name] = copy.deepcopy(value)
            events.append(['save', Path(path).name])

        def fact_call(*args, **kwargs):
            calls.append(dict(label=args[1], mode=args[2], indices=kwargs.get('indices'), suffix=kwargs.get('suffix', 'fact')))
            events.append(['dispatch', args[1], kwargs.get('suffix', 'fact')])
            return {'status': 'offline-recording-reader'}

        error = None
        with patch.dict(old.__dict__, dict(reg=lambda: ({'frames': [{'label': 'f1'}, {'label': 'f2'}]}, None),
                                          load=load, save=save, fact_call=fact_call,
                                          time=types.SimpleNamespace(time_ns=lambda: 0), __name__='__main__')):
            with patch.object(old.sys, 'argv', [str(old.__file__), 'phase%d' % stage]), patch('sys.stdout', new=io.StringIO()):
                try: exec(dispatch, old.__dict__)
                except (AssertionError, KeyError) as exc: error = type(exc).__name__
        records.append(dict(stage=stage, action=action, error=error, calls=calls, events=events,
                            budget_after=writes.get('BUDGET_AFTER%d.json' % stage),
                            phase3_published='PHASE3_INPUT.json' in writes))
    return records


class LegacyEntryReproduction(unittest.TestCase):
    def test_original_main_rejects_terminal_and_dispatches_empty_and_early_native(self):
        records = legacy_reproductions()
        for result in records[:4]:
            self.assertEqual(result['error'], 'AssertionError')
            self.assertEqual(result['calls'], [])
        empty = records[4]
        self.assertEqual(len(empty['calls']), 2)
        self.assertTrue(all(call['indices'] == [] for call in empty['calls']))
        self.assertEqual(empty['budget_after']['facts'], 4)
        self.assertTrue(empty['phase3_published'])
        early = records[5]
        self.assertEqual(len(early['calls']), 4)
        receipt_delivery = early['events'].index(['save', 'PHASE2_INPUT.json'])
        self.assertLess(early['events'].index(['load', 'PHASE1_RESPONSE.json']), receipt_delivery)
        self.assertLess(early['events'].index(['dispatch', 'f1', 'common_native']), receipt_delivery)


def decision(action, **fields):
    return dict(response=dict(response_id='$response', task_sha256='$task', condition_id='$condition',run_nonce='$run',
                              prompt_id='$prompt', evidence_ref='$evidence', action=action, **fields))


def fixture(steps):
    return dict(schema='offline-region-witness-script-v1',
                task=dict(task_sha256='a'*64, condition_id='offline-one', sources={
                    'f1': dict(file_sha256='b'*64, frame=1, mesh='Mesh', rig='Rig'),
                    'f2': dict(file_sha256='c'*64, frame=25, mesh='Mesh', rig='Rig')}),
                model_steps=copy.deepcopy(steps), reader=dict(
                    base_data=dict(details_omitted=1, state='unknown'),
                    targeted_data=dict(state='measured', triangle=49),
                    supplement_data=dict(state='unknown', reason='numeric_resolution')))


def base_step():
    return decision('base', anchors={'f1':'chosen-one','f2':'chosen-two'})


def gap():
    return dict(pointer='/results/0/receipt/data/details_omitted', kind='omitted', expected=1,
                reason='a required row is omitted in the delivered base evidence')


def through_entry(script):
    from verification.region_witness_control import main
    published = {}
    reserved = []
    code = main(['--script','offline-script.json','--output','offline-result'],
                load_script=lambda path: copy.deepcopy(script),
                reserve_output=lambda path: reserved.append(str(path)),
                publish=lambda path,result: published.update(result))
    assert code == 0 and reserved == ['offline-result']
    return published


class OfflineControlEntry(unittest.TestCase):
    def assert_no_live_calls(self, report):
        self.assertEqual(report['real_model_calls'],0)
        self.assertEqual(report['product_calls'],0)
        self.assertTrue(report['simulated_only'])

    def test_final_and_abstain_are_terminal_at_every_stage(self):
        for stage in (1,2,3):
            for action in ('final','abstain'):
                with self.subTest(stage=stage,action=action):
                    steps=[base_step(),decision('verify',triangle_indices=[49])][:stage-1]
                    steps.append(decision(action,**({'answer':{'copied':None}} if action=='final' else {'reason':'evidence_insufficient'})))
                    steps.append(decision('supplement',gap=gap()))
                    report=through_entry(fixture(steps))
                    self.assertEqual(report['terminal']['status'],action)
                    self.assertEqual(report['counts']['model_stages'],stage)
                    self.assertEqual(report['counts']['physical_reader_calls'],2*stage)
                    self.assert_no_live_calls(report)

    def test_direct_verification_needs_no_native(self):
        report=through_entry(fixture([base_step(),decision('verify',triangle_indices=[49,65]),decision('final',answer={'confirmed':True})]))
        self.assertEqual(report['terminal']['status'],'final')
        self.assertEqual(report['counts']['facts'],4)
        self.assertEqual(report['counts']['native_supplements'],0)
        self.assertEqual(report['counts']['physical_reader_calls'],6)
        self.assertEqual([r['selection'] for r in report['reader_calls'][-2:]],[[49,65],[49,65]])

    def test_script_transport_never_rewrites_target_or_answer_literals(self):
        anchors={'f1':'$task','f2':'$condition'}
        answer={'literal':'$task','evidence_literal':'$evidence','target':['$response']}
        report=through_entry(fixture([decision('base',anchors=anchors),decision('final',answer=answer)]))
        self.assertEqual([q['selection'] for q in report['reader_calls'][2:]],list(anchors.values()))
        self.assertEqual(report['terminal']['answer'],answer)

    def test_empty_selection_is_abstention_not_queries(self):
        report=through_entry(fixture([base_step(),decision('verify',triangle_indices=[]),decision('final',answer=False)]))
        self.assertEqual(report['terminal']['status'],'abstain')
        self.assertEqual(report['terminal']['reason'],'empty_triangle_selection')
        self.assertIsNone(report['terminal']['answer'])
        self.assertEqual(report['counts']['facts'],2)
        self.assertEqual(report['counts']['model_stages'],2)
        self.assertEqual(report['counts']['physical_reader_calls'],4)

    def test_directory_stage_cannot_preempt_native(self):
        report=through_entry(fixture([decision('supplement',gap=gap())]))
        self.assertEqual(report['terminal']['status'],'rejected')
        self.assertEqual(report['counts']['native_supplements'],0)
        self.assertEqual(report['counts']['physical_reader_calls'],2)

    def test_stale_forged_and_cross_condition_bindings_do_not_dispatch_native(self):
        variations=[('task_sha256','d'*64),('condition_id','another-arm'),('evidence_ref','$previous_evidence'),
                    ('evidence_ref',{'evidence_id':'never-delivered','origin_response_id':'forged','sources_sha256':'wrong'})]
        for key,value in variations:
            with self.subTest(key=key,value=value):
                step=decision('supplement',gap=gap());step['response'][key]=value
                report=through_entry(fixture([base_step(),step]))
                self.assertEqual(report['terminal']['status'],'rejected')
                self.assertEqual(report['counts']['native_supplements'],0)
                self.assertEqual(report['counts']['physical_reader_calls'],4)

    def test_wrong_source_digest_and_response_id_are_bound(self):
        for field in ('sources_sha256','origin_response_id','evidence_id'):
            with self.subTest(field=field):
                ref={k:'$evidence.'+k for k in ('evidence_id','origin_response_id','sources_sha256')}
                ref[field]='wrong'
                step=decision('supplement',gap=gap());step['response']['evidence_ref']=ref
                report=through_entry(fixture([base_step(),step]))
                self.assertEqual(report['counts']['native_supplements'],0)
                self.assertEqual(report['terminal']['status'],'rejected')

    def test_newly_prepared_but_undelivered_report_cannot_be_referenced(self):
        first=base_step()
        second=decision('supplement',gap=gap())['response']
        # Same delivery batch: base has been computed, but no new model prompt
        # has delivered it. Even a fresh response ID cannot authorize a query.
        second['response_id']='new-id-in-old-prompt'
        first['additional_deliveries']=[second]
        report=through_entry(fixture([first]))
        self.assertEqual(report['terminal']['status'],'rejected')
        self.assertEqual(report['counts']['native_supplements'],0)
        self.assertEqual(report['counts']['model_stages'],1)
        self.assertEqual(report['counts']['facts'],2)

    def test_gap_must_resolve_to_delivered_missing_or_unknown_data(self):
        for bad in (dict(gap(),expected=99),dict(gap(),kind='unknown',expected=0),dict(gap(),reason='')):
            with self.subTest(bad=bad):
                report=through_entry(fixture([base_step(),decision('supplement',gap=bad)]))
                self.assertEqual(report['counts']['native_supplements'],0)
                self.assertEqual(report['terminal']['status'],'rejected')

    def test_metadata_known_counts_and_unregistered_missing_are_not_gaps(self):
        markers=[dict(pointer='/evidence_sequence',kind='unknown',expected=2,reason='fake'),
                 dict(pointer='/results/0/receipt/data/vertex_count',kind='unknown',expected=8,reason='fake'),
                 dict(pointer='/results/0/receipt/data/unregistered',kind='missing',expected=None,reason='fake'),
                 dict(pointer='/results/0/receipt/data/details_omitted',kind='unknown',expected=1,reason='wrong field kind')]
        for marker in markers:
            with self.subTest(marker=marker):
                script=fixture([base_step(),decision('supplement',gap=marker)])
                script['reader']['base_data']=dict(state='measured',details_omitted=1,vertex_count=8,triangle_rows=[])
                report=through_entry(script)
                self.assertEqual(report['terminal']['status'],'rejected')
                self.assertEqual(report['counts']['native_supplements'],0)
                self.assertEqual(report['counts']['physical_reader_calls'],4)

    def test_declared_unknown_and_required_missing_markers_can_supplement(self):
        for marker in (dict(pointer='/results/0/receipt/data/state',kind='unknown',expected='unknown',reason='unresolved metric'),
                       dict(pointer='/results/0/receipt/data/triangle_rows',kind='missing',expected=None,reason='required original rows absent')):
            with self.subTest(marker=marker):
                report=through_entry(fixture([base_step(),decision('supplement',gap=marker),decision('abstain',reason='still unknown')]))
                self.assertEqual(report['counts']['native_supplements'],1)
                self.assertEqual(report['terminal']['status'],'abstain')
                self.assertIsNone(report['terminal']['answer'])

    def test_stale_same_content_evidence_from_another_run_is_rejected(self):
        prior=through_entry(fixture([base_step(),decision('abstain',reason='done')]))
        old=prior['evidence'][-1]
        step=decision('supplement',gap=gap());step['response']['evidence_ref']={k:old[k] for k in ('evidence_id','origin_response_id','sources_sha256')}
        report=through_entry(fixture([base_step(),step]))
        self.assertNotEqual(prior['run_nonce'],report['run_nonce'])
        self.assertEqual(report['terminal']['status'],'rejected')
        self.assertEqual(report['counts']['native_supplements'],0)
        self.assertEqual(report['counts']['physical_reader_calls'],4)

    def test_duplicate_supplement_decision_spends_one_joint_only(self):
        step=decision('supplement',gap=gap());step['duplicate_deliveries']=3
        report=through_entry(fixture([base_step(),step,decision('final',answer=None)]))
        self.assertEqual(report['terminal']['status'],'final')
        self.assertEqual(report['counts']['native_supplements'],1)
        self.assertEqual(report['counts']['physical_reader_calls'],6)
        self.assertEqual(report['counts']['model_stages'],3)

    def test_second_supplement_does_not_dispatch_or_open_new_window(self):
        report=through_entry(fixture([base_step(),decision('supplement',gap=gap()),decision('supplement',gap=gap())]))
        self.assertEqual(report['terminal']['status'],'model_stage_exhausted')
        self.assertEqual(report['counts']['native_supplements'],1)
        self.assertEqual(report['counts']['physical_reader_calls'],6)

    def test_already_reserved_output_blocks_replay_before_reading_script(self):
        from verification.region_witness_control import main
        loader=[];publisher=[]
        def exists(path):raise FileExistsError('existing registered result')
        with self.assertRaises(FileExistsError):
            main(['--script','script','--output','already-used'],reserve_output=exists,
                 load_script=lambda path:loader.append(path),publish=lambda *args:publisher.append(args))
        self.assertEqual(loader,[]);self.assertEqual(publisher,[])

    def test_actual_gap_supplement_is_delivered_before_final(self):
        report=through_entry(fixture([base_step(),decision('supplement',gap=gap()),decision('final',answer={'result':None,'reason':'unknown'})]))
        self.assertEqual(report['terminal']['status'],'final')
        self.assertEqual(report['counts']['facts'],2)
        self.assertEqual(report['counts']['native_supplements'],1)
        self.assertEqual(report['counts']['physical_reader_calls'],6)
        events=report['events']
        base_delivery=next(i for i,e in enumerate(events) if e['event']=='evidence_delivered' and e['evidence_ref']['origin_response_id'].endswith('/model/1/response'))
        supplement_dispatch=next(i for i,e in enumerate(events) if e['event']=='dispatch' and e['request']['kind']=='supplement')
        supplement_delivery=max(i for i,e in enumerate(events) if e['event']=='evidence_delivered')
        final_decision=max(i for i,e in enumerate(events) if e['event']=='decision_received')
        self.assertLess(base_delivery,supplement_dispatch)
        self.assertLess(supplement_dispatch,supplement_delivery)
        self.assertLess(supplement_delivery,final_decision)
        self.assertEqual(report['terminal']['answer']['result'],None)

    def test_combined_existing_target_and_supplement_fits_original_three_stages(self):
        report=through_entry(fixture([base_step(),decision('verify_and_supplement',triangle_indices=[999],gap=gap()),decision('final',answer={'copied':'unchanged'})]))
        self.assertEqual(report['counts']['physical_reader_calls'],8)
        self.assertEqual(report['counts']['facts'],4)
        self.assertEqual(report['counts']['native_supplements'],1)
        self.assertEqual(report['counts']['model_stages'],3)
        self.assertEqual([r['selection'] for r in report['reader_calls'][-2:]],[[999],[999]])

    def test_last_stage_query_cannot_create_a_fourth_model_stage(self):
        report=through_entry(fixture([base_step(),decision('supplement',gap=gap()),decision('verify',triangle_indices=[49]),decision('final',answer=True)]))
        self.assertEqual(report['terminal']['status'],'model_stage_exhausted')
        self.assertIsNone(report['terminal']['answer'])
        self.assertEqual(report['counts']['physical_reader_calls'],6)
        self.assertEqual(report['counts']['model_stages'],3)
        self.assertEqual(report['counts']['facts'],2)

    def test_duplicate_deliveries_do_not_add_queries_or_model_stages(self):
        base=base_step();base['duplicate_deliveries']=3
        verify=decision('verify',triangle_indices=[49]);verify['duplicate_deliveries']=2
        final=decision('final',answer={'literal':False});final['duplicate_deliveries']=3
        report=through_entry(fixture([base,verify,final,decision('supplement',gap=gap())]))
        self.assertEqual(report['counts']['physical_reader_calls'],6)
        self.assertEqual(report['counts']['model_stages'],3)
        self.assertEqual(report['counts']['facts'],4)
        self.assertEqual(report['terminal']['answer'],{'literal':False})
        self.assertEqual(sum(e['event']=='duplicate_decision' for e in report['events']),5)

    def test_response_id_conflict_is_rejected_without_more_dispatch(self):
        base=base_step();conflict=decision('abstain',reason='changed')['response'];base['additional_deliveries']=[conflict]
        report=through_entry(fixture([base]))
        self.assertEqual(report['terminal']['reason'],'response_id_conflict')
        self.assertEqual(report['counts']['facts'],2)

    def test_unknown_geometry_is_not_transport_failure_or_false(self):
        report=through_entry(fixture([base_step(),decision('abstain',reason='geometry_unknown')]))
        self.assertEqual(report['terminal']['status'],'abstain')
        self.assertIsNone(report['terminal']['answer'])
        self.assertEqual(report['evidence'][-1]['results'][0]['receipt']['data']['state'],'unknown')

    def test_expired_model_response_spends_stage_and_dispatches_no_query(self):
        base=base_step();base['advance_ns']=600_000_000_000
        report=through_entry(fixture([base]))
        self.assertEqual(report['terminal']['status'],'deadline_exceeded')
        self.assertEqual(report['counts']['model_stages'],1)
        self.assertEqual(report['counts']['facts'],0)

    def test_failed_unknown_and_exception_receipts_never_refund_or_retry(self):
        overrides=[{'receipt':{'status':'failed'}},{'receipt':{'status':'unknown'}},{'raise':True}]
        for override in overrides:
            with self.subTest(override=override):
                script=fixture([base_step(),decision('final',answer=False)]);script['reader']['overrides']={'3':override}
                report=through_entry(script)
                self.assertIn(report['terminal']['status'],('execution_failed','receipt_unknown'))
                self.assertEqual(report['counts']['facts'],1)
                self.assertEqual(report['counts']['physical_reader_calls'],3)
                self.assertEqual(report['counts']['model_stages'],1)
                self.assertIsNone(report['terminal']['answer'])

    def test_partial_joint_failure_keeps_joint_charge_and_partial_real_count(self):
        script=fixture([base_step(),decision('supplement',gap=gap()),decision('final',answer=True)])
        script['reader']['overrides']={'6':{'receipt':{'status':'unknown'}}}
        report=through_entry(script)
        self.assertEqual(report['terminal']['status'],'receipt_unknown')
        self.assertEqual(report['counts']['native_supplements'],1)
        self.assertEqual(report['counts']['physical_reader_calls'],6)
        self.assertEqual(report['counts']['model_stages'],2)
        self.assertEqual(len(report['evidence']),2)

    def test_reader_deadline_and_total_deadline_keep_spent_cost(self):
        for advance in (30_000_000_000,600_000_000_000):
            with self.subTest(advance=advance):
                script=fixture([base_step()]);script['reader']['overrides']={'3':{'advance_ns':advance}}
                report=through_entry(script)
                self.assertEqual(report['terminal']['status'],'deadline_exceeded')
                self.assertEqual(report['counts']['facts'],1)
                self.assertEqual(report['counts']['physical_reader_calls'],3)
                self.assertEqual({r['task_deadline_ns'] for r in report['reader_calls']},{600_000_000_000})

    def test_fact_native_and_model_exhaustion_do_not_reopen_windows(self):
        from verification.region_witness_control import CAPS
        for key,cap,steps in [('facts',2,[base_step(),decision('verify',triangle_indices=[49])]),
                              ('native_supplements',0,[base_step(),decision('supplement',gap=gap())]),
                              ('model_stages',1,[base_step(),decision('final',answer=True)])]:
            with self.subTest(key=key):
                script=fixture(steps);script['limits']=dict(CAPS,**{key:cap});report=through_entry(script)
                self.assertIn(report['terminal']['status'],('budget_exhausted','model_stage_exhausted'))
                self.assertLessEqual(report['counts'][key],cap)
                self.assertEqual(report['deadline_ns'],600_000_000_000)

    def test_bad_receipt_binding_and_boolean_source_frame_do_not_publish(self):
        wrong={'file_sha256':'b'*64,'frame':True,'mesh':'Mesh','rig':'Rig'}
        for mismatch in ({'request_id':'other'},{'condition_id':'other'},{'source_ref':wrong}):
            with self.subTest(mismatch=mismatch):
                script=fixture([base_step()]);script['reader']['overrides']={'3':{'receipt':mismatch}}
                report=through_entry(script)
                self.assertEqual(report['terminal']['status'],'receipt_unknown')
                self.assertEqual(report['counts']['facts'],1)
                self.assertEqual(len(report['evidence']),1)

    def test_receipt_byte_limit_is_preserved(self):
        script=fixture([base_step()]);script['reader']['overrides']={'3':{'receipt':{'data':'x'*524289}}}
        report=through_entry(script)
        self.assertEqual(report['terminal']['status'],'receipt_unknown')
        self.assertEqual(report['counts']['facts'],1)

    def test_snapshots_do_not_share_mutable_model_or_reader_objects(self):
        from verification import region_witness_control as module
        original=module.ScriptedModel.respond
        def mutable_model(model,prompt):
            result=original(model,prompt);prompt['evidence']['results'].clear();prompt['counts']['facts']=999
            return result
        original_read=module.RecordingReader.read
        stored=[]
        def mutable_reader(reader,request):
            receipt=original_read(reader,request);stored.append(receipt);return receipt
        with patch.object(module.ScriptedModel,'respond',mutable_model),patch.object(module.RecordingReader,'read',mutable_reader):
            report=through_entry(fixture([base_step(),decision('final',answer={'literal':None})]))
        for receipt in stored:receipt['data'].clear()
        self.assertEqual(report['counts']['facts'],2)
        self.assertTrue(report['evidence'][-1]['results'][0]['receipt']['data'])


if __name__ == '__main__':
    unittest.main()
