"""Independent saved-evidence cost arithmetic. No product imports or live calls."""
from pathlib import Path
from collections import Counter
from statistics import median
import ast, base64, hashlib, io, json, math, re, zipfile

NS=Path('C:/Users/Administrator/.codex/worktrees/m1-source-face-binding-001/hefe/verification/m1_source_face_binding_001')
RUN=Path('D:/he_source_face_001')
OUT=Path(__file__).parent
checks=[]; inputs={}
def raw(path):
    path=Path(path); b=path.read_bytes(); inputs[str(path)]=hashlib.sha256(b).hexdigest(); return b
def read(path): return json.loads(raw(path))
def check(ok,label):
    checks.append({'check':label,'passed':bool(ok)})
    if not ok: raise AssertionError(label)
def text_bytes(content): return sum(len(x['text'].encode('utf8')) for x in content if x['type']=='text')
def image_info(content):
    images=[base64.b64decode(x['data']) for x in content if x['type']=='image']
    return [hashlib.sha256(b).hexdigest() for b in images],sum(map(len,images))
def npy_info(data):
    f=io.BytesIO(data); check(f.read(6)==b'\x93NUMPY','NPY magic')
    ver=f.read(2); width=2 if ver[0]==1 else 4
    n=int.from_bytes(f.read(width),'little'); h=ast.literal_eval(f.read(n).decode('latin1'))
    body=f.read(); dtype=h['descr']; m=re.fullmatch(r'[|<>=]([A-Za-z?])(\d+)',dtype)
    check(m is not None,'primitive array dtype')
    size=int(m[2])*(4 if m[1]=='U' else 1)
    check(len(body)==math.prod(h['shape'])*size,'NPY payload shape size')
    return {'dtype':dtype,'shape':list(h['shape']),'nbytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}

cost=read(NS/'COST.json'); qual=read(NS/'admin/QUALITY.json')
by={x['slot_id']:x for x in cost['slots']}; qby={x['slot_id']:x for x in qual['slots']}
sequence=['A1','B1','B2','A2','A3','B3']; slots=[]; last=0
for sid in sequence:
    root=RUN/'formal'/sid; c=by[sid]
    clock=read(RUN/'formal/slot_records'/sid/'SLOT_TIMING.json')
    consumer=read(root/'c/CONSUMER.json')
    events=[json.loads(x) for x in raw(root/'c/stdout.raw.bin').splitlines() if x.strip()]
    completed=[x['item'] for x in events if x.get('type')=='item.completed']
    calls=[x for x in completed if x.get('type')=='mcp_tool_call']
    usages=[x['usage'] for x in events if x.get('type')=='turn.completed']
    check(len(usages)==1,sid+': one raw turn usage')
    usage=usages[0]; check(usage==consumer['usage']==c['reported_usage'],sid+': raw consumer cost usage match')
    elapsed=clock['SLOT_RESULT_closed_ns']-clock['started_ns']
    check(elapsed==clock['elapsed_ns']==c['full_slot_ns'],sid+': full clock arithmetic')
    check(last<=clock['started_ns'],sid+': serial order'); last=clock['SLOT_RESULT_closed_ns']
    check(clock['started_ns']<=consumer['started_ns']<consumer['prompt_submitted_ns']<=consumer['final_received_ns']<=consumer['cleanup_end_ns']<=clock['SLOT_RESULT_closed_ns'],sid+': contained consumer/cleanup')
    check(consumer['exit_code']==0 and consumer['valid_completion'],sid+': completed normally')
    for name,cl in c['clocks'].items():
        check(cl['elapsed_ns']==cl['closed_ns']-cl['started_ns'],sid+': '+name+' arithmetic')
        check(clock['started_ns']<=cl['started_ns']<cl['closed_ns']<=clock['SLOT_RESULT_closed_ns'],sid+': '+name+' contained')
    tool_rows=[]; tooltext=0; images=[]; pngbytes=0; handler=0
    requests=sorted((root/'o').glob('tool_*/REQUEST.json'))
    check(len(requests)==len(calls)==c['counts']['tools'],sid+': business denominator')
    for i,(path,item) in enumerate(zip(requests,calls),1):
        req=read(path)['params']; receipt=read(path.with_name('RECEIPT.json')); result=read(path.with_name('RESPONSE.json'))['result']
        check(req['name']==receipt['name']==item['tool'],sid+f': tool {i} name')
        check(req['arguments']==item['arguments'],sid+f': tool {i} arguments')
        check(result['content']==item['result']['content'],sid+f': tool {i} exact CLI content')
        check(result.get('isError') is False and item.get('status')=='completed',sid+f': tool {i} successful protocol/CLI status')
        check(receipt['elapsed_ns']==receipt['closed_ns']-receipt['started_ns'],sid+f': tool {i} handler')
        check(not receipt['is_error'] and not receipt['response_serialization_error'],sid+f': tool {i} no error')
        size=text_bytes(result['content']); hashes,bytes_=image_info(result['content'])
        check(size==receipt['content_metrics']['text_UTF8_bytes'],sid+f': tool {i} actual text')
        check(len(hashes)==receipt['content_metrics']['image_blocks'] and bytes_==receipt['content_metrics']['PNG_bytes'],sid+f': tool {i} actual images')
        stdout=''
        for block in result['content']:
            if block['type']=='text' and req['name']=='execute_python': stdout+=json.loads(block['text']).get('stdout','')
        code=req['arguments'].get('code','')
        tool_rows.append({'number':i,'name':req['name'],'text_bytes':size,'stdout_bytes':len(stdout.encode()),'images':len(hashes),'PNG_bytes':bytes_,'handler_ns':receipt['elapsed_ns'],'request':str(path),'response':str(path.with_name('RESPONSE.json')),'code':code})
        tooltext+=size; images+=hashes; pngbytes+=bytes_; handler+=receipt['elapsed_ns']
    assistant=sum(len(x['text'].encode()) for x in completed if x.get('type')=='agent_message')
    check(tooltext==c['bytes']['tool_reply_text_UTF8'],sid+': tool text total')
    check(assistant==c['bytes']['assistant_public_text_UTF8'],sid+': assistant public text separately')
    check(len(images)==c['counts']['CLI_images'] and pngbytes==c['bytes']['CLI_PNG'],sid+': actual delivered images')
    check(len(images)==len(set(images)),sid+': no duplicate delivered PNG')
    trace=[json.loads(x) for x in raw(root/'o/TRACE.jsonl').splitlines() if x.strip()]
    renders=[x for x in trace if x['event']=='render_attempt']
    check(len(renders)==4==c['counts']['rasters'],sid+': 4 actual rasters')
    check([x['view_name'] for x in renders]==['SCENE','LEFT','BACK','TOP'],sid+': necessary TOP after 3 product frames')
    observed={}
    for path in list((root/'o/product_state.json.active_observation').rglob('*.npz'))+list((root/'o/frames').rglob('*.npz')):
        b=raw(path); arr={}
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            for name in z.namelist(): arr[name.removesuffix('.npy')]=npy_info(z.read(name))
        png=path.with_suffix('.png'); pngraw=raw(png)
        observed[path.stem]={'NPZ_bytes':len(b),'PNG_bytes':len(pngraw),'arrays':arr}
    check(len(observed)==4,sid+': all actual frame files')
    for frame in c['frames']:
        got=observed[frame['view_name']]
        check(got['NPZ_bytes']==frame['NPZ_bytes'] and got['PNG_bytes']==frame['PNG_bytes'],sid+': frame bytes '+frame['view_name'])
        check(got['arrays']==frame['arrays'],sid+': all saved NPY shapes/payloads '+frame['view_name'])
    for field,expr in [('all_saved_arrays',sum(x['nbytes'] for f in observed.values() for x in f['arrays'].values())),('generated_PNG',sum(x['PNG_bytes'] for x in observed.values())),('generated_NPZ',sum(x['NPZ_bytes'] for x in observed.values()))]:
        check(expr==c['bytes'][field],sid+': '+field)
    check(qby[sid]['final_quality_passed']==c['quality_passed']==True,sid+': successful quality denominator')
    slots.append({'slot':sid,'full_ns':elapsed,'handler_ns':handler,'usage':usage,'calls':len(calls),'raster':len(renders),'images':len(images),'PNG_bytes':pngbytes,'tool_text_bytes':tooltext,'assistant_text_bytes':assistant,'tools':tool_rows})

groups={}
for arm in 'AB':
    rows=[x for x in slots if x['slot'][0]==arm]; use=Counter()
    for row in rows:use.update(row['usage'])
    check(dict(use)==cost['groups'][arm]['usage_sum'],arm+': usage sum')
    groups[arm]={'usage':dict(use),'input_plus_output':use['input_tokens']+use['output_tokens'],'full_ns':sum(x['full_ns'] for x in rows),'handler_ns':sum(x['handler_ns'] for x in rows)}
    for key in ['calls','raster','images','PNG_bytes','tool_text_bytes','assistant_text_bytes']:
        groups[arm][key]=sum(x[key] for x in rows)
    check(groups[arm]['tool_text_bytes']==cost['groups'][arm]['tool_reply_text_UTF8'],arm+': tool text group')
    check(groups[arm]['assistant_text_bytes']==cost['groups'][arm]['assistant_public_text_UTF8'],arm+': assistant text group')
ratios=[]
for i in range(1,4):
    a=next(x for x in slots if x['slot']==f'A{i}'); b=next(x for x in slots if x['slot']==f'B{i}'); ratio=b['full_ns']/a['full_ns'];ratios.append(ratio)
    check(ratio==cost['decision']['pairs'][i-1]['B_over_A'],f'pair {i} raw ratio')
check(median(ratios)==cost['decision']['median_B_over_A'],'median paired ratio')
check(median(ratios)<=.9 and sum(x<1 for x in ratios)==2,'registered speed threshold')
check(groups['B']['input_plus_output']<=groups['A']['input_plus_output'],'registered usage threshold')
check(cost['decision']['limited_positive_signal'] and qual['all_six_quality_complete'] and qual['B_actual_source_binding_adoption_count']==3,'complete original gates; quality semantic separately audited')
batch=read(RUN/'formal/BATCH_TIMING.json'); total=sum(x['full_ns'] for x in slots)
check(batch['elapsed_ns']==batch['aggregate_results_closed_ns']-batch['started_ns']>=total,'batch nests slots')
intents=[read(p) for p in sorted((RUN/'raster_budget').glob('attempt_*/INTENT.json'))]
check([x['global_attempt'] for x in intents]==list(range(1,31)),'global 30 attempts contiguous')
check(sum(x['phase']=='preparation' for x in intents)==6 and sum(x['phase']=='formal' for x in intents)==24,'qualification/formal denominator')
check(len(cost['durable_intents'])==len(intents) and len(cost['raster_attempts'])==30,'ledger matches cost denominator')
q=read(RUN/'preparation/Q01/QUALIFICATION_RUN.json')
check(q['actual_rasters']==q['cumulative_preparation_rasters']==6 and q['outer_retries']==0,'single qualification no retries')
check(q['elapsed_ns']==q['closed_ns']-q['started_ns'],'qualification arithmetic')
eng=read(NS/'ENGINEERING_REPORT.json')
medians={}
for arm,rows in eng['projection_measurements'].items():
    check(len(rows)==31,'engineering 31 rotations '+arm)
    for row in rows:check(row['projection_and_encoding_ns']==row['projection_ns']+row['encoding_ns'],'engineering stage arithmetic '+arm)
    medians[arm]={field:median([r[field] for r in rows]) for field in ['projection_ns','encoding_ns','projection_and_encoding_ns']}
    check(medians[arm]==eng['medians_ns'][arm],'engineering median '+arm)
    check(median([x['peak_python_bytes'] for x in eng['memory_measurements'][arm]]) in [241688,259632,259664],'engineering saved memory median '+arm)
for row in eng['local_encoding_controls']:
    check(median(row['projection_and_ranges_encoding_ns'])==row['median_ns'],'encoding control median')
lookup=eng['representative_consumer_lookup']
for k,values in lookup['paired_execution_ns'].items():check(median(values)==lookup['medians_ns'][k],'lookup median '+k)
baseline=read(NS/'BASELINE.json')
preparation_ns=batch['started_ns']-baseline['preparation_started_ns']
check(preparation_ns==1716001203500,'preparation boundary through batch start')
explore={arm:sum(x['tools'][1]['text_bytes'] for x in slots if x['slot'][0]==arm) for arm in 'AB'}
first={arm:sum(x['tools'][0]['text_bytes'] for x in slots if x['slot'][0]==arm) for arm in 'AB'}
increment=groups['B']['tool_text_bytes']-groups['A']['tool_text_bytes']
archive=read(NS/'RUNTIME_ARCHIVE.json'); indexed={str(Path(x['original_path'])):x for x in archive['files']}
for path,digest in list(inputs.items()):
    if path in indexed:
        row=indexed[path]; check(digest==row['sha256']==hashlib.sha256((NS/row['archive_path']).read_bytes()).hexdigest(),'archived input '+row['relative_path'])
result={'schema':'independent-m1-source-face-cost-v1','passed':all(x['passed'] for x in checks),'checks':checks,'new_product_model_Blender_raster_calls':0,'slots':slots,'groups':groups,'paired_ratios':ratios,'median_ratio':median(ratios),'raw_usage_reduction_percent':(1-groups['B']['input_plus_output']/groups['A']['input_plus_output'])*100,'batch_ns':batch['elapsed_ns'],'sum_slots_ns':total,'preparation_ns':preparation_ns,'engineering_medians_ns':medians,'text_increment_attribution':{'total':increment,'first_product_reply_A_B':first,'tool_02_exploration_A_B':explore,'first_product_reply_increment':first['B']-first['A'],'tool02_increment':explore['B']-explore['A'],'tool02_share_of_increment':(explore['B']-explore['A'])/increment},'inputs_sha256':inputs,'limitations':['No new model trials or product calls; engineering timing independently recalculated from saved rows, not remeasured','Quality/adoption gate cross-checked against sealed result, semantic correctness handled by separate quality review','No image-token or cash attribution; raw usage follows same CLI source; provider aggregation unconfirmed','All original field changes held fixed, but consumer behavior varies, so total timing cannot be assigned to one operation','Sparse ranges remain O(source faces); Python allocated peak is not RSS','Full preparation/coordination/reviewer token cost unmeasured']}
with (OUT/'RESULT.json').open('x',encoding='utf8',newline='\n') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({'passed':result['passed'],'checks':len(checks),'groups':groups,'paired_ratios':ratios,'text_increment_attribution':result['text_increment_attribution']},ensure_ascii=False,indent=2))
