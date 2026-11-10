"""Independent comparison of root-produced records, not the author comparator."""
from pathlib import Path
import collections, hashlib, json, math
HERE=Path(__file__).parent
MODULE='verification/m1_nearest_evidence_001/tests/test_nearest_evidence.py'
PINS={'baseline':'0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a',
      'candidate':'7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1'}
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(v,pin):
    if isinstance(v,dict):
        result={}
        for key,value in v.items():
            if key=='runtime_source_sha256':
                assert value==pin
                result[key]='<exact-verified-version-pin>'
            else: result[key]=norm(value,pin)
        return result
    if isinstance(v,list):return [norm(item,pin) for item in v]
    return v
def core(v,pin):
    return norm({k:x for k,x in v.items() if k not in ('best_known_evidence','measurement_semantics','trace_id')},pin)
data={};identities={}
for role,pin in PINS.items():
    folder=HERE/('root_'+role+'_01')
    result=read(folder/'RESULTS.json')
    assert result['successful'] and result['tests']==49 and result['runtime_source_sha256']==pin
    assert not result['failures'] and not result['errors'] and not result['skipped']
    identity=read(folder/'EXECUTION_IDENTITY.json')
    assert identity['guard_verify_loaded'] and identity['source_count']==137
    assert identity['checkout_files_unchanged'] and identity['loaded_tests_unchanged'] and identity['original_read_evidence_unchanged']
    identities[role]=identity
    data[role]=read(folder/'EVIDENCE.json')[MODULE]
for key in ('loaded_tests','fixture_sha256','original_read_evidence_sha256','runner_sha256'):
    assert identities['baseline'][key]==identities['candidate'][key],key
assert set(data['baseline'])==set(data['candidate']) and len(data['candidate'])==18
cases=[]; counts=collections.Counter(); totals={'baseline':0,'candidate':0}; text_cases=0
for key,after in sorted(data['candidate'].items()):
    before=data['baseline'][key]
    assert core(before['body'],PINS['baseline'])==core(after['body'],PINS['candidate']),key
    assert norm(before['capture_binding'],PINS['baseline'])==norm(after['capture_binding'],PINS['candidate']),key
    for field in ('counts','measurements','diagnostics','packet_work','selector'):
        assert before[field]==after[field],(key,field)
    body=after['body']; evidence=body['best_known_evidence']
    assert [row['candidate'] for row in evidence]==body['best_known_objects']
    measurements=after['measurements']
    if key.startswith('order.warm_z_'):
        assert not measurements
        measurements=data['candidate']['order.cold_z_service']['measurements']
    for row in evidence:
        measurement=measurements[row['candidate']['id']]
        for field in ('point_a_world','point_b_world','direction_a_to_b','witness_status','direction_status'):
            assert row[field]==measurement.get(field),(key,field)
        for field in ('witness_reason','direction_reason'):
            assert (field in row)==(field in measurement)
            if field in row:assert row[field]==measurement[field]
        assert body['measurement_semantics']['method']==measurement['method']
        if row['witness_status']=='measured':
            d=math.dist(row['point_a_world'],row['point_b_world'])
            assert math.isclose(d,body['best_known_distance_m'],rel_tol=1e-12,abs_tol=1e-12),(key,d)
    if body['status']!='complete':assert body['nearest_objects'] is None and body['distance_m'] is None
    if before['raw_text'] is not None:
        assert after['raw_text'] is not None
        text_cases+=1
        totals['baseline']+=len(before['raw_text'].encode('utf-8'))
        totals['candidate']+=len(after['raw_text'].encode('utf-8'))
    counts.update(after['counts'])
    cases.append({'case':key,'core_equal':True,'capture_binding_equal':True,'counts_equal':True,
        'measurements_equal':True,'winner_evidence_matches_measurement':True,'status':body['status']})
result={'passed':True,'root_tests_each_version':49,'root_entry_pairs':18,'cases':cases,
    'counts_each_version':dict(counts),'captured_content_text_cases':text_cases,
    'captured_content_text_bytes':totals,'content_text_delta':totals['candidate']-totals['baseline'],
    'inputs':{role:{name:sha(HERE/('root_'+role+'_01')/name) for name in ('RESULTS.json','EVIDENCE.json','EXECUTION_IDENTITY.json')} for role in PINS},
    'scope':'Independent root execution of fixed runner; separate standard-library comparison of actual new root records. Only added root fields/trace and exact-validated runtime pin normalized; scene/epoch/fingerprint/capture values retained. Point-distance check supplements existing fixture surface-membership checks; no model/Blender/installed-entry qualification.'}
(HERE/'ROOT_COMPARISON.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:result[k] for k in ('passed','root_tests_each_version','root_entry_pairs','counts_each_version','captured_content_text_bytes','content_text_delta')}))
