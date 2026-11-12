"""Read-only anonymous packet/contract provenance. Does not read cost or map."""
from pathlib import Path
import hashlib,json,subprocess

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HERE=Path(__file__).resolve().parent
BASE='verification/m4_spatial_fact_consumption_001/'
PUBLIC=BASE+'runtime/handoff_01/public/'
COMMIT='5cdf62f311f94890ca569d06c1a858f1578225e4'
PREP='02c7784ec4e23e9b03a3485367d8db54b4d5db34'
ROOT_PLAN=Path('D:/hefe/docs/M4_SPATIAL_FACT_CONSUMPTION_001_PLAN.md')
ROOT_SHA='aa6b4ffaf6eb6ca93c4fec28a3134fedd25a0c5be54582f9f47fdbd044ed040a'
PLAN_SHA='d40c81babcb1a9d1826752df4dfe23e5d790536bd23cf0798edc0bbc90f9e672'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args])
assert git('rev-parse','HEAD').decode().strip()==COMMIT
assert git('status','--porcelain')==b''
reader=subprocess.Popen(['git','-C',str(ROOT),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
def blob(commit,path):
    assert path.startswith(PUBLIC) or path in allowed, 'Path outside declared source audit'
    reader.stdin.write((commit+':'+path+'\n').encode());reader.stdin.flush()
    header=reader.stdout.readline().split()
    assert len(header)==3 and header[1]==b'blob',(commit,path,header)
    raw=reader.stdout.read(int(header[2]));assert reader.stdout.read(1)==b'\n'
    return raw
allowed={BASE+name for name in ('PUBLIC_PACKET_MANIFEST.json','FORMAL_QUALITY_READY.json',
    'POSTRUN_INTEGRITY.json','ROOT_PLAN.md','PLAN.json','input/PROMPT.txt','input/scene.blend',
    'scoring/SCORING_CONTRACT.json','scoring/ACTUAL_SNAPSHOT.json','scoring/TRUTH.json')}
OLD='verification/m3_sufficient_separation_001/entry/run_01/'
allowed.update({OLD+'ACTUAL_SNAPSHOT.json',OLD+'native/input.blend',OLD+'ACTUAL_ORACLE.json'})
try:
    manifest_raw=(ROOT/(BASE+'PUBLIC_PACKET_MANIFEST.json')).read_bytes()
    assert manifest_raw==blob(COMMIT,BASE+'PUBLIC_PACKET_MANIFEST.json')
    manifest=json.loads(manifest_raw);listed=manifest['files']
    assert [r['path'] for r in listed]==sorted(r['path'] for r in listed)
    assert len({r['path'] for r in listed})==len(listed)
    actual_paths=sorted(p.relative_to(ROOT/PUBLIC).as_posix() for p in (ROOT/PUBLIC).rglob('*') if p.is_file())
    assert actual_paths==[r['path'] for r in listed]
    checked=[]
    for row in listed:
        relative=row['path'];assert '..' not in Path(relative).parts and not Path(relative).is_absolute()
        raw=(ROOT/PUBLIC/relative).read_bytes()
        assert len(raw)==row['bytes'] and sha(raw)==row['sha256'],relative
        assert raw==blob(COMMIT,PUBLIC+relative),relative
        checked.append(dict(path=relative,bytes=len(raw),sha256=sha(raw)))
    digest=sha(json.dumps(listed,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
    assert digest==manifest['packet_sha256']
    safe_receipts={}
    for name in ('FORMAL_QUALITY_READY.json','POSTRUN_INTEGRITY.json'):
        raw=(ROOT/(BASE+name)).read_bytes();assert raw==blob(COMMIT,BASE+name)
        receipt=json.loads(raw)
        assert receipt['public_packet_sha256']==digest and receipt['plan_sha256']==PLAN_SHA
        assert receipt['completed']==6 and receipt['execution_failed']==0 and receipt['not_run']==0
        assert receipt['scoring_performed'] is False and receipt['cost_analysis_performed'] is False
        safe_receipts[name]={'sha256':sha(raw),'completed':receipt['completed'],
            'execution_failed':receipt['execution_failed'],'not_run':receipt['not_run']}
    root_raw=ROOT_PLAN.read_bytes()
    assert sha(root_raw)==ROOT_SHA
    assert root_raw==(ROOT/(BASE+'ROOT_PLAN.md')).read_bytes()==blob(COMMIT,BASE+'ROOT_PLAN.md')==blob(PREP,BASE+'ROOT_PLAN.md')
    # Hash-only local execution PLAN: its group/cost configuration is not decoded.
    local_plan=(ROOT/(BASE+'PLAN.json')).read_bytes()
    assert sha(local_plan)==PLAN_SHA and local_plan==blob(COMMIT,BASE+'PLAN.json')==blob(PREP,BASE+'PLAN.json')
    task=(ROOT/(PUBLIC+'tasks/T1.txt')).read_bytes()
    input_task=(ROOT/(BASE+'input/PROMPT.txt')).read_bytes()
    assert task==input_task==blob(COMMIT,BASE+'input/PROMPT.txt')==blob(PREP,BASE+'input/PROMPT.txt')
    quoted=[line[2:] for line in root_raw.decode('utf-8').splitlines() if line.startswith('> ')]
    assert len(quoted)==1 and task.decode('utf-8').strip()==quoted[0]
    scoring=[]
    for name in ('SCORING_CONTRACT.json','ACTUAL_SNAPSHOT.json','TRUTH.json'):
        public=(ROOT/(PUBLIC+'scoring/'+name)).read_bytes()
        frozen=(ROOT/(BASE+'scoring/'+name)).read_bytes()
        assert public==frozen==blob(COMMIT,BASE+'scoring/'+name)==blob(PREP,BASE+'scoring/'+name)
        scoring.append({'path':'scoring/'+name,'sha256':sha(public),'same_as_preparation':True})
    contract=json.loads((ROOT/(PUBLIC+'scoring/SCORING_CONTRACT.json')).read_bytes())
    assert contract['primary_fixed_denominators']=={'relations':3,'minimum_surface_gaps':3,
        'minimum_4mm_decisions':3,'localized_nearest_point_pairs':3,'three_candidate_nearest_or_true_tie':1,'consumer_slots':6}
    assert contract['distance_policy']['absolute_error_m']==1e-6
    assert contract['witness_policy']['final_coordinate_component_error_m']==1e-6
    snapshot_raw=(ROOT/(PUBLIC+'scoring/ACTUAL_SNAPSHOT.json')).read_bytes()
    snapshot=json.loads(snapshot_raw)
    truth=json.loads((ROOT/(PUBLIC+'scoring/TRUTH.json')).read_bytes())
    old_raw=(ROOT/(OLD+'ACTUAL_SNAPSHOT.json')).read_bytes()
    assert old_raw==blob(COMMIT,OLD+'ACTUAL_SNAPSHOT.json')
    old_snapshot=json.loads(old_raw)
    canonical_snapshot=sha(json.dumps(old_snapshot,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
    assert canonical_snapshot==truth['binding']['snapshot_sha256']
    assert snapshot_raw==old_raw and snapshot==old_snapshot, 'public geometry byte/semantic drift'
    object_counts={'objects':len(snapshot['objects']),
        'vertices':sum(len(r['vertices_world']) for r in snapshot['objects']),
        'triangles':sum(len(r['triangles']) for r in snapshot['objects'])}
    assert object_counts=={'objects':14,'vertices':848,'triangles':1640}
    asset=(ROOT/(BASE+'input/scene.blend')).read_bytes()
    old_asset=(ROOT/(OLD+'native/input.blend')).read_bytes()
    assert asset==old_asset==blob(COMMIT,BASE+'input/scene.blend')==blob(PREP,BASE+'input/scene.blend')==blob(COMMIT,OLD+'native/input.blend')
    asset_sha=sha(asset)
    assert asset_sha=='27f197a8cc312832382ae06cb633cbf846f20a1a22797909a15dfda8513ade46'
    index=json.loads((ROOT/(PUBLIC+'INDEX.json')).read_bytes())
    assert index['fixed_slots']==6 and len(index['answers'])==6 and index['scoring_performed'] is False
    anonymous=[]
    for row in index['answers']:
        directory=row['directory'];assert directory==row['anonymous_id'] and directory.startswith('answer_')
        answer=(ROOT/(PUBLIC+directory+'/'+row['answer_file'])).read_bytes()
        assert sha(answer)==row['answer_original_sha256']==row['source_provenance']['public_final_sha256']
        assert row['answer_state']=='present' and row['execution_record_state']=='completed'
        source=json.loads((ROOT/(PUBLIC+directory+'/'+row['source_consistency_file'])).read_bytes())
        assert source['ACTOR_CONFIG']['asset_sha256']==source['owner_IDENTITY']['asset_sha256']==asset_sha
        assert source['INITIAL_original_file_sha256']==source['FINAL_original_file_sha256']
        assert source['CONSUMER_INPUT']['input_image_count']==0
        assert source['CONSUMER_INPUT']['image_delivery']['initial_attachment_in_argv'] is False
        close=source['CLOSE'];assert close['asset_unchanged'] is True and close['geometry_unchanged'] is True
        worker=close['worker_fingerprint_fields']
        assert worker['initial_geometry_fingerprint']==worker['final_geometry_fingerprint']
        anonymous.append({'anonymous_id':directory,'answer_sha256':sha(answer),'source_projection_consistent':True})
    result={'passed':True,'scope':'Anonymous packet provenance/contract only; no answer grading, cost or map read, product execution or Blender/model calls.',
        'commit':COMMIT,'preparation_commit':PREP,'root_plan_sha256':ROOT_SHA,'execution_plan_sha256':PLAN_SHA,
        'different_plan_digests_expected':True,'packet_sha256':digest,'public_file_count':len(checked),'files':checked,
        'root_plan_exact_copy':True,'prompt_matches_root_plan_and_preparation':True,'frozen_scoring_materials':scoring,
        'geometry':{'public_raw_sha256':sha(snapshot_raw),'previous_raw_sha256':sha(old_raw),
            'oracle_canonical_snapshot_sha256':canonical_snapshot,
            'exact_raw_and_parsed_snapshot_equality':True,'digest_scope_difference':'raw file SHA256 versus canonical JSON digest',**object_counts},
        'asset_sha256':asset_sha,'same_prior_actual_input_asset':True,'anonymous_slots':anonymous,
        'receipt_claims_checked':safe_receipts,
        'limits':['source_consistency closure/unchanged flags remain producer claims; private originals not opened',
            'business answer/tool text not semantically inspected; route inference and mechanism/cost judgment not performed',
            'independent scoring/oracle geometry computations are delegated to root and grading agents'],
        'AL':{'own_context_bound':True,'task_access':'parent_read_only','assignment_current':False,'parent_task_written':False}}
    (HERE/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('passed','public_file_count','packet_sha256','root_plan_exact_copy','prompt_matches_root_plan_and_preparation','same_prior_actual_input_asset')},sort_keys=True))
finally:
    reader.stdin.close();reader.stdout.close();assert reader.wait(timeout=20)==0
