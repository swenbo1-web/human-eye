"""Independent arithmetic/consumption review. Reads saved evidence; no product calls."""
from pathlib import Path
from collections import Counter
import base64, hashlib, json, sys, zipfile, io

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe')
NS=ROOT/'verification/m4_occluded_scene_transfer_001'
RUN=Path('D:/he_occluded_transfer_001')
OUT=Path(__file__).parent
sys.path.insert(0,'D:/he_anchor_001/venv/Lib/site-packages')
import numpy as np

checks=[]; inputs={}
def check(ok,label):
    checks.append({'check':label,'passed':bool(ok)})
    if not ok: raise AssertionError(label)
def raw(path):
    path=Path(path); data=path.read_bytes(); inputs[str(path)]=hashlib.sha256(data).hexdigest(); return data
def read(path): return json.loads(raw(path))
cost=read(NS/'COST.json')
quality=read(NS/'admin/QUALITY.json')
qby={x['slot_id']:x for x in quality['slots']}
by={x['slot_id']:x for x in cost['slots']}
sequence=['N1','P1','P2','N2','N3','P3']
slots=[]; maps=[]; raw_usage={g:Counter() for g in 'NP'}
last=0
for slot in sequence:
    root=RUN/'formal'/slot
    clock=read(RUN/'formal/slot_records'/slot/'SLOT_TIMING.json')
    consumer=read(root/'c/CONSUMER.json')
    events=[json.loads(line) for line in raw(root/'c/stdout.raw.bin').splitlines() if line.strip()]
    usages=[e['usage'] for e in events if e.get('type')=='turn.completed']
    check(len(usages)==1,slot+': one raw usage event')
    usage=usages[0]; raw_usage[slot[0]].update(usage)
    check(usage==consumer['usage']==by[slot]['reported_usage'],slot+': raw/consumer/cost usage agree')
    elapsed=clock['SLOT_RESULT_closed_ns']-clock['started_ns']
    check(elapsed==clock['elapsed_ns']==by[slot]['full_slot_ns'],slot+': outer arithmetic')
    check(clock['started_ns']>=last,slot+': serial order');last=clock['SLOT_RESULT_closed_ns']
    check(clock['started_ns']<=consumer['started_ns']<consumer['prompt_submitted_ns']<=consumer['final_received_ns']<=consumer['cleanup_end_ns']<=clock['SLOT_RESULT_closed_ns'],slot+': consumer contained by full slot')
    check(by[slot]['clocks']['route']['closed_ns']<=clock['SLOT_RESULT_closed_ns'],slot+': route contained')
    check(consumer['exit_code']==0 and consumer['valid_completion'],slot+': process completed')
    completed=[e['item'] for e in events if e['type']=='item.completed' and e.get('item',{}).get('type')=='mcp_tool_call']
    image_hashes=[]; cli_text_bytes=0
    for item in completed:
        for block in item['result']['content']:
            if block['type']=='image': image_hashes.append(hashlib.sha256(base64.b64decode(block['data'])).hexdigest())
            elif block['type']=='text':cli_text_bytes+=len(block['text'].encode())
    tools=[]; server_images=[]; handler_ns=0; response_text=0
    for i,request in enumerate(sorted((root/'c/owner_turn').glob('tool_*/REQUEST.json'))):
        req=read(request)['params'];receipt=read(request.with_name('RECEIPT.json'))
        response=read(request.with_name('RESPONSE.json'))['result']
        check(req['name']==receipt['name']==completed[i]['tool'],slot+f': tool {i+1} alignment')
        check(req['arguments']==completed[i]['arguments'],slot+f': tool {i+1} arguments')
        check(receipt['closed_ns']-receipt['started_ns']==receipt['elapsed_ns'],slot+f': tool {i+1} time')
        check(not receipt['is_error'] and not receipt['response_serialization_error'],slot+f': tool {i+1} result')
        handler_ns+=receipt['elapsed_ns']
        for block in response['content']:
            if block['type']=='image':server_images.append(hashlib.sha256(base64.b64decode(block['data'])).hexdigest())
            elif block['type']=='text':response_text+=len(block['text'].encode())
        tools.append({'number':i+1,'name':req['name'],'arguments':req['arguments'],'handler_ns':receipt['elapsed_ns'],'content_metrics':receipt['content_metrics']})
    check(len(tools)==len(completed)==by[slot]['counts']['tools'],slot+': business count')
    check(image_hashes==server_images,slot+': server/CLI image deliveries exact')
    check(len(image_hashes)==by[slot]['counts']['CLI_images'],slot+': image count')
    check(cli_text_bytes==by[slot]['bytes']['CLI_text'],slot+': CLI text byte count')
    trace=[json.loads(x) for x in raw(root/'o/TRACE.jsonl').splitlines() if x.strip()]
    renders=[e for e in trace if e['event']=='render_attempt']
    check(len(renders)==by[slot]['counts']['rasters'],slot+': raster attempts')
    check([x['view_name'] for x in renders]==[x['view_name'] for x in by[slot]['frames']],slot+': frame order')
    slots.append({'slot':slot,'full_ns':elapsed,'handler_ns':handler_ns,'usage':usage,'quality':qby[slot]['final_quality_passed'],'calls':len(tools),'rasters':len(renders),'view_constructions':[x['view_name'] for x in renders],'images':len(image_hashes),'CLI_text_bytes':cli_text_bytes,'server_text_bytes':response_text,'tools':tools})
    if slot.startswith('P'):
        obs=json.loads(read(root/'c/owner_turn/tool_01/RESPONSE.json')['result']['content'][0]['text'])
        regions=[dict(zip(obs['regions']['columns'],r)) for r in obs['regions']['rows']]
        files=list((root/'o/product_state.json.active_observation').rglob('*.npz'))
        with np.load(io.BytesIO(raw(files[0])),allow_pickle=False) as a:
            offsets=a['face_patch_offsets'];face_patch=a['face_patch_ids'];rois=a['patch_roi_ids']
            check(rois.tolist()==[r['roi_id'] for r in regions],slot+': persisted map region order')
            local=[]
            for i,r in enumerate(regions):
                oi=r['object_index'];ids=np.flatnonzero(face_patch[int(offsets[oi]):int(offsets[oi+1])]==i).tolist()
                check(len(ids)==r['triangle_count'],slot+f': region {i} source count')
                local.append(ids)
            check(sum(map(len,local))==122 and int(np.sum(face_patch<0))==4,slot+': total mapping support')
            # Raw TOP frame can use the already-published global face map without any geometry matching.
            pixel_matches=[]
            for view,x,y in [('TOP',135,175),('LEFT',234,483)]:
                if view=='TOP':p=next((root/'o/frames').rglob('TOP.npz'))
                else:p=sorted(files)[1]
                with np.load(io.BytesIO(raw(p)),allow_pickle=False) as frame:
                    triangle=int(frame['triangle_ids'][y,x]);region=int(face_patch[triangle]);oi=regions[region]['object_index']
                    pixel_matches.append({'view':view,'triangle':triangle,'region':region,'object_index':oi,'local_ids':local[region]})
            check(pixel_matches[0]['object_index']==1 and pixel_matches[0]['local_ids']==[2,3],slot+': TOP lookup from saved mapping')
            check(pixel_matches[1]['object_index']==0 and pixel_matches[1]['local_ids']==[10,11],slot+': LEFT lookup from saved mapping')
        # Compare all ids with model-generated binding (if saved final JSON exists); P2 emitted tables instead.
        scratch=list((root/'o/scratch').glob('*inspection.json'))
        if scratch:
            report=read(scratch[0]);given={x['roi_alias']:x.get('source_triangle_indices',x.get('local_source_triangle_indices')) for x in report['surfaces']}
            check(all(given[r['roi_id']]==local[i] for i,r in enumerate(regions)),slot+': native reconstructed binding equals saved map')
        original_text=read(root/'c/owner_turn/tool_01/RESPONSE.json')['result']['content'][0]['text']
        proposed=json.loads(original_text);proposed['regions']['columns'].append('source_triangle_indices')
        for row,ids in zip(proposed['regions']['rows'],local):row.append(ids)
        compact=lambda v:json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()
        maps.append({'slot':slot,'source_triangles':126,'supported_triangles':122,'unsupported_triangles':4,'regions':61,'pixel_lookups':pixel_matches,'original_UTF8_bytes':len(original_text.encode()),'proposed_UTF8_bytes':len(compact(proposed)),'added_compact_UTF8_bytes':len(compact(proposed))-len(compact(obs)),'proposal_is_offline_only':True,'new_product_calls':0})

