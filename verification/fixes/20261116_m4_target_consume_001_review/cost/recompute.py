"""Independent saved-evidence identity, cost and native-baseline review."""
from pathlib import Path
from fractions import Fraction
import hashlib
import ast
import json
import statistics
import subprocess
import tomllib
import zipfile

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
NS = ROOT / 'verification/m4_target_task_consumption_001'
RUN = Path('D:/he_m4_target_consume_001')
OUT = Path(__file__).resolve().parent
FINAL = 'bc177d231329dac630b4d02a161076b2b9fb50e3'
BASE = '71a505135ecf202c0e8572fb01bbe21c410342e2'
FROZEN_GIT = 'bfd4279e52c80e16c7909729b70569178b70587f'
ORDER = ['N1','P1','P2','N2','N3','P3']
checks = 0

def check(value, label):
    global checks
    checks += 1
    if not value:
        raise AssertionError(label)

def sha(blob):
    return hashlib.sha256(blob).hexdigest()

def read(path):
    return json.loads(Path(path).read_bytes())

def git(*args, binary=False):
    raw = subprocess.run(['git', *args], cwd=ROOT, check=True, stdout=subprocess.PIPE).stdout
    return raw if binary else raw.decode('utf8').strip()

def git_blobs(specs):
    raw = subprocess.run(['git','cat-file','--batch'], cwd=ROOT, input=('\n'.join(specs)+'\n').encode(), check=True, stdout=subprocess.PIPE).stdout
    offset = 0
    result = []
    for spec in specs:
        end = raw.index(b'\n', offset)
        fields = raw[offset:end].split()
        check(len(fields)==3 and fields[1]==b'blob', 'Git blob '+spec)
        size = int(fields[2])
        result.append(raw[end+1:end+1+size])
        check(raw[end+1+size:end+2+size]==b'\n', 'Git batch framing')
        offset = end+2+size
    check(offset==len(raw), 'Git complete batch')
    return result

check(git('rev-parse','HEAD')==FINAL, 'fixed final HEAD')
check(git('status','--porcelain')=='', 'author worktree clean')
check(git('diff','--name-only',BASE,FINAL,'--','human_eye_plugin','human_eye_foveated_renderer.py','human_eye_hook.py')=='', 'product unchanged')
manifest = read(NS/'CONTENT_MANIFEST.json')
entries = manifest['files']
manifest_paths = [r['path'] for r in entries]
relative_manifest = (NS/'CONTENT_MANIFEST.json').relative_to(ROOT).as_posix()
changed = git('diff','--name-only',BASE,FINAL).splitlines()
check(len(entries)==1606 and set(changed)==set(manifest_paths+[relative_manifest]), '1607 Git paths exact closure')
blobs = git_blobs([FINAL+':'+p for p in manifest_paths+[relative_manifest]])
for row, blob in zip(entries,blobs):
    actual = (ROOT/row['path']).read_bytes()
    check(actual==blob and len(blob)==row['bytes'] and sha(blob)==row['sha256'], 'manifest member '+row['path'])
check(blobs[-1]==(NS/'CONTENT_MANIFEST.json').read_bytes(), 'manifest actual Git bytes')

archive = read(NS/'RUNTIME_ARCHIVE.json')
check(len(archive['files'])==1129, 'runtime archive denominator')
for row in archive['files']:
    source = Path(row['original_path']).read_bytes()
    saved = (NS/row['archive_path']).read_bytes()
    check(source==saved and len(source)==row['bytes'] and sha(source)==row['sha256'], 'runtime archive '+row['relative_path'])

frozen = read(NS/'FROZEN.json')
check(len(frozen['files'])==423, '423 formal pins')
for row in frozen['files']:
    actual = Path(row['path']).read_bytes()
    check(sha(actual)==row['sha256'] and len(actual)==row['bytes'], 'formal pin '+row['path'])
frozen_core = ['PLAN.json','FROZEN.json','native_tools.py','bridge.py','run_slot.py','run_formal.py']
frozen_blobs = git_blobs([FROZEN_GIT+':'+(NS/p).relative_to(ROOT).as_posix() for p in frozen_core])
for name,blob in zip(frozen_core,frozen_blobs):
    check(blob==(NS/name).read_bytes(), 'formal Git core '+name)

binding = read(NS/'PRODUCT_RUN_BINDING.json')
check(binding['preparation_git']=='c309d7e4302518cd5f7d1c3966e7c7fa338ea128', 'product Git')
check(len(binding['source_manifest'])==141, '141 product source')
wheel_paths = list((ROOT/'verification/m4_target_acquisition_002/build_B').glob('*.whl'))
check(len(wheel_paths)==1, 'one frozen wheel')
wheel = wheel_paths[0]
check(sha(wheel.read_bytes())==binding['wheel_sha256']=='aefa75ab15aa47632ecb16f6a59af207186e2b66ced9a5baa2253ec55eb36486', 'wheel digest')
product_blobs = git_blobs([FINAL+':'+r['path'] for r in binding['source_manifest']])
with zipfile.ZipFile(wheel) as z:
    for row,blob in zip(binding['source_manifest'],product_blobs):
        install = (Path(binding['install_root'])/row['path']).read_bytes()
        check(install==blob==z.read(row['path']) and sha(blob)==row['sha256'], 'Git/install/wheel '+row['path'])
