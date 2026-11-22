"""Freeze the replay and build exactly one isolated shared-normalization candidate."""

import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from subprocess import check_output, run
import sys
import time
import tomllib
from zipfile import ZIP_DEFLATED, ZipFile


NS = Path(__file__).resolve().parent
V = NS.parent
REPO = V.parent
ROOT = Path('D:/he_m2_source_region_shared_normalization_001')
BASE = '31e9b46a68e5f791df9a75a1bad11caa8a6e8410'
PLAN = '165874d50272f3956bc2a34f1e9748f3d318fca3:docs/M2_SOURCE_REGION_SHARED_NORMALIZATION_001_PLAN.md'
BASE_BINDING = V/'m2_source_region_normalization_triangle_list_001/install/PRODUCT_RUN_BINDING.json'
MAIN = 'c5f987efafc5af3607497307baf0b6ccd30f23f5'
MAIN_ARCHIVE = Path('D:/he_m2_source_region_normalization_triangle_list_001/sealed/ORIGINAL_RUNTIME.zip')
MAIN_ARCHIVE_SHA = '306219f44244e4d6d58cd83992a4e1a035369021382a45815e84f070ae4d316b'
DUAL_ORIGIN = 'eeae0719aa49896c84d4f48e97f86585159f6a37'
HOLDOUT = '721ed392'
RECTANGLE = 'c18b7bdc'
PYTHON = Path('D:/he_anchor_001/venv/Scripts/python.exe')
BUILDER = V/'build_candidate_release.py'
BLOBS = V/'m4_cross_scale_local_first_view_001/install/build_install.py'
DATA = ('human_eye_plugin/plugin.json','human_eye_plugin/mcp_config.json')
DELTA = ('human_eye_plugin/live_service.py','human_eye_plugin/source_region.py')
SCHEDULE = (
    ('N1','dual',False),('P1','dual',False),('P2','dual',False),('N2','dual',False),
    ('N3','dual',False),('P3','dual',False),('IN','main',False),('IP','main',False),
    ('PN','paired_image',False),('PP','paired_image',False),
    ('HN','holdout',False),('HP','holdout',False),('RN','rectangle',False),('RP','rectangle',False),
    ('CN','main',True),('CP','main',True),('FN','defaults',True),('FP','defaults',True),
    ('EN','bad_edge',False),('EP','bad_edge',False),
)
BASE_LABELS = ('N1','N2','N3','IN','PN','HN','RN','CN','FN','EN')
TIMED_LABELS = tuple(arm[0] for arm in SCHEDULE[:6])
HOT_SCHEDULE = ('HA1','HB1','HB2','HA2')