for group in 'NP':check(dict(raw_usage[group])==cost['groups'][group]['usage_sum'],group+': total raw usage')
check(raw_usage['N']['input_tokens']+raw_usage['N']['output_tokens']==348400,'N raw input/output')
check(raw_usage['P']['input_tokens']+raw_usage['P']['output_tokens']==349856,'P raw input/output')
check([x['slot'] for x in slots if not x['quality']]==['N2'],'failure denominator')
paired=[]
for i in range(1,4):
    n=next(x for x in slots if x['slot']==f'N{i}');p=next(x for x in slots if x['slot']==f'P{i}')
    ratio=p['full_ns']/n['full_ns'] if n['quality'] and p['quality'] else None
    check(ratio==cost['decision']['pairs'][i-1]['P_over_N'],f'pair {i}: ratio with failure exclusion')
    paired.append(ratio)
check(cost['decision']['median_P_over_N'] is None and not cost['decision']['limited_positive_signal'],'no positive claim')
batch=read(RUN/'formal/BATCH_TIMING.json');total=sum(x['full_ns'] for x in slots)
check(batch['elapsed_ns']==batch['aggregate_results_closed_ns']-batch['started_ns'],'batch arithmetic')
check(batch['elapsed_ns']>=total,'slot times nested within batch')
archive=read(NS/'RUNTIME_ARCHIVE.json');indexed={str(Path(x['original_path'])):x for x in archive['files']}
for path,digest in list(inputs.items()):
    if path in indexed:
        row=indexed[path];check(digest==row['sha256']==hashlib.sha256((NS/row['archive_path']).read_bytes()).hexdigest(),'archive '+row['relative_path'])
