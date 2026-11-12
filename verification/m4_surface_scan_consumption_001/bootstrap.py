"""Prepare frozen BASE and ordinary declarations without starting a consumer."""
import ast
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import secrets
import subprocess
import time
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
QUAL = ROOT/'verification/m4_surface_scan_001/qualification'
QUAL_COMMIT = '96fce78b98cb749885792112e039a406744d282b'
PRODUCT = 'c1cb2da32034e056a270384e691a2cde8dddbc0d'
DELIVERY = '860b87138d40de9cc08b01c947dd864d58da9295'
SOURCE = 'c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def save(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')


def git_bytes(commit,path):
    return subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT)


def native_schema(path):
    tree = ast.parse(path.read_bytes())
    return ast.literal_eval(next(node.value for node in tree.body if isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Name) and target.id == 'NATIVE' for target in node.targets)))


def main():
    started = time.perf_counter_ns()
    assert not (HERE/'STARTED.json').exists() and not (HERE/'PLAN.json').exists()
    assert sha(HERE/'ROOT_PLAN.md') == '8c2baa7394f12d003291dbc643aa1c5ed6aba38e6215240d4e1f0148943f1989'
    ready_path = HERE/'installations/P_READY.json'
    ready = read(ready_path)
    original_ready = ROOT/'verification/m4_surface_scan_001_opt1/installation/run_01/READY.json'
    assert ready_path.read_bytes() == original_ready.read_bytes() == git_bytes(DELIVERY,original_ready.relative_to(ROOT).as_posix())
    assert ready['commit'] == PRODUCT and ready['source_sha256'] == SOURCE and ready['source_count'] == 138
    candidate_path = ROOT/'verification/m4_surface_scan_001_opt1/CANDIDATE_SOURCE.json'
    committed_candidate = git_bytes(PRODUCT,candidate_path.relative_to(ROOT).as_posix())
    assert candidate_path.read_bytes() == committed_candidate
    identity = json.loads(committed_candidate)['identity']
    manifest = identity['source_files']
    assert manifest == read(Path(ready['fixed_inputs']))['manifest'] and len(manifest) == 138
    canonical = json.dumps(dict(base_version=identity['base_version'],
        implementation_revision=identity['implementation_revision'],files=manifest),
        sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
    assert hashlib.sha256(canonical).hexdigest() == SOURCE
    refs = ''.join(PRODUCT+':'+row['path']+'\n' for row in manifest).encode()
    blobs = io.BytesIO(subprocess.run(['git','cat-file','--batch'],input=refs,cwd=ROOT,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout)
    wheel_path = next(Path(ready['fixed_inputs']).parent.glob('bundle/*.whl'))
    assert sha(wheel_path) == ready['wheel_sha256']
    with zipfile.ZipFile(wheel_path) as wheel:
        for row in manifest:
            header = blobs.readline().split()
            assert len(header) == 3 and header[1] == b'blob'
            raw = blobs.read(int(header[2]))
            assert blobs.read(1) == b'\n' and hashlib.sha256(raw).hexdigest() == row['sha256']
            assert (ROOT/row['path']).read_bytes() == (Path(ready['install_root'])/row['path']).read_bytes() == wheel.read(row['path']) == raw
    assert blobs.read() == b''
    assert sha(Path(ready['entry'])) == ready['launcher_sha256']
    assert sha(Path(ready['release'])/'admin/RUNTIME_BINDING.json') == ready['binding_sha256']

    qualification_path = QUAL/'QUALIFICATION_READY.json'
    qualification = git_bytes(QUAL_COMMIT,qualification_path.relative_to(ROOT).as_posix())
    assert qualification_path.read_bytes() == qualification
    promised = json.loads(qualification)
    names = {'asset':'assembly.blend','base_snapshot':'BASE_SNAPSHOT.json','edit_snapshot':'EDIT_SNAPSHOT.json',
        'base_truth':'BASE_TRUTH.json','edit_truth':'EDIT_TRUTH.json','geometry_freeze':'GEOMETRY_FREEZE.json',
        'control_certificates':'CONTROL_CERTIFICATES.json'}
    checked = {str(QUAL/name):promised[key+'_sha256'] for key,name in names.items()}
    worker = QUAL.parent/'worker'
    checked[str(worker/'pose_native.py')] = promised['pose_helper_sha256']
    checked[str(worker/'POSE_PATCH.json')] = promised['pose_patch_sha256']
    assert all(sha(Path(path)) == digest for path,digest in checked.items())
    qmanifest_path = QUAL/'SOURCE_OUTPUT_MANIFEST.json'
    qmanifest = git_bytes(QUAL_COMMIT,qmanifest_path.relative_to(ROOT).as_posix())
    assert qmanifest_path.read_bytes() == qmanifest
    for row in json.loads(qmanifest)['files']:
        path = QUAL.parent/row['path']
        assert sha(path) == row['sha256'] and path.stat().st_size == row['bytes']
    assert sha(HERE/'input/scene.blend') == promised['asset_sha256']
    prompt = next(line[2:] for line in (HERE/'ROOT_PLAN.md').read_text(encoding='utf8').splitlines() if line.startswith('> 检查'))
    assert (HERE/'input/PROMPT.txt').read_bytes() == (prompt+'\n').encode('utf8')

    native_path = ROOT/'verification/native_plugin_complex_003/actor.py'
    native = native_schema(native_path)
    tools_path = ROOT/'verification/m4_surface_scan_001_opt1/engineering/run_01/pair_01/B/TOOLS.json'
    assert tools_path.read_bytes() == git_bytes(DELIVERY,tools_path.relative_to(ROOT).as_posix())
    observe = [tool for tool in read(tools_path)['result']['tools'] if tool['name'] == 'human_eye_scene_observe']
    assert len(observe) == 1
    for name,value in [('COMMON_NATIVE.json',native),('P_PUBLIC_TOOLS.json',observe),
        ('N_CONSUMER_TOOLS.json',[native]),('P_CONSUMER_TOOLS.json',[native,observe[0]])]:
        save(HERE/'schemas'/name,value)
    sequence = read(HERE/'SEQUENCE.json')['sequence']
    assert [row['cell'] for row in sequence] == ['N1','P1','P2','N2','N3','P3']
    save(HERE/'private/ANON_MAP.json',dict(created_before_consumers=True,
        labels_scope='private mapping; publish anonymous_id only',
        rows=[dict(row,anonymous_id='answer_'+secrets.token_hex(8)) for row in sequence]))
    save(HERE/'QUALIFICATION_SEAL.json',dict(qualification_commit=QUAL_COMMIT,
        qualification_ready_sha256=hashlib.sha256(qualification).hexdigest(),
        existing_promises=checked,qualification_files_verified=len(json.loads(qmanifest)['files']),
        product_commit=PRODUCT,product_source_sha256=SOURCE,product_sources_verified=138,
        root_opt1_review_manifest_sha256=sha(HERE/'preflight/ADMIN_REVIEW_MANIFEST.json'),
        model_consumers=0,Blender_sessions=0,live_product_processes=0))
    protected = {str(path):sha(path) for path in [ROOT/'pyproject.toml',
        Path('C:/Users/Administrator/.codex/config.toml'),Path('D:/hefe/.codex/config.toml')]}
    protected.update(checked)
    protected[str(qmanifest_path)] = hashlib.sha256(qmanifest).hexdigest()
    for row in json.loads(qmanifest)['files']:
        protected[str(QUAL.parent/row['path'])] = row['sha256']
    save(HERE/'preflight/PROTECTED_BEFORE.json',protected)
    save(HERE/'preflight/SOURCE_BINDING.json',dict(source_count=138,source_sha256=SOURCE,
        source_manifest=manifest,installation_ready_sha256=sha(ready_path),
        actual_asset_copy=str(QUAL/'assembly.blend'),asset_sha256=promised['asset_sha256'],
        snapshot_sha256=promised['base_snapshot_sha256'],truth_sha256=promised['base_truth_sha256'],
        qualification_seal_sha256=sha(HERE/'QUALIFICATION_SEAL.json'),
        previous_actual_tools_list=str(tools_path),previous_actual_tools_list_sha256=sha(tools_path),
        common_native_source=str(native_path),common_native_source_sha256=sha(native_path),
        common_native_schema_unchanged=True,observe_declaration_unchanged=True,
        commit_wheel_install_checkout_equal=True,installation_rebuilt=False,
        models=0,Blender_sessions=0,live_product_processes=0))
    save(HERE/'preflight/BOOTSTRAP_RECEIPT.json',dict(recorded_utc=datetime.now(timezone.utc).isoformat(),
        elapsed_ns=time.perf_counter_ns()-started,models=0,Blender_sessions=0,product_pretests=0,
        qualification_promises_verified=9,qualification_files_verified=len(json.loads(qmanifest)['files']),
        runtime_sources_verified=138,ordinary_observe_tools=len(observe)))
    print(json.dumps(dict(prepared_input=True,source_count=138,model_consumers=0,Blender_sessions=0)))


if __name__ == '__main__':
    main()
