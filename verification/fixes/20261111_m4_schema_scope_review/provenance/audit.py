"""Read-only schema-fix provenance audit. Does not import or execute project code."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

WT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
PREFIX='verification/m4_geometry_schema_scope_fix_001'
HEAD='00b13060a3cbe709b38f6e98ce04a6e5c3dabfb4'
BASE='be2de48bd9656787c4cdfbc5767c2551defcaada'
RUNTIME_BASE='a81e530a03460f93846e3bef4c45ebaa9347531b'
HERE=Path(__file__).resolve().parent


def sha(raw):return hashlib.sha256(raw).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=HERE/'audit.json')
    args=parser.parse_args();checks=[];batch=WT/PREFIX
    def check(name,condition,detail=None):checks.append(dict(name=name,passed=bool(condition),detail=detail))
    def git(*args):return subprocess.run(['git','-C',str(WT),*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout
    def read(path):return json.loads((batch/path).read_bytes())
    def blobs(commit,paths):
        proc=subprocess.run(['git','-C',str(WT),'cat-file','--batch'],input=''.join(commit+':'+p+'\n' for p in paths).encode(),check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        pos=0;out={}
        for path in paths:
            end=proc.stdout.index(b'\n',pos);oid,kind,size=proc.stdout[pos:end].decode().split();size=int(size)
            assert kind=='blob';out[path]=(oid,proc.stdout[end+1:end+1+size]);pos=end+size+2
        return out
    before=git('status','--short').decode();check('HEAD',git('rev-parse','HEAD').decode().strip()==HEAD)
    index=read('INDEX.json');ready=read('SCHEMA_FIX_READY.json');sd=read('SOURCE_DIFF.json');identity=read('r1/EXECUTION_IDENTITY.json')
    expected={r['path'] for r in index['files']}|{PREFIX+'/'+p for p in index['self_reference_files']}
    tracked=set(git('ls-tree','-r','--name-only',HEAD,'--',PREFIX).decode().splitlines())
    disk={p.relative_to(WT).as_posix() for p in batch.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    check('index159_unique',len(index['files'])==len({r['path'] for r in index['files']})==index['file_count']==159)
    check('Git161_exact',len(tracked)==161 and tracked==expected)
    check('disk161_exact',disk==expected,dict(extra=sorted(disk-expected),missing=sorted(expected-disk)))
    all_blobs=blobs(HEAD,sorted(expected));pins={r['path']:r for r in index['files']};files=[]
    for path,(oid,raw) in all_blobs.items():
        check('Git_disk:'+path,raw==(WT/path).read_bytes())
        if path in pins:check('index_pin:'+path,len(raw)==pins[path]['bytes'] and sha(raw)==pins[path]['sha256'])
        files.append(dict(path=path,git_blob=oid,bytes=len(raw),sha256=sha(raw)))
    check('indexed_bytes',sum(p['bytes'] for p in index['files'])==index['bytes']==4267582)
    check('ready_index_hash',sha((batch/'INDEX.json').read_bytes())==ready['index_sha256'])
    manifest=sd['manifest'];paths=[r['path'] for r in manifest]
    now=blobs(HEAD,paths);old=blobs(BASE,paths);runtime_old=blobs(RUNTIME_BASE,paths)
    check('manifest137_unique',len(paths)==len(set(paths))==137)
    check('old_runtime_binding',all(old[p][1]==runtime_old[p][1] for p in paths))
    changed=[]
    for row in manifest:
        p=row['path'];raw=now[p][1]
        check('runtime_pin:'+p,sha(raw)==row['sha256'] and raw==(WT/p).read_bytes())
        check('runtime_snapshot:'+p,raw==(batch/'r1/e'/p).read_bytes())
        if raw!=old[p][1]:changed.append(p)
    check('one_runtime_change',changed==sd['changed_files']==['human_eye_plugin/live_spatial_mcp.py'])
    constants={}
    for node in ast.parse(now['human_eye_plugin/runtime_identity.py'][1]).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('BASE_VERSION','IMPLEMENTATION_REVISION') for t in node.targets):constants[node.targets[0].id]=ast.literal_eval(node.value)
    canonical=sha(json.dumps(dict(base_version=constants['BASE_VERSION'],implementation_revision=constants['IMPLEMENTATION_REVISION'],files=manifest),sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    check('canonical4ebc',canonical==sd['source_sha256']==identity['canonical_source_sha256']==ready['runtime_source_sha256']=='4ebc3910652ee461d9fa7476c8df0ecf6312580d6a02e1066c0eac88bef5c76c')
    mcp='human_eye_plugin/live_spatial_mcp.py';braw=old[mcp][1];nraw=now[mcp][1]
    check('MCP_hashes',sha(braw)==sd['source_file_before_sha256'] and sha(nraw)==sd['source_file_after_sha256'])
    before_anchor=b'               ]}}],\n'
    after_anchor=b'               ]}},\n              {"if": {"required": ["geometry"]},\n               "then": {"required": ["mode", "target", "candidates"],\n                        "properties": {"mode": {"const": "task"}}}}],\n'
    check('one_exact_byte_change',braw.count(before_anchor)==1 and nraw.count(after_anchor)==1 and braw.replace(before_anchor,after_anchor)==nraw and len(nraw)-len(braw)==188)
    btree=ast.parse(braw);ntree=ast.parse(nraw)
    query=next(n.value for n in ntree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_QUERY_SCHEMA' for t in n.targets))
    rules=next(v for k,v in zip(query.keys,query.values) if isinstance(k,ast.Constant) and k.value=='allOf')
    appended=ast.literal_eval(rules.elts.pop())
    check('one_schema_condition',appended==sd['schema_condition'])
    check('whole_AST_without_condition_equal',ast.dump(ntree,include_attributes=False)==ast.dump(btree,include_attributes=False))
    check('compact_schema_file_bytes_unchanged',(batch/'r1/BASELINE_COMPACT_SCHEMAS.json').read_bytes()==(batch/'r1/CANDIDATE_COMPACT_SCHEMAS.json').read_bytes())
    check('baseline_saved_source',braw==(batch/'r1/BASELINE_MCP.py').read_bytes())
    check('identity_manifest',identity['manifest']==manifest)
    for key,path in [('runner_sha256','run_checks.py'),('source_diff_sha256','SOURCE_DIFF.json'),('test_source_sha256','tests/test_schema_scope.py'),('work_order_sha256','WORK_ORDER.json')]:
        check('identity_pin:'+key,identity[key]==sha((batch/path).read_bytes()))
    for item in read('WORK_ORDER.json')['inputs']:
        check('root_work_order_input:'+item['path'],sha(Path(item['path']).read_bytes())==item['sha256'])
    results=read('r1/RESULTS.json')
    check('saved_qualification',results['passed'] and not results['errors'] and not results['failures'] and results['test_methods']==4 and results['generic_fixed_query_cases']==20 and results['compact_schema_validator_controls']==3 and results['finite_compact_dispatches']==3)
    check('no_new_performance_or_install_admission',ready['new_version_full_admission'] is False and ready['new_version_performance_measured'] is False and ready['previous_default_latency_regression_unresolved'] is True and ready['previous_full_admission'] is False)
    history_path='verification/m4_relation_selected_evidence_001'
    check('previous1976_Git_evidence_unmodified',git('diff','--name-only',BASE,HEAD,'--',history_path).strip()==b'')
    previous=json.loads((WT/history_path/'EVIDENCE_READY.json').read_bytes())
    check('previous_latency_result_retained',previous['cost']['baseline_default_warm_median_ms']==37.53295 and previous['cost']['candidate_default_warm_median_ms']==38.87395 and previous['full_admission'] is False)
    check('worktree_unchanged',before==git('status','--short').decode())
    out=dict(fixed_commit=HEAD,baseline=BASE,baseline_runtime=RUNTIME_BASE,files=files,source_count=137,canonical=canonical,
             changed_sources=changed,byte_delta=len(nraw)-len(braw),schema_condition=appended,checks=checks,passed=all(c['passed'] for c in checks),
             failed=[c for c in checks if not c['passed']],old_latency_unresolved=True,
             not_run=['product imports/tests','performance','installation','Blender','models'],
             history_scope='Prior 1976-file batch Git diff is empty; this audit does not repeat its full disk hash matrix')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(passed=out['passed'],checks=len(checks),failed=out['failed'],files=len(files),canonical=canonical,output=str(args.output)),ensure_ascii=False))
    return 0 if out['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