identity = dict(base_version=binding['base_version'], implementation_revision=binding['implementation_revision'], files=binding['source_manifest'])
aggregate = sha(json.dumps(identity,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
check(aggregate==binding['source_sha256']=='776b0f0914e116fece16d2b3875ee16ffebf4896a7e394861287ffaa6fe025be', 'aggregate source')

plan = read(NS/'PLAN.json')
formal = read(RUN/'RUN_RESULT.json')
start = read(RUN/'FORMAL_STARTED.json')
check(sha((NS/'PLAN.json').read_bytes())==formal['plan_sha256']==start['plan_sha256'], 'plan before formal')
check(sha((NS/'FROZEN.json').read_bytes())==formal['frozen_sha256']==start['freeze_sha256'], 'freeze before formal')
check([r['slot_id'] for r in formal['records']]==ORDER and formal['actual_consumers']==6 and formal['outer_retries']==formal['replacement_samples']==0, 'one six-slot formal batch')
check(plan['limits']==dict(business_tools_per_slot=12,consumers=6,formal_rasters=36,owned_seconds=600,owned_starts=8,qualification_rasters=12,rasters_per_slot=6,task_seconds=450,total_rasters=48), 'original limits')

records = []
profiles = []
common_schemas = []
prefix_assignment = next(node for node in ast.parse((NS/'launcher.py').read_text(encoding='utf8')).body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='PREFIXES' for target in node.targets))
prefixes = ast.literal_eval(prefix_assignment.value)
common_task = (NS/'inputs/COMMON_TASK.txt').read_bytes()
answer_schema = (NS/'inputs/ANSWER_SCHEMA.json').read_bytes()
check(sha(common_task)==plan['common_task_sha256'] and sha(answer_schema)==plan['answer_schema_sha256'], 'common raw task and answer schema')
for group in ('N','P'):
    prompt = prefixes[group].encode('utf8')+b'\n\n'+common_task+b'\n\nANSWER_SCHEMA.json\n'+answer_schema
    check(sha(prompt)==plan['prompt_sha256'][group], 'same common task suffix '+group)
for slot in ORDER:
    folder = RUN/'formal'/slot
    result = read(folder/'SLOT_RESULT.json')
    pub = read(folder/'SLOT_PUBLICATION.json')
    consumer = read(folder/'consumer/CONSUMER.json')
    timing = read(folder/'consumer/FINAL_TIMING.json')
    raw_stdout = (folder/'consumer/stdout.raw.bin').read_bytes()
    events = [json.loads(line) for line in raw_stdout.splitlines() if line]
    completed = [e for e in events if e.get('type')=='turn.completed']
    threads = [e['thread_id'] for e in events if e.get('type')=='thread.started']
    check(len(completed)==len(threads)==1 and threads[0]==consumer['thread_id'], slot+' one terminal usage and fresh thread')
    usage = completed[0]['usage']
    check(usage==consumer['usage'] and consumer['usage_rows']==consumer['raw_usage_events']==[usage], slot+' raw usage projection')
    check(all(type(v) is int and v>=0 for v in usage.values()) and usage['cached_input_tokens']<=usage['input_tokens'] and usage['reasoning_output_tokens']<=usage['output_tokens'], slot+' usage fields')
    check(sha(raw_stdout)==consumer['stdout_raw_sha256'], slot+' raw stdout binding')
    check(pub['result_sha256']==sha((folder/'SLOT_RESULT.json').read_bytes()), slot+' publication binding')
    begin = pub['slot_started_ns']
    end = pub['slot_result_published_ns']
    clocks = result['clocks']
    check(clocks['slot_started_ns']==begin and pub['complete_slot_ns']==end-begin, slot+' full boundary')
    check(begin<=clocks['owner_ready_ns']<=clocks['business_closed_ns']<=clocks['cleanup_started_ns']<=clocks['cleanup_closed_ns']<=end, slot+' root cleanup contained')
    check(clocks['consumer_deadline_ns']==begin+450_000_000_000 and clocks['owned_deadline_ns']==begin+600_000_000_000 and end<clocks['owned_deadline_ns'], slot+' original deadlines')
    check(begin<=timing['started_ns']<=consumer['prompt_submitted_ns']<=consumer['final_received_ns']<=consumer['process_exit_ns']<=timing['consumer_record_closed_ns']<=end, slot+' CLI response exit recorded in complete task')
    check(consumer['exit_code']==0 and consumer['process_reaped'] and consumer['valid_completion'] and consumer['safe_to_continue'], slot+' complete CLI task')
    check(consumer['input_sha256']==plan['prompt_sha256'][slot[0]], slot+' actual frozen prompt')
    argv = consumer['argv']
    settings = [argv[i+1] for i,x in enumerate(argv) if x=='-c' and not argv[i+1].startswith('mcp_servers.arm_engine=')]
    check(len(settings)==len(set(x.split('=',1)[0] for x in settings)), slot+' unique overrides')
    cfg = tomllib.loads('\n'.join(settings))
    check(cfg['model']=='gpt-6.1-sol' and cfg['model_reasoning_effort']=='medium' and cfg['service_tier']=='default', slot+' fixed profile')
    profiles.append(settings)
    check(sha(Path(argv[0]).read_bytes())=='01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6', slot+' actual CLI hash')
    tools = read(folder/'owner/TOOLS.json')
    metrics = read(folder/'owner/METRICS.json')
    schemas = read(folder/'owner/TOOLS_SCHEMA.json')
    common_schemas.append([tool for tool in schemas if tool['name']!='active_observation'])
    check(('active_observation' in [tool['name'] for tool in schemas])==(slot[0]=='P'), slot+' only product additional tool')
    check(tools['calls']==len(tools['tools'])==len(consumer['tool_calls'])==metrics['tool_attempts']<=12, slot+' real tool denominator')
    service = sum(t['closed_ns']-t['started_ns'] for t in tools['tools'])
    check(all(t['elapsed_ns']==t['closed_ns']-t['started_ns'] for t in tools['tools']), slot+' tool timestamps')
    public = metrics['public_content']
    records.append(dict(slot=slot, thread=threads[0], begin=begin, end=end, complete_ns=end-begin, usage=usage, raw_total=usage['input_tokens']+usage['output_tokens'], uncached_input=usage['input_tokens']-usage['cached_input_tokens'], tools=tools['calls'], service_ns=service, tool_errors=[t for t in tools['tools'] if t['is_error']], image_blocks=sum(r['image_blocks'] for r in public), PNG_bytes=sum(r['PNG_bytes'] for r in public), text_bytes=sum(r['text_UTF8_bytes'] for r in public), usage_semantics=consumer['usage_semantics']))
check(len({r['thread'] for r in records})==6, 'six distinct threads')
check(all(p==profiles[0] for p in profiles), 'identical common CLI settings')
check(all(s==common_schemas[0] for s in common_schemas), 'same common tool descriptions and schemas')
check(all(a['end']<=b['begin'] for a,b in zip(records,records[1:])), 'formal serial order')

pairs = []
for i in (1,2,3):
    n = next(r for r in records if r['slot']=='N'+str(i))
    p = next(r for r in records if r['slot']=='P'+str(i))
    ratio = Fraction(p['complete_ns'],n['complete_ns'])
    pairs.append(dict(pair=i, exact=str(ratio), ratio=float(ratio)))
totals = {}
for group in ('N','P'):
    rows = [r for r in records if r['slot'][0]==group]
    totals[group] = {k:sum(r[k] for r in rows) for k in ('complete_ns','raw_total','uncached_input','tools','service_ns','image_blocks','PNG_bytes','text_bytes')}
    totals[group]['usage'] = {k:sum(r['usage'][k] for r in rows) for k in rows[0]['usage']}
    totals[group]['uncached_input_plus_output'] = totals[group]['uncached_input']+totals[group]['usage']['output_tokens']
median = statistics.median(p['ratio'] for p in pairs)
decision = read(NS/'DECISION.json')
check(median==decision['complete_time_paired_median_P_over_N'], 'published paired median')
check(totals['N']['raw_total']==416003 and totals['P']['raw_total']==78973, 'published raw usage totals')
check(median<=.90 and all(p['ratio']<1 for p in pairs) and totals['P']['raw_total']<=totals['N']['raw_total'], 'frozen cost gates')

n3_tools = read(RUN/'formal/N3/owner/TOOLS.json')['tools']
check([i+1 for i,tool in enumerate(n3_tools) if tool['is_error']]==[6], 'N3 exact failed tool number')
check(all(not r['tool_errors'] for r in records if r['slot']!='N3'), 'other five slots no business tool errors')
rejection = dict(failed_service_ns=n3_tools[5]['elapsed_ns'], failed_to_next_start_ns=n3_tools[6]['started_ns']-n3_tools[5]['closed_ns'], next_attempt_service_ns=n3_tools[6]['elapsed_ns'], causal_removable_cost='unknown')
answer = dict(status='passed_checked_scope', checks=checks, manifest_members=len(entries), Git_changed_paths=len(changed), archive_files=len(archive['files']), formal_pins=len(frozen['files']), product_source_files=141, records=records, pairs=pairs, totals=totals, median=median, reduction=1-median, raw_usage_reduction=1-totals['P']['raw_total']/totals['N']['raw_total'], uncached_input_plus_output_reduction=1-totals['P']['uncached_input_plus_output']/totals['N']['uncached_input_plus_output'], N3_rejection=rejection, new_Blender=0, new_raster=0, new_model_calls=0)
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(answer,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({k:answer[k] for k in ('status','checks','median','reduction','raw_usage_reduction','uncached_input_plus_output_reduction')}))
