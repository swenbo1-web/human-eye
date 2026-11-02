"""Region queries retain full source, fixed selection and owned CLI lifetime.

Authored complete sources and mocked stdio launch exercise the real source
consumer; none of these tests grants native asset or model-benefit coverage.
"""
import contextlib,copy,io,json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from human_eye_plugin import small_skin_source_process as process,surface_deformation as deformation
from verification import test_small_skin_source_process as transport
from verification.test_small_skin_source import rehash
from verification.test_surface_deformation import one_triangle


def selection(packet,bounds=None):
    old=transport.stable_selection(packet)
    return dict(schema='surface-deformation-region-selection-v1',source_ref=old['source_ref'],
        region=dict(kind='closed_aabb',coordinate_space='current_world_m',
            bounds=[[-1.,-1.,-1.],[8.,8.,1.]] if bounds is None else copy.deepcopy(bounds)))


def several(packet,*,unweighted=False):
    """Six disjoint right triangles, all identity-skinned and in the full box."""
    p=copy.deepcopy(packet);points=[];faces=[];edges=[]
    for i in range(6):
        x=2.*(i%3);y=2.*(i//3);base=len(points)
        points.extend([[x,y,0.],[x+1.,y,0.],[x,y+1.,0.]])
        faces.append([base,base+1,base+2]);edges.extend([[base,base+1],[base,base+2],[base+1,base+2]])
    weights=[[[0,1.]] for _ in points]
    if unweighted:weights[0]=[]
    p['inputs']['mesh'].update(vertices=points,triangles=faces,edges=edges,weights=weights)
    p['evaluated'].update(vertices=copy.deepcopy(points),triangles=copy.deepcopy(faces))
    return rehash(p)


class RegionProductTests(unittest.TestCase):
    def setUp(self):self.support=transport.SmallSourceTransportTests()

    def test_region_requires_observation_and_freezes_selection(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.captured(actor)
            try:
                with self.assertRaisesRegex(process.core.SmallSourceError,'small_skin_observation_required'):
                    actor.bind_region_selection(p,selection(p),deadline_ns=actor.deadline_ns)
                p=self.support.observe(actor);chosen=selection(p);prior=copy.deepcopy(chosen)
                query=actor.bind_region_selection(p,chosen,deadline_ns=actor.deadline_ns)
                self.assertEqual(chosen,prior);self.assertEqual(query['schema'],'surface-deformation-region-query-v1')
                self.assertEqual(query['expected_source_sha256'],p['source_sha256'])
                chosen['region']['bounds'][0][0]=50.
                self.assertEqual(query['region'],prior['region'])
            finally:actor.close()

    def test_region_deadline_must_be_original_and_transport_open(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor)
            try:
                with self.assertRaisesRegex(process.core.SmallSourceError,'selection_window'):
                    actor.bind_region_selection(p,selection(p),deadline_ns=actor.deadline_ns+1)
                actor.close()
                with self.assertRaisesRegex(process.core.SmallSourceError,'selection_window'):
                    actor.bind_region_selection(p,selection(p),deadline_ns=actor.deadline_ns)
            finally:actor.close()

    def test_valid_region_omits_global_details_honestly_and_preserves_counts(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor)
            try:
                normal=actor.analyze(p,deadline_ns=actor.deadline_ns)
                query=actor.bind_region_selection(p,selection(p),deadline_ns=actor.deadline_ns)
                report=actor.analyze(p,deadline_ns=actor.deadline_ns,region_query=query)
                region=report.pop('region_query');self.assertNotIn('task_query',report)
                self.assertEqual(report.pop('global_detail_scope'),'omitted_for_requested_region')
                self.assertEqual(report.pop('triangles'),[]);self.assertEqual(report.pop('triangles_omitted'),1)
                normal.pop('triangles');normal.pop('triangles_omitted');self.assertEqual(report,normal)
                self.assertEqual(region['source_sha256'],p['source_sha256']);self.assertEqual(region['matched_triangle_indices'],[0])
                self.assertEqual(region['triangles'][0]['principal_stretches'],[1.,1.]);self.assertEqual(region['triangles_total'],1)
                self.assertEqual(region['metric_scope'],'whole_original_triangles_not_clipped_integrals')
            finally:actor.close()

    def test_six_members_have_complete_ids_counts_and_honest_four_detail_limit(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor,several(self.support.captured(actor)))
            try:
                query=actor.bind_region_selection(p,selection(p),deadline_ns=actor.deadline_ns)
                region=actor.analyze(p,deadline_ns=actor.deadline_ns,region_query=query)['region_query']
                self.assertEqual(region['matched_triangle_indices'],list(range(6)));self.assertTrue(region['membership_complete'])
                self.assertEqual(region['triangles_scanned'],6);self.assertEqual(region['vertices_transformed'],18)
                self.assertEqual(region['triangles_total'],6);self.assertEqual(region['triangles_measured'],6)
                self.assertEqual(region['triangles_unknown'],0);self.assertEqual(region['triangles_collapsed'],0)
                self.assertEqual(len(region['triangles']),4);self.assertEqual(region['details_omitted'],2)
                self.assertTrue(region['all_members_measurable']);self.assertEqual(region['unknown_reasons'],{})
                for witness in region['metric_extrema'].values():self.assertEqual(witness,dict(triangle=0,value=1.))
            finally:actor.close()

    def test_unknown_members_are_not_hidden_by_four_detail_limit(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor,several(self.support.captured(actor),unweighted=True))
            try:
                query=actor.bind_region_selection(p,selection(p),deadline_ns=actor.deadline_ns)
                region=actor.analyze(p,deadline_ns=actor.deadline_ns,region_query=query)['region_query']
                self.assertEqual(region['status'],'partial');self.assertFalse(region['all_members_measurable'])
                self.assertEqual(region['triangles_unknown'],1);self.assertEqual(region['triangles_measured'],5)
                self.assertEqual(region['unknown_reasons'],{'unweighted_vertex_source':1})
                row=next(x for x in region['triangles'] if x['triangle']==0)
                self.assertEqual(row['state'],'unknown');self.assertIsNone(row['principal_stretches'])
                for witness in region['metric_extrema'].values():self.assertEqual(witness,dict(triangle=1,value=1.))
            finally:actor.close()

    def test_empty_region_is_complete_zero_members_not_healthy_geometry(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor)
            try:
                query=actor.bind_region_selection(p,selection(p,[[50.,50.,50.],[51.,51.,51.]]),deadline_ns=actor.deadline_ns)
                report=actor.analyze(p,deadline_ns=actor.deadline_ns,region_query=query);region=report['region_query']
                self.assertEqual(region['status'],'empty');self.assertEqual(region['matched_triangle_indices'],[])
                self.assertEqual(region['triangles_scanned'],1);self.assertEqual(region['triangles_total'],0)
                self.assertEqual(region['triangles'],[]);self.assertEqual(region['details_omitted'],0)
                self.assertTrue(region['membership_complete']);self.assertTrue(all(x is None for x in region['metric_extrema'].values()))
                self.assertEqual(report['damage_classification'],'not_inferred');self.assertFalse(report['execution_authority'])
            finally:actor.close()

    def test_region_full_tail_invalid_source_is_refused_before_geometry(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=several(self.support.captured(actor));p['evaluated']['vertices'][-1][0]+=.125;rehash(p)
            try:
                with patch.object(process.surface_deformation,'_analyze_geometry') as geometry:
                    with self.assertRaisesRegex(process.core.SmallSourceError,'small_skin_LBS_replay_disagreement'):
                        self.support.observe(actor,p)
                    self.assertIsNone(actor.source);geometry.assert_not_called()
            finally:actor.close()

    def test_region_selection_revalidates_entire_observed_packet(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor,several(self.support.captured(actor)))
            try:
                corrupt=copy.deepcopy(p);corrupt['evaluated']['vertices'][-1][0]+=.125;rehash(corrupt)
                with patch.object(process.surface_deformation,'_analyze_geometry') as geometry:
                    with self.assertRaisesRegex(process.core.SmallSourceError,'small_skin_stale_source'):
                        actor.bind_region_selection(corrupt,selection(p,[[-1.,-1.,-1.],[1.1,1.1,1.]]),deadline_ns=actor.deadline_ns)
                    geometry.assert_not_called()
            finally:actor.close()

    def test_region_bound_to_old_source_cannot_be_reused(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor)
            try:
                query=actor.bind_region_selection(p,selection(p),deadline_ns=actor.deadline_ns);query['expected_source_sha256']='0'*64
                with self.assertRaisesRegex(ValueError,'rig_pose_deformation_region_stale_source'):
                    actor.analyze(p,deadline_ns=actor.deadline_ns,region_query=query)
            finally:actor.close()

    def test_wrong_region_source_frame_space_and_bounds_are_exactly_refused(self):
        cases=[('stale_selection',lambda v:v['source_ref'].update(scene_sha256='0'*64)),
            ('frame',lambda v:v['source_ref']['frame'].update(number=True)),
            ('region_kind',lambda v:v['region'].update(coordinate_space='reference_local_m')),
            ('region_bounds',lambda v:v['region']['bounds'][0].__setitem__(0,True)),
            ('region_extent',lambda v:v['region']['bounds'][1].__setitem__(0,-1.)),
            ('selection_fields',lambda v:v.update(triangle_indices=[0]))]
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor)
            try:
                for code,change in cases:
                    with self.subTest(code=code):
                        chosen=selection(p);change(chosen)
                        with self.assertRaisesRegex(ValueError,'rig_pose_deformation_region_'+code):
                            actor.bind_region_selection(p,chosen,deadline_ns=actor.deadline_ns)
            finally:actor.close()

    def test_region_binding_checks_inputs_before_and_after_its_validation(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor);verify=actor.verify_inputs
            try:
                with patch.object(actor,'verify_inputs',side_effect=[None,process.core.SmallSourceError('scene_pin','unavailable')]) as pins:
                    with self.assertRaisesRegex(process.core.SmallSourceError,'small_skin_scene_pin'):
                        actor.bind_region_selection(p,selection(p),deadline_ns=actor.deadline_ns)
                    self.assertEqual(pins.call_count,2)
                verify()
            finally:actor.close()

    def test_api_queries_mutually_exclusive_and_old_four_face_query_unchanged(self):
        with self.support.setup_actor() as h:
            actor=h.create();p=self.support.observe(actor,several(self.support.captured(actor)))
            try:
                old=actor.bind_selection(p,transport.stable_selection(p,(0,1,2,3)),deadline_ns=actor.deadline_ns)
                new=actor.bind_region_selection(p,selection(p),deadline_ns=actor.deadline_ns)
                with patch.object(process.surface_deformation,'_analyze_geometry') as geometry:
                    with self.assertRaisesRegex(ValueError,'rig_pose_deformation_query_modes'):
                        actor.analyze(p,deadline_ns=actor.deadline_ns,query=old,region_query=new)
                    geometry.assert_not_called()
                report=actor.analyze(p,deadline_ns=actor.deadline_ns,query=old)
                self.assertEqual(report['task_query']['triangle_indices'],[0,1,2,3]);self.assertNotIn('region_query',report)
                with self.assertRaisesRegex(ValueError,'deformation_query_indices'):
                    actor.bind_selection(p,transport.stable_selection(p,(0,1,2,3,4)),deadline_ns=actor.deadline_ns)
                legacy=one_triangle()
                with self.assertRaisesRegex(ValueError,'deformation_query_fields'):
                    deformation.analyze(legacy,deadline_ns=time.perf_counter_ns()+5_000_000_000,query=new)
            finally:actor.close()


class RegionCLITests(unittest.TestCase):
    def invoke(self,*,blob=None,change_file=False,expire_selection=False,second_changed=False,relative=False,close_exit=0,expire_close=False,late_encode=False):
        support=transport.SmallSourceTransportTests()
        with support.setup_actor() as h:
            actor=h.create();p=several(support.captured(actor));actor.received_ns=100;actor.deadline_ns=1000
            chosen=selection(p);path=h.root/'region.json';path.write_bytes(json.dumps(chosen).encode() if blob is None else blob)
            out=h.root/'output';clock=[100];events=[];saved_names={};real_open=Path.open;real_fsync=os.fsync;real_dumps=json.dumps
            real_analyze=actor.analyze;real_close=actor.close
            def next_packet():
                if change_file:path.write_text('null')
                packet=copy.deepcopy(p)
                if second_changed and actor.sequence==2:
                    mesh=packet['inputs']['closure'][2];mesh['matrix_parent_inverse'][0][3]=.125
                    mesh['matrix_basis'][0][3]=-.125;mesh['location'][0]=-.125;rehash(packet)
                return dict(kind='snapshot',id=actor.sequence,packet=packet)
            def analyze(*a,**kw):events.append(('analyze',copy.deepcopy(kw)));return real_analyze(*a,**kw)
            def close():
                if not actor.closed:
                    events.append(('close',None));real_close();h.child.returncode=close_exit
                    if expire_close:clock[0]=1000
            def opened(file,*a,**kw):
                stream=real_open(file,*a,**kw);saved_names[stream.fileno()]=file.name
                if a and a[0]=='xb':events.append(('save',file.name))
                return stream
            def fsync(fd):
                real_fsync(fd)
                if expire_selection and saved_names[fd]=='REGION_SELECTION.json':clock[0]=1000
            def dumps(value,*a,**kw):
                text=real_dumps(value,*a,**kw)
                if late_encode and type(value) is dict and 'evidence' in value:clock[0]=1000
                return text
            argv=['--operator-profile',str(h.path),'--output',str(out),'--region-query','region.json' if relative else str(path)]
            stdout=io.StringIO()
            with patch.object(process,'SmallSkinSourceProcess',return_value=actor),patch.object(actor,'_next',side_effect=next_packet),\
                    patch.object(actor,'analyze',side_effect=analyze),patch.object(actor,'close',side_effect=close),\
                    patch.object(process.time,'perf_counter_ns',side_effect=lambda:clock[0]),patch.object(Path,'open',opened),\
                    patch.object(os,'fsync',fsync),patch.object(process.run_reader.__globals__['json'],'dumps',dumps),contextlib.redirect_stdout(stdout):
                code=process.main(argv)
            lines=stdout.getvalue().splitlines();self.assertEqual(len(lines),1);self.assertTrue(actor.closed)
            files={f.name:f.read_bytes() for f in out.iterdir() if f.is_file()}
            return code,json.loads(lines[0]),files,events,actor.sequence,chosen

    def test_cli_freezes_region_file_and_passes_only_bound_region_query(self):
        code,value,files,events,count,chosen=self.invoke(change_file=True)
        self.assertEqual(code,0);self.assertEqual(count,2);self.assertEqual(value['region_query']['matched_triangle_indices'],list(range(6)))
        self.assertNotIn('task_query',value);self.assertEqual(json.loads(files['REGION_SELECTION.json']),chosen)
        self.assertNotIn('SELECTION.json',files);kw=next(v for k,v in events if k=='analyze')
        self.assertIn('region_query',kw);self.assertNotIn('query',kw)
        self.assertEqual(kw['region_query']['expected_source_sha256'],value['source_sha256'])
        self.assertLess(events.index(('close',None)),events.index(('save','REPORT_PENDING.json')))

    def test_cli_null_or_bad_schema_cannot_fall_back_to_overview(self):
        for value in (None,True,[],{},dict(schema='surface-deformation-selection-v1',triangle_indices=[0])):
            with self.subTest(value=value):
                code,result,files,events,count,_=self.invoke(blob=json.dumps(value).encode())
                self.assertEqual(code,1);self.assertEqual(count,1);self.assertIn('deformation_region_selection_fields',result['reason'])
                self.assertNotIn('REPORT.json',files);self.assertFalse(any(k=='analyze' for k,v in events))

    def test_cli_duplicate_nonfinite_and_byte_budget_fail_before_inspect(self):
        for blob,reason in ((b'{"schema":0,"schema":1}','duplicate_JSON_key'),(b'{"schema":NaN}','nonfinite'),(b' '*4097,'selection_byte_budget')):
            with self.subTest(reason=reason):
                code,result,files,_,count,_=self.invoke(blob=blob)
                self.assertEqual(code,1);self.assertEqual(count,0);self.assertIn(reason,result['reason']);self.assertNotIn('REPORT.json',files)

    def test_cli_relative_region_path_is_refused_before_inspect(self):
        code,result,files,_,count,_=self.invoke(relative=True)
        self.assertEqual(code,1);self.assertEqual(count,0);self.assertIn('selection_path',result['reason']);self.assertNotIn('REPORT.json',files)

    def test_cli_region_selection_fsync_keeps_original_deadline(self):
        code,result,files,_,count,_=self.invoke(expire_selection=True)
        self.assertEqual(code,1);self.assertEqual(count,0);self.assertEqual(result['reason'],'rig_pose_original_deadline')
        self.assertIn('REGION_SELECTION.json',files);self.assertNotIn('REPORT.json',files)

    def test_cli_changed_second_source_cannot_rebind_region(self):
        code,result,files,events,count,_=self.invoke(second_changed=True)
        self.assertEqual(code,1);self.assertEqual(count,2);self.assertEqual(result['reason'],'small_skin_stale_source')
        self.assertNotIn('REPORT.json',files);self.assertFalse(any(k=='analyze' for k,v in events))

    def test_cli_nonzero_close_or_close_expiry_cannot_publish_region_success(self):
        for options,reason in ((dict(close_exit=73),'rig_pose_source_worker_exit'),(dict(expire_close=True),'rig_pose_original_deadline')):
            with self.subTest(options=options):
                code,result,files,_,count,_=self.invoke(**options)
                self.assertEqual(code,1);self.assertEqual(count,2);self.assertEqual(result['reason'],reason)
                self.assertNotIn('REPORT.json',files);self.assertNotIn('REPORT_PENDING.json',files)

    def test_cli_late_region_success_encoding_revokes_report(self):
        code,result,files,_,count,_=self.invoke(late_encode=True)
        self.assertEqual(code,1);self.assertEqual(count,2);self.assertEqual(result['reason'],'rig_pose_original_deadline')
        self.assertNotIn('REPORT.json',files);self.assertIn('REVOKED_REPORT.json',files)

    def test_cli_triangle_and_region_flags_are_mutually_exclusive_before_launch(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(process,'SmallSkinSourceProcess') as constructor,contextlib.redirect_stderr(io.StringIO()):
            root=Path(folder).resolve()
            with self.assertRaises(SystemExit) as caught:
                process.main(['--operator-profile',str(root/'profile.json'),'--output',str(root/'out'),
                    '--triangle-query',str(root/'faces.json'),'--region-query',str(root/'region.json')])
            self.assertEqual(caught.exception.code,2);constructor.assert_not_called()


if __name__=='__main__':unittest.main()