def git(*args):
    return check_output(['git','-C',str(REPO),*args])


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8',newline='\n') as stream:
        stream.write(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def digest(data):
    return {'bytes':len(data),'sha256':sha256(data).hexdigest()}


def pin(path):
    path = Path(path).resolve(strict=True)
    return {'path':str(path),**digest(path.read_bytes())}


def require(ok,reason):
    if not ok:
        raise ValueError(reason)


def freeze(candidate,reports):
    require(not (ROOT/'candidate_install').exists() and not (NS/'FROZEN.json').exists()
            and not (ROOT/'arms').exists(),'once_only_freeze_before_build_and_formal_slots')
    require((NS/'PLAN.md').read_bytes()==git('show',PLAN),'fixed_planning_commit_changed')
    require(git('rev-list','--parents','-n','1',candidate).decode().split()==[candidate,BASE]
            and tuple(git('diff','--name-only',BASE,candidate).decode().splitlines())==DELTA,
            'sole_direct_source_region_normalization_share_required')
    paths = {}

    def capture(path,expected=None):
        record = pin(path)
        require(expected is None or all(record[k]==expected[k] for k in ('bytes','sha256')),
                'new_replay_source_does_not_match_fixed_evidence/'+record['path'])
        paths[record['path']] = record
        return record

    public_index = V/'m2_source_region_normalization_triangle_list_001/RESULT.json'
    require(public_index.read_bytes()==git('show',MAIN+':'+public_index.relative_to(REPO).as_posix()),
            'archived_Yanyite_identity_changed')
    published = read(public_index)['raw_evidence_local']
    source_index = MAIN_ARCHIVE.with_name('RAW_INDEX.json')
    indexed = read(source_index)
    require(capture(MAIN_ARCHIVE,published['archive'])['sha256']==MAIN_ARCHIVE_SHA==indexed['archive']['sha256'],
            'fixed_main_raw_archive_changed')
    with ZipFile(MAIN_ARCHIVE) as archive:
        for name in ('runtime/arms/P1/CAPTURE_01.json','runtime/arms/P1/CAPTURE_02.json',
                     'runtime/arms/P1/product_full/call_001/SERVICE_RESULT.json',
                     'runtime/arms/P1/mcp/rpc_04/TX.bin','runtime/arms/P1/mcp/rpc_04/RX.bin',
                     'runtime/arms/DP/CAPTURE_01.json','runtime/arms/DP/CAPTURE_02.json',
                     'runtime/arms/DP/mcp/rpc_04/TX.bin','runtime/arms/DP/mcp/rpc_05/TX.bin',
                     'runtime/arms/DP/product_full/call_001/SERVICE_RESULT.json',
                     'runtime/arms/DP/product_full/call_002/SERVICE_RESULT.json'):
            require(digest(archive.read(name))==indexed['members'][name],'primary_original_changed/'+name)
        main_observation = json.loads(archive.read('runtime/arms/P1/product_full/call_001/SERVICE_RESULT.json'))
        require(len(main_observation['region_ref']['source_triangle_indices'])==311
                and main_observation['frames'][0]['PNG_bytes']==16975,'primary_source_region_or_png_changed')
    binding = read(BASE_BINDING)
    require(binding['preparation_git']==BASE and len(binding['source_manifest'])==143
            and binding['source_sha256']=='6aaa60003ebbb8d689b8d9858a74a247c6d4f0de13bacac0d5dcead019555d70'
            and binding['wheel_sha256']=='4724ff9f97cd8eb108b38396fa5ea3a12c3daf0fa960dc62eedcfe10e8f34e14',
            'expected_existing_fixed_baseline')
    require(capture(binding['wheel_path'])['sha256']==binding['wheel_sha256'],'fixed_baseline_wheel_changed')
    for row in binding['source_manifest']:
        require(capture(Path(binding['install_root'])/row['path'])['sha256']==row['sha256'],
                'baseline_installed_module_changed/'+row['path'])
    require(len(reports)>=2,'independent_geometry_and_actual_stdio_preflight_required')
    for path in (public_index,source_index,BASE_BINDING,BUILDER,BLOBS,PYTHON,Path(sys.executable),*reports):
        capture(path)
    for path in (V/'m2_source_region_normalization_triangle_list_001/score.py',
                 V/'m2_source_region_normalization_triangle_list_001/checks/default_stdio.py',
                 V/'m4_source_region_nonplanar_short_circuit_001/score.py',
                 V/'m4_source_region_nonplanar_short_circuit_001/qualification.py',
                 V/'m4_local_coverage_object_bounds_001/checks/replay.py',
                 V/'m4_local_coverage_object_bounds_001/checks/fixture.py',
                 V/'m1_region_task_first_packet_consumption_holdout_001/checks/evidence.py',
                 V/'m4_cross_scale_live_qualification_001/checks/delivery.py',
                 V/'m5_global_observe_measure_qualification_001/checks/live_wire.py'):
        capture(path)
    for report in reports:
        proof=read(report)
        require(proof['passed'] is True,'prebuild_admission_rejected/'+str(report))
        for original in proof.get('source_pins',[]):
            capture(original['path'],original)
    for path in NS.rglob('*'):
        if path.is_file():
            require(path.suffix!='.pyc','unexpected_binary_cache_in_frozen_scope')
            if path.suffix=='.py':
                ast.parse(path.read_bytes(),filename=str(path))
            capture(path)
    result = {
        'plan':PLAN,'baseline_git':BASE,'candidate_git':candidate,'changed_runtime_sources':list(DELTA),
        'sources':{'main':MAIN,'dual_original':DUAL_ORIGIN,
                   'holdout':git('rev-parse',HOLDOUT).decode().strip(),'rectangle':git('rev-parse',RECTANGLE).decode().strip()},
        'schedule':[list(arm) for arm in SCHEDULE],'timed_pairs':[['N1','P1'],['N2','P2'],['N3','P3']],
        'gate':{'second_prepare_paired_median_reduction':0.80,'second_service_paired_median_reduction':0.50,
                'sum_service_paired_median_reduction':0.20},
        'hot_diagnostic':{'schedule':list(HOT_SCHEDULE),'warm_per_process':10,'GC_builtin_configuration_unchanged':True},
        'candidate_wheels':1,'candidate_installs':1,'new_Blender':0,'new_models':0,'replacements':0,
        'source_inputs':[paths[path] for path in sorted(paths)],
    }
    write(NS/'FROZEN.json',result)
    print('Frozen',pin(NS/'FROZEN.json')['sha256'],len(paths),'sources',flush=True)


def verified_freeze():
    f = read(NS/'FROZEN.json')
    require(f['baseline_git']==BASE and all(pin(row['path'])==row for row in f['source_inputs']),
            'frozen_candidate_source_or_replay_input_changed')
    return f


def build():
    require(sys.flags.isolated and sys.dont_write_bytecode and Path(sys.executable).resolve()==PYTHON.resolve(),
            'only_pinned_isolated_installer')
    f = verified_freeze()
    selected = f['candidate_git']
    start = time.perf_counter_ns()
    binding = read(BASE_BINDING)
    names = [row['path'] for row in binding['source_manifest']]
    files = [*names,*DATA,'pyproject.toml']
    blobs = run_path(str(BLOBS))['git_blobs']
    before, after = blobs(BASE,files),blobs(selected,files)
    require(tuple(name for name in files if before[name]!=after[name])==DELTA,
            'candidate_product_binary_scope_changed')
    helper = run_path(str(BUILDER))
    old_wheel = Path(binding['wheel_path'])
    helper['verify_wheel'](old_wheel.read_bytes())
    with ZipFile(old_wheel) as pack:
        require(all(pack.read(name)==before[name]==(Path(binding['install_root'])/name).read_bytes()
                    for name in [*names,*DATA]),'base_Git_wheel_runtime_identity_mismatch')
    root = ROOT/'candidate_install'
    root.mkdir(parents=True,exist_ok=False)
    staging = root/'git_source'
    for name,raw in after.items():
        target = staging/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
    manifest = [{'path':name,'sha256':digest(after[name])['sha256']} for name in names]
    version = '9.7.2+m2.source.region.shared.normalization.001'
    wheel_name, raw = helper['wheel_bytes'](
        staging,manifest,tomllib.loads(after['pyproject.toml'].decode())['project'],version)
    wheel = root/wheel_name
    wheel.write_bytes(raw)
    verified = helper['verify_wheel'](raw)
    installed = root/'product'
    command = [str(PYTHON),'-IB','-m','pip','--isolated','--disable-pip-version-check','install','--no-index',
               '--no-deps','--no-compile','--target',str(installed),str(wheel)]
    result = run(command,capture_output=True,timeout=90)
    (root/'PIP_STDOUT.bin').write_bytes(result.stdout)
    (root/'PIP_STDERR.bin').write_bytes(result.stderr)
    result.check_returncode()
    with ZipFile(wheel) as pack:
        require(sorted(name for name in pack.namelist() if name.endswith('.py'))==names
                and all(pack.read(name)==(installed/name).read_bytes()
                        for name in pack.namelist() if not name.endswith('/RECORD')),
                'candidate_installed_file_bytes_mismatch')
    require(sorted(path.relative_to(installed).as_posix() for path in installed.rglob('*.py'))==names,
            'unexpected_candidate_runtime_file_set')
    identity = {k:binding[k] for k in ('base_version','implementation_revision')}
    source_hash = digest(json.dumps({**identity,'files':manifest},sort_keys=True,separators=(',',':')).encode())['sha256']
    result = {**identity,'build_id':'sha256:'+source_hash,'source_sha256':source_hash,'source_manifest':manifest,
              'distribution_version':version,'install_root':str(installed),'dependency_root':binding['dependency_root'],
              'preparation_git':selected,'protocol_version':binding['protocol_version'],'wheel_path':str(wheel),
              'wheel_sha256':digest(raw)['sha256'],'historical_preparation_git':BASE,
              'historical_source_sha256':binding['source_sha256'],'changed_product_sources':list(DELTA),
              'unchanged_product_sources':143-len(DELTA)}
    write(NS/'install/PRODUCT_RUN_BINDING.json',result)
    write(NS/'install/BUILD_INSTALL.json',{
        'passed':True,'binding':result,'baseline_verified_sources':len(names),'wheel_RECORD':verified,
        'wheel':pin(wheel),'installed_files':[pin(path) for path in sorted(installed.rglob('*')) if path.is_file()],
        'command':command,'actual_candidate_wheels':1,'actual_candidate_installs':1,
        'elapsed_ns':time.perf_counter_ns()-start,
    })
    print(json.dumps({k:result[k] for k in ('preparation_git','source_sha256','wheel_sha256','install_root')}),flush=True)


def experiment(exact_receipt):
    frozen=verified_freeze()
    check=read(exact_receipt)
    require(check['passed'] is True and check['binding_git']==frozen['candidate_git'],
            'fixed_installed_candidate_exact_controls_required')
    install=NS/'install/PRODUCT_RUN_BINDING.json'
    require(read(install)['preparation_git']==frozen['candidate_git'],'unbound_installed_candidate')
    journal=ROOT/'FORMAL_SEQUENCE.jsonl'
    require(not any((ROOT/path).exists() for path in ('arms','controls',journal.name)),
            'one_nonrepeated_formal_schedule')
    with journal.open('x',encoding='utf8',newline='\n') as stream:
        def event(row):
            stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n')
            stream.flush()

        event({'event':'frozen','freeze_sha256':pin(NS/'FROZEN.json')['sha256'],
               'schedule':frozen['schedule'],'exact_receipt':pin(exact_receipt)})
        for index,(label,fixture,control) in enumerate(SCHEDULE):
            binding=BASE_BINDING if label in BASE_LABELS else install
            target=ROOT/('arms' if label in TIMED_LABELS else 'controls')/label
            entry = 'defaults.py' if fixture=='defaults' else 'replay.py'
            args=[sys.executable,'-IB','-X','utf8',str(NS/'harness'/entry),
                  '--binding',str(binding),'--output',str(target)]
            if fixture!='defaults':
                args.extend(('--fixture',fixture))
                if control:
                    args.append('--controls')
            start=time.perf_counter_ns()
            event({'event':'start','label':label,'fixture':fixture,'control':control,'binding':pin(binding),
                   'started_ns':start,'argv':args})
            process=run(args,cwd=REPO)
            now=time.perf_counter_ns()
            summary=target/'SUMMARY.json'
            event({'event':'exit','label':label,'exit_code':process.returncode,'finished_ns':now,
                   'wall_ns':now-start,'summary':pin(summary) if summary.is_file() else None})
            if process.returncode or not summary.is_file() or read(summary).get('passed') is not True:
                event({'event':'blocked','label':label,'unrun':[a[0] for a in SCHEDULE[index+1:]]})
                return 1
        event({'event':'complete','finished_ns':time.perf_counter_ns(),'new_Blender':0,'new_models':0})
    return 0


def archive():
    frozen=verified_freeze()
    checker=run_path(str(V/'perf050_dense_micro_surface_holdout_recovery_001/archive_evidence.py'))['check_named_bytes']
    sealed=ROOT/'sealed'
    sealed.mkdir(exist_ok=False)
    target=sealed/'ORIGINAL_RUNTIME.zip'
    build_root=ROOT/'candidate_install'
    allowed=set(build_root.glob('*.whl'))|{build_root/'PIP_STDOUT.bin',build_root/'PIP_STDERR.bin'}
    files=sorted(path for path in ROOT.rglob('*') if path.is_file() and not path.is_relative_to(sealed)
                 and (not path.is_relative_to(build_root) or path in allowed))
    entries={}
    with ZipFile(target,'x',compression=ZIP_DEFLATED,compresslevel=5) as result:
        for path in files:
            name='runtime/'+path.relative_to(ROOT).as_posix()
            material=path.read_bytes()
            checker(name,material)
            entries[name]=digest(material)
            result.writestr(name,material)
    with ZipFile(target) as result:
        require(len(result.namelist())==len(entries) and set(result.namelist())==entries.keys()
                and all(digest(result.read(name))==value for name,value in entries.items()),
                'sealed_actual_replay_bytes_changed')
    award={'freeze_sha256':pin(NS/'FROZEN.json')['sha256'],'archive':{'name':target.name,**digest(target.read_bytes())},
           'member_count':len(entries),'members':entries}
    write(sealed/'RAW_INDEX.json',award)
    print(len(entries),'closed raw files',award['archive'],flush=True)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('freeze','build','experiment','archive'))
    parser.add_argument('--candidate')
    parser.add_argument('--reports',type=Path,nargs='*',default=[])
    parser.add_argument('--exact-receipt',type=Path)
    args = parser.parse_args()
    if args.phase=='freeze':
        require(args.candidate and args.reports,'freeze_before_build_requires_product_and_replay_preflight')
        freeze(args.candidate,args.reports)
    elif args.phase=='build':
        build()
    elif args.phase=='experiment':
        require(args.exact_receipt,'actual_installed_exact_candidate_receipt_required')
        raise SystemExit(experiment(args.exact_receipt))
    else:
        archive()
