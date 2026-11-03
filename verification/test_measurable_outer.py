"""Synthetic checker counterexamples; not product/source admission evidence."""
import copy,hashlib,json,math,unittest
from pathlib import Path
from unittest.mock import patch
from verification import measurable_outer_checker as c


REGISTRATION=Path(__file__).parent/'fixtures/measurable_outer_extremum_v1.json'


def packet(reg,pid=201):
    identity={k:'a'*64 for k in c.PIN_KEYS};identity.update(runtime_source_sha256='d9b01eec9ce561b9f9fe5304cc37c50aa641b1826ed3ee788501eb2f49192360',document_epoch='b'*32,process_id=pid)
    raw=c._packet(reg)['inputs'];raw['mesh']['name']=reg['mesh_name'];raw['actions']=[]
    bones=[];evaluated=[]
    for spec in reg['bones']:
        matrix=copy.deepcopy(reg['rig_matrix_world'])
        for axis in range(3):matrix[axis][3]=spec['pose_location'][axis]
        row=dict(name=spec['name'],parent=None,rest_head=spec['head'][:],rest_tail=spec['tail'][:],location=spec['pose_location'][:],
            rest_matrix=copy.deepcopy(reg['rig_matrix_world']),basis_matrix=copy.deepcopy(matrix),pose_matrix=copy.deepcopy(matrix),
            pose_head=spec['pose_location'][:],pose_tail=[a+b-d for a,b,d in zip(spec['pose_location'],spec['tail'],spec['head'])])
        bones.append(row);evaluated.append({k:copy.deepcopy(row[k]) for k in ('name','pose_matrix','pose_head','pose_tail')})
    raw['rig']=dict(name=reg['rig_name'],bones=bones)
    current=c._packet(reg)['evaluated'];current.update(rig_matrix_world=copy.deepcopy(reg['rig_matrix_world']),triangles=copy.deepcopy(reg['triangles']),bones=evaluated,original_links_verified=True)
    value=dict(schema='small-skin-source-snapshot-v1',identity=identity,inputs=raw,evaluated=current,
        audit=dict(before_sha256=c.digest(raw),after_sha256=c.digest(raw),independent_before_sha256='c'*64,independent_after_sha256='c'*64),capture_id='test-only')
    value['source_sha256']=c.digest({k:v for k,v in value.items() if k!='capture_id'});return value


