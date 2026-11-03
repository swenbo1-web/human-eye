"""Independent math/checks for one frozen moderate peripheral-extremum case.

This consumes a separately trusted recorded capture. It is not production
source admission, and imports no production selector or metric implementation.
"""
import copy,hashlib,json,math
from fractions import Fraction as F
from pathlib import Path
from verification import deformation_region_oracle as oracle
from verification.deformation_anchor_oracle import anchor_id,stable_object,PIN_KEYS

REGISTRATION_SHA256='7b1ba80835ca2d9c0c53e3e42058fcf5ecf77a1485c6764a623db08cacc4230c'
METRICS=('max_principal_stretch','min_principal_stretch','min_area_ratio','max_area_ratio')
STATES=('measured','collapsed','unknown')
SOURCE_VALIDATION_FIELDS={'schema','method','max_replay_error','replay_atol','animation_curves_checked','not_coordinate_measurement_error'}


def need(value,reason):
    if not value:raise ValueError('measurable_outer_'+reason)


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()
def load_registration(path):
    raw=Path(path).read_bytes();need(hashlib.sha256(raw).hexdigest()==REGISTRATION_SHA256,'registration_bytes')
    return json.loads(raw)
def _registration(value):
    frozen=load_registration(Path(__file__).parent/'fixtures/measurable_outer_extremum_v1.json')
    need(encoded(value)==encoded(frozen),'registration_changed');return value
def near(a,b):return type(a) in (int,float) and type(b) in (int,float) and math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-9)
def hex_text(value,length):return type(value) is str and len(value)==length and all(v in '0123456789abcdef' for v in value)
def count(value,expected):return type(value) is int and value==expected


def _packet(reg):
    return dict(inputs=dict(frame=copy.deepcopy(reg['frame']),unit_scale_m=reg['unit_scale_m'],
        mesh=dict(vertices=copy.deepcopy(reg['vertices']),triangles=copy.deepcopy(reg['triangles']),
            weights=[[] if b is None else [[b,1.]] for b in reg['weight_bones']],groups=reg['groups'][:])),
        evaluated=dict(vertices=copy.deepcopy(reg['expected_evaluated_vertices']),mesh_matrix_world=copy.deepcopy(reg['mesh_matrix_world'])))


def _summary(rows,ids):
    chosen=[rows[i] for i in ids];counts={s:sum(r['state']==s for r in chosen) for s in STATES}
    reasons={reason:sum(r['reason']==reason for r in chosen if r['state']=='unknown') for reason in sorted({r['reason'] for r in chosen if r['state']=='unknown'})}
    good=[r for r in chosen if r['state']!='unknown'];extrema=dict.fromkeys(METRICS)
    if good:extrema=dict(zip(METRICS,[max(r['principal_stretches'][0] for r in good),min(r['principal_stretches'][1] for r in good),min(r['area_ratio'] for r in good),max(r['area_ratio'] for r in good)]))
    return dict(core_status='empty' if not ids else 'partial' if counts['unknown'] else 'observed',core_triangle_count=len(ids),core_states=counts,core_unknown_reasons=reasons,core_extrema=extrema)


def check_facts(actual,expected):
    need(type(actual) is dict and set(actual)==set(expected),'facts_fields')
    for k in ('core_status','core_triangle_count','core_states','core_unknown_reasons'):
        need(actual[k]==expected[k],'facts_'+k)
    need(type(actual['core_triangle_count']) is int,'facts_count_type')
    need(type(actual['core_states']) is dict and set(actual['core_states'])==set(STATES) and all(type(x) is int for x in actual['core_states'].values()),'facts_state_type')
    need(type(actual['core_unknown_reasons']) is dict and all(type(x) is int for x in actual['core_unknown_reasons'].values()),'facts_reason_type')
    need(type(actual['core_extrema']) is dict and set(actual['core_extrema'])==set(METRICS),'facts_extrema_fields')
    for k in METRICS:need(actual['core_extrema'][k] is None and expected['core_extrema'][k] is None or near(actual['core_extrema'][k],expected['core_extrema'][k]),'facts_'+k)


