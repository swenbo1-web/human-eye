"""Two directed local calls on byte-identical isolated helper/actor copies.

No listener, renderer, Blender, model or provider is started. The fault is a
registered deadline exception at the final check, after actual base64 encoding.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent/'deadline_counterexample'/'second_attempt'
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_image_consumption_001')
HERE.mkdir(parents=True,exist_ok=True)
snapshot=HERE/'source';snapshot.mkdir(exist_ok=True)
source={}
for name in ('image_content.py','actor.py'):
    raw=(AUTHOR/name).read_bytes(); target=snapshot/name
    with target.open('xb') as f:f.write(raw)
    source[name]=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),byte_identical=target.read_bytes()==raw)
spec=importlib.util.spec_from_file_location('_root_image001_counterexample',snapshot/'actor.py')
actor=importlib.util.module_from_spec(spec);spec.loader.exec_module(actor)
original_deadline=actor.IMAGE.deadline
cases={}
for case in ('normal','post_encode_deadline'):
    out=HERE/case
    actor.IMAGE.deadline=original_deadline
    owner=actor.Owner(dict(group='N',output=str(out),images_manifest=str(AUTHOR/'inputs/IMAGES.json'),
                           worker_deadline_ns=time.perf_counter_ns()+60_000_000_000,max_tool_calls=4))
    checks=[0]
    if case=='post_encode_deadline':
        def fail_at_final(deadline_ns):
            checks[0]+=1
            if checks[0]==3:raise TimeoutError('injected_original_route_deadline_after_encode')
            return original_deadline(deadline_ns)
        actor.IMAGE.deadline=fail_at_final
    owner.calls=1
    error=None;image_blocks_returned=0
    try:
        response=owner.image_result(['view-a'])
        image_blocks_returned=sum(c['type']=='image' for c in response['content'])
    except actor.IMAGE.ImageContentError as e:
        error=dict(type=type(e).__name__,message=str(e))
    metrics=owner.save_metrics()
    receipts=owner.constructions+owner.construction_failures
    encoded_receipts=[r for r in receipts if r.get('base64_chars',0)>0 and r.get('image_block_JSON_bytes',0)>0 and 'encode' in r['stages']]
    cases[case]=dict(error=error,deadline_calls_after_init=checks[0],encoded_receipts=len(encoded_receipts),
        encoded_PNG_bytes=sum(r['PNG_bytes_read'] for r in encoded_receipts),
        receipt_constructed_flags=[r['constructed'] for r in receipts],
        metrics_constructed_blocks=metrics['constructed_image_blocks'],metrics_constructed_PNG_bytes=metrics['constructed_PNG_bytes'],
        metrics_failed_constructions=metrics['failed_image_constructions'],image_blocks_returned=image_blocks_returned,
        server_sent_blocks=metrics['server_socket_sent_image_blocks'])
assert cases['normal']['encoded_receipts']==cases['normal']['metrics_constructed_blocks']==1
fault=cases['post_encode_deadline']
assert fault['encoded_receipts']==1 and fault['encoded_PNG_bytes']==1909
assert fault['metrics_constructed_blocks']==fault['metrics_constructed_PNG_bytes']==0 and fault['receipt_constructed_flags']==[False]
assert fault['image_blocks_returned']==fault['server_sent_blocks']==0 and fault['deadline_calls_after_init']==3
result=dict(finding='confirmed_post_encode_deadline_undercount',author_commit='a54ad3a9bf738e8f9b5a75c71c29b0a6b105a6ff',sources=source,cases=cases,
    reproduction_scope='Two local helper+actor image_result calls on byte-identical copies; third deadline check injection only. No clocks, product code, original evidence or admission rules edited.',
    actual_cost=dict(image_blocks_encoded=2,PNG_payload_encoded_bytes=3818,network_images_sent=0,new_PNG_renders=0,new_model_Blender_provider_calls=0),
    limitation='Deterministic boundary injection demonstrates the counting defect; real N/P001 never hit this branch and retain their passing image qualification.')
(HERE/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(result,ensure_ascii=False))