def publication(report):return json.dumps(report,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()+b'\n'


def outputs(reg,truth):
    rows=[copy.deepcopy(truth['rows'][i]) for i in truth['core_members']]
    ref=dict(catalog_sha256='d'*64,policy_sha256='e'*64,anchor_id=truth['registered_anchor_id'],half_extents_m=reg['policy']['core_half'][:],region=copy.deepcopy(reg['core_region']))
    report=dict(schema='surface-deformation-core-facts-v1',source_sha256=truth['source_sha256'],
        execution_authority=False,geometry_setters=0,original_file_saved=False,
        source_validation=dict(schema='small-skin-source-snapshot-v1',method='external_binding_full_dependency_FK_and_LBS',max_replay_error=0.,replay_atol=2e-5,animation_curves_checked=0,not_coordinate_measurement_error=True),
        live_capture={k:truth['identity'][k] for k in ('document_epoch','process_id')},source_ref=copy.deepcopy(truth['source_ref']),operator_pins={k:truth['identity'][k] for k in c.PIN_KEYS},
        core_ref=ref,facts=copy.deepcopy(truth['core_facts']),core_witnesses=dict.fromkeys(c.METRICS,0),
        completeness=dict(membership_complete=True,core_facts_complete=True,metric_witnesses_complete=True,unknown_reasons_omitted=0,member_ids_omitted=3,per_face_rows_omitted=3,all_members_unknown=False,all_members_measurable=False),
        scope=dict(metric_scope='whole_original_triangles_not_clipped_integrals',extrema_scope='measured_and_collapsed_core_members_only',peripheral_context='not_reported',peripheral_shrinking=False,
            damage='not_inferred',anatomy='not_inferred',volume='not_checked',visibility='not_checked',timeline='not_checked',contact_extent='not_checked'))
    raw=publication(report)
    audit=dict(schema='surface-deformation-core-facts-audit-v1',source_sha256=truth['source_sha256'],core_ref=copy.deepcopy(ref),core_triangle_indices=[0,1,2],core_rows=rows,core_rows_sha256=c.digest(rows),
        core_membership=dict(source_sha256=truth['source_sha256'],region=copy.deepcopy(reg['core_region']),membership_complete=True,triangles_scanned=4,vertices_transformed=12,matched_triangle_indices=[0,1,2]),
        published_publication_bytes=len(raw),published_publication_sha256=hashlib.sha256(raw).hexdigest(),actor_B2_rows_passes=1,geometry_cache_preparations=1,region_scans=1,
        pure_projection_B2_rows_passes=0,pure_projection_geometry_cache_preparations=0,pure_projection_region_scans=0,candidates_evaluated=0)
    return report,audit


class MeasurableOuterTests(unittest.TestCase):
    def setUp(self):
        self.reg=c.load_registration(REGISTRATION);self.p=packet(self.reg);self.truth=c.verify_snapshot(self.p,self.reg);self.report,self.audit=outputs(self.reg,self.truth)

    def test_frozen_independent_preflight_is_measured_and_discriminating(self):
        value=c.preflight(self.reg)
        self.assertTrue(value['passed']);self.assertEqual(value['core_members'],[0,1,2]);self.assertEqual(value['peripheral_members'],[3])
        self.assertEqual(value['rows'][2]['reason'],'unweighted_vertex_source');self.assertEqual(value['rows'][3]['state'],'measured')
        self.assertGreater(value['reliability']['3']['metric_error_headroom_factor'],30)
        self.assertGreater(value['reliability']['3']['area_error_headroom_factor'],25)
        self.assertTrue(c.check_report(self.report,self.audit,self.truth)['passed'])

    def test_global_extrema_cannot_substitute_for_core(self):
        report=copy.deepcopy(self.report);report['facts']['core_extrema']=self.truth['global_extrema']
        with self.assertRaisesRegex(ValueError,'facts_max_principal_stretch'):c.check_report(report,self.audit,self.truth)

    def test_peripheral_or_unknown_witness_rejected_even_with_correct_numbers(self):
        for witness in (2,3,True):
            report=copy.deepcopy(self.report);report['core_witnesses']['max_principal_stretch']=witness
            with self.subTest(witness=witness),self.assertRaisesRegex(ValueError,'core_witness'):c.check_report(report,self.audit,self.truth)

    def test_shifted_world_box_and_wrong_anchor_cannot_hide_behind_same_facts(self):
        for mutate in (lambda r:r['core_ref'].update(region=dict(kind='closed_aabb',coordinate_space='current_world_m',bounds=[[-.125,-.25,-.25],[.375,.25,.25]])),
                       lambda r:r['core_ref'].update(anchor_id=c.anchor_id('Armature','OuterShift','head'))):
            report=copy.deepcopy(self.report);mutate(report);audit=copy.deepcopy(self.audit);audit['core_ref']=copy.deepcopy(report['core_ref'])
            with self.assertRaisesRegex(ValueError,'registered_world_core'):c.check_report(report,audit,self.truth)

    def test_capture_source_and_audit_cannot_be_swapped(self):
        for mutate,reason in ((lambda r:r.update(source_sha256='0'*64),'report_source_binding'),
                              (lambda r:r['live_capture'].update(process_id=999),'report_live_binding')):
            report=copy.deepcopy(self.report);mutate(report)
            with self.assertRaisesRegex(ValueError,reason):c.check_report(report,self.audit,self.truth)
        audit=copy.deepcopy(self.audit);audit['source_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'audit_binding'):c.check_report(self.report,audit,self.truth)
        other=c.verify_snapshot(packet(self.reg,pid=202),self.reg)
        self.assertEqual(other['geometry_sha256'],self.truth['geometry_sha256'])
        with self.assertRaisesRegex(ValueError,'report_source_binding'):c.check_report(self.report,self.audit,other)

    def test_unknown_nulls_reasons_and_omitted_audit_rows_preserved(self):
        for mutate,reason in ((lambda r:r['facts']['core_unknown_reasons'].clear(),'facts_core_unknown_reasons'),
                              (lambda r:r['facts']['core_extrema'].update(min_area_ratio=None),'facts_min_area_ratio')):
            report=copy.deepcopy(self.report);mutate(report)
            with self.assertRaisesRegex(ValueError,reason):c.check_report(report,self.audit,self.truth)
        audit=copy.deepcopy(self.audit);audit['core_rows'][2]['area_ratio']=1.
        with self.assertRaisesRegex(ValueError,'unknown_nulls'):c.check_report(self.report,audit,self.truth)
        audit=copy.deepcopy(self.audit);audit['core_rows'].pop()
        with self.assertRaisesRegex(ValueError,'audit_rows'):c.check_report(self.report,audit,self.truth)

    def test_registration_and_geometry_changes_cannot_select_new_case(self):
        reg=copy.deepcopy(self.reg);reg['vertices'][10][0]=1.5
        with self.assertRaisesRegex(ValueError,'registration_changed'):c.preflight(reg)
        packet_value=copy.deepcopy(self.p);packet_value['evaluated']['vertices'][10][0]=1.5
        packet_value['source_sha256']=c.digest({k:v for k,v in packet_value.items() if k not in ('source_sha256','capture_id')})
        with self.assertRaisesRegex(ValueError,'evaluated_vertices'):c.verify_snapshot(packet_value,self.reg)

    def test_not_realized_is_not_promoted_to_success(self):
        original=c.oracle.all_facts
        def unknown(*args):
            rows=original(*args);rows[3].update(state='unknown',reason='metric_resolution_insufficient',principal_stretches=None,area_ratio=None);return rows
        with patch.object(c.oracle,'all_facts',side_effect=unknown):value=c.preflight(self.reg)
        self.assertFalse(value['passed']);self.assertEqual(value['status'],'not_realized')

    def test_booleans_cannot_impersonate_measurement_counts_or_ids(self):
        report=copy.deepcopy(self.report);report['completeness']['unknown_reasons_omitted']=False
        with self.assertRaisesRegex(ValueError,'core_omissions'):c.check_report(report,self.audit,self.truth)
        audit=copy.deepcopy(self.audit);audit['actor_B2_rows_passes']=True
        with self.assertRaisesRegex(ValueError,'audit_work_counts'):c.check_report(self.report,audit,self.truth)
        audit=copy.deepcopy(self.audit);audit['core_rows'][0]['vertices'][0]=False
        with self.assertRaisesRegex(ValueError,'row_index_types'):c.check_report(self.report,audit,self.truth)

    def test_legacy_peripheral_query_has_own_capture_and_partial_global_status(self):
        report=copy.deepcopy(self.report);report.update(schema='surface-deformation-diagnostic-v1',source={k:self.truth['identity'][k] for k in c.PIN_KEYS+('document_epoch','process_id')},
            task_query=dict(schema='surface-deformation-query-result-v1',source_sha256=self.truth['source_sha256'],triangle_indices=[3],status='observed',triangles=[copy.deepcopy(self.truth['rows'][3])]),
            status='partial',triangles_total=4,triangles_measured=3,triangles_collapsed=0,triangles_unknown=1,unknown_reasons={'unweighted_vertex_source':1})
        self.assertTrue(c.check_peripheral_report(report,self.truth)['passed'])
        report['task_query']['triangles'][0]['principal_stretches']=[1.5]
        with self.assertRaisesRegex(ValueError,'row_stretches'):c.check_peripheral_report(report,self.truth)

    def test_source_validation_contract_cannot_be_relaxed_with_recomputed_audit(self):
        changes=[('replay_atol',.01),('replay_atol',float('inf')),('replay_atol',float('nan')),
                 ('max_replay_error',float('nan')),('max_replay_error',float('inf')),('max_replay_error',-1.),('max_replay_error',2.1e-5),
                 ('animation_curves_checked',False),('animation_curves_checked',1)]
        for key,value in changes:
            report=copy.deepcopy(self.report);report['source_validation'][key]=value;audit=copy.deepcopy(self.audit)
            if not isinstance(value,float) or math.isfinite(value):
                raw=publication(report);audit['published_publication_bytes']=len(raw);audit['published_publication_sha256']=hashlib.sha256(raw).hexdigest()
            with self.subTest(key=key,value=value),self.assertRaisesRegex(ValueError,'report_validation_metadata'):c.check_report(report,audit,self.truth)
        for mutate in (lambda v:v.pop('animation_curves_checked'),lambda v:v.update(unregistered_field=True)):
            report=copy.deepcopy(self.report);mutate(report['source_validation'])
            raw=publication(report);audit=copy.deepcopy(self.audit);audit['published_publication_bytes']=len(raw);audit['published_publication_sha256']=hashlib.sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError,'report_validation_metadata'):c.check_report(report,audit,self.truth)

    def test_matching_worker_query_accepts_only_documented_success_shapes(self):
        cap=dict(process_id=201)
        exited=dict(pid=201,state='exited',exit_code=0,no_signal_sent=True)
        absent=dict(pid=201,state='absent',error=87,query='OpenProcess QUERY_LIMITED_INFORMATION only',no_signal_sent=True)
        self.assertTrue(c.check_worker_status(exited,cap)['passed']);self.assertTrue(c.check_worker_status(absent,cap)['passed'])
        for status in (dict(exited,pid=1),dict(exited,pid=True),dict(absent,pid=1),dict(exited,no_signal_sent=1)):
            reason='worker_status_no_signal' if status.get('no_signal_sent') is not True else 'worker_status_pid'
            with self.subTest(status=status),self.assertRaisesRegex(ValueError,reason):c.check_worker_status(status,cap)
        with self.assertRaisesRegex(ValueError,'worker_status_pid'):c.check_worker_status(exited,dict(process_id=True))

    def test_worker_unknown_running_error_or_nonzero_exit_is_not_success(self):
        cap=dict(process_id=201)
        for status,reason in [
            (dict(pid=201,state='unknown',error=5,no_signal_sent=True),'worker_status_state'),
            (dict(pid=201,state='running',exit_code=259,no_signal_sent=True),'worker_status_state'),
            (dict(pid=201,state='exited',exit_code=1,no_signal_sent=True),'worker_status_exit'),
            (dict(pid=201,state='exited',exit_code=False,no_signal_sent=True),'worker_status_exit'),
            (dict(pid=201,state='absent',error=5,query='OpenProcess QUERY_LIMITED_INFORMATION only',no_signal_sent=True),'worker_status_absent'),
            (dict(pid=201,state='absent',error=87,query='unregistered',no_signal_sent=True),'worker_status_absent')]:
            with self.subTest(status=status),self.assertRaisesRegex(ValueError,reason):c.check_worker_status(status,cap)


if __name__=='__main__':unittest.main()