def reliability(original,current):
    """Re-express the published finite error model, not a physical certificate."""
    import numpy as np
    a=np.array(original,dtype=float);b=np.array(current,dtype=float)
    longest=max(float(np.linalg.norm(a[(i+1)%3]-a[i])) for i in range(3))
    area0=float(np.linalg.norm(np.cross(a[1]-a[0],a[2]-a[0])))
    area1=float(np.linalg.norm(np.cross(b[1]-b[0],b[2]-b[0])))
    q0=8*(2**-24*float(np.max(np.abs(a)))+2**-149);q1=8*(2**-24*float(np.max(np.abs(b)))+2**-149)
    height=area0/longest;smin=float(np.linalg.svd((a-a.mean(axis=0)).T,compute_uv=False)[1])
    _,chart=np.linalg.qr((a[1:]-a[0]).T,mode='reduced');gradient=np.linalg.solve(chart.T,b[1:]-b[0]).T
    high,low=map(float,np.linalg.svd(gradient,compute_uv=False))
    error=max(8*(3*q1+max(1.,high)*3*q0)/(smin-3*q0),32*(q1+max(1.,high)*q0)/height)
    area_error=(high+low)*error+error*error
    return dict(q_reference=q0,q_current=q1,reference_longest=longest,reference_height=height,centered_reference_smin=smin,
        reference_length_to_resolution=longest/(16*q0),reference_height_to_resolution=height/(16*q0),
        reference_area_to_ill_conditioning=area0/(2**-20*longest*longest),metric_error=error,metric_error_limit=.01,
        area_error=area_error,area_error_limit=.02,metric_error_headroom_factor=.01/error,area_error_headroom_factor=.02/area_error,
        current_min_stretch_to_error=low/(4*error),reference_double_area=area0,current_double_area=area1,
        interpretation='published numeric resolution model, not physical precision certification')


def preflight(registration):
    reg=_registration(registration);p=_packet(reg);core=oracle.matching_indices(p,reg['core_region']['bounds'])
    all_ids=list(range(len(reg['triangles'])));peripheral=[i for i in all_ids if i not in set(core)];rows=oracle.all_facts(p,all_ids)
    need(core==reg['expected_members']['core'] and peripheral==reg['expected_members']['peripheral'],'preflight_members')
    facts=_summary(rows,core);check_facts(facts,reg['expected_core_facts'])
    # Exact dyadic analytic map: x-edge 1/4 ->3/8, y-edge stays1/4.
    tri=reg['triangles'][3];a=[reg['vertices'][i] for i in tri];b=[reg['expected_evaluated_vertices'][i] for i in tri]
    sx=(F(b[1][0])-F(b[0][0]))/(F(a[1][0])-F(a[0][0]));sy=(F(b[2][1])-F(b[0][1]))/(F(a[2][1])-F(a[0][1]))
    need((sx,sy,sx*sy)==(F(3,2),F(1),F(3,2)),'analytic_map')
    outer=rows[3];realized=outer['state']=='measured' and near(outer['principal_stretches'][0],float(sx)) and near(outer['principal_stretches'][1],float(sy)) and near(outer['area_ratio'],float(sx*sy))
    realized=realized and outer['principal_stretches'][0]>facts['core_extrema']['max_principal_stretch'] and outer['area_ratio']>facts['core_extrema']['max_area_ratio']
    return dict(schema='measurable-outer-independent-preflight-v1',status='realized' if realized else 'not_realized',passed=bool(realized),
        registration_raw_sha256=REGISTRATION_SHA256,analytic_affine_diagonal=['3/2','1'],analytic_area_ratio='3/2',
        core_members=core,peripheral_members=peripheral,core_facts=facts,global_extrema=_summary(rows,all_ids)['core_extrema'],
        rows=rows,reliability={str(i):reliability([reg['vertices'][v] for v in reg['triangles'][i]],[reg['expected_evaluated_vertices'][v] for v in reg['triangles'][i]]) for i in (0,1,3)},
        oracle='exact Fraction SAT plus independent NumPy QR/SVD, crosschecked by dyadic analytic map',production_called=False)


