"""Complete-source anchor catalog/query entry and publication counterexamples.

Authored source fixtures exercise the real validator over mocked native stdio;
they do not certify a native asset or model-task interpretation by themselves.
"""
import contextlib,copy,io,itertools,json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from human_eye_plugin import small_skin_source_process as process,surface_deformation as deformation
from verification import test_small_skin_source_process as transport
from verification.test_small_skin_source import rehash
from verification.test_deformation_region_process import several,selection as region_selection
from verification.test_reader_startup_cleanup import Process
from verification.test_surface_deformation import one_triangle


def chosen(catalog,*,endpoint='head',half=(10.,10.,10.)):
    anchor=next(a for a in catalog['anchors'] if a['endpoint']==endpoint)
    return dict(schema='surface-deformation-anchor-selection-v1',source_ref=copy.deepcopy(catalog['source_ref']),
        catalog_sha256=catalog['catalog_sha256'],anchor_id=anchor['anchor_id'],half_extents_m=list(half))


def offset_rest(packet,offset=.125):
    p=copy.deepcopy(packet);bone=p['inputs']['rig']['bones'][0]
    for key in ('rest_matrix','pose_matrix'):bone[key][1][3]=offset
    bone.update(rest_head=[0.,offset,0.],rest_tail=[0.,1.+offset,0.],pose_head=[0.,offset,0.],pose_tail=[0.,1.+offset,0.])
    evaluated=p['evaluated']['bones'][0]
    for key in ('pose_matrix','pose_head','pose_tail'):evaluated[key]=copy.deepcopy(bone[key])
    return rehash(p)


