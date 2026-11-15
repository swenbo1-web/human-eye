"""Independent historical identity confirmation; no product or performance execution."""
import ast
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path('D:/hefe')
OUT = Path(__file__).resolve().parent
B = ROOT/'verification/fixes/20261106_perf020_o4'
OLD = ROOT/'verification/fixes/20261106_perf020_o4_independent'
COMMITS = {
    'E':'11c8fc7332e530ead2f8fa30d2a35c7eb14e7d15',
    'F':'b644c79430ced0c710dc9c8c27b2c72598dfe63f',
    'restore':'9fc576a5216176b459586ce95a4f9e34a313da20',
    'M4_base':'03eb4e2971891dfe0160972cbcf974e3dcf1a21c',
    'M4_candidate':'691f7b78ed89ccf30df47847fc1e99ad51a1dc64',
}
checks, inputs = [], {}
def sha(raw): return hashlib.sha256(raw).hexdigest()
def raw(path):
    path=Path(path); data=path.read_bytes(); inputs[str(path)]={'sha256':sha(data),'bytes':len(data)}; return data
def js(path): return json.loads(raw(path))
def ck(name, passed, **evidence): checks.append(dict(name=name,passed=bool(passed),**evidence))
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)
def snapshot(commit):
    const={}
    for node in ast.parse(git('show',commit+':human_eye_plugin/runtime_identity.py').decode()).body:
        if isinstance(node,ast.Assign):
            for t in node.targets:
                if isinstance(t,ast.Name) and t.id in ('_ROOT_MODULES','BASE_VERSION','IMPLEMENTATION_REVISION'):
                    const[t.id]=ast.literal_eval(node.value)
    paths=list(const['_ROOT_MODULES'])+[p for p in git('ls-tree','-r','--name-only',commit,'--','human_eye_plugin','human_eye_module1_operators').decode().splitlines() if p.count('/')==1 and p.endswith('.py')]
    with tarfile.open(fileobj=io.BytesIO(git('archive',commit,'--',*paths))) as tar:
        blobs={p:tar.extractfile(p).read() for p in sorted(paths)}
    identity=dict(base_version=const['BASE_VERSION'],implementation_revision=const['IMPLEMENTATION_REVISION'],files=[dict(path=p,sha256=sha(b)) for p,b in blobs.items()])
    return blobs,sha(json.dumps(identity,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())

snaps={k:snapshot(v) for k,v in COMMITS.items()}
for label,digest in [('E','e59048677b7cc05ac0f15b359e5444de2cc3ccc196994a701e74a2510f144163'),('F','30b28aab341dcec6d7504a95a15089acda506af0a0c11bd14ffd6644ecdb258d'),('restore','e59048677b7cc05ac0f15b359e5444de2cc3ccc196994a701e74a2510f144163')]:
    ck(label+' Git130 identity',len(snaps[label][0])==130 and snaps[label][1]==digest)
ck('historical restoration exactly E',snaps['E'][0]==snaps['restore'][0])
relations={}
for current in ('M4_base','M4_candidate'):
    row={}
    for past in ('E','F','restore','M4_base'):
        result=subprocess.run(['git','merge-base','--is-ancestor',COMMITS[past],COMMITS[current]],cwd=ROOT)
        if result.returncode not in (0,1): raise RuntimeError('git merge-base failed')
        row[past]=result.returncode==0
    row['merge_base_with_restore']=git('merge-base',COMMITS['restore'],COMMITS[current]).decode().strip()
    relations[current]=row
    ck(current+' history separate',row['E'] and row['M4_base'] and not row['F'] and not row['restore'] and row['merge_base_with_restore']==COMMITS['E'])

pins={
    ROOT/'docs/PERF020_O4_RESIDENT_TASK_HOST_ACCEPTANCE.md':'1b1f4c831ebefb4f965c532728b169a983d81fde4c8c41f0776ddfe97434ccb4',
    B/'FINAL_MANIFEST.json':'989430e862f750342463b71931a5505a78ffbdda41e3846a6bbb88a57e0731a2',
    B/'cost/formal_01/FREEZE.json':'0d81a37e894f4902407a20c71c6b9c12d6c05c9aa7ff23a5f3e3aa8b5bae354f',
    B/'cost/formal_01/SUMMARY.json':'4def42eca7c0ee521600487f4d912b7af6d8ea0e8b24ac9c3a890cb4502840f0',
    OLD/'REVIEW.md':'aa7ef72e5795b08aa0ac0ff893bd390ebf253fd34b29b98ab6a2b9f54f7ba6be',
    ROOT/'verification/fixes/20261109_f_history_confirmation/REVIEW.md':'77a9171ed0d071c8f13604dab5fbbf693ccaf40438b823521d3140c4b31871af',
}
for p,h in pins.items(): ck('historical pin '+str(p),sha(raw(p))==h)
old_manifest=js(OLD/'MANIFEST.json')
for row in old_manifest['files']:
    if row['path'] in ('INTEGRITY.json','REVIEW.md','verify_identity.py','code/STATIC_REVIEW.json'):
        b=raw(OLD/row['path']); ck('prior independent audit '+row['path'],len(b)==row['bytes'] and sha(b)==row['sha256'])
ck('prior closed disposition',old_manifest['disposition']=='F_not_admitted_E_restoration_verified')
integrity=js(OLD/'INTEGRITY.json')
ck('prior audit remains complete within original scope',integrity['mismatches']==[] and integrity['sealed_files']==1327 and integrity['active130_exact_E'])
sealed={row['path']:row for row in js(B/'FINAL_MANIFEST.json')['files']}
entry_path=B/'environment/candidate/ENTRY.json'
entry=js(entry_path)
ck('F ENTRY sealed pin',sha(raw(entry_path))==sealed['environment/candidate/ENTRY.json']['sha256'])
ck('F ENTRY Git identity',entry['commit']==COMMITS['F'] and entry['source_sha256']==snaps['F'][1] and entry['source_file_count']==130)
for key in ('wheel','entry','admin','binding','dependencies'):
    ck('F retained '+key+' pin',sha(raw(entry[key+'_path']))==entry[key+'_sha256'])
for name,key in [('SOURCE_INTEGRITY.json','source_integrity_sha256'),('INSTALL_METADATA.json','install_metadata_sha256')]:
    ck('F retained '+name,sha(raw(entry_path.parent/name))==entry[key])
binding=js(entry['binding_path'])
ck('F binding all130 equals Git',binding['source_files']==[dict(path=p,sha256=sha(b)) for p,b in snaps['F'][0].items()])
changed=[p for p in snaps['E'][0] if snaps['E'][0][p]!=snaps['F'][0][p]]
ck('E/F changed only original2 files',set(changed)=={'human_eye_plugin/blender_mcp_host.py','human_eye_plugin/runtime_identity.py'})
for name in changed:
    ck('retained F install key '+name,raw(Path(entry['runtime_path'])/name)==snaps['F'][0][name])
raw(ROOT/'verification/fixes/20261114_f_history_duplicate/REVIEW.md')
raw(ROOT/'verification/fixes/20261107_f_recheck/REVIEW.md')
result={
    'scope':'Historical duplicate identity confirmation only; no current deployment assertion',
    'passed':all(c['passed'] for c in checks),'check_count':len(checks),'checks':checks,
    'identities':{k:dict(commit=COMMITS[k],count=len(b),source_sha256=d) for k,(b,d) in snaps.items()},
    'ancestry':relations,'input_pins':inputs,
    'new_product_Blender_model_config_calls':0,'full_historical_1327_matrix_rerun':False,
    'current_default_install_or_desktop_examined':False,
    'historical_install_scope':'F wheel full file hash; admin/binding/dependency records; two changed installed source files only; previous 130-source/full-wheel/install matrix remains historical evidence',
    'decision':'Already closed PERF-020-O4/F duplicate; keep F unadmitted. Historical E restoration is complete, never apply it over present M4.',
    'AL':{'parent_requested_task':'4354fcdd-72ef-4fe5-b564-c3056863fed2','parent_write_version':718,
          'child_assignment':'e5d54595-8858-4234-ab59-509afd896bad','assignment_current':False,
          'assignment_task':'cd683dda-67f4-4252-aa0f-83be9a1e9627','note':'Root followup explicitly authorized this read-only historical review; no parent task write or assertion of child rebinding.'},
}
dest=OUT/'RESULT.json'
if dest.exists(): raise RuntimeError('refuse overwriting prior review')
dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'passed':result['passed'],'checks':len(checks),'identities':result['identities'],'ancestry':relations,'failed':[c for c in checks if not c['passed']],'result':str(dest)},ensure_ascii=False))
