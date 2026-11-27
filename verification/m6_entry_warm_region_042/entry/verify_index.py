"""Read-only recomputation of 042 E metadata evidence; no Codex process launch."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent

def pin(path):
 p=Path(path).resolve();b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def read(path):return json.loads(Path(path).read_bytes())
def check(ref):assert pin(ref['path'])==ref;return Path(ref['path'])

def main():
 index=read(HERE/'INDEX.json');raw=read(check(index['raw_index']));seen={};count=0
 for case in raw['cases']:
  result=read(check(case['result']));listed=read(check(case['discovery']))
  assert result['status']=='metadata_complete'and result['definition']['arm']==case['arm']
  assert result['auth_or_key_files_copied']is False and result['credential_file_names_present']==[]
  assert result['cleanup']['pids']==[]and result['cleanup']['accounting']['active_processes']==0
  assert result['cleanup']['readers_joined']
  assert result['registration_after']==result['definition']['registration_refs']
  for ref in result['definition']['registration_refs']:check(ref)
  tx=[json.loads(line)for line in check(case['TX']).read_bytes().splitlines()if line.strip()]
  rx=[json.loads(line)for line in check(case['RX']).read_bytes().splitlines()if line.strip()]
  assert [row['method']for row in tx]==['initialize','initialized','hooks/list']
  assert not any(row.get('method')in('hook/started','hook/completed','thread/started','turn/started')for row in rx)
  hook=[h for d in listed['result']['data']for h in d['hooks']];assert len(hook)==1
  hook=hook[0];assert hook['enabled']and hook['trustStatus']=='untrusted'and hook['currentHash']==case['current_hash']
  key=case['arm'];value=(hook['key'],hook['currentHash'],hook['command'])
  if key in seen:assert seen[key]==value
  seen[key]=value;count+=1
 install=read(check(raw['runtime_source_check']));assert install['status']=='pass'and install['source_count']==143
 assert count==4 and set(seen)=={'H0','H1'}
 assert all(row['formal_denominator']is False for row in raw['diagnostics'])
 assert all(case['status']=='NOT_RUN'for case in raw['formal'].values())
 print(json.dumps(dict(status='pass',valid_metadata_probes=count,matched_registration_pairs=2,
  selected_R3_source_files=143,turns=0,models=0,trust_grants=0,observations=0,
  actual_automatic_Hook_qualification=False,index=pin(HERE/'INDEX.json')),ensure_ascii=False))

if __name__=='__main__':main()
