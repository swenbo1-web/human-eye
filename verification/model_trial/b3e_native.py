"""Independent native mathematics on a COMMON externally validated B3 capture.

This verifies input coherence for the finite pilot. It is not a second source
admission/approval service and cannot create trust from a self-consistent packet.
No production geometry selector, metric, or source validator is imported.
"""
from __future__ import annotations
import copy,hashlib,json,math,time
from verification.deformation_anchor_oracle import (STABLE_KEYS,PIN_KEYS,digest,verify_catalog,expected_box)
from verification.deformation_region_oracle import matching_indices,all_facts

METRICS=('max_principal_stretch','min_principal_stretch','min_area_ratio','max_area_ratio')
POLICY_FIELDS={'schema','source_ref','catalog_sha256','anchor_id','required_core_half_extents_m','primary_half_extents_m','candidate_half_extents_m','max_surplus_members','min_saved_bytes','planning_budget_ms'}

class NativeEvidenceError(ValueError):pass

def need(value,reason):
 if not value:raise NativeEvidenceError('b3e_native_'+reason)
def finite(value,bound=1e12):return type(value) in (int,float) and math.isfinite(value) and abs(value)<=bound
def hex64(value):return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)
def text(value):return type(value) is str and 0<len(value)<=1024 and not any(0xD800<=ord(c)<=0xDFFF for c in value)
def vec(value,size=3,bound=1e12):return type(value) is list and len(value)==size and all(finite(v,bound) for v in value)
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')
def matrix(value):return type(value) is list and len(value)==4 and all(vec(row,4) for row in value) and value[3]==[0,0,0,1]

def validate_shared_capture(packet):
 need(type(packet) is dict and set(packet)=={'schema','identity','inputs','evaluated','audit','capture_id','source_sha256'} and packet['schema']=='small-skin-source-snapshot-v1','packet_schema')
 need(hex64(packet['source_sha256']) and text(packet['capture_id']),'packet_identity')
 identity=packet['identity'];need(type(identity) is dict and set(identity)==set(PIN_KEYS)|{'document_epoch','process_id'},'identity_fields')
 need(all(hex64(identity[k]) for k in PIN_KEYS) and text(identity['document_epoch']) and type(identity['process_id']) is int and identity['process_id']>0,'identity_values')
 raw=packet['inputs'];evaluated=packet['evaluated']
 need(type(raw) is dict and set(raw)=={'frame','unit_scale_m','context','scene','closure','rig','mesh','actions'},'input_fields')
 frame=raw['frame'];need(type(frame) is dict and set(frame)=={'number','subframe'} and type(frame['number']) is int and finite(frame['subframe'],1) and 0<=frame['subframe']<1,'frame')
 need(finite(raw['unit_scale_m'],1e6) and raw['unit_scale_m']>0,'unit')
 need(type(raw['context']) is dict and type(raw['scene']) is dict and type(raw['closure']) is list and 1<=len(raw['closure'])<=16 and type(raw['actions']) is list and len(raw['actions'])<=16,'capture_shape')
 rig=raw['rig'];mesh=raw['mesh'];need(type(rig) is dict and type(mesh) is dict and text(rig.get('name')) and text(mesh.get('name')),'roles')
 need(type(rig.get('bones')) is list and 1<=len(rig['bones'])<=16 and all(type(b) is dict and text(b.get('name')) for b in rig['bones']),'bones')
 need(len({b['name'] for b in rig['bones']})==len(rig['bones']),'bones')
 need(type(evaluated) is dict and set(evaluated)=={'rig_matrix_world','mesh_matrix_world','bones','vertices','triangles','original_links_verified'},'evaluated_fields')
 need(evaluated['original_links_verified'] is True and matrix(evaluated['mesh_matrix_world']) and matrix(evaluated['rig_matrix_world']),'evaluated_shape')
 original=mesh.get('vertices');current=evaluated['vertices'];triangles=mesh.get('triangles')
 need(type(original) is list and 1<=len(original)<=256 and type(current) is list and len(current)==len(original) and all(vec(p,3,10) for p in original+current),'vertices')
 need(type(triangles) is list and 1<=len(triangles)<=256 and all(type(tri) is list and len(tri)==3 and all(type(i) is int and 0<=i<len(original) for i in tri) and len(set(tri))==3 for tri in triangles),'triangles')
 need(type(evaluated['triangles']) is list and evaluated['triangles']==triangles,'evaluated_topology')
 weights=mesh.get('weights');groups=mesh.get('groups')
 need(type(groups) is list and len(groups)<=32 and all(text(g) for g in groups) and len(set(groups))==len(groups),'groups')
 need(type(weights) is list and len(weights)==len(original),'weights')
 for row in weights:
  need(type(row) is list and len(row)<=8 and all(type(v) is list and len(v)==2 and type(v[0]) is int and 0<=v[0]<len(groups) and finite(v[1],1) and v[1]>=0 for v in row),'weights')
  need(len({v[0] for v in row})==len(row),'weights')
 need(type(evaluated['bones']) is list and len(evaluated['bones'])==len(rig['bones']),'evaluated_bones')
 for row in evaluated['bones']:
  need(type(row) is dict and text(row.get('name')) and matrix(row.get('pose_matrix')) and vec(row.get('pose_head')) and vec(row.get('pose_tail')),'evaluated_bones')
 audit=packet['audit'];need(type(audit) is dict and set(audit)=={'before_sha256','after_sha256','independent_before_sha256','independent_after_sha256'} and all(hex64(v) for v in audit.values()),'capture_audit')
 need(audit['before_sha256']==audit['after_sha256']==digest(raw) and audit['independent_before_sha256']==audit['independent_after_sha256'],'capture_audit')
 need(packet['source_sha256']==digest({k:v for k,v in packet.items() if k not in ('source_sha256','capture_id')}),'source_digest')


