"""Recompute frozen records only: no project imports, runtime calls or benchmark reruns."""
import argparse
import ast
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import statistics
import subprocess
import zipfile

WT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HEAD = 'be2de48bd9656787c4cdfbc5767c2551defcaada'
PRODUCT = 'a81e530a03460f93846e3bef4c45ebaa9347531b'
BASE = 'e077fce38b5951efff8166b3b688d05ffa2ebf04'
CONTRACT = '2a2332d0'
PREFIX = 'verification/m4_relation_selected_evidence_001'
BATCH = WT / PREFIX
HERE = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')


def stats(values):
    return dict(count=len(values), minimum=min(values), median=statistics.median(values), maximum=max(values), sum=sum(values))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'audit.json')
    args = parser.parse_args()
    checks = []
    def check(name, condition, detail=None):
        checks.append(dict(name=name, passed=bool(condition), detail=detail))
    def git(*argv):
        return subprocess.run(['git', '-C', str(WT), *argv], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    def read(path):
        return json.loads((BATCH / path).read_bytes())
    def blobs(commit, paths):
        proc = subprocess.run(['git', '-C', str(WT), 'cat-file', '--batch'],
                              input=''.join(commit + ':' + p + '\n' for p in paths).encode(),
                              check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        pos, result = 0, {}
        for p in paths:
            end = proc.stdout.index(b'\n', pos)
            oid, kind, size = proc.stdout[pos:end].decode().split()
            size = int(size)
            assert kind == 'blob'
            result[p] = (oid, proc.stdout[end + 1:end + 1 + size])
            pos = end + size + 2
        return result
    before = git('status', '--short').decode()
    check('HEAD', git('rev-parse', 'HEAD').decode().strip() == HEAD)
    idx, ready, candidate = (read(p) for p in ('EVIDENCE_INDEX.json', 'EVIDENCE_READY.json', 'CANDIDATE_SOURCE.json'))
    paths = [r['path'] for r in idx['files']]
    expected = set(paths) | {PREFIX + '/' + p for p in idx['self_references']}
    tracked = set(git('ls-tree', '-r', '--name-only', HEAD, '--', PREFIX).decode().splitlines())
    disk_all = {p.relative_to(WT).as_posix() for p in BATCH.rglob('*') if p.is_file()}
    bytecode = {p for p in disk_all if '__pycache__' in p.split('/') or p.endswith('.pyc')}
    check('1974_unique_indexed', len(paths) == len(set(paths)) == idx['file_count'] == 1974)
    check('1976_Git_exact_set', tracked == expected and len(tracked) == 1976,
          {'missing': sorted(expected-tracked), 'extra': sorted(tracked-expected)})
    check('1976_disk_exact_set', disk_all-bytecode == expected,
          {'missing': sorted(expected-(disk_all-bytecode)), 'extra': sorted((disk_all-bytecode)-expected), 'bytecode_count': len(bytecode)})
    original = blobs(HEAD, sorted(expected))
    pins = {r['path']: r for r in idx['files']}
    files = []
    for path, (oid, raw) in original.items():
        check('blob_disk:' + path, raw == (WT/path).read_bytes())
        if path in pins:
            pin = pins[path]
            check('pin:' + path, sha(raw) == pin['sha256'] and len(raw) == pin['bytes'])
        files.append(dict(path=path, bytes=len(raw), sha256=sha(raw), git_blob=oid))
    check('indexed_bytes', sum(r['bytes'] for r in idx['files']) == idx['bytes'] == ready['indexed_bytes'] == 66561394)
    check('index_ready_sha', sha((BATCH/'EVIDENCE_INDEX.json').read_bytes()) == ready['evidence_index_sha256'])
    for earlier, later in [(CONTRACT, PRODUCT), (PRODUCT, HEAD)]:
        check('Git_ancestor:' + earlier + ':' + later, subprocess.run(['git','-C',str(WT),'merge-base','--is-ancestor',earlier,later]).returncode == 0)
    for name in ('CONTRACT.md','WORK_ORDER.json'):
        check('contract_precedes_product:' + name, git('show',CONTRACT+':'+PREFIX+'/'+name) == (BATCH/name).read_bytes())
    runtime_paths = [r['path'] for r in candidate['manifest']]
    check('137_runtime_manifest', len(runtime_paths) == len(set(runtime_paths)) == 137)
    product_blobs = blobs(PRODUCT, runtime_paths)
    contract_blobs = blobs(CONTRACT, runtime_paths)
    base_blobs = blobs(BASE, runtime_paths)
    baseline_manifest = read('INPUT_BINDINGS.json')['baseline_source_manifest']
    check('contract_baseline_runtime_unchanged', all(contract_blobs[p][1] == base_blobs[p][1] for p in runtime_paths))
    changed = [p for p in runtime_paths if product_blobs[p][1] != base_blobs[p][1]]
    check('three_product_changes', sorted(changed) == candidate['changed_files'])
    check('frozen_since_product_commit', git('diff','--name-only',PRODUCT,HEAD,'--',*runtime_paths).strip() == b'')
    installs = {'candidate': read('installation/READY.json'),
                'baseline': json.loads((WT/'verification/m4_local_relation_evidence_001/installation/READY.json').read_bytes())}
    install_checks = []
    for role, manifest, source_blobs in [('candidate',candidate['manifest'],product_blobs), ('baseline',baseline_manifest,base_blobs)]:
        install = installs[role]
        root = Path(install['install_root'])
        for row in manifest:
            raw = source_blobs[row['path']][1]
            check(role+'_Git_pin:'+row['path'], sha(raw) == row['sha256'])
            check(role+'_installed_pin:'+row['path'], (root/row['path']).read_bytes() == raw)
            if role == 'candidate':
                check('candidate_checkout_pin:'+row['path'], (WT/row['path']).read_bytes() == raw)
        constants = {}
        for node in ast.parse(source_blobs['human_eye_plugin/runtime_identity.py'][1]).body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'BASE_VERSION','IMPLEMENTATION_REVISION'} for t in node.targets):
                constants[node.targets[0].id] = ast.literal_eval(node.value)
        canonical = sha(json.dumps({'base_version':constants['BASE_VERSION'], 'implementation_revision':constants['IMPLEMENTATION_REVISION'],
                                    'files':manifest},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
        check(role+'_canonical', canonical == install['source_sha256'])
        check(role+'_installed_ready', install['source_count'] == 137 and install['no_default_activation'])
        install_checks.append(dict(role=role,source_sha256=canonical,source_count=len(manifest),root=str(root)))
    receipt=read('installation/run_01/receipt/ISOLATED_INSTALL.json')
    wheel=next(Path(receipt['bundle']).glob('*.whl'))
    check('candidate_wheel_sha',sha(wheel.read_bytes()) == installs['candidate']['wheel_sha256'] == receipt['wheel_sha256'])
    with zipfile.ZipFile(wheel) as z:
        for p in runtime_paths:
            check('wheel_runtime:'+p,z.read(p)==product_blobs[p][1])
        record=next(p for p in z.namelist() if p.endswith('.dist-info/RECORD'))
        record_rows=list(csv.reader(io.StringIO(z.read(record).decode())))
        for name,digest,size in record_rows:
            if digest:
                encoded='sha256='+base64.urlsafe_b64encode(hashlib.sha256(z.read(name)).digest()).decode().rstrip('=')
                check('wheel_RECORD:'+name, digest==encoded and int(size)==len(z.read(name)))
    check('install_protection_record',read('installation/run_01/PROTECTED_AFTER.json')['all_unchanged'] is True)
    bindings=read('entry/INPUT_BINDINGS.json')
    check('fixed_inputs',bindings==read('entry/run_01/FIXED_INPUTS.json'))
    check('153_pins',len(bindings['source_files_sha256'])==153)
    for path,digest in bindings['source_files_sha256'].items():
        check('entry_protected_pin:'+path,sha((WT/path).read_bytes())==digest)
    entry=read('entry/run_01/RESULTS.json')
    check('7_sessions_fixed_order',[s['case'] for s in entry['cases']]==bindings['sessions'] and len(entry['cases'])==7)
    analysis=read('analysis/run_02/RESULTS.json')
    analysis_sessions={s['case']['id']:s for s in analysis['sessions']}
    raw_rows=[]; sessions=[]; engineering=[]; schemas={}; rpc_total=0; close_count=0
    for case in entry['cases']:
        info=case['case']; caseid=info['id'];folder=BATCH/'entry/run_01'/caseid
        check('case_record:'+caseid,case==json.loads((folder/'RESULTS.json').read_bytes()))
        check('session_close:'+caseid,case['passed'] and not case['errors'] and case['product_close']['confirmed']
              and case['product_close']['exit_code']==0 and case['product_close']['process_reaped']
              and case['native_close']['exit_code']==0 and case['native_close']['process_reaped']
              and case['native_close']['source_file_unchanged'] and case['native_close']['protected_files_unchanged'])
        worker=[json.loads(line) for line in (folder/'native/WORKER_EVENTS.jsonl').read_text().splitlines()]
        check('raw_worker_events:'+caseid,worker==case['all_worker_events'])
        received=[v for v in worker if type(v.get('started_ns')) is int and type(v.get('sequence')) is int]
        rpc_total+=len(received)
        init=json.loads((folder/'ACTUAL_INITIALIZE.json').read_bytes())['result']['_meta']['human_eye']
        check('session_installed_identity:'+caseid,init['source_kind']=='installed_distribution' and init['source_file_count']==137
              and init['source_sha256']==installs[info['role']]['source_sha256'] and init['identity_check']['compatible'])
        tools=json.loads((folder/'ACTUAL_TOOLS.json').read_bytes())['result']['tools']
        schema={t['name']:len(compact(t)) for t in tools}
        check('schema:'+caseid,schema==case['tool_schema_compact_JSON_bytes'])
        schemas.setdefault(info['role'],[]).append(schema)
        by_label={}; assigned=[]
        author_rows={r['label']:r for r in analysis_sessions[caseid]['rows']}
        for row in case['rows']:
            label=row['label'];kind=row['kind']; start,end=row['started_ns'],row['ended_ns']
            elapsed=end-start
            check('entry_clock:'+caseid+'/'+label,row.get('entry_elapsed_ns',elapsed)==elapsed)
            matched=[e for e in received if start<=e['started_ns']<=end]
            check('RPC_mapping:'+caseid+'/'+label,matched==row['worker_received_events'] and len(matched)==row['worker_received_RPC_count'])
            assigned += [e['sequence'] for e in matched]
            item=dict(case_id=caseid,role=info['role'],transformed=info['transformed'],label=label,kind=kind,mode=row.get('mode'),
                      entry_elapsed_ns=elapsed,started_ns=start,ended_ns=end,worker_RPC=len(matched),
                      profile_scope_ns=sum(e.get('qa_work',{}).get('profile_scope_ns',0) for e in matched))
            if kind=='relation':
                response=json.loads((folder/(label+'.RESPONSE.json')).read_bytes()); text=response['result']['content'][0]['text']; body=json.loads(text)
                check('response:'+caseid+'/'+label,body==row['body'] and len(text.encode())==row['text_utf8_bytes'])
                trace=row['request_trace'];spans=trace['spans']
                item.update(body_bytes=len(text.encode()),geometry_bytes=len(compact(body['geometry'])) if 'geometry' in body else 0,
                            Peer_elapsed_ns=row['stdio']['elapsed_ns'],trace_duration_ns=trace['duration_ns'],
                            host_capture_inclusive_ns=sum(s['duration_ns'] for s in spans if s['name']=='host.capture' and s['outcome']=='completed'),
                            content_encode_inclusive_ns=sum(s['duration_ns'] for s in spans if s['name']=='mcp.content_encode' and s['outcome']=='completed'),
                            peak_rss=trace['peak_rss']['bytes'])
                check('source_in_response:'+caseid+'/'+label,body['context']['runtime_source_sha256']==installs[info['role']]['source_sha256'])
            elif kind=='native_supplement':
                text=row['receipt']['response']['result']['result']
                check('native_body:'+caseid+'/'+label,len(text.encode())==row['body_utf8_bytes'])
                item.update(body_bytes=len(text.encode()),oracle_retained=row['oracle_retained'])
            for key in ('entry_elapsed_ns','profile_scope_ns','Peer_elapsed_ns','trace_duration_ns','host_capture_inclusive_ns','content_encode_inclusive_ns'):
                if key in item:check('author_arithmetic:'+caseid+'/'+label+':'+key,item[key]==author_rows[label][key])
            if 'body_bytes' in item:check('author_body:'+caseid+'/'+label,item['body_bytes']==author_rows[label]['body_utf8_bytes'])
            by_label[label]=item;raw_rows.append(item)
        remaining=[e for e in received if e['sequence'] not in assigned]
        check('unique_assignment:'+caseid,len(assigned)==len(set(assigned)))
        check('one_close_RPC:'+caseid,len(remaining)==1)
        close_count+=len(remaining)
        default=[v for v in by_label.values() if re.fullmatch('warm_[0-9]+_OFF',v['label'])]
        sess=dict(case=info,session_wall_ns=case['session_wall_ns'],RPC=len(received),cold=by_label['cold'],
                  default=stats([v['entry_elapsed_ns'] for v in default]),
                  request_order=[r['label'] for r in case['rows']],default_rows=default,
                  peak_rss=max(v['peak_rss'] for v in by_label.values() if 'peak_rss' in v))
        sessions.append(sess)
        if not info['transformed']:
            for cycle in range(1,6):
                name='warm_'+str(cycle)+'_OFF';off=by_label.get(name+'_comparison',by_label[name]);native=by_label[name+'_supplement']
                check('sequential_pair:'+caseid+'/'+name,off['ended_ns']<=native['started_ns'])
                if info['role']=='candidate':
                    full=by_label['warm_'+str(cycle)+'_full']
                    engineering.append(dict(case_id=caseid,cycle=cycle,OFF_plus_native_ns=off['entry_elapsed_ns']+native['entry_elapsed_ns'],
                                            pair_window_ns=native['ended_ns']-off['started_ns'],FULL_ns=full['entry_elapsed_ns'],
                                            paired_delta_ns=full['entry_elapsed_ns']-off['entry_elapsed_ns']-native['entry_elapsed_ns'],
                                            OFF_plus_native_bytes=off['body_bytes']+native['body_bytes'],FULL_bytes=full['body_bytes'],
                                            OFF_plus_native_RPC=off['worker_RPC']+native['worker_RPC'],FULL_RPC=full['worker_RPC']))
    check('138_RPC',rpc_total==138 and close_count==7)
    counts={kind:sum(r['kind']==kind for r in raw_rows) for kind in ('relation','native_supplement','registered_QA_change')}
    check('row_counts',counts=={'relation':92,'native_supplement':38,'registered_QA_change':1})
    default={role:[r for r in raw_rows if r['role']==role and not r['transformed'] and re.fullmatch('warm_[0-9]+_OFF',r['label'])] for role in ('baseline','candidate')}
    default_stats={role:{key:stats([r[key] for r in rows]) for key in ('entry_elapsed_ns','Peer_elapsed_ns','trace_duration_ns','host_capture_inclusive_ns','profile_scope_ns','content_encode_inclusive_ns')} for role,rows in default.items()}
    delta=default_stats['candidate']['entry_elapsed_ns']['median']-default_stats['baseline']['entry_elapsed_ns']['median']
    percent=100*delta/default_stats['baseline']['entry_elapsed_ns']['median']
    check('default_10_20',len(default['baseline'])==10 and len(default['candidate'])==20)
    check('default_recomputed',delta==1341000 and abs(percent-ready['cost']['default_median_regression_percent'])<1e-12)
    for role in default_stats:
        for key,value in default_stats[role].items():check('default_distribution:'+role+':'+key,value==analysis['default_latency_review'][role][key])
    comparison={k:stats([r[k] for r in engineering]) for k in ('OFF_plus_native_ns','pair_window_ns','FULL_ns','paired_delta_ns','OFF_plus_native_bytes','FULL_bytes')}
    check('20_engineering_pairs',len(engineering)==20 and comparison['FULL_ns']['median']==38859900 and comparison['OFF_plus_native_ns']['median']==80870300)
    check('same_fields_RPC',all(r['FULL_RPC']==1 and r['OFF_plus_native_RPC']==2 for r in engineering))
    schema_sizes={role:items[0] for role,items in schemas.items()}
    check('within_version_schema',all(all(v==items[0] for v in items) for items in schemas.values()))
    check('relation_schema1150_1713',schema_sizes['baseline']['human_eye_spatial_relations']==1150 and schema_sizes['candidate']['human_eye_spatial_relations']==1713)
    check('nearest_schema961',all(v['human_eye_surface_nearest']==961 for v in schema_sizes.values()))
    body_sizes={mode:sorted({r['body_bytes'] for r in raw_rows if r['kind']=='relation' and not r['transformed']
                            and not r['label'].startswith('changed') and r['mode']==mode}) for mode in ('OFF','vertices','full')}
    check('body_sizes',body_sizes=={'OFF':[5361],'vertices':[8192],'full':[9015]})
    check('worktree_unchanged',before==git('status','--short').decode())
    output=dict(fixed_commit=HEAD,product_commit=PRODUCT,contract_commit=CONTRACT,files=files,ignored_bytecode_count=len(bytecode),
                installed=install_checks,changed_sources=changed,source_pin_count=153,RPC_total=rpc_total,row_counts=counts,
                sessions=sessions,rows=raw_rows,schema_sizes=schema_sizes,body_sizes=body_sizes,
                default_stats=default_stats,default_delta_ns=delta,default_percent=percent,engineering_pairs=engineering,engineering_summary=comparison,
                checks=checks,passed=all(v['passed'] for v in checks),failed=[v for v in checks if not v['passed']],
                not_run=['performance', 'product or prototype imports', 'Blender', 'models'],
                timing_scope='Saved instrumented engineering entry; session-level clustering and different preceding call sequences retained')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(passed=output['passed'],checks=len(checks),failed=output['failed'],files=len(files),RPC=rpc_total,
                          session_medians=[dict(case=s['case']['id'],median_ms=s['default']['median']/1e6,cold_ms=s['cold']['entry_elapsed_ns']/1e6) for s in sessions],
                          default_percent=percent,comparison=comparison,output=str(args.output)),ensure_ascii=False))
    return 0 if output['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
