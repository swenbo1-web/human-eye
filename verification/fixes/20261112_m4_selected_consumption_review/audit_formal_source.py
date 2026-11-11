import hashlib, json, subprocess
from pathlib import Path
from datetime import datetime, timezone
WT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
ROOT=Path(__file__).resolve().parent
PREFIX='verification/m4_selected_geometry_consumption_001'
B=WT/PREFIX
HEAD='de35ceda1f5e3f5af2c9ec02f0e4646808f417c2'
def read(p): return json.loads(p.read_bytes())
def sha(b): return hashlib.sha256(b).hexdigest()
def git(*a): return subprocess.check_output(['git','-C',str(WT),*a])
def blobs(c,ps):
    raw=subprocess.check_output(['git','-C',str(WT),'cat-file','--batch'],input=''.join(c+':'+p+'\n' for p in ps).encode())
    pos=0; ans={}
    for p in ps:
        end=raw.index(b'\n',pos);oid,kind,size=raw[pos:end].split();size=int(size);assert kind==b'blob'
        ans[p]=raw[end+1:end+size+1];pos=end+size+2
    assert pos==len(raw)
    return ans
checks=[]
def ck(name,ok,detail=None):
    checks.append({'name':name,'passed':bool(ok),'detail':detail})
ck('fixed clean implementation HEAD',git('rev-parse','HEAD').decode().strip()==HEAD and git('status','--short')==b'')
index=read(B/'FORMAL_INDEX.json');idx={r['path']:r for r in index['files']}
paths=sorted(set(idx)|set(PREFIX+'/'+p for p in index['self_reference_files']))
tracked=set(git('ls-tree','-r','--name-only',HEAD,'--',PREFIX).decode().splitlines())
ck('formal exact tracked set',set(paths)==tracked,{'indexed':len(idx),'total':len(paths)})
bad=[]
for p,raw in blobs(HEAD,paths).items():
    if raw!=(WT/p).read_bytes() or (p in idx and (sha(raw)!=idx[p]['sha256'] or len(raw)!=idx[p]['bytes'])):bad.append(p)
ck('formal Git disk hashes bytes',not bad,bad)
prep=read(Path('D:/hefe/verification/fixes/20261111_m4_selected_consumption_prep_review/source/audit.json'))
pins=prep['files'];bad=[r['path'] for r in pins if sha((WT/r['path']).read_bytes())!=r['sha256']]
ck('preparation remains same bytes',not bad,{'count':len(pins),'bad':bad})
go=read(B/'GO.json')
ck('GO and PLAN fixed',sha((B/'GO.json').read_bytes())=='d962e9ee0e1ad8cdce22683b2bc38b9558efe3a96f146f525ea9d5e5cb3f458c' and sha((B/'PLAN.json').read_bytes())=='bd8af1e9619ccf9dad8c43a3ecf17eb240843f5b76f4ca9390b8a283ecc00096')
fixed=read(B/'installation/run_01/FIXED_BUILD_INPUTS.json');manifest=fixed['manifest'];rpaths=[r['path'] for r in manifest]
cur=blobs(HEAD,rpaths);candidate=blobs(go['sources']['G']['commit'],rpaths)
ck('137 current source matches fixed candidate',len(rpaths)==137 and all(cur[p]==candidate[p]==(WT/p).read_bytes() for p in rpaths))
plan=read(B/'PLAN.json')
rows=[];common_args=[]
for num,group in enumerate(go['sequence'],1):
    cell=B/'cells'/f'sgc{num:02d}';config=read(cell/'ACTOR_CONFIG.json');c=read(cell/'CONSUMER.json');ident=read(cell/'owner/IDENTITY.json');close=read(cell/'owner/CLOSE.json');finish=read(cell/'OWNER_FINISH.json')
    ck(f'{num} group and no errors',c['external_group']==config['external_group']==group and c['status']=='completed' and not c['errors'] and not c['unexpected_tool_deviations'])
    ck(f'{num} common source',config['asset_sha256']==ident['asset_sha256']=='91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85' and ident['common_native_sha256']=='a3285b07579737947164ba6a4d8fc14cf6cd8c4332ef9952e1b0c1f674cc353a')
    ck(f'{num} input and image file',c['input_sha256']=='c443f907474a78ebb2491127d0064ea301d6c4ecbc6d60f1d91adc33fe1f9757' and c['input_image_count']==1 and c['public_image_count']==0 and c['initial_image_unchanged'])
    ck(f'{num} closed immutable scene',close['geometry_unchanged'] and close['asset_unchanged'] and close['confirmed'] and finish['confirmed'] and finish['exit_code']==0 and close['native_close']['process_reaped'] and close['native_close']['exit_code']==0 and close['worker_closed']['initial_geometry_fingerprint']==close['worker_closed']['final_geometry_fingerprint'])
    ri=ident.get('runtime_identity')
    if group in ('P','G'):
        ck(f'{num} actual product identity',ri['source_sha256']==go['sources'][group]['sha256'] and ri['source_file_count']==137 and ri['identity_check']['compatible'] and ri['distribution_version']==('9.7.2+lr.r1' if group=='P' else '9.7.2+sg.r1'))
        ck(f'{num} product launcher receipt',close['plugin_close']['confirmed'] and close['plugin_close']['process_reaped'] and close['plugin_close']['exit_code']==0)
    argv=c['argv'];opts=[argv[i+1] for i,x in enumerate(argv[:-1]) if x=='-c']; opts=[v for v in opts if not v.startswith('mcp_servers.')]
    common_args.append(opts)
    ck(f'{num} requested model and hooks disabled','model="gpt-6.1-sol"' in opts and 'model_reasoning_effort="medium"' in opts and 'features.hooks=false' in opts and 'features.memories=false' in opts and '--ignore-user-config' in argv and '--ignore-rules' in argv)
    rows.append({'cell':f'sgc{num:02d}','group':group,'reported_model':c['model'],'requested_effort':c['requested_effort'],'resolved_effort':c['resolved_effort'],'image_delivery':c['image_delivery'],'product_identity':None if not ri else {k:ri[k] for k in ('source_sha256','source_file_count','distribution_version')},'owner_finish_confirmed':finish['confirmed'],'thin_client_exit':'unknown'})
ck('same non-MCP -c options across nine',all(x==common_args[0] for x in common_args))
out={'scope':'Independent saved formal source/input/identity review; no new runtime execution','created_utc':datetime.now(timezone.utc).isoformat(),'commit':HEAD,'passed':all(x['passed'] for x in checks),'checks':checks,'rows':rows,'limitations':['Loaded identity is a bound runtime report, not a new process replay.','Consumer bridge thin-client EXIT and product wrapper internal runtime PID exit are not independently proved in these formal records; actual owner/native and product launcher receipts are separately recorded.','Image attachment/argv binding does not confirm provider delivery or cognitive use.','FREEZE retains preparation model_consumers=0 and formal_GO=false; formal GO/STARTED/PROCESS and actual records establish the later stage, not those stale preparation fields.']}
dest=ROOT/'source';dest.mkdir(exist_ok=True)
(dest/'RESULTS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'checks':len(checks),'passed':out['passed'],'failed':[x for x in checks if not x['passed']]}))