def validate_policy(policy,catalog):
 need(type(policy) is dict and set(policy)==POLICY_FIELDS and policy['schema']=='surface-deformation-context-policy-v1','policy_fields')
 need(policy['source_ref']==catalog['source_ref'] and policy['catalog_sha256']==catalog['catalog_sha256'],'policy_source')
 need(text(policy['anchor_id']),'policy_anchor')
 halves=[policy['required_core_half_extents_m'],policy['primary_half_extents_m']];candidates=policy['candidate_half_extents_m']
 need(type(candidates) is list and len(candidates)<=2,'policy_candidates');halves+=candidates
 need(all(vec(h,3,1e6) and all(x>=1e-6 for x in h) for h in halves),'policy_halves')
 core,primary=halves[:2];need(all(c<=p for c,p in zip(core,primary)),'policy_halves')
 need(len({tuple(h) for h in [primary,*candidates]})==len(candidates)+1 and all(all(c<=h<=p for c,h,p in zip(core,half,primary)) for half in candidates),'policy_candidates')
 for key,lo,hi in [('max_surplus_members',0,256),('min_saved_bytes',256,65536),('planning_budget_ms',1,250)]:need(type(policy[key]) is int and lo<=policy[key]<=hi,'policy_'+key)


def prepare_native(packet,catalog,policy):
 """Return (compact public facts, private complete truth with helper cost).

 The caller must separately bind a trustworthy shared acquisition receipt and
 the policy FILE digest. policy_content_sha256 here hashes canonical content,
 never claims to be the operator's exact raw-file SHA. Captures may be historical
 and confer no live window or editing authority.
 """
 started=time.perf_counter_ns()
 try:validate_shared_capture(packet)
 except NativeEvidenceError:raise
 except (ValueError,TypeError,KeyError,IndexError,OverflowError,RecursionError) as exc:raise NativeEvidenceError('b3e_native_packet_shape') from exc
 need(type(catalog) is dict and STABLE_KEYS<=set(catalog) and hex64(catalog.get('catalog_sha256')),'catalog_fields')
 need(catalog.get('execution_authority') is False and type(catalog.get('geometry_setters')) is int and catalog['geometry_setters']==0 and catalog.get('original_file_saved') is False,'readonly_capture_provenance')
 # Stable catalogs are intentionally reusable only after recomputing every
 # public geometry/pin field against the supplied CURRENT common snapshot.
 need(type(catalog.get('live_capture')) is dict and set(catalog['live_capture'])=={'source_sha256','document_epoch','process_id'} and hex64(catalog.get('source_sha256')),'catalog_capture')
 live=catalog['live_capture'];need(live['source_sha256']==catalog['source_sha256'] and text(live['document_epoch']) and type(live['process_id']) is int and live['process_id']>0,'catalog_capture')
 checked=copy.deepcopy(catalog);checked['source_sha256']=packet['source_sha256'];checked['live_capture']=dict(source_sha256=packet['source_sha256'],document_epoch=packet['identity']['document_epoch'],process_id=packet['identity']['process_id'])
 try:verify_catalog(checked,packet)
 except (AssertionError,ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:raise NativeEvidenceError('b3e_native_catalog_binding') from exc
 validate_policy(policy,checked)
 anchor=next((a for a in checked['anchors'] if a['anchor_id']==policy['anchor_id']),None)
 need(anchor is not None and anchor.get('state')=='available','anchor_unavailable')
 region=expected_box(anchor,policy['required_core_half_extents_m'])
 need(all(vec(v,3,1e9) for v in region['bounds']) and all(a<b for a,b in zip(*region['bounds'])),'core_region')
 members=matching_indices(packet,region['bounds']);rows=all_facts(packet,members)
 counts={state:sum(v['state']==state for v in rows.values()) for state in ('measured','collapsed','unknown')}
 reasons=sorted({r['reason'] for r in rows.values() if r['state']=='unknown'})
 unknown={why:sum(r['state']=='unknown' and r['reason']==why for r in rows.values()) for why in reasons}
 measured=[r for r in rows.values() if r['state']!='unknown']
 extrema=dict(zip(METRICS,[max(r['principal_stretches'][0] for r in measured),min(r['principal_stretches'][1] for r in measured),min(r['area_ratio'] for r in measured),max(r['area_ratio'] for r in measured)])) if measured else {k:None for k in METRICS}
 facts=dict(core_status='empty' if not members else 'partial' if counts['unknown'] else 'observed',core_triangle_count=len(members),core_states=counts,core_unknown_reasons=unknown,core_extrema=extrema)
 source_ref=copy.deepcopy(checked['source_ref']);policy_digest=digest(policy)
 report=dict(schema='b3e-native-core-evidence-v1',source_ref=source_ref,source_observation_sha256=packet['source_sha256'],catalog_sha256=catalog['catalog_sha256'],
  policy_content_sha256=policy_digest,policy_digest_model='canonical_utf8_json_not_operator_file_bytes',core_region=region,facts=copy.deepcopy(facts),
  scope=dict(capture='shared_externally_validated_B3_capture_not_independent_production_admission',geometry='independent_exact_SAT_and_NumPy_QR_SVD',
   metric_scope='whole_original_triangles_not_clipped_integrals',extrema_scope='measured_and_collapsed_core_members_only',contact_extent='not_checked',damage='not_inferred',volume='not_checked',visibility='not_checked',timeline='not_checked'),
  execution_authority=False,geometry_setters=0,original_file_saved=False)
 payload=encode(report)
 truth=dict(facts=copy.deepcopy(facts),core_triangle_indices=members[:],core_facts=copy.deepcopy(rows),core_region=copy.deepcopy(region),source_ref=copy.deepcopy(source_ref),
  source_observation_sha256=packet['source_sha256'],catalog_sha256=catalog['catalog_sha256'],policy_content_sha256=policy_digest,
  provenance=dict(snapshot_schema=packet['schema'],snapshot_canonical_sha256=digest(packet),catalog_original_capture=copy.deepcopy(catalog['live_capture']),stable_catalog_recomputed_against_current_snapshot=True,
   external_acquisition_receipt_required=True,raw_operator_policy_file_sha256_required_from_caller=True,live_observation_window_not_granted=True),
  measurement=dict(public_report_canonical_utf8_bytes=len(payload),public_report_canonical_utf8_sha256=hashlib.sha256(payload).hexdigest(),
   basis='entire helper validation geometry aggregation copies and canonical public serialization; excludes caller artifact writes/model/common acquisition',common_capture_elapsed_ns=None))
 truth['measurement']['full_prepare_elapsed_ns']=time.perf_counter_ns()-started
 return report,truth
