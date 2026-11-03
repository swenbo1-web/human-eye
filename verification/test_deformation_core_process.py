"""Core-only production actor/CLI integration over real source validation.

Worker stdio is authored, while source admission, B2, exact membership, pinned
policy, lifecycle and publication are real. This is not external asset QA or
evidence of model benefit. Existing context fixtures and tests stay untouched.
"""
import contextlib,copy,hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from human_eye_plugin import small_skin_source_process as process,skin_source_process as old_process
from human_eye_plugin import deformation_context as context,deformation_anchors as anchors,deformation_region as region
from verification import test_small_skin_source_process as transport
from verification import test_deformation_context_process as context_tests
from verification.test_deformation_anchor_process import chosen
from verification.test_deformation_region_process import selection as region_selection
from verification.test_small_skin_source import rehash


class CoreActorTests(unittest.TestCase):
    def setUp(self):self.support=transport.SmallSourceTransportTests()
    case=context_tests.ContextActorTests.case

    def query(self,h):return h.actor.bind_context_selection(h.p,h.selection,deadline_ns=h.actor.deadline_ns)

    def test_real_admission_one_B2_one_core_scan_no_primary_or_candidate(self):
        with self.case() as h:
            query=self.query(h);rows=process.surface_deformation._geometry_rows
            with patch.object(process.surface_deformation,'_geometry_rows',wraps=rows) as B2,\
                    patch.object(region,'prepare_geometry',wraps=region.prepare_geometry) as prepare,\
                    patch.object(region,'select_prepared',wraps=region.select_prepared) as select,\
                    patch.object(anchors,'box',wraps=anchors.box) as box,\
                    patch.object(anchors,'resolve',side_effect=AssertionError('primary or candidate')):
                report=h.actor.analyze(h.p,deadline_ns=h.actor.deadline_ns,core_query=query)
            self.assertEqual((B2.call_count,prepare.call_count,select.call_count,box.call_count),(1,1,1,1))
            self.assertEqual(box.call_args.args[1],h.policy['required_core_half_extents_m'])
            self.assertEqual(report['schema'],'surface-deformation-core-facts-v1');self.assertEqual(report['facts']['core_triangle_count'],1)
            self.assertEqual(report['facts']['core_states'],dict(measured=1,collapsed=0,unknown=0))
            self.assertEqual(set(report['core_witnesses'].values()),{0});self.assertTrue(report['completeness']['core_facts_complete'])
            self.assertEqual(report['source_validation']['method'],'external_binding_full_dependency_FK_and_LBS')
            self.assertEqual(report['operator_pins'],h.actor._anchor_pins());self.assertEqual(report['source_sha256'],h.p['source_sha256'])
            audit=json.loads(h.actor.core_audit_bytes)
            self.assertEqual(audit['core_triangle_indices'],[0]);self.assertEqual(audit['actor_B2_rows_passes'],1)
            self.assertEqual(audit['geometry_cache_preparations'],1);self.assertEqual(audit['region_scans'],1)
            self.assertEqual(audit['candidates_evaluated'],0);self.assertFalse(audit['peripheral_shrinking'])
            self.assertEqual(audit['published_publication_bytes'],len(context.publication_bytes(report)))
            self.assertEqual(audit['published_publication_sha256'],hashlib.sha256(context.publication_bytes(report)).hexdigest())
            self.assertNotIn('context_quality',report);self.assertNotIn('region_query',report)

    def test_all_old_actor_modes_are_exclusive_and_output_unchanged_after_core(self):
        with self.case() as h:
            actor=h.actor;packet=h.p;core_query=self.query(h)
            old=actor.bind_selection(packet,transport.stable_selection(packet,(0,)),deadline_ns=actor.deadline_ns)
            selected_region=actor.bind_region_selection(packet,region_selection(packet),deadline_ns=actor.deadline_ns)
            anchor=actor.bind_anchor_selection(packet,chosen(h.catalog),deadline_ns=actor.deadline_ns)
            modes=[{},dict(query=old),dict(region_query=selected_region),dict(anchor_query=anchor),dict(context_query=core_query)]
            before=[context.publication_bytes(actor.analyze(packet,deadline_ns=actor.deadline_ns,**mode)) for mode in modes]
            actor.analyze(packet,deadline_ns=actor.deadline_ns,core_query=core_query)
            after=[context.publication_bytes(actor.analyze(packet,deadline_ns=actor.deadline_ns,**mode)) for mode in modes]
            self.assertEqual(before,after)
            for mode in modes[1:]:
                with self.subTest(mode=next(iter(mode))),self.assertRaisesRegex(ValueError,'deformation_query_modes'):
                    actor.analyze(packet,deadline_ns=actor.deadline_ns,core_query=core_query,**mode)

    def test_policy_file_and_changed_source_reject_before_B2(self):
        for change,reason in (('policy','small_skin_context_policy_changed'),('source','small_skin_stale_source')):
            with self.subTest(change=change),self.case() as h:
                query=self.query(h);packet=copy.deepcopy(h.p)
                if change=='policy':h.path.write_bytes(h.blob+b' ')
                else:packet['evaluated']['vertices'][-1][0]+=.125;rehash(packet)
                with patch.object(process.surface_deformation,'_geometry_rows') as B2:
                    with self.assertRaisesRegex(process.core.SmallSourceError,reason):h.actor.analyze(packet,deadline_ns=h.actor.deadline_ns,core_query=query)
                    B2.assert_not_called()
                self.assertFalse(hasattr(h.actor,'core_audit_bytes'))

    def test_stale_query_policy_or_catalog_and_original_window_are_explicit_failures(self):
        with self.case() as h:
            query=self.query(h)
            for edits,reason in [(dict(expected_source_sha256='0'*64),'context_stale_source'),(dict(policy_sha256='0'*64),'context_policy_binding'),
                    (dict(catalog_sha256='0'*64),'context_stale_catalog'),(dict(extra=True),'context_query_fields')]:
                with self.subTest(edits=edits),self.assertRaisesRegex(ValueError,reason):
                    h.actor.analyze(h.p,deadline_ns=h.actor.deadline_ns,core_query=dict(query,**edits))
                self.assertFalse(hasattr(h.actor,'core_audit_bytes'))
            with self.assertRaisesRegex(process.core.SmallSourceError,'small_skin_analysis_window'):
                h.actor.analyze(h.p,deadline_ns=h.actor.deadline_ns+1,core_query=query)
            h.actor.deadline_ns=0
            with self.assertRaisesRegex(ValueError,'original_deadline'):h.actor.analyze(h.p,deadline_ns=0,core_query=query)

    def test_installer_still_rejects_policy_outside_frozen_context_contract(self):
        for half,reason in (([.1,.5,.5],'candidate_core'),([11.,.5,.5],'candidate_primary')):
            with self.subTest(half=half),self.support.setup_actor() as h:
                actor=h.create();packet=self.support.observe(actor)
                try:
                    catalog=actor.describe_anchors(packet,deadline_ns=actor.deadline_ns)
                    policy=context_tests.policy_for(catalog,candidate_half_extents_m=[half]);blob=json.dumps(policy).encode()
                    path=h.root/'policy.json';path.write_bytes(blob)
                    with self.assertRaisesRegex(ValueError,'deformation_context_'+reason):actor.set_context_policy(path,hashlib.sha256(blob).hexdigest())
                    self.assertFalse(hasattr(actor,'context_policy_bytes'))
                finally:actor.close()


