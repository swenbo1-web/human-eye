"""Independent stored-image and actual CLI/MCP content review. No author imports."""
import base64
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile
import numpy as np
from PIL import Image

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_image_consumption_001')
OUT=Path(__file__).resolve().parent
checks=[]; inputs={}; results={}
def raw(p):
    p=Path(p); data=p.read_bytes(); inputs[str(p)]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()};return data
def doc(p): return json.loads(raw(p))
def check(name,condition): checks.append({'name':name,'passed':bool(condition)})
def sha(b):return hashlib.sha256(b).hexdigest()
def lines(p):return [json.loads(line) for line in raw(p).decode('utf8').splitlines()]

expected={
 'view-a':{'bytes':1909,'sha256':'7604f2449bd8a344603bfb70fdfc14e991e4f0d77963835e0d647aff5f94e6f8'},
 'view-b':{'bytes':4790,'sha256':'c1f56b07da11042603613ea973b1e8fea5ee1b5b2ae8b519d3cef683daab0372'},
}
pixels={}; images={}
for ref,expected_image in expected.items():
    b=raw(ROOT/'inputs'/(ref+'.png'));images[ref]=b
    check(ref+'/registered_bytes',len(b)==expected_image['bytes'] and sha(b)==expected_image['sha256'])
    with Image.open(io.BytesIO(b)) as im:
        check(ref+'/decoded_format_dimensions',im.format=='PNG' and im.size==(512,512))
        array=np.asarray(im.convert('RGB'))
    colors,counts=np.unique(array.reshape(-1,3),return_counts=True,axis=0)
    background=colors[np.argmax(counts)]
    mask=np.any(array!=background,axis=2); y,x=np.where(mask)
    pixels[ref]={'background_RGB':background.tolist(),'foreground_pixels':int(mask.sum()),'foreground_bounds_xy':[int(x.min()),int(y.min()),int(x.max()),int(y.max())],
                 'colors':colors.tolist(),'counts':counts.tolist()}
    kinds=[];offset=8
    while offset<len(b):
        size=struct.unpack('>I',b[offset:offset+4])[0];kinds.append(b[offset+4:offset+8].decode());offset+=size+12
    check(ref+'/no_embedded_text_metadata',set(kinds)<= {'IHDR','IDAT','IEND'})
check('actual_visual_contrast',pixels['view-a']['foreground_pixels']==3 and pixels['view-b']['foreground_pixels']>10000)
prompt=raw(ROOT/'inputs/PROMPT.txt')
check('frozen_common_prompt',sha(prompt)=='600f5b721edce87ca10c0e8832b66ffe39c8c74db56d4268a72399a2c7eb8fea')
check('prompt_no_answer_mapping',not any(s in prompt.decode() for s in ['view-b 有','view-a 则','BACK','SCENE','Obj_','owner','depth','expected']))

