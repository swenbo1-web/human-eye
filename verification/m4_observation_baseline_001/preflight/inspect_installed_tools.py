"""Metadata-only installed stdio probe; no host, geometry, image or model."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

HERE=Path(__file__).resolve().parent
BATCH=HERE.parent
sha=lambda raw:hashlib.sha256(raw).hexdigest()
out=HERE/'metadata_01';out.mkdir(exist_ok=False)
ready=json.loads((BATCH/'installation/READY.json').read_bytes())
config=dict(schema_version='1.0',enabled=True,observe_on_prompt=False,project_root=ready['install_root'],
    state_file=str(out/'state.json'),audit_file=str(out/'audit.jsonl'),quad_size=128,
    expected_identity={'source_sha256':ready['source_sha256']})
(out/'config.json').write_text(json.dumps(config),encoding='utf8')
messages=[dict(jsonrpc='2.0',id=1,method='initialize',params={'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'m4-metadata-preparation','version':'001'}}),
    dict(jsonrpc='2.0',method='notifications/initialized'),dict(jsonrpc='2.0',id=2,method='tools/list'),dict(jsonrpc='2.0',id=3,method='ping')]
payload=b''.join((json.dumps(row,separators=(',',':'))+'\n').encode() for row in messages)
argv=[ready['dependency_python'],'-I','-B',ready['entry'],'serve','--config',str(out/'config.json'),'--spatial-task-only']
began=time.perf_counter_ns();process=None;stdout=stderr=b''
record={'argv':argv,'started_ns':began,'timeout_s':30,'pid':None,'returncode':None,'timed_out':False}
try:
    process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    record['pid']=process.pid
    try:stdout,stderr=process.communicate(payload,timeout=30)
    except subprocess.TimeoutExpired:
        record['timed_out']=True;process.kill();stdout,stderr=process.communicate(timeout=10)
    record['returncode']=process.returncode
finally:
    (out/'STDIN.jsonl').write_bytes(payload);(out/'STDOUT.jsonl').write_bytes(stdout);(out/'STDERR.txt').write_bytes(stderr)
    record.update(ended_ns=time.perf_counter_ns(),stdin_sha256=sha(payload),stdout_sha256=sha(stdout),stderr_sha256=sha(stderr))
    (out/'PROCESS.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
assert record['returncode']==0 and not record['timed_out']
replies=[json.loads(line) for line in stdout.splitlines() if line]
assert [row['id'] for row in replies]==[1,2,3]
identity=replies[0]['result']['_meta']['human_eye']
assert identity['source_sha256']==ready['source_sha256'] and identity['source_kind']=='installed_distribution'
assert identity['distribution_version']==ready['version']
tools=replies[1]['result']['tools']
assert [row['name'] for row in tools]==['human_eye_spatial_relations','human_eye_surface_nearest']
assert replies[2]['result']=={}
p=HERE/'P';p.mkdir(exist_ok=False)
(p/'PUBLIC_TOOLS.json').write_text(json.dumps(tools,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf8')
(out/'RESULTS.json').write_text(json.dumps(dict(passed=True,source_sha256=identity['source_sha256'],source_kind=identity['source_kind'],
    distribution_version=identity['distribution_version'],tools=[row['name'] for row in tools],installed_process_exit=process.returncode,
    public_tools='preflight/P/PUBLIC_TOOLS.json',public_tools_sha256=sha((p/'PUBLIC_TOOLS.json').read_bytes()),
    actual_Blender_calls=0,geometry_queries=0,model_calls=0,images_generated=0),indent=2)+'\n',encoding='utf8')
print(json.dumps({'passed':True,'tools':[row['name'] for row in tools],'source_sha256':identity['source_sha256']}))
