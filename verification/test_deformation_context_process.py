"""Complete-source context policy, actor and canonical publication regression.

Native stdio is mocked, but source admission, geometry and publication gates
are real. These fixtures establish no external asset or model-task benefit.
"""
import contextlib,copy,hashlib,io,json,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from human_eye_plugin import small_skin_source_process as process
from human_eye_plugin import skin_source_process as old_process
from human_eye_plugin import deformation_context as context
from verification import test_small_skin_source_process as transport
from verification.test_deformation_anchor_process import chosen
from verification.test_deformation_region_process import selection as region_selection
from verification.test_reader_startup_cleanup import Process
from verification.test_small_skin_source import rehash


def islands(packet,count=9):
    """One anchor-touching face and bounded, fully weighted background islands."""
    p=copy.deepcopy(packet);points=[];faces=[];edges=[]
    for i in range(count):
        x=2.*(i%3);y=2.*(i//3);base=len(points)
        points.extend([[x,y,0.],[x+1.,y,0.],[x,y+1.,0.]])
        faces.append([base,base+1,base+2]);edges.extend([[base,base+1],[base,base+2],[base+1,base+2]])
    p['inputs']['mesh'].update(vertices=points,triangles=faces,edges=edges,weights=[[[0,1.]] for _ in points])
    p['evaluated'].update(vertices=copy.deepcopy(points),triangles=copy.deepcopy(faces))
    return rehash(p)


def policy_for(catalog,**changes):
    anchor=next(v for v in catalog['anchors'] if v['endpoint']=='head')
    value=dict(schema='surface-deformation-context-policy-v1',source_ref=copy.deepcopy(catalog['source_ref']),
        catalog_sha256=catalog['catalog_sha256'],anchor_id=anchor['anchor_id'],required_core_half_extents_m=[.25,.25,.25],
        primary_half_extents_m=[10.,10.,10.],candidate_half_extents_m=[[.5,.5,.5]],max_surplus_members=0,
        min_saved_bytes=256,planning_budget_ms=250)
    value.update(changes);return value


def selected(policy,blob):
    return dict(schema='surface-deformation-context-selection-v1',source_ref=copy.deepcopy(policy['source_ref']),
        catalog_sha256=policy['catalog_sha256'],anchor_id=policy['anchor_id'],policy_sha256=hashlib.sha256(blob).hexdigest())


def unicode_bone(packet):
    p=copy.deepcopy(packet);p['inputs']['rig']['bones'][0]['name']='骨骼'
    p['evaluated']['bones'][0]['name']='骨骼';p['inputs']['mesh']['groups']=['骨骼']
    return rehash(p)


class BinaryCapture(io.StringIO):
    def __init__(self):super().__init__();self.buffer=io.BytesIO()
    def payload(self):return self.buffer.getvalue() or self.getvalue().encode('utf8')


class ContextActorTests(unittest.TestCase):
    def setUp(self):self.support=transport.SmallSourceTransportTests()

    @contextlib.contextmanager
    def case(self,**changes):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor,islands(self.support.captured(actor)))
            try:
                catalog=actor.describe_anchors(p,deadline_ns=actor.deadline_ns);policy=policy_for(catalog,**changes)
                blob=json.dumps(policy,ensure_ascii=False).encode('utf8');path=h.root/'policy.json';path.write_bytes(blob)
                actor.set_context_policy(path,hashlib.sha256(blob).hexdigest());selection=selected(policy,blob)
                yield SimpleNamespace(h=h,actor=actor,p=p,catalog=catalog,policy=policy,blob=blob,path=path,selection=selection)
            finally:actor.close()

    def test_operator_freezes_exact_bytes_once_and_no_mutable_policy_alias(self):
        with self.case() as h:
            self.assertEqual(h.actor.context_policy_bytes,h.blob);self.assertIs(type(h.actor.context_policy_bytes),bytes)
            original=h.actor._context_policy();original['candidate_half_extents_m'][0][0]=5.
            self.assertEqual(h.actor._context_policy()['candidate_half_extents_m'],[[.5,.5,.5]])
            with self.assertRaisesRegex(ValueError,'deformation_context_policy_already_set'):
                h.actor.set_context_policy(h.path,hashlib.sha256(h.blob).hexdigest())
            query=h.actor.bind_context_selection(h.p,h.selection,deadline_ns=h.actor.deadline_ns)
            h.selection['source_ref']['frame']['number']=99
            self.assertEqual(query['expected_source_sha256'],h.p['source_sha256'])
            self.assertEqual(h.actor.analyze(h.p,deadline_ns=h.actor.deadline_ns,context_query=query)['context_quality']['core_triangle_indices'],[0])

    def test_changed_operator_file_rejects_inspect_bind_and_analyze_before_geometry(self):
        for stage in ('inspect','bind','analyze'):
            with self.subTest(stage=stage),self.case() as h:
                query=h.actor.bind_context_selection(h.p,h.selection,deadline_ns=h.actor.deadline_ns)
                h.path.write_bytes(h.blob+b' ')
                call={'inspect':h.actor.inspect,'bind':lambda:h.actor.bind_context_selection(h.p,h.selection,deadline_ns=h.actor.deadline_ns),
                    'analyze':lambda:h.actor.analyze(h.p,deadline_ns=h.actor.deadline_ns,context_query=query)}[stage]
                with patch.object(process.surface_deformation,'_geometry_rows') as geometry:
                    with self.assertRaisesRegex(process.core.SmallSourceError,'small_skin_context_policy_changed'):call()
                    geometry.assert_not_called()

    def test_operator_pin_budget_and_bad_policy_fail_without_configuration(self):
        with self.support.setup_actor() as h:
            actor=h.create();path=h.root/'policy.json'
            try:
                for blob,digest,reason in ((b'null',None,'policy_fields'),(b' '*4097,None,'context_policy_pin'),
                        (b'{}','0'*64,'context_policy_pin'),(b'{"schema":0,"schema":1}',None,'duplicate_JSON_key')):
                    path.write_bytes(blob)
                    with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):
                        actor.set_context_policy(path,digest or hashlib.sha256(blob).hexdigest())
                    self.assertFalse(hasattr(actor,'context_policy_bytes'))
                for badpath,digest in ((Path('policy.json'),'0'*64),(path,True)):
                    with self.subTest(path=badpath,digest=digest),self.assertRaisesRegex(ValueError,'deformation_context_policy_pin'):
                        actor.set_context_policy(badpath,digest)
            finally:actor.close()

    def test_context_needs_real_observation_policy_and_original_window(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.captured(actor)
            try:
                with self.assertRaisesRegex(process.core.SmallSourceError,'small_skin_observation_required'):
                    actor.bind_context_selection(p,{},deadline_ns=actor.deadline_ns)
                p=self.support.observe(actor)
                with self.assertRaisesRegex(ValueError,'deformation_context_policy_required'):
                    actor.bind_context_selection(p,{},deadline_ns=actor.deadline_ns)
            finally:actor.close()
        with self.case() as h:
            with self.assertRaisesRegex(process.core.SmallSourceError,'selection_window'):
                h.actor.bind_context_selection(h.p,h.selection,deadline_ns=h.actor.deadline_ns+1)
            query=h.actor.bind_context_selection(h.p,h.selection,deadline_ns=h.actor.deadline_ns)
            h.actor.close()
            with self.assertRaisesRegex(process.core.SmallSourceError,'analysis_window'):
                h.actor.analyze(h.p,deadline_ns=h.actor.deadline_ns,context_query=query)

    def test_model_selection_has_no_authority_to_change_scope_or_policy(self):
        with self.case() as h:
            cases=[(None,'selection_fields'),([], 'selection_fields'),(dict(h.selection,half_extents_m=[.1,.1,.1]),'selection_fields'),
                (dict(h.selection,policy_sha256='0'*64),'policy_binding'),(dict(h.selection,catalog_sha256='0'*64),'stale_catalog'),
                (dict(h.selection,anchor_id='bone-anchor:'+'0'*64),'policy_binding')]
            stale=copy.deepcopy(h.selection);stale['source_ref']['frame']['number']=2;cases.append((stale,'stale_selection'))
            for value,reason in cases:
                with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,'deformation_context_'+reason):
                    h.actor.bind_context_selection(h.p,value,deadline_ns=h.actor.deadline_ns)

    def test_query_tampering_and_changed_complete_source_never_fall_back(self):
        with self.case() as h:
            query=h.actor.bind_context_selection(h.p,h.selection,deadline_ns=h.actor.deadline_ns)
            for key,value,reason in [('expected_source_sha256','0'*64,'stale_source'),('policy_sha256','0'*64,'policy_binding'),
                    ('catalog_sha256','0'*64,'stale_catalog'),('anchor_id','bone-anchor:'+'0'*64,'policy_binding')]:
                bad=dict(query,**{key:value})
                with self.subTest(key=key),self.assertRaisesRegex(ValueError,'deformation_context_'+reason):
                    h.actor.analyze(h.p,deadline_ns=h.actor.deadline_ns,context_query=bad)
            for value in (True,[],dict(query,region={})):
                with self.subTest(value=value),self.assertRaisesRegex(ValueError,'deformation_context_query_fields'):
                    h.actor.analyze(h.p,deadline_ns=h.actor.deadline_ns,context_query=value)
            bad=copy.deepcopy(h.p);bad['evaluated']['vertices'][-1][0]+=.125;rehash(bad)
            with patch.object(process.surface_deformation,'_geometry_rows') as geometry:
                with self.assertRaisesRegex(process.core.SmallSourceError,'small_skin_stale_source'):
                    h.actor.analyze(bad,deadline_ns=h.actor.deadline_ns,context_query=query)
                geometry.assert_not_called()

    def test_policy_cannot_cut_required_core_or_expand_primary(self):
        for half,reason in (([.1,.5,.5],'candidate_core'),([11.,.5,.5],'candidate_primary')):
            with self.subTest(half=half),self.support.setup_actor() as h:
                actor=h.create();p=self.support.observe(actor);catalog=actor.describe_anchors(p,deadline_ns=actor.deadline_ns)
                policy=policy_for(catalog,candidate_half_extents_m=[half]);blob=json.dumps(policy).encode();path=h.root/'policy.json';path.write_bytes(blob)
                try:
                    with self.assertRaisesRegex(ValueError,'deformation_context_'+reason):actor.set_context_policy(path,hashlib.sha256(blob).hexdigest())
                    self.assertFalse(hasattr(actor,'context_policy_bytes'))
                finally:actor.close()

    def test_one_full_B2_pass_and_final_gate_include_source_validation_and_anchor(self):
        with self.case() as h:
            query=h.actor.bind_context_selection(h.p,h.selection,deadline_ns=h.actor.deadline_ns)
            recipe=h.actor.bind_anchor_selection(h.p,chosen(h.catalog),deadline_ns=h.actor.deadline_ns)
            baseline=h.actor.analyze(h.p,deadline_ns=h.actor.deadline_ns,anchor_query=recipe)
            rows=process.surface_deformation._geometry_rows
            with patch.object(process.surface_deformation,'_geometry_rows',wraps=rows) as geometry:
                report=h.actor.analyze(h.p,deadline_ns=h.actor.deadline_ns,context_query=query)
                self.assertEqual(geometry.call_count,1)
            audit=json.loads(h.actor.context_audit_bytes);quality=report['context_quality']
            self.assertEqual(quality['decision'],'selected_context');self.assertEqual(quality['reason'],'verified_byte_gain')
            self.assertEqual(quality['core_triangle_indices'],[0]);self.assertEqual(report['region_query']['matched_triangle_indices'],[0])
            self.assertEqual(audit['primary_report'],baseline)
            self.assertIn('source_validation',audit['primary_report']);self.assertIn('anchor_query',audit['primary_report'])
            self.assertEqual(audit['B2_rows_passes'],1);self.assertEqual(audit['geometry_cache_preparations'],1)
            self.assertEqual(audit['primary_publication_bytes'],len(context.publication_bytes(baseline)))
            self.assertEqual(audit['published_publication_bytes'],len(context.publication_bytes(report)))
            self.assertEqual(audit['published_publication_sha256'],hashlib.sha256(context.publication_bytes(report)).hexdigest())
            self.assertGreaterEqual(len(context.publication_bytes(baseline))-len(context.publication_bytes(report)),h.policy['min_saved_bytes'])
            self.assertNotIn('published_publication_bytes',quality);self.assertNotIn('candidate_records',quality)
            self.assertEqual(audit['core_rows_sha256'],quality['core_rows_sha256'])
            self.assertEqual(audit['core_rows'],[report['region_query']['triangles'][0]])
            self.assertEqual(report['damage_classification'],'not_inferred');self.assertFalse(report['execution_authority'])

    def test_normal_core_needs_no_candidates_and_keeps_primary(self):
        with self.case(required_core_half_extents_m=[10.,10.,10.],candidate_half_extents_m=[]) as h:
            query=h.actor.bind_context_selection(h.p,h.selection,deadline_ns=h.actor.deadline_ns)
            report=h.actor.analyze(h.p,deadline_ns=h.actor.deadline_ns,context_query=query);audit=json.loads(h.actor.context_audit_bytes)
            quality=report['context_quality'];self.assertEqual(quality['reason'],'within_surplus_budget')
            self.assertEqual(quality['decision'],'retained_primary');self.assertEqual(quality['candidates_evaluated'],0)
            self.assertEqual(audit['candidate_records'],[]);self.assertEqual(quality['core_triangle_indices'],list(range(9)))

    def test_context_exclusive_with_all_old_queries_and_old_reports_unchanged(self):
        with self.case() as h:
            actor=h.actor;p=h.p;query=actor.bind_context_selection(p,h.selection,deadline_ns=actor.deadline_ns)
            old=actor.bind_selection(p,transport.stable_selection(p,(0,)),deadline_ns=actor.deadline_ns)
            region=actor.bind_region_selection(p,region_selection(p),deadline_ns=actor.deadline_ns)
            anchor=actor.bind_anchor_selection(p,chosen(h.catalog),deadline_ns=actor.deadline_ns)
            for field,value in [('query',old),('region_query',region),('anchor_query',anchor)]:
                with self.subTest(field=field),self.assertRaisesRegex(ValueError,'deformation_query_modes'):
                    actor.analyze(p,deadline_ns=actor.deadline_ns,context_query=query,**{field:value})
                report=actor.analyze(p,deadline_ns=actor.deadline_ns,**{field:value})
                self.assertNotIn('context_quality',report)
            self.assertEqual(actor.analyze(p,deadline_ns=actor.deadline_ns,query=old)['task_query']['triangle_indices'],[0])