result={'schema':'independent-occluded-cost-review-v1','passed':all(x['passed'] for x in checks),'checks':checks,'new_product_model_Blender_raster_calls':0,'slots':slots,'groups':{g:dict(raw_usage[g]) for g in 'NP'},'P_raw_extra':1456,'P_raw_extra_percent':(349856/348400-1)*100,'paired_ratios':paired,'complete_slot_sum_ns':total,'batch_ns':batch['elapsed_ns'],'batch_extra_ns':batch['elapsed_ns']-total,'offline_mapping':maps,'inputs_sha256':inputs,'limits':['provider usage aggregate scope unconfirmed','cash and image-token attribution unmeasured','no counterfactual model benefit measured','this is CAPTURE_REPLAY, not live Blender collection'],'exploration_errors_retained':['Initial assumed nested archive/formal path does not exist; archive uses flat indexed paths, corrected to verified original runtime paths','Initial event probe did not guard item.result=null; later raw parser selects completed mcp items']}
(OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':result['passed'],'checks':len(checks),'groups':result['groups'],'paired_ratios':paired,'mapping':maps,'counts':[{k:x[k] for k in ['slot','full_ns','handler_ns','calls','rasters','images','CLI_text_bytes','server_text_bytes']} for x in slots]},ensure_ascii=False,indent=2))