class AnchorProductTests(unittest.TestCase):
    def setUp(self):self.support=transport.SmallSourceTransportTests()

    def test_catalog_and_selection_require_actual_observation(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.captured(actor)
            try:
                with patch.object(process.surface_deformation,'_analyze_geometry') as geometry:
                    for call in (lambda:actor.describe_anchors(p,deadline_ns=actor.deadline_ns),
                            lambda:actor.bind_anchor_selection(p,{},deadline_ns=actor.deadline_ns)):
                        with self.assertRaisesRegex(process.core.SmallSourceError,'small_skin_observation_required'):call()
                    geometry.assert_not_called()
            finally:actor.close()

    def test_catalog_reads_full_source_without_B2_or_health_conclusions(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.captured(actor);p['inputs']['mesh']['weights'][0]=[];rehash(p)
            try:
                p=self.support.observe(actor,p)
                with patch.object(process.surface_deformation,'_analyze_geometry') as geometry:
                    catalog=actor.describe_anchors(p,deadline_ns=actor.deadline_ns)
                    geometry.assert_not_called()
                self.assertEqual(catalog['schema'],'surface-deformation-anchor-catalog-v1')
                self.assertEqual(catalog['status'],'observed')
                self.assertEqual(catalog['completeness']['bones_total'],1)
                self.assertEqual(catalog['completeness']['anchors_total'],2)
                self.assertEqual(catalog['completeness']['anchors_omitted'],0)
                self.assertEqual({a['endpoint'] for a in catalog['anchors']},{'head','tail'})
                self.assertEqual(catalog['source_sha256'],p['source_sha256'])
                self.assertFalse(catalog['execution_authority']);self.assertEqual(catalog['geometry_setters'],0)
                self.assertFalse(catalog['original_file_saved']);self.assertNotIn('triangles_measured',catalog)
                self.assertIn('anatomical_semantics',catalog['scope']['not_inferred'])
                self.assertIn('damage',catalog['scope']['not_inferred'])
            finally:actor.close()

    def test_identity_bound_query_generates_real_region_and_preserves_choice(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor,several(self.support.captured(actor)))
            try:
                catalog=actor.describe_anchors(p,deadline_ns=actor.deadline_ns);selection=chosen(catalog);before=copy.deepcopy(selection)
                query=actor.bind_anchor_selection(p,selection,deadline_ns=actor.deadline_ns)
                self.assertEqual(query['schema'],'surface-deformation-anchor-query-v1')
                self.assertEqual(query['expected_source_sha256'],p['source_sha256'])
                self.assertEqual(selection,before);selection['half_extents_m'][0]=.25
                self.assertEqual(query['half_extents_m'],before['half_extents_m'])
                report=actor.analyze(p,deadline_ns=actor.deadline_ns,anchor_query=query)
                trace=report['anchor_query'];region=report['region_query']
                self.assertEqual(trace['anchor_id'],before['anchor_id']);self.assertEqual(trace['bone_name'],'Bone');self.assertEqual(trace['endpoint'],'head')
                self.assertEqual(trace['source_sha256'],p['source_sha256']);self.assertEqual(trace['catalog_sha256'],catalog['catalog_sha256'])
                self.assertEqual(trace['center_world_m'],[0.,0.,0.]);self.assertEqual(trace['region']['bounds'],[[-10.,-10.,-10.],[10.,10.,10.]])
                self.assertEqual(trace['region'],region['region']);self.assertEqual(region['matched_triangle_indices'],list(range(6)))
                self.assertEqual(region['triangles_total'],6);self.assertEqual(region['details_omitted'],2);self.assertEqual(len(region['triangles']),4)
                self.assertEqual(report['triangles'],[]);self.assertEqual(report['triangles_omitted'],6)
                self.assertEqual(report['damage_classification'],'not_inferred');self.assertFalse(report['execution_authority'])
                self.assertEqual(query['half_extents_m'],before['half_extents_m'])
            finally:actor.close()

    def test_catalog_or_binding_revalidates_whole_changed_packet_before_geometry(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor,several(self.support.captured(actor)))
            try:
                catalog=actor.describe_anchors(p,deadline_ns=actor.deadline_ns);selection=chosen(catalog)
                bad=copy.deepcopy(p);bad['evaluated']['vertices'][-1][0]+=.125;rehash(bad)
                with patch.object(process.surface_deformation,'_analyze_geometry') as geometry:
                    for call in (lambda:actor.describe_anchors(bad,deadline_ns=actor.deadline_ns),
                            lambda:actor.bind_anchor_selection(bad,selection,deadline_ns=actor.deadline_ns)):
                        with self.assertRaisesRegex(process.core.SmallSourceError,'small_skin_stale_source'):call()
                    geometry.assert_not_called()
            finally:actor.close()

    def test_first_invalid_tail_cannot_become_catalog_admission(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=several(self.support.captured(actor));p['evaluated']['vertices'][-1][0]+=.125;rehash(p)
            try:
                with self.assertRaisesRegex(process.core.SmallSourceError,'small_skin_LBS_replay_disagreement'):self.support.observe(actor,p)
                self.assertIsNone(actor.source)
            finally:actor.close()

    def test_old_recipe_and_forged_catalog_or_anchor_do_not_bypass_resolution(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor)
            try:
                catalog=actor.describe_anchors(p,deadline_ns=actor.deadline_ns);selection=chosen(catalog)
                query=actor.bind_anchor_selection(p,selection,deadline_ns=actor.deadline_ns)
                for field,value,reason in [('expected_source_sha256','0'*64,'stale_source'),('catalog_sha256','0'*64,'stale_catalog'),
                        ('anchor_id','bone-anchor:'+'0'*64,'unknown_anchor')]:
                    bad=copy.deepcopy(query);bad[field]=value
                    with self.subTest(field=field),patch.object(process.surface_deformation,'_analyze_geometry') as geometry:
                        with self.assertRaisesRegex(ValueError,'rig_pose_deformation_anchor_'+reason):actor.analyze(p,deadline_ns=actor.deadline_ns,anchor_query=bad)
                        geometry.assert_not_called()
                for value in (True,[],{},dict(query,qualified=True),dict(query,region=dict(kind='closed_aabb'))):
                    with self.subTest(value=value),self.assertRaisesRegex(ValueError,'rig_pose_deformation_anchor_query_fields'):
                        actor.analyze(p,deadline_ns=actor.deadline_ns,anchor_query=value)
            finally:actor.close()

    def test_wrong_source_frame_extent_and_untrusted_center_are_exact_refusals(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor)
            try:
                selection=chosen(actor.describe_anchors(p,deadline_ns=actor.deadline_ns))
                cases=[('stale_selection',lambda x:x['source_ref'].update(scene_sha256='0'*64)),
                    ('frame',lambda x:x['source_ref']['frame'].update(number=True)),('stale_catalog',lambda x:x.update(catalog_sha256='0'*64)),
                    ('anchor_id',lambda x:x.update(anchor_id='Bone.head')),('unknown_anchor',lambda x:x.update(anchor_id='bone-anchor:'+'0'*64)),
                    ('half_extents',lambda x:x['half_extents_m'].__setitem__(0,True)),('half_extents',lambda x:x['half_extents_m'].__setitem__(1,0.)),
                    ('half_extents',lambda x:x['half_extents_m'].__setitem__(1,1e6+1)),('selection_fields',lambda x:x.update(center_world_m=[50.,50.,50.])),
                    ('selection_fields',lambda x:x.update(region=region_selection(p)['region']))]
                for reason,change in cases:
                    bad=copy.deepcopy(selection);change(bad)
                    with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,'rig_pose_deformation_anchor_'+reason):
                        actor.bind_anchor_selection(p,bad,deadline_ns=actor.deadline_ns)
            finally:actor.close()

    def test_fresh_call_recomputes_same_stable_catalog_and_refuses_old_live_recipe(self):
        with self.support.setup_actor() as h:
            first=h.create();p=self.support.observe(first);catalog=first.describe_anchors(p,deadline_ns=first.deadline_ns)
            selection=chosen(catalog);old=first.bind_anchor_selection(p,selection,deadline_ns=first.deadline_ns);first.close()
            ready=h.handshake.side_effect
            def fresh_ready(actor):
                value=ready(actor);value['document_epoch']='b'*32;return value
            h.handshake.side_effect=fresh_ready;child=Process();child.pid=h.child.pid
            with patch.object(process.subprocess,'Popen',return_value=child):second=h.create()
            try:
                p2=self.support.observe(second);catalog2=second.describe_anchors(p2,deadline_ns=second.deadline_ns)
                self.assertNotEqual(p['source_sha256'],p2['source_sha256']);self.assertEqual(catalog['catalog_sha256'],catalog2['catalog_sha256'])
                fresh=second.bind_anchor_selection(p2,selection,deadline_ns=second.deadline_ns)
                self.assertEqual(fresh['expected_source_sha256'],p2['source_sha256'])
                with self.assertRaisesRegex(ValueError,'rig_pose_deformation_anchor_stale_source'):
                    second.analyze(p2,deadline_ns=second.deadline_ns,anchor_query=old)
                self.assertEqual(second.analyze(p2,deadline_ns=second.deadline_ns,anchor_query=fresh)['anchor_query']['anchor_id'],selection['anchor_id'])
            finally:second.close()

    def test_operator_profile_bytes_change_invalidates_stable_catalog_even_same_scene(self):
        with self.support.setup_actor() as h:
            first=h.create();p=self.support.observe(first);catalog=first.describe_anchors(p,deadline_ns=first.deadline_ns);selection=chosen(catalog);first.close()
            h.path.write_bytes(h.path.read_bytes()+b' ');child=Process();child.pid=h.child.pid
            with patch.object(process.subprocess,'Popen',return_value=child):second=h.create()
            try:
                p2=self.support.observe(second);catalog2=second.describe_anchors(p2,deadline_ns=second.deadline_ns)
                self.assertNotEqual(catalog['catalog_sha256'],catalog2['catalog_sha256'])
                with self.assertRaisesRegex(ValueError,'rig_pose_deformation_anchor_stale_catalog'):
                    second.bind_anchor_selection(p2,selection,deadline_ns=second.deadline_ns)
            finally:second.close()

    def test_unavailable_underflow_anchor_is_retained_but_not_selectable(self):
        with self.support.setup_actor() as h:
            unit=5e-324;profile=copy.deepcopy(h.profile);profile['unit_scale_m']=unit;h.path.write_text(json.dumps(profile))
            ready=h.handshake.side_effect
            def tiny_ready(actor):
                value=ready(actor);value['unit_scale_m']=unit;return value
            h.handshake.side_effect=tiny_ready;actor=h.create();p=offset_rest(self.support.captured(actor));p['inputs']['unit_scale_m']=unit;rehash(p)
            try:
                p=self.support.observe(actor,p);catalog=actor.describe_anchors(p,deadline_ns=actor.deadline_ns)
                endpoint=next(a for a in catalog['anchors'] if a['endpoint']=='head')
                self.assertEqual(endpoint['state'],'unavailable');self.assertEqual(endpoint['reason'],'coordinate_underflow')
                self.assertIsNone(endpoint['position_world_m']);self.assertEqual(catalog['completeness']['anchors_total'],2)
                with self.assertRaisesRegex(ValueError,'rig_pose_deformation_anchor_anchor_unavailable'):
                    actor.bind_anchor_selection(p,chosen(catalog),deadline_ns=actor.deadline_ns)
            finally:actor.close()

    def test_original_window_closed_actor_and_input_pin_checks_remain(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor);selection=chosen(actor.describe_anchors(p,deadline_ns=actor.deadline_ns))
            try:
                for call in (lambda:actor.describe_anchors(p,deadline_ns=actor.deadline_ns+1),
                        lambda:actor.bind_anchor_selection(p,selection,deadline_ns=actor.deadline_ns+1)):
                    with self.assertRaisesRegex(process.core.SmallSourceError,'window'):call()
                for call in (lambda:actor.describe_anchors(p,deadline_ns=actor.deadline_ns),
                        lambda:actor.bind_anchor_selection(p,selection,deadline_ns=actor.deadline_ns)):
                    with patch.object(actor,'verify_inputs',side_effect=[None,process.core.SmallSourceError('scene_pin','unavailable')]) as pins:
                        with self.assertRaisesRegex(process.core.SmallSourceError,'small_skin_scene_pin'):call()
                        self.assertEqual(pins.call_count,2)
                actor.close()
                with self.assertRaisesRegex(process.core.SmallSourceError,'window'):actor.describe_anchors(p,deadline_ns=actor.deadline_ns)
            finally:actor.close()

    def test_queries_are_exclusive_and_old_B1_region_and_four_faces_remain(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor,several(self.support.captured(actor)))
            try:
                old=actor.bind_selection(p,transport.stable_selection(p,(0,1,2,3)),deadline_ns=actor.deadline_ns)
                region=actor.bind_region_selection(p,region_selection(p),deadline_ns=actor.deadline_ns)
                recipe=actor.bind_anchor_selection(p,chosen(actor.describe_anchors(p,deadline_ns=actor.deadline_ns)),deadline_ns=actor.deadline_ns)
                for kw in (dict(query=old,anchor_query=recipe),dict(region_query=region,anchor_query=recipe),dict(query=old,region_query=region,anchor_query=recipe)):
                    with self.subTest(fields=list(kw)),self.assertRaisesRegex(ValueError,'rig_pose_deformation_query_modes'):actor.analyze(p,deadline_ns=actor.deadline_ns,**kw)
                self.assertEqual(actor.analyze(p,deadline_ns=actor.deadline_ns,query=old)['task_query']['triangle_indices'],[0,1,2,3])
                self.assertEqual(actor.analyze(p,deadline_ns=actor.deadline_ns,region_query=region)['region_query']['triangles_total'],6)
                with self.assertRaisesRegex(ValueError,'deformation_query_fields'):
                    deformation.analyze(one_triangle(),deadline_ns=time.perf_counter_ns()+5_000_000_000,query=recipe)
            finally:actor.close()


class AnchorCLITests(unittest.TestCase):
    def invoke(self,*,catalog_mode=False,blob=None,change_file=False,expire_selection=False,second_changed=False,
            relative=False,close_exit=0,expire_close=False,late_encode=False,oversize=False,publish_pin_change=False):
        support=transport.SmallSourceTransportTests()
        with support.setup_actor() as h:
            preparer=h.create();p=support.observe(preparer,several(support.captured(preparer)))
            catalog=preparer.describe_anchors(p,deadline_ns=preparer.deadline_ns);selection=chosen(catalog);preparer.close()
            child=Process();child.pid=h.child.pid
            with patch.object(process.subprocess,'Popen',return_value=child):actor=h.create()
            p=several(support.captured(actor));actor.received_ns=100;actor.deadline_ns=1000
            path=h.root/'anchor.json';path.write_bytes(json.dumps(selection).encode() if blob is None else blob)
            out=h.root/'output';clock=[100];events=[];saved_names={};real_open=Path.open;real_fsync=os.fsync;real_dumps=json.dumps;real_replace=os.replace
            real_analyze=actor.analyze;real_catalog=actor.describe_anchors;real_close=actor.close
            def next_packet():
                if change_file:path.write_text('null')
                packet=copy.deepcopy(p)
                if second_changed and actor.sequence==2:
                    mesh=packet['inputs']['closure'][2];mesh['matrix_parent_inverse'][0][3]=.125
                    mesh['matrix_basis'][0][3]=-.125;mesh['location'][0]=-.125;rehash(packet)
                return dict(kind='snapshot',id=actor.sequence,packet=packet)
            def analyze(*a,**kw):
                events.append(('analyze',copy.deepcopy(kw)));result=real_analyze(*a,**kw)
                if oversize:result['oversize_test_padding']='x'*(process.r.MAX_BYTES+1)
                return result
            def describe(*a,**kw):
                events.append(('catalog',copy.deepcopy(kw)));result=real_catalog(*a,**kw)
                if oversize:result['oversize_test_padding']='x'*(process.r.MAX_BYTES+1)
                return result
            def close():
                if not actor.closed:
                    events.append(('close',None));real_close();child.returncode=close_exit
                    if expire_close:clock[0]=1000
            def opened(file,*a,**kw):
                stream=real_open(file,*a,**kw);saved_names[stream.fileno()]=file.name
                if a and a[0]=='xb':events.append(('save',file.name))
                return stream
            def fsync(fd):
                real_fsync(fd)
                if expire_selection and saved_names[fd]=='ANCHOR_SELECTION.json':clock[0]=1000
            def replaced(source,destination):
                real_replace(source,destination)
                if publish_pin_change and Path(destination).name=='REPORT.json':Path(h.profile['scene_file']).write_bytes(b'changed after publish')
            def dumps(value,*a,**kw):
                text=real_dumps(value,*a,**kw)
                if late_encode and type(value) is dict and 'evidence' in value:clock[0]=1000
                return text
            argv=['--operator-profile',str(h.path),'--output',str(out)]+(['--anchors-only'] if catalog_mode else ['--anchor-query','anchor.json' if relative else str(path)])
            stdout=io.StringIO()
            with patch.object(process,'SmallSkinSourceProcess',return_value=actor),patch.object(actor,'_next',side_effect=next_packet),\
                    patch.object(actor,'analyze',side_effect=analyze),patch.object(actor,'describe_anchors',side_effect=describe),patch.object(actor,'close',side_effect=close),\
                    patch.object(process.time,'perf_counter_ns',side_effect=lambda:clock[0]),patch.object(Path,'open',opened),\
                    patch.object(os,'fsync',fsync),patch.object(os,'replace',replaced),patch.object(process.run_reader.__globals__['json'],'dumps',dumps),contextlib.redirect_stdout(stdout):
                code=process.main(argv)
            lines=stdout.getvalue().splitlines();self.assertEqual(len(lines),1);self.assertTrue(actor.closed)
            files={f.name:f.read_bytes() for f in out.iterdir() if f.is_file()}
            return code,json.loads(lines[0]),files,events,actor.sequence,selection

    def test_anchor_cli_freezes_selection_and_passes_only_anchor_recipe(self):
        code,value,files,events,count,selection=self.invoke(change_file=True)
        self.assertEqual(code,0);self.assertEqual(count,2);self.assertEqual(value['region_query']['triangles_total'],6)
        self.assertEqual(value['anchor_query']['anchor_id'],selection['anchor_id']);self.assertEqual(json.loads(files['ANCHOR_SELECTION.json']),selection)
        self.assertNotIn('SELECTION.json',files);self.assertNotIn('REGION_SELECTION.json',files)
        kw=next(v for k,v in events if k=='analyze');self.assertIn('anchor_query',kw);self.assertNotIn('query',kw);self.assertNotIn('region_query',kw)
        self.assertLess(events.index(('close',None)),events.index(('save','REPORT_PENDING.json')))

    def test_catalog_cli_is_two_complete_reads_and_no_B2_or_selection(self):
        code,value,files,events,count,_=self.invoke(catalog_mode=True)
        self.assertEqual(code,0);self.assertEqual(count,2);self.assertEqual(value['schema'],'surface-deformation-anchor-catalog-v1')
        self.assertEqual(sum(k=='catalog' for k,v in events),1);self.assertFalse(any(k=='analyze' for k,v in events))
        self.assertNotIn('ANCHOR_SELECTION.json',files);self.assertIn('SNAPSHOTS.json',files)
        self.assertLess(events.index(('close',None)),events.index(('save','REPORT_PENDING.json')))
        self.assertFalse(value['execution_authority']);self.assertNotIn('region_query',value)

    def test_anchor_cli_null_bad_schema_or_extra_center_never_falls_back(self):
        for value in (None,True,[],{},dict(schema='surface-deformation-region-selection-v1',region={})):
            with self.subTest(value=value):
                code,result,files,events,count,_=self.invoke(blob=json.dumps(value).encode())
                self.assertEqual(code,1);self.assertEqual(count,1);self.assertIn('deformation_anchor_selection_fields',result['reason'])
                self.assertNotIn('REPORT.json',files);self.assertFalse(any(k=='analyze' for k,v in events))

    def test_anchor_cli_invalid_encoding_path_and_4k_budget_fail_before_read(self):
        for blob,reason in ((b'{"schema":0,"schema":1}','duplicate_JSON_key'),(b'{"schema":NaN}','nonfinite'),(b' '*4097,'selection_byte_budget')):
            with self.subTest(reason=reason):
                code,result,files,_,count,_=self.invoke(blob=blob)
                self.assertEqual(code,1);self.assertEqual(count,0);self.assertIn(reason,result['reason']);self.assertNotIn('REPORT.json',files)
        code,result,files,_,count,_=self.invoke(relative=True)
        self.assertEqual(code,1);self.assertEqual(count,0);self.assertIn('selection_path',result['reason']);self.assertNotIn('REPORT.json',files)

    def test_anchor_selection_save_expiry_prevents_observation(self):
        code,result,files,_,count,_=self.invoke(expire_selection=True)
        self.assertEqual(code,1);self.assertEqual(count,0);self.assertEqual(result['reason'],'rig_pose_original_deadline')
        self.assertIn('ANCHOR_SELECTION.json',files);self.assertNotIn('REPORT.json',files)

    def test_changed_second_source_blocks_both_catalog_and_query(self):
        for catalog_mode in (True,False):
            with self.subTest(catalog=catalog_mode):
                code,result,files,events,count,_=self.invoke(catalog_mode=catalog_mode,second_changed=True)
                self.assertEqual(code,1);self.assertEqual(count,2);self.assertEqual(result['reason'],'small_skin_stale_source')
                self.assertNotIn('REPORT.json',files);self.assertFalse(any(k in ('catalog','analyze') for k,v in events))

    def test_close_error_or_close_expiry_prevents_both_success_modes(self):
        for catalog_mode in (True,False):
            for options,reason in ((dict(close_exit=73),'rig_pose_source_worker_exit'),(dict(expire_close=True),'rig_pose_original_deadline')):
                with self.subTest(catalog=catalog_mode,options=options):
                    code,result,files,_,count,_=self.invoke(catalog_mode=catalog_mode,**options)
                    self.assertEqual(code,1);self.assertEqual(count,2);self.assertEqual(result['reason'],reason)
                    self.assertNotIn('REPORT.json',files);self.assertNotIn('REPORT_PENDING.json',files)

    def test_late_encoding_expiry_or_source_change_revokes_both_reports(self):
        for catalog_mode in (True,False):
            for option,reason in (('late_encode','rig_pose_original_deadline'),('publish_pin_change','small_skin_scene_pin')):
                with self.subTest(catalog=catalog_mode,stage=option):
                    code,result,files,_,count,_=self.invoke(catalog_mode=catalog_mode,**{option:True})
                    self.assertEqual(code,1);self.assertEqual(count,2);self.assertEqual(result['reason'],reason)
                    self.assertNotIn('REPORT.json',files);self.assertIn('REVOKED_REPORT.json',files)

    def test_both_anchor_outputs_reject_more_than_512k_success_bytes(self):
        for catalog_mode in (True,False):
            with self.subTest(catalog=catalog_mode):
                code,result,files,_,count,_=self.invoke(catalog_mode=catalog_mode,oversize=True)
                self.assertEqual(code,1);self.assertEqual(count,2);self.assertEqual(result['reason'],'rig_pose_deformation_anchor_report_byte_budget')
                self.assertNotIn('REPORT.json',files);self.assertLess(len(json.dumps(result).encode()),process.r.MAX_BYTES)

    def test_all_four_cli_modes_are_mutually_exclusive_before_launch(self):
        modes=[['--anchors-only'],['--anchor-query','anchor.json'],['--region-query','region.json'],['--triangle-query','faces.json']]
        for first,second in itertools.combinations(modes,2):
            with self.subTest(modes=first+second),tempfile.TemporaryDirectory() as folder,patch.object(process,'SmallSkinSourceProcess') as constructor,contextlib.redirect_stderr(io.StringIO()):
                root=Path(folder).resolve()
                with self.assertRaises(SystemExit) as caught:process.main(['--operator-profile',str(root/'profile.json'),'--output',str(root/'out'),*first,*second])
                self.assertEqual(caught.exception.code,2);constructor.assert_not_called()


if __name__=='__main__':unittest.main()