def _points(value,expected,reason):
    need(type(value) is list and len(value)==len(expected),reason)
    for got,want in zip(value,expected):
        need(type(got) is list and len(got)==len(want) and all(type(x) in (int,float) and math.isfinite(x) for x in got) and got==want,reason)


def _row(actual,expected):
    need(type(actual) is dict and type(actual.get('triangle')) is int,'row_shape')
    need(type(actual.get('vertices')) is list and len(actual['vertices'])==3 and all(type(i) is int for i in actual['vertices'])
        and type(actual.get('unweighted_vertices')) is list and all(type(i) is int for i in actual['unweighted_vertices']),'row_index_types')
    for name in ('triangle','vertices','state','reason','unweighted_vertices','reference_geometry','current_geometry'):
        need(actual.get(name)==expected[name],'row_'+name)
    if expected['state']=='unknown':need(actual.get('principal_stretches') is None and actual.get('area_ratio') is None,'unknown_nulls')
    else:
        factors=actual.get('principal_stretches')
        need(type(factors) is list and len(factors)==2 and all(near(a,b) for a,b in zip(factors,expected['principal_stretches'])),'row_stretches')
        need(near(actual.get('area_ratio'),expected['area_ratio']),'row_area')


def verify_snapshot(packet,registration):
    """Independent geometry on THIS capture, never a catalog's earlier capture.

    The caller must separately establish its actual fixed-entry acquisition and
    external file/profile/binary/policy pins. Self-consistent JSON is not trust.
    """
    reg=_registration(registration)
    need(type(packet) is dict and set(packet)=={'schema','identity','inputs','evaluated','audit','capture_id','source_sha256'} and packet['schema']=='small-skin-source-snapshot-v1','packet_shape')
    need(packet['source_sha256']==digest({k:v for k,v in packet.items() if k not in ('source_sha256','capture_id')}),'packet_digest')
    identity=packet['identity'];need(set(identity)==set(PIN_KEYS)|{'document_epoch','process_id'},'packet_identity')
    need(type(identity['process_id']) is int and identity['process_id']>0 and hex_text(identity['document_epoch'],32) and all(hex_text(identity[k],64) for k in PIN_KEYS),'packet_live_identity')
    need(identity['runtime_source_sha256']=='d9b01eec9ce561b9f9fe5304cc37c50aa641b1826ed3ee788501eb2f49192360','runtime_identity')
    raw=packet['inputs'];current=packet['evaluated'];mesh=raw['mesh'];rig=raw['rig']
    need(raw['frame']==reg['frame'] and type(raw['frame']['number']) is int and type(raw['frame']['subframe']) in (int,float)
        and type(raw['unit_scale_m']) in (int,float) and raw['unit_scale_m']==reg['unit_scale_m'],'frame_units')
    need(mesh['name']==reg['mesh_name'] and rig['name']==reg['rig_name'],'roles')
    _points(mesh['vertices'],reg['vertices'],'original_vertices');_points(current['vertices'],reg['expected_evaluated_vertices'],'evaluated_vertices')
    need(mesh['triangles']==reg['triangles']==current['triangles'],'topology')
    need(all(type(i) is int for tri in mesh['triangles']+current['triangles'] for i in tri),'topology_types')
    need(mesh['groups']==reg['groups'] and mesh['weights']==[[] if b is None else [[b,1.]] for b in reg['weight_bones']],'weights_groups')
    need(all(type(i) is int and type(w) in (int,float) for row in mesh['weights'] for i,w in row),'weight_types')
    _points(current['mesh_matrix_world'],reg['mesh_matrix_world'],'mesh_world');_points(current['rig_matrix_world'],reg['rig_matrix_world'],'rig_world')
    need(current['original_links_verified'] is True and raw['actions']==[],'fixed_source_shape')
    need(type(rig['bones']) is list and len(rig['bones'])==2 and {b['name'] for b in rig['bones']}==set(reg['groups']),'bone_names')
    need(type(current['bones']) is list and len(current['bones'])==2 and {b['name'] for b in current['bones']}==set(reg['groups']),'evaluated_bone_names')
    for expected in reg['bones']:
        b=next(x for x in rig['bones'] if x['name']==expected['name']);e=next(x for x in current['bones'] if x['name']==expected['name'])
        need(b['parent'] is None and b['rest_head']==expected['head'] and b['rest_tail']==expected['tail'] and b['location']==expected['pose_location'],'bone_source')
        transform=copy.deepcopy(reg['rig_matrix_world'])
        for axis in range(3):transform[axis][3]=expected['pose_location'][axis]
        _points(b['rest_matrix'],reg['rig_matrix_world'],'bone_rest_matrix');_points(b['basis_matrix'],transform,'bone_basis_matrix')
        _points(b['pose_matrix'],transform,'bone_pose_matrix');_points(e['pose_matrix'],transform,'evaluated_bone_matrix')
        head=expected['pose_location'];tail=[head[i]+expected['tail'][i]-expected['head'][i] for i in range(3)]
        need(b['pose_head']==head and b['pose_tail']==tail and e['pose_head']==head and e['pose_tail']==tail,'bone_endpoints')
    audit=packet['audit'];need(audit['before_sha256']==audit['after_sha256']==digest(raw) and audit['independent_before_sha256']==audit['independent_after_sha256'],'snapshot_readonly_audit')
    ids=list(range(len(reg['triangles'])));core=oracle.matching_indices(packet,reg['core_region']['bounds']);peripheral=[i for i in ids if i not in set(core)]
    need(core==reg['expected_members']['core'] and peripheral==reg['expected_members']['peripheral'],'captured_members')
    rows=oracle.all_facts(packet,ids);facts=_summary(rows,core);check_facts(facts,reg['expected_core_facts'])
    outer=rows[3];realized=outer['state']=='measured' and all(near(a,b) for a,b in zip(outer['principal_stretches'],reg['expected_peripheral']['principal_stretches'])) and near(outer['area_ratio'],1.5)
    realized=realized and outer['principal_stretches'][0]>facts['core_extrema']['max_principal_stretch'] and outer['area_ratio']>facts['core_extrema']['max_area_ratio']
    geometry=dict(original=mesh['vertices'],current=current['vertices'],triangles=mesh['triangles'],weights=mesh['weights'],groups=mesh['groups'],
        rig=rig['bones'],mesh_world=current['mesh_matrix_world'],rig_world=current['rig_matrix_world'],frame=raw['frame'],unit_scale_m=raw['unit_scale_m'])
    return dict(status='realized' if realized else 'not_realized',challenge_realized=bool(realized),source_sha256=packet['source_sha256'],
        identity=copy.deepcopy(identity),source_ref=dict(scene_sha256=identity['scene_sha256'],rig_object_id=stable_object(reg['rig_name']),mesh_object_id=stable_object(reg['mesh_name']),frame=copy.deepcopy(reg['frame'])),
        registered_core_region=copy.deepcopy(reg['core_region']),registered_half_extents=reg['policy']['core_half'][:],
        registered_anchor_id=anchor_id(reg['rig_name'],reg['core_anchor']['bone_name'],reg['core_anchor']['endpoint']),
        core_members=core,peripheral_members=peripheral,core_facts=facts,global_extrema=_summary(rows,ids)['core_extrema'],rows=rows,
        geometry_sha256=digest(geometry),trusted_actual_acquisition_required=True,oracle='exact Fraction SAT and independent NumPy QR/SVD')