class ContextCLITests(unittest.TestCase):
    def invoke(self,*,blob=None,policy_blob=None,policy_sha=None,change_selection=False,change_policy=False,second_changed=False,
            expire_save=None,close_exit=0,expire_close=False,publish_change=None,relative=False,text_only=False,padding=False,unicode_source=False):
        support=transport.SmallSourceTransportTests()
        with support.setup_actor() as h:
            authored=lambda actor:(unicode_bone if unicode_source else lambda v:v)(islands(support.captured(actor)))
            preparer=h.create();p=support.observe(preparer,authored(preparer))
            policy=policy_for(preparer.describe_anchors(p,deadline_ns=preparer.deadline_ns));preparer.close()
            frozen=json.dumps(policy,ensure_ascii=False).encode() if policy_blob is None else policy_blob
            selection=selected(policy,frozen);path=h.root/'selection.json';path.write_bytes(json.dumps(selection).encode() if blob is None else blob)
            policy_path=h.root/'policy.json';policy_path.write_bytes(frozen);out=h.root/'output'
            child=Process();child.pid=h.child.pid
            with patch.object(process.subprocess,'Popen',return_value=child):actor=h.create()
            p=authored(actor);actor.received_ns=100;actor.deadline_ns=1_000_000_000
            clock=[100];events=[];names={};real_open=Path.open;real_fsync=os.fsync;real_replace=os.replace
            real_analyze=actor.analyze;real_close=actor.close
            def next_packet():
                if change_selection:path.write_bytes(b'null')
                if change_policy and actor.sequence==2:policy_path.write_bytes(frozen+b' ')
                packet=copy.deepcopy(p)
                if second_changed and actor.sequence==2:
                    mesh=packet['inputs']['closure'][2];mesh['matrix_parent_inverse'][0][3]=.125
                    mesh['matrix_basis'][0][3]=-.125;mesh['location'][0]=-.125;rehash(packet)
                return dict(kind='snapshot',id=actor.sequence,packet=packet)
            def analyze(*a,**kw):
                events.append(('analyze',copy.deepcopy(kw)));report=real_analyze(*a,**kw)
                if padding:report['too_large']='x'*(process.r.MAX_BYTES+1)
                return report
            def close():
                if not actor.closed:
                    events.append(('close',None));real_close();child.returncode=close_exit
                    if expire_close:clock[0]=actor.deadline_ns
            def opened(file,*a,**kw):
                stream=real_open(file,*a,**kw);names[stream.fileno()]=file.name
                if a and a[0]=='xb':events.append(('save',file.name))
                return stream
            def fsync(fd):
                real_fsync(fd)
                if names.get(fd)==expire_save:clock[0]=actor.deadline_ns
            def replaced(source,destination):
                real_replace(source,destination)
                if Path(destination).name=='REPORT.json':
                    if publish_change=='source':Path(h.profile['scene_file']).write_bytes(b'changed after publication')
                    if publish_change=='policy':policy_path.write_bytes(frozen+b' ')
            argv=['--operator-profile',str(h.path),'--output',str(out),'--context-query','selection.json' if relative else str(path),
                '--context-policy',str(policy_path),'--context-policy-sha256',policy_sha or hashlib.sha256(frozen).hexdigest()]
            stdout=io.StringIO() if text_only else BinaryCapture()
            with patch.object(process,'SmallSkinSourceProcess',return_value=actor),patch.object(actor,'_next',side_effect=next_packet),\
                    patch.object(actor,'analyze',side_effect=analyze),patch.object(actor,'close',side_effect=close),\
                    patch.object(process.time,'perf_counter_ns',side_effect=lambda:clock[0]),patch.object(Path,'open',opened),\
                    patch.object(os,'fsync',fsync),patch.object(os,'replace',replaced),contextlib.redirect_stdout(stdout):
                code=process.main(argv)
            payload=stdout.getvalue().encode() if text_only else stdout.payload()
            self.assertEqual(len(payload.splitlines()),1);self.assertTrue(actor.closed)
            files={f.name:f.read_bytes() for f in out.iterdir() if f.is_file()}
            return SimpleNamespace(code=code,value=json.loads(payload),payload=payload,files=files,events=events,
                count=actor.sequence,selection=selection,policy=policy,text=stdout.getvalue())

    def test_success_uses_two_reads_one_analysis_and_binary_canonical_report(self):
        h=self.invoke(change_selection=True)
        self.assertEqual(h.code,0);self.assertEqual(h.count,2);self.assertEqual(h.text,'')
        self.assertEqual(sum(k=='analyze' for k,v in h.events),1)
        kw=next(v for k,v in h.events if k=='analyze');self.assertEqual(set(kw),{'deadline_ns','context_query'})
        self.assertEqual(json.loads(h.files['CONTEXT_SELECTION.json']),h.selection)
        self.assertEqual(json.loads(h.files['CONTEXT_POLICY.json']),h.policy)
        self.assertEqual(h.value,json.loads(h.files['REPORT.json']));self.assertEqual(h.payload,context.publication_bytes(h.value))
        self.assertNotIn('evidence',h.value);self.assertNotIn('elapsed_ns',h.value)
        audit=json.loads(h.files['CONTEXT_AUDIT.json']);publication=json.loads(h.files['PUBLICATION.json'])
        self.assertEqual(publication['payload_bytes'],len(h.payload));self.assertEqual(publication['payload_sha256'],hashlib.sha256(h.payload).hexdigest())
        self.assertEqual(audit['published_publication_bytes'],len(h.payload))
        self.assertEqual(audit['published_publication_sha256'],publication['payload_sha256'])
        self.assertLess(h.events.index(('close',None)),h.events.index(('save','REPORT_PENDING.json')))
        self.assertFalse(h.value['execution_authority']);self.assertEqual(h.value['geometry_setters'],0)

    def test_text_only_mock_keeps_identical_canonical_publication(self):
        h=self.invoke(text_only=True);self.assertEqual(h.code,0);self.assertEqual(h.payload,context.publication_bytes(h.value))

    def test_non_ASCII_source_still_publishes_ASCII_and_counts_real_escape_bytes(self):
        h=self.invoke(unicode_source=True)
        self.assertEqual(h.code,0);self.assertEqual(h.value['anchor_query']['bone_name'],'骨骼')
        self.assertTrue(all(v<128 for v in h.payload));self.assertIn(b'\\u9aa8\\u9abc',h.payload)
        self.assertEqual(h.payload,context.publication_bytes(h.value))
        self.assertEqual(json.loads(h.files['PUBLICATION.json'])['payload_bytes'],len(h.payload))

    def test_null_bad_extra_scope_selection_is_explicit_failure_after_one_read(self):
        for value in (None,True,[],{},dict(schema='surface-deformation-context-selection-v1',candidate_half_extents_m=[])):
            with self.subTest(value=value):
                h=self.invoke(blob=json.dumps(value).encode());self.assertEqual(h.code,1);self.assertEqual(h.count,1)
                self.assertIn('deformation_context_selection_fields',h.value['reason']);self.assertNotIn('REPORT.json',h.files)
                self.assertFalse(any(k=='analyze' for k,v in h.events))

    def test_invalid_JSON_budget_path_policy_and_pin_fail_before_native_read(self):
        for options,reason in [(dict(blob=b'{"a":0,"a":1}'),'duplicate_JSON_key'),(dict(blob=b'{"a":NaN}'),'nonfinite'),
                (dict(blob=b' '*4097),'selection_byte_budget'),(dict(relative=True),'selection_path'),
                (dict(policy_blob=b'null'),'policy_fields'),(dict(policy_blob=b' '*4097),'context_policy_pin'),
                (dict(policy_sha='0'*64),'context_policy_pin')]:
            with self.subTest(reason=reason):
                h=self.invoke(**options);self.assertEqual(h.code,1);self.assertEqual(h.count,0)
                self.assertIn(reason,h.value['reason']);self.assertNotIn('REPORT.json',h.files)

    def test_selection_or_policy_save_expiry_prevents_native_observation(self):
        for name in ('CONTEXT_POLICY.json','CONTEXT_SELECTION.json'):
            with self.subTest(name=name):
                h=self.invoke(expire_save=name);self.assertEqual(h.code,1);self.assertEqual(h.count,0)
                self.assertEqual(h.value['reason'],'rig_pose_original_deadline');self.assertNotIn('REPORT.json',h.files)

    def test_changed_second_source_or_policy_never_becomes_context_success(self):
        for options,reason in [(dict(second_changed=True),'small_skin_stale_source'),(dict(change_policy=True),'small_skin_context_policy_changed')]:
            with self.subTest(reason=reason):
                h=self.invoke(**options);self.assertEqual(h.code,1);self.assertEqual(h.count,2)
                self.assertEqual(h.value['reason'],reason);self.assertNotIn('REPORT.json',h.files)

    def test_late_close_audit_and_report_deadlines_do_not_publish_success(self):
        for options,reason in [(dict(close_exit=73),'rig_pose_source_worker_exit'),(dict(expire_close=True),'rig_pose_original_deadline'),
                (dict(expire_save='CONTEXT_AUDIT.json'),'rig_pose_original_deadline'),(dict(expire_save='REPORT_PENDING.json'),'rig_pose_original_deadline')]:
            with self.subTest(options=options):
                h=self.invoke(**options);self.assertEqual(h.code,1);self.assertEqual(h.count,2)
                self.assertEqual(h.value['reason'],reason);self.assertNotIn('REPORT.json',h.files)

    def test_source_policy_change_or_publication_expiry_revokes_existing_report(self):
        for options,reason in [(dict(publish_change='source'),'small_skin_scene_pin'),(dict(publish_change='policy'),'small_skin_context_policy_changed'),
                (dict(expire_save='PUBLICATION.json'),'rig_pose_original_deadline')]:
            with self.subTest(options=options):
                h=self.invoke(**options);self.assertEqual(h.code,1);self.assertEqual(h.value['reason'],reason)
                self.assertNotIn('REPORT.json',h.files);self.assertIn('REVOKED_REPORT.json',h.files)

    def test_more_than_512k_final_success_is_revoked(self):
        h=self.invoke(padding=True);self.assertEqual(h.code,1);self.assertEqual(h.value['reason'],'rig_pose_deformation_context_report_byte_budget')
        self.assertNotIn('REPORT.json',h.files);self.assertIn('REVOKED_REPORT.json',h.files)

    def test_context_and_old_four_CLI_modes_are_mutually_exclusive_before_launch(self):
        for mode in (['--anchors-only'],['--anchor-query','a'],['--region-query','r'],['--triangle-query','t']):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder,patch.object(process,'SmallSkinSourceProcess') as constructor,contextlib.redirect_stderr(io.StringIO()):
                root=Path(folder).resolve()
                with self.assertRaises(SystemExit) as caught:process.main(['--operator-profile',str(root/'profile'),'--output',str(root/'out'),'--context-query','c',*mode])
                self.assertEqual(caught.exception.code,2);constructor.assert_not_called()

    def test_two_operator_args_are_required_together_and_only_in_context_mode(self):
        cases=[['--context-query','c'],['--context-query','c','--context-policy','p'],
            ['--context-query','c','--context-policy-sha256','0'*64],['--context-policy','p','--context-policy-sha256','0'*64],
            ['--anchor-query','a','--context-policy','p','--context-policy-sha256','0'*64]]
        for extra in cases:
            with self.subTest(args=extra),tempfile.TemporaryDirectory() as folder,patch.object(process,'SmallSkinSourceProcess') as constructor,contextlib.redirect_stderr(io.StringIO()),contextlib.redirect_stdout(io.StringIO()):
                root=Path(folder).resolve()
                with self.assertRaises(SystemExit) as caught:process.main(['--operator-profile',str(root/'profile'),'--output',str(root/'out'),*extra])
                self.assertEqual(caught.exception.code,2);constructor.assert_not_called()

    def test_old_B1_CLI_does_not_admit_new_context_arguments(self):
        with patch.object(old_process,'SkinSourceProcess') as constructor,contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:old_process.main(['--operator-profile','p','--output','o','--context-query','c'])
            self.assertEqual(caught.exception.code,2);constructor.assert_not_called()


if __name__=='__main__':unittest.main()
