"""Offline source, packet, protocol and retained evidence verification."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[3]
PIN = 'fb5a4485c935512c1521b160c55e6034a30ae8177e2662b6a132fec5d85a4509'
BASELINE = 'c3b93d34d1cbdc370b3630d540490b79093b3d82'


def read(path):
    return json.loads(path.read_text('utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    (HERE/name).write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf8')


source = read(HERE/'SOURCE_CHECK.json')
identity = source['identity']
assert identity['source_sha256'] == PIN and identity['source_kind'] == 'installed_distribution'
manifest = {row['path']: row['sha256'] for row in identity['source_files']}
assert len(manifest) == 131
roots = {}
for label, root in (('checkout', REPO), ('installed_B', Path(source['purelib']))):
    names = {name for name in manifest if '/' not in name}
    for package in ('human_eye_plugin','human_eye_module1_operators'):
        names.update(package+'/'+path.name for path in (root/package).glob('*.py'))
    actual = {name:sha(root/name) for name in sorted(names)}
    assert actual == manifest
    payload = dict(base_version=identity['base_version'], implementation_revision=identity['implementation_revision'],
                   files=[dict(path=name,sha256=digest) for name,digest in actual.items()])
    digest = hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    assert digest == PIN
    roots[label] = dict(source_count=len(actual),source_sha256=digest,mismatches=[])
raw = subprocess.run(['git','cat-file','--batch'],cwd=REPO,
    input=''.join(BASELINE+':'+name+'\n' for name in manifest).encode(),stdout=subprocess.PIPE,check=True).stdout
stream = io.BytesIO(raw)
for name,digest in manifest.items():
    header=stream.readline().split()
    assert len(header)==3 and header[1]==b'blob'
    content=stream.read(int(header[2]))
    assert stream.read(1)==b'\n' and hashlib.sha256(content).hexdigest()==digest
assert not stream.read()
assert not subprocess.check_output(['git','diff','--name-only',BASELINE,'--','human_eye_plugin',
    'human_eye_module1_operators',*[name for name in manifest if '/' not in name]],cwd=REPO,text=True).strip()
helpers = read(REPO/'verification/fixes/surface_facts_001/engineering_b/QA_COPIES.json')
for record in helpers:
    assert sha(Path(record['target'])) == record['sha256']
save('FINAL_SOURCE_CHECK.json',dict(checked_utc=datetime.now(timezone.utc).isoformat(),
    baseline_head=BASELINE,source_sha256=PIN,source_count=131,roots=roots,
    accepted_Git_131_blobs_equal=True,product_diff_empty=True,installed_helpers_unchanged=len(helpers),
    product_builds=0,installs=0,geometry_route_remains_closed=True))

bindings = read(HERE/'dispatch/BINDINGS.json')['bindings']
usage = read(HERE/'audit/MODEL_USAGE.json')
cost = read(HERE/'audit/COSTS.json')
models = {row['binding']['answer_id']:row for row in usage['consumers']}
summary = read(HERE/'analysis/SUMMARY.json')
assert len(bindings)==len(models)==len(cost['chains'])==8 and not usage['issues']
assert summary['public_finals']==8 and summary['within_dispatch_budget']==6 and summary['late']==2
assert sum(row['model_usage']['within_answer_budget'] for row in models.values())==6
settings=set()
for row in bindings:
    assert row['status']=='closed_completed'
    model=models[row['answer_id']]['model_usage']
    assert model['completed_turn_count']==1 and model['usage_complete_from_observed_counters']
    for turn in model['turns']:
        for context in turn['contexts']:
            settings.add((context['model'],context['effort'],context['collaboration_model'],context['collaboration_effort']))
    exact=HERE/'answers_private'/(row['chain_id']+'.txt')
    assert sha(exact)==models[row['answer_id']]['public_final_sha256']
    packet=HERE/'public/answers'/(row['answer_id']+'.txt')
    prefix='【晚于期限的公开回答，未计期限内完成】\n\n'.encode('utf8') if not model['within_answer_budget'] else b''
    assert packet.read_bytes()==prefix+exact.read_bytes()
    assert sha(Path(row['prompt_path']))==row['prompt_sha256']
    assert sha(HERE/'runs'/row['chain_id']/'input.blend')==sha(HERE/'author'/row['case']/'scene.blend')
assert settings=={('gpt-6.1-sol','ultra','gpt-6.1-sol','ultra')}
cleanup=read(HERE/'CLEANUP.json')
assert cleanup['session_count']==10 and cleanup['bad_close_receipt_count']==cleanup['possibly_owned_count']==0
assert not cleanup['matching_live_processes']
qualification=read(HERE/'QUALIFICATION.json')
assert qualification['passed'] and qualification['observe_count']==qualification['raw_readback_count']==2
assert qualification['qa_update_count']==0 and len(qualification['cases'])==2
for record in read(HERE/'ASSET_BUILD_MANIFEST.json')['cases']:
    author=HERE/'author'/record['case']
    for filename,key in (('scene.blend','scene_sha256'),('EXPECTED_GEOMETRY.json','expected_geometry_sha256'),
                         ('TRUTH.json','truth_sha256'),('BUILD_READBACK.json','build_readback_sha256')):
        assert sha(author/filename)==record[key]
assert (HERE/'RESULTS.md').is_file() and (HERE/'public/ANSWERS.md').is_file()
files=[]
for path in sorted(HERE.rglob('*')):
    if not path.is_file():continue
    relative=path.relative_to(HERE)
    if '__pycache__' in relative.parts or path.suffix in ('.lock','.pyc','.pyo'):continue
    if path.name in ('input.blend','EVIDENCE_INDEX.json'):continue
    files.append(dict(path=relative.as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
save('EVIDENCE_INDEX.json',dict(sealed_utc=datetime.now(timezone.utc).isoformat(),source_sha256=PIN,source_count=131,
    baseline_product_head=BASELINE,scope='new QA/evidence only; no raw rollouts or hidden reasoning; excludes locks, bytecode and duplicate input.blend copies',
    public_answer_package='public/ANSWERS.md',public_truth='public/QUESTIONS_AND_TRUTH.json',
    separate_condition_map='analysis/CONDITION_MAP.json',separate_author_score='analysis/AUTHOR_SCORE.json',
    separate_costs='audit/COSTS.json',files=files))
print(json.dumps(dict(source_sha256=PIN,source_count=131,retained_files=len(files),
    public_finals=8,within_dispatch_budget=6,late=2,closed_sessions=10,product_changes=0)))
