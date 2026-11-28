"""Check the normal package entry, with a standalone config and no Blender scene."""
import json
from pathlib import Path
import subprocess
import sys

site,root=map(Path,sys.argv[1:])
root.mkdir(exist_ok=False)
cfg=root/'config.json'
cfg.write_text(json.dumps(dict(schema_version='1.0',enabled=True,project_root=str(site),
    state_file='state.json',audit_file='audit.jsonl',blender={'port':1})), encoding='utf8')
messages=[dict(jsonrpc='2.0',id=1,method='initialize',params={}),
          dict(jsonrpc='2.0',id=2,method='tools/list',params={}),
          dict(jsonrpc='2.0',id=3,method='tools/call',params={'name':'human_eye_scene_observe',
               'arguments':{'query':{'mode':'active_observation','objects':[{'name':'Box'}],
                                      'focus':{'normal_world':[0,0,0]}}}})]
tx=b''.join((json.dumps(m)+'\n').encode() for m in messages)
launch='import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_module("human_eye_plugin.production_server",run_name="__main__")'
p=subprocess.run([sys.executable,'-I','-B','-c',launch,str(site),'--config',str(cfg)],cwd=root,
    input=tx, stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25)
(root/'stdio.tx').write_bytes(tx)
(root/'stdio.rx').write_bytes(p.stdout)
(root/'stderr.log').write_bytes(p.stderr)
p.check_returncode()
hello,listed,rejected=[json.loads(line) for line in p.stdout.splitlines()]
tools=listed['result']['tools']
assert len(tools)==5
schema=next(t for t in tools if t['name']=='human_eye_scene_observe')['inputSchema']
assert '"focus"' in json.dumps(schema) and rejected['result']['isError']
assert 'focus' in rejected['result']['content'][0]['text']
print('production entry, five tools, focus schema, invalid focus rejected, stdout EOF, exit 0')