def _report_common(report,truth):
    need(report.get('source_sha256')==truth['source_sha256'],'report_source_binding')
    need(report.get('execution_authority') is False and type(report.get('geometry_setters')) is int and report['geometry_setters']==0 and report.get('original_file_saved') is False,'report_readonly')
    v=report.get('source_validation');need(type(v) is dict and set(v)==SOURCE_VALIDATION_FIELDS
        and v.get('schema')=='small-skin-source-snapshot-v1' and v.get('method')=='external_binding_full_dependency_FK_and_LBS'
        and v.get('not_coordinate_measurement_error') is True and type(v.get('max_replay_error')) in (int,float) and math.isfinite(v['max_replay_error'])
        and type(v.get('replay_atol')) in (int,float) and math.isfinite(v['replay_atol']) and v['replay_atol']==2e-5
        and 0<=v['max_replay_error']<=v['replay_atol'] and type(v.get('animation_curves_checked')) is int and v['animation_curves_checked']==0,'report_validation_metadata')


def check_worker_status(status,capabilities):
    """Bind the readonly post-CLI Windows query to THIS capture's worker PID.

    The caller still has to pin the collector/receipt and correlate its command.
    This status does not by itself prove how or when the worker terminated.
    """
    need(type(status) is dict and type(capabilities) is dict,'worker_status_shape')
    pid=capabilities.get('process_id')
    need(type(pid) is int and pid>0 and type(status.get('pid')) is int and status['pid']==pid,'worker_status_pid')
    need(status.get('no_signal_sent') is True,'worker_status_no_signal')
    state=status.get('state')
    if state=='exited':
        need(set(status)=={'pid','state','exit_code','no_signal_sent'} and count(status.get('exit_code'),0),'worker_status_exit')
    elif state=='absent':
        need(set(status)=={'pid','state','error','query','no_signal_sent'} and count(status.get('error'),87)
            and status.get('query')=='OpenProcess QUERY_LIMITED_INFORMATION only','worker_status_absent')
    else:need(False,'worker_status_state')
    return dict(passed=True,pid=pid,state=state,no_signal_sent=True,scope='matching capture worker readonly process query; not renewed live authority')