class CoreCLITests(unittest.TestCase):
    def invoke(self,**kwargs):
        # Reuse exactly the complete-source stdio/lifecycle fixture, changing
        # only the explicit mode passed to the real production main function.
        original_main=process.main
        def core_main(argv):
            argv=list(argv);argv[argv.index('--context-query')]='--core-query';return original_main(argv)
        with patch.object(process,'main',side_effect=core_main):return context_tests.ContextCLITests.invoke(self,**kwargs)

    def failure(self,h,reason,*,revoked=False):
        self.assertEqual(h.code,1);self.assertEqual(h.value['reason'],reason);self.assertEqual(h.value['status'],'unavailable')
        self.assertNotIn('REPORT.json',h.files);self.assertNotIn('facts',h.value);self.assertNotIn('schema',h.value)
        self.assertFalse(h.value['execution_authority']);self.assertEqual(h.value['geometry_setters'],0)
        self.assertEqual(len(h.payload.splitlines()),1);self.assertNotIn(b'surface-deformation-core-facts-v1',h.payload)
        if revoked:self.assertIn('REVOKED_REPORT.json',h.files)

    def test_ascii_LF_single_publication_complete_sidecars_and_close_before_report(self):
        h=self.invoke(change_selection=True,unicode_source=True)
        self.assertEqual(h.code,0);self.assertEqual(h.count,2);self.assertEqual(h.text,'')
        self.assertEqual(sum(key=='analyze' for key,value in h.events),1)
        kw=next(value for key,value in h.events if key=='analyze');self.assertEqual(set(kw),{'deadline_ns','core_query'})
        self.assertEqual(h.value['schema'],'surface-deformation-core-facts-v1');self.assertTrue(all(value<128 for value in h.payload))
        self.assertEqual(h.payload,context.publication_bytes(h.value));self.assertTrue(h.payload.endswith(b'\n'));self.assertFalse(h.payload.endswith(b'\n\n'))
        self.assertEqual(json.loads(h.files['CORE_SELECTION.json']),h.selection);self.assertEqual(json.loads(h.files['CONTEXT_POLICY.json']),h.policy)
        self.assertNotIn('CONTEXT_AUDIT.json',h.files);self.assertNotIn('CONTEXT_SELECTION.json',h.files)
        self.assertEqual(h.value,json.loads(h.files['REPORT.json']));self.assertNotIn('elapsed_ns',h.value);self.assertNotIn('evidence',h.value)
        audit=json.loads(h.files['CORE_AUDIT.json']);publication=json.loads(h.files['PUBLICATION.json'])
        self.assertEqual(publication['payload_bytes'],len(h.payload));self.assertEqual(audit['published_publication_bytes'],len(h.payload))
        self.assertEqual(publication['payload_sha256'],hashlib.sha256(h.payload).hexdigest())
        self.assertEqual(audit['published_publication_sha256'],publication['payload_sha256'])
        self.assertLess(h.events.index(('save','CORE_AUDIT.json')),h.events.index(('close',None)))
        self.assertLess(h.events.index(('close',None)),h.events.index(('save','REPORT_PENDING.json')))

    def test_text_only_fallback_keeps_same_canonical_bytes(self):
        h=self.invoke(text_only=True);self.assertEqual(h.code,0);self.assertEqual(h.payload,context.publication_bytes(h.value))

    def test_invalid_selection_policy_or_raw_pin_fail_at_the_existing_gate(self):
        for options,reason,count in [(dict(blob=b'null'),'rig_pose_deformation_context_selection_fields',1),
                (dict(blob=b'{"x":0,"x":1}'),'rig_pose_duplicate_JSON_key',0),(dict(blob=b' '*4097),'rig_pose_deformation_selection_byte_budget',0),
                (dict(relative=True),'rig_pose_deformation_selection_path',0),(dict(policy_blob=b'null'),'rig_pose_deformation_context_policy_fields',0),
                (dict(policy_sha='0'*64),'small_skin_context_policy_pin',0)]:
            with self.subTest(options=options):
                h=self.invoke(**options);self.failure(h,reason);self.assertEqual(h.count,count)
                self.assertFalse(any(key=='analyze' for key,value in h.events))

    def test_early_saved_policy_selection_or_snapshot_expiry_prevents_success(self):
        for name,count in [('CONTEXT_POLICY.json',0),('CORE_SELECTION.json',0),('SNAPSHOTS.json',2)]:
            with self.subTest(name=name):
                h=self.invoke(expire_save=name);self.failure(h,'rig_pose_original_deadline');self.assertEqual(h.count,count)
                self.assertFalse(any(key=='analyze' for key,value in h.events))

    def test_changed_source_and_policy_still_fail_during_second_real_observation(self):
        for options,reason in [(dict(second_changed=True),'small_skin_stale_source'),(dict(change_policy=True),'small_skin_context_policy_changed')]:
            with self.subTest(options=options):
                h=self.invoke(**options);self.failure(h,reason);self.assertEqual(h.count,2)

    def test_audit_report_fsync_expiry_bad_exit_and_close_expiry_have_no_valid_stdout(self):
        for options,reason in [(dict(expire_save='CORE_AUDIT.json'),'rig_pose_original_deadline'),
                (dict(expire_save='REPORT_PENDING.json'),'rig_pose_original_deadline'),(dict(close_exit=73),'rig_pose_source_worker_exit'),
                (dict(expire_close=True),'rig_pose_original_deadline')]:
            with self.subTest(options=options):
                h=self.invoke(**options);self.failure(h,reason);self.assertEqual(h.count,2)

    def test_publication_fsync_expiry_and_source_or_policy_changes_revoke_report(self):
        for options,reason in [(dict(expire_save='PUBLICATION.json'),'rig_pose_original_deadline'),(dict(publish_change='source'),'small_skin_scene_pin'),
                (dict(publish_change='policy'),'small_skin_context_policy_changed')]:
            with self.subTest(options=options):self.failure(self.invoke(**options),reason,revoked=True)

    def test_final_too_large_mutated_report_is_revoked_before_stdout_success(self):
        self.failure(self.invoke(padding=True),'rig_pose_deformation_core_report_byte_budget',revoked=True)

    def test_every_existing_CLI_mode_is_exclusive_before_process_creation(self):
        for mode in (['--anchors-only'],['--anchor-query','a'],['--region-query','r'],['--triangle-query','t'],['--context-query','c']):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder,patch.object(process,'SmallSkinSourceProcess') as constructor,contextlib.redirect_stderr(io.StringIO()):
                root=Path(folder).resolve()
                with self.assertRaises(SystemExit) as caught:process.main(['--operator-profile',str(root/'profile'),'--output',str(root/'out'),'--core-query','c',*mode])
                self.assertEqual(caught.exception.code,2);constructor.assert_not_called()

    def test_core_requires_both_operator_options_and_old_B1_does_not_admit_core_mode(self):
        for extra in (['--core-query','c'],['--core-query','c','--context-policy','p'],['--core-query','c','--context-policy-sha256','0'*64]):
            with self.subTest(extra=extra),patch.object(process,'SmallSkinSourceProcess') as constructor,contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:process.main(['--operator-profile','p','--output','o',*extra])
                self.assertEqual(caught.exception.code,2);constructor.assert_not_called()
        with patch.object(old_process,'SkinSourceProcess') as constructor,contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:old_process.main(['--operator-profile','p','--output','o','--core-query','c'])
            self.assertEqual(caught.exception.code,2);constructor.assert_not_called()


if __name__=='__main__':unittest.main()