settings={}; schemas={}; flat_blocks={}; thread_ids=[]
for arm in ['N','P']:
    base=ROOT/'r'/arm; prefix=arm+'/'
    consumer=doc(base/'c/CONSUMER.json'); started=doc(base/'c/CONSUMER_STARTED.json')
    records=lines(base/'c/events.jsonl');events=[r['event'] for r in records]
    mcp=[(r['perf_ns'],r['event']['item']) for r in records if r['event']['type']=='item.completed' and r['event'].get('item',{}).get('type')=='mcp_tool_call']
    check(prefix+'one_real_fresh_thread',consumer['execution_kind']=='provider' and consumer['expected_thread_id'] is None and consumer['turn_index']==1 and sum(e['type']=='thread.started' for e in events)==1)
    tid=next(e['thread_id'] for e in events if e['type']=='thread.started');thread_ids.append(tid)
    check(prefix+'thread_binding',tid==consumer['thread_id'])
    check(prefix+'one_started_completed_turn',sum(e['type']=='turn.started' for e in events)==sum(e['type']=='turn.completed' for e in events)==1)
    for record in [consumer,started]:
        check(prefix+'stdin_common_prompt_binding',record['input_sha256']==sha(prompt) and record['input_text_bytes']==len(prompt))
    argv=consumer['argv'];settings[arm]=[argv[i+1] for i,v in enumerate(argv[:-1]) if v=='-c' and not argv[i+1].startswith('mcp_servers.')]
    check(prefix+'actual_frozen_argv',argv==consumer['frozen_cli_argv'] and argv[0].endswith('codex.exe') and '0.152.1' in argv[0] and 'resume' not in argv)
    check(prefix+'no_initial_image_argument',consumer['initial_image']['count']==0 and '--image' not in argv and '-i' not in argv)
    check(prefix+'isolated_context_flags',all(flag in argv for flag in ['--ignore-user-config','--ignore-rules','--strict-config']))
    schema=doc(base/'o/TOOLS_SCHEMA.json');schemas[arm]=schema
    check(prefix+'expected_public_tools',[s['name'] for s in schema]==(['execute_python','read_image']+(['human_eye_image_observe'] if arm=='P' else [])))
    public_schema=json.dumps(schema,ensure_ascii=False)
    check(prefix+'schema_no_visual_answer',not any(s in public_schema for s in ['BACK','SCENE','Obj_','菱形','gray','grey','blank','foreground','owner','depth','pixel_count']))
    attachments=list((base/'c/attachments').glob('*/STARTED.json'))
    check(prefix+'one_stdio_attachment',len(attachments)==1)
    attach=attachments[0].parent
    protocol=[]
    for tx in sorted(attach.glob('*/TX.bin')):
        request=doc(tx);rx=tx.with_name('RX.bin');response=doc(rx) if rx.exists() else None
        protocol.append((request,response))
        if request['method']=='tools/list':check(prefix+'actual_wire_schema',response['result']['tools']==schema)
    wire_calls=[pair for pair in protocol if pair[0]['method']=='tools/call']
    check(prefix+'wire_cli_attempt_count',len(wire_calls)==len(mcp)==(2 if arm=='N' else 1))
    check(prefix+'no_python_or_other_tools',all(item['tool'] in ['read_image','human_eye_image_observe'] for _,item in mcp))
    flat=[];calls=[]
    for index,((when,item),(wire_request,wire_response)) in enumerate(zip(mcp,wire_calls),1):
        pp=prefix+str(index)+'/'
        owner_request=doc(base/'o'/('tool_'+str(index).zfill(2))/'REQUEST.json')
        owner_response=doc(base/'o'/('tool_'+str(index).zfill(2))/'RESPONSE.json')
        check(pp+'actual_request_owner_stdio_CLI',owner_request==wire_request and owner_request['params']['name']==item['tool'] and owner_request['params']['arguments']==item['arguments'])
        check(pp+'complete_non_error',item['status']=='completed' and item['error'] is None and owner_response['result']['isError'] is False)
        check(pp+'actual_response_owner_stdio',owner_response==wire_response)
        content=item['result']['content']
        check(pp+'actual_content_owner_stdio_CLI',content==wire_response['result']['content'])
        check(pp+'CLI_normalized_envelope',set(item['result'])=={'content','structured_content'} and item['result']['structured_content'] is None)
        refs=[item['arguments']['ref']] if item['tool']=='read_image' else item['arguments']['refs']
        check(pp+'alternating_label_image',len(content)==2*len(refs) and all(content[i]['type']==('text' if i%2==0 else 'image') for i in range(len(content))))
        for i,ref in enumerate(refs):
            label,block=content[2*i:2*i+2]
            check(pp+ref+'/only_public_label',label=={'type':'text','text':ref+' (512x512, image/png)'})
            check(pp+ref+'/standard_image_fields',set(block)=={'type','data','mimeType'} and block['mimeType']=='image/png')
            b=base64.b64decode(block['data'],validate=True)
            check(pp+ref+'/exact_original_png',b==images[ref])
            check(pp+ref+'/base64_round_trip',base64.b64encode(b).decode()==block['data'])
            flat.append((ref,block))
        calls.append({'tool':item['tool'],'arguments':item['arguments'],'completed_ns':when,'image_blocks':len(refs)})
    check(prefix+'ordered_images', [ref for ref,_ in flat]==['view-a','view-b'])
    flat_blocks[arm]=flat
    agent=[(r['perf_ns'],r['event']['item']['text']) for r in records if r['event']['type']=='item.completed' and r['event'].get('item',{}).get('type')=='agent_message']
    final=raw(base/'c/PUBLIC_FINAL.txt').decode('utf8').strip()
    check(prefix+'final_event_same_as_files',final==agent[-1][1].strip()==raw(base/'c/final.txt').decode('utf8').strip())
    check(prefix+'answer_after_all_images',agent[-1][0]>max(t for t,_ in mcp))
    check(prefix+'answer_matches_visible_mapping',final.startswith('view-b 有清晰的大面积几何轮廓') and 'view-a 则几乎是' in final and all(s in final for s in ['深色','浅灰色菱形','亮点']))
    # This exact output check records the actual answer, not a required future scoring template.
    warnings=[e['item']['message'] for e in events if e.get('item',{}).get('type')=='error']
    check(prefix+'both_warnings_retained',len(warnings)==2 and 'skip_host_skill_discovery' in warnings[0] and 'fallback metadata' in warnings[1])
    check(prefix+'unobserved_provider_not_filled',consumer['image_delivery']['provider_delivery_confirmed'] is None and consumer['image_delivery']['model_view_confirmed'] is None and consumer['resolved_effort'] is None and consumer['provider_requests'] is None)
    archive=doc(base/'c/ARCHIVE.json');zipraw=raw(base/'c.raw.zip')
    check(prefix+'archive_digest',sha(zipraw)==archive['archive_sha256'])
    with zipfile.ZipFile(io.BytesIO(zipraw)) as z:
        names=z.namelist()
        for filename in ['events.jsonl','final.txt','PUBLIC_FINAL.txt']:
            matches=[n for n in names if n==filename or n.endswith('/'+filename)]
            check(prefix+'archive_'+filename,len(matches)==1 and z.read(matches[0])==raw(base/'c'/filename))
    results[arm]={'thread_id':tid,'completed_tools':calls,'final':final,'warnings':warnings,'image_blocks':len(flat),
                  'PNG_bytes':sum(len(base64.b64decode(block['data'])) for _,block in flat),
                  'prompt_sha256':sha(prompt),'requested_model':consumer['model'],'requested_effort':consumer['requested_effort'],
                  'resolved_model_and_effort':'unobserved','provider_internal_request':'unobserved'}
check('two_independent_threads',len(set(thread_ids))==2)
check('same_effective_requested_settings',settings['N']==settings['P'])
check('same_common_tool_schemas',schemas['N']==schemas['P'][:2])
check('same_image_bytes_and_labels_across_routes',flat_blocks['N']==flat_blocks['P'])
out={'source_commit':'a54ad3a9bf738e8f9b5a75c71c29b0a6b105a6ff','scope':'Independent offline decode and original owner/stdio/CLI content chain. No author helper/validator imports, no new model or process test.',
     'checks':checks,'check_count':len(checks),'failed':[c for c in checks if not c['passed']],
     'pixels':pixels,'routes':results,'source_files':inputs,'settings_same':settings['N']==settings['P'],
     'interpretation':'Stored actual CLI image content and content-consistent post-image answers support this finite transport/visual qualification. Not proof of internal provider payload, resolved model, generic vision, or native-versus-plugin task benefit.',
     'new_model_Blender_renderer_API_calls':0}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:out[k] for k in ['check_count','failed','pixels','new_model_Blender_renderer_API_calls']},ensure_ascii=False))