def check_report(report,audit,truth):
    """Compare frozen independent core truth with the formal core report."""
    _report_common(report,truth);need(report.get('schema')=='surface-deformation-core-facts-v1','core_schema')
    identity=truth['identity'];need(report.get('live_capture')=={k:identity[k] for k in ('document_epoch','process_id')},'report_live_binding')
    need(report.get('source_ref')==truth['source_ref'] and report.get('operator_pins')=={k:identity[k] for k in PIN_KEYS},'report_pins_ref')
    ref=report.get('core_ref');need(type(ref) is dict and ref.get('region')==truth['registered_core_region'] and ref.get('half_extents_m')==truth['registered_half_extents']
        and ref.get('anchor_id')==truth['registered_anchor_id'],'registered_world_core')
    check_facts(report.get('facts'),truth['core_facts'])
    witnesses=report.get('core_witnesses');need(type(witnesses) is dict and set(witnesses)==set(METRICS),'core_witness_fields')
    for key in METRICS:
        witness=witnesses[key];need(type(witness) is int and witness in (0,1),'core_witness')
        row=truth['rows'][witness];value=row['principal_stretches'][0 if key=='max_principal_stretch' else 1] if 'stretch' in key else row['area_ratio']
        need(row['state']=='measured' and near(value,report['facts']['core_extrema'][key]),'core_witness_value')
    complete=report.get('completeness');need(type(complete) is dict and all(complete.get(k) is True for k in ('membership_complete','core_facts_complete','metric_witnesses_complete')),'core_completeness')
    need(count(complete.get('unknown_reasons_omitted'),0) and count(complete.get('member_ids_omitted'),3) and count(complete.get('per_face_rows_omitted'),3)
        and complete.get('all_members_unknown') is False and complete.get('all_members_measurable') is False,'core_omissions')
    scope=report.get('scope');need(type(scope) is dict and scope.get('metric_scope')=='whole_original_triangles_not_clipped_integrals' and scope.get('extrema_scope')=='measured_and_collapsed_core_members_only'
        and scope.get('peripheral_context')=='not_reported' and scope.get('peripheral_shrinking') is False and all(scope.get(k)=='not_inferred' for k in ('damage','anatomy'))
        and all(scope.get(k)=='not_checked' for k in ('volume','visibility','timeline','contact_extent')),'core_scope')
    need(audit.get('schema')=='surface-deformation-core-facts-audit-v1' and audit.get('source_sha256')==truth['source_sha256'] and audit.get('core_ref')==ref,'audit_binding')
    need(audit.get('core_triangle_indices')==truth['core_members'],'audit_members')
    rows=audit.get('core_rows');need(type(rows) is list and len(rows)==3 and [r.get('triangle') for r in rows]==truth['core_members'],'audit_rows')
    for row in rows:_row(row,truth['rows'][row['triangle']])
    need(audit.get('core_rows_sha256')==digest(rows),'audit_rows_digest')
    membership=audit.get('core_membership');need(type(membership) is dict and membership.get('source_sha256')==truth['source_sha256'] and membership.get('region')==truth['registered_core_region']
        and membership.get('membership_complete') is True and count(membership.get('triangles_scanned'),4) and count(membership.get('vertices_transformed'),12)
        and membership.get('matched_triangle_indices')==truth['core_members'],'audit_complete_membership')
    raw=json.dumps(report,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'
    need(count(audit.get('published_publication_bytes'),len(raw)) and audit.get('published_publication_sha256')==hashlib.sha256(raw).hexdigest(),'audit_publication')
    need(count(audit.get('actor_B2_rows_passes'),1) and count(audit.get('geometry_cache_preparations'),1) and count(audit.get('region_scans'),1)
        and all(count(audit.get(k),0) for k in ('pure_projection_B2_rows_passes','pure_projection_geometry_cache_preparations','pure_projection_region_scans','candidates_evaluated')),'audit_work_counts')
    return dict(passed=True,challenge_realized=truth['challenge_realized'],source_sha256=truth['source_sha256'],core_members=truth['core_members'],
        core_extrema=truth['core_facts']['core_extrema'],peripheral_extrema={k:truth['global_extrema'][k] for k in ('max_principal_stretch','max_area_ratio')},
        claim='one fixed same-capture core conformance check; no live execution authority or model-value claim')


def check_peripheral_report(report,truth):
    """Legacy triangle[3] result; its source belongs to ITS separate capture."""
    _report_common(report,truth);need(report.get('schema')=='surface-deformation-diagnostic-v1','peripheral_schema')
    source=report.get('source');need(type(source) is dict and all(source.get(k)==truth['identity'][k] for k in PIN_KEYS+('document_epoch','process_id')),'peripheral_source_binding')
    q=report.get('task_query');need(type(q) is dict and q.get('schema')=='surface-deformation-query-result-v1' and q.get('source_sha256')==truth['source_sha256']
        and q.get('triangle_indices')==[3] and q.get('status')=='observed','peripheral_task_binding')
    rows=q.get('triangles');need(type(rows) is list and len(rows)==1,'peripheral_rows');_row(rows[0],truth['rows'][3])
    need(rows[0]['state']=='measured' and near(rows[0]['principal_stretches'][0],1.5) and near(rows[0]['area_ratio'],1.5),'peripheral_measurable')
    # Whole-mesh status remains partial because core face2 is unweighted.
    need(report.get('status')=='partial' and report.get('triangles_total')==4 and report.get('triangles_measured')==3
        and report.get('triangles_collapsed')==0 and report.get('triangles_unknown')==1 and report.get('unknown_reasons')=={'unweighted_vertex_source':1},'peripheral_global_summary')
    return dict(passed=True,source_sha256=truth['source_sha256'],triangle=3,state='measured',principal_stretches=rows[0]['principal_stretches'],area_ratio=rows[0]['area_ratio'],
        same_capture_as_core_claimed=False,core_truth_must_come_from_own_core_capture=True)
