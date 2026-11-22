"""Freeze the replay and build exactly one isolated global-first-frame candidate."""

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
ROOT = Path('D:/he_m4_region_task_global_first_frame_001')
BASE = '0b6116d70af512f81a6ba053dd02a5e924530593'
PLAN = 'f4f08749ccbdd4ebd02c38b724f259eba4fb98be:docs/M4_REGION_TASK_GLOBAL_FIRST_FRAME_001_PLAN.md'
BASE_BINDING = V/'m4_local_coverage_object_bounds_001/install/PRODUCT_RUN_BINDING.json'
PRODUCT_NS = V/'m4_dense_sweep_integrated_native_startup_001'
MAIN = '5b7910c1486071abae84466cb0b51230dc111aa0'
MAIN_TERMINAL = '3cdb270694e6d7096dfd3554b6a19edea5a3891a1ee76d35d204e8713c916a06'
HOLDOUT = '39fd39cd'
HOLDOUT_NS = V/'m4_cross_scale_assembly_transfer_001'
HOLDOUT_TERMINAL = 'd0d2294f5e5fe006d2f3f23deaf34290dba696b39424585b7cd5e4494d8ffa90'
TRANSFER = 'f56108e537a0664c07a0e9cb2f88186f30ec604c'
TRANSFER_TERMINAL = '78229e6cc7d987a32fac00380372c7b745b7449871e01cd5a57227f42c34e291'
PYTHON = Path('D:/he_anchor_001/venv/Scripts/python.exe')
BUILDER = V/'build_candidate_release.py'
BLOBS = V/'m4_cross_scale_local_first_view_001/install/build_install.py'
DATA = ('human_eye_plugin/plugin.json','human_eye_plugin/mcp_config.json')
DELTA = ('human_eye_plugin/active_observation_region_task.py',)
MAIN_PAIRS = (('N1','P1'),('P2','N2'),('N3','P3'))
HOLDOUT_PAIR = ('HN','HP')
TRANSFER_PAIR = ('TN','TP')


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


def freeze(candidate, reports):
    require(not (ROOT/'candidate_install').exists() and not (NS/'FROZEN.json').exists(),
            'one_freeze_before_any_candidate_build')
    require((NS/'PLAN.md').read_bytes()==git('show',PLAN),'fixed_planning_commit_changed')
    require(git('rev-list','--parents','-n','1',candidate).decode().split()==[candidate,BASE]
            and tuple(git('diff','--name-only',BASE,candidate).decode().splitlines())==DELTA,
            'expected_direct_product_code_scope_changed')
    paths = {}

    def capture(path,expected=None):
        row = pin(path)
        require(expected is None or all(row[key]==expected[key] for key in ('bytes','sha256')),
                'pinned_replay_input_changed/'+row['path'])
        paths[Path(row['path'])] = row
        return row

    index,archive = (PRODUCT_NS/name for name in ('RAW_INDEX.json','ORIGINAL_RUNTIME.zip'))
    for path in (index,archive):
        require(path.read_bytes()==git('show',f'{MAIN}:{path.relative_to(REPO).as_posix()}'),
                'main_archived_commit_bytes_changed/'+path.name)
    idx = read(index)
    require(capture(archive)['sha256']==idx['archive']['sha256'],'main_archive_sha_mismatch')
    with ZipFile(archive) as z:
        name = 'runtime/slots/P1/TERMINAL_SOURCE.json'
        require(digest(z.read(name))==idx['members'][name]
                and idx['members'][name]['sha256']==MAIN_TERMINAL,'pinned_main_terminal_mismatch')
    held_index = HOLDOUT_NS/'RUNTIME_INDEX.json'
    require(held_index.read_bytes()==git('show',f'{HOLDOUT}:{held_index.relative_to(REPO).as_posix()}'),
            'holdout_Git_index_changed')
    held = read(held_index)
    held_archive = Path(held['archive']['path'])
    capture(held_index)
    capture(held_archive,held['archive'])
    name = 'slots/P1/TERMINAL_SOURCE.json'
    terminal, = [row for row in held['files'] if row['path']==name]
    with ZipFile(held_archive) as z:
        require(digest(z.read(name))=={k:terminal[k] for k in ('bytes','sha256')}
                and terminal['sha256']==HOLDOUT_TERMINAL,'pinned_assembly_holdout_terminal_mismatch')

    transfer = V/'perf050_dense_micro_surface_holdout_recovery_001'
    for name in ('RAW_INDEX.json','ORIGINAL_RUNTIME.zip'):
        path = transfer/name
        require(path.read_bytes()==git('show',f'{TRANSFER}:{path.relative_to(REPO).as_posix()}'),
                'transfer_archived_commit_bytes_changed/'+name)
        capture(path)
    transfer_index = read(transfer/'RAW_INDEX.json')
    with ZipFile(transfer/'ORIGINAL_RUNTIME.zip') as zipper:
        terminals = [name for name in zipper.namelist() if name.endswith('slots/P2/TERMINAL_SOURCE.json')]
        require(len(terminals)==1 and digest(zipper.read(terminals[0]))==transfer_index['members'][terminals[0]]
                and transfer_index['members'][terminals[0]]['sha256']==TRANSFER_TERMINAL,
                'pinned_dense_transfer_terminal_mismatch')

    binding = read(BASE_BINDING)
    require(binding['preparation_git']==BASE and len(binding['source_manifest'])==143
            and binding['source_sha256']=='317258d315ec448e785ec74a4893138e4a851dfda373a20747506bd919af2be4'
            and binding['wheel_sha256']=='7768cb7a09b9a0087f3550adb54fc25154a2e5bf819bae9ef269e313260d0394',
            'expected_existing_object_bounds_install')
    require(capture(binding['wheel_path'])['sha256']==binding['wheel_sha256'],'fixed_baseline_wheel_changed')
    for row in binding['source_manifest']:
        path = Path(binding['install_root'])/row['path']
        require(capture(path)['sha256']==row['sha256'],'fixed_baseline_module_changed/'+row['path'])
    previous = V/'m4_local_coverage_object_bounds_001'
    for path in (previous/'checks/replay.py', previous/'checks/fixture.py',
                 V/'m1_region_task_witness_image_path_001/checks/evidence.py',
                 V/'m1_region_task_witness_image_path_001/checks/controls.py',
                 V/'m1_region_task_first_packet_consumption_holdout_001/checks/evidence.py',
                 V/'m1_region_task_first_packet_consumption_holdout_001/fixture/TRUTH.json',
                 V/'m4_dense_region_brief_001/checks/brief_schema.py'):
        capture(path)
    for path in (index,BASE_BINDING,BUILDER,BLOBS,PYTHON,NS/'PLAN.md',Path(__file__),*reports):
        capture(path)
    for report in reports:
        case = read(report)
        require(case['passed'] is True,'prebuild_qualification_blocked/'+str(report))
        for item in case.get('source_pins',[]):
            capture(item['path'],item)
    for path in NS.rglob('*'):
        if path.is_file():
            require(path.suffix!='.pyc','unexpected_bytecode_in_frozen_sources')
            if path.suffix=='.py':
                ast.parse(path.read_bytes(),filename=str(path))
            capture(path)
    specification = {
        'plan':PLAN,'baseline_git':BASE,'candidate_git':candidate,'changed_runtime_sources':list(DELTA),
        'main':{'archive_git':MAIN,'terminal_sha256':MAIN_TERMINAL,'cold_expected_rasters':3,
                'candidate_cold_expected_rasters':2, 'max_global_pixel_bound':6},
        'holdout':{'archive_git':git('rev-parse',HOLDOUT).decode().strip(),'name':'assembly_transfer_P1',
                   'terminal_sha256':HOLDOUT_TERMINAL},
        'transfer':{'archive_git':TRANSFER,'terminal_sha256':TRANSFER_TERMINAL,'slot':'P2'},
        'main_pair_order':MAIN_PAIRS,'holdout_order':HOLDOUT_PAIR,'transfer_order':TRANSFER_PAIR,
        'controls':{'main_full':('FN','FP'),'ordinary':('ON','OP')},'min_paired_median_cold_MCP_improvement':0.10,
        'candidate_wheels':1,'candidate_installs':1,'new_Blender_models_each':0,'replacements':0,
        'source_inputs':[paths[p] for p in sorted(paths)],
    }
    write(NS/'FROZEN.json',specification)
    print('Frozen',pin(NS/'FROZEN.json')['sha256'],len(paths),'pins',flush=True)


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
    version = '9.7.2+m4.region.task.global.first.frame.001'
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
    f = verified_freeze()
    check = read(exact_receipt)
    require(check['passed'] is True and check['installed'] is True and check['binding_git']==f['candidate_git'],
            'wrong_or_failed_installed_candidate_controls')
    new_binding = NS/'install/PRODUCT_RUN_BINDING.json'
    require(read(new_binding)['preparation_git']==f['candidate_git'],'frozen_candidate_not_installed')
    schedule = [(label,'main','timed',None) for pair in f['main_pair_order'] for label in pair]
    schedule.extend((label,'holdout','held',None) for label in f['holdout_order'])
    schedule.extend((label,'transfer','transfer',None) for label in f['transfer_order'])
    schedule.extend((label,'main',group,flag) for group,flag in (
        ('main_full','--full-control'),('ordinary','--controls')) for label in f['controls'][group])
    require(not (ROOT/'arms').exists() and not (ROOT/'controls').exists(),
            'one_nonrepeating_formal_replay_sequence')
    journal = ROOT/'FORMAL_SEQUENCE.jsonl'
    with journal.open('x',encoding='utf8',newline='\n') as stream:
        def add(row):
            stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n')
            stream.flush()
        add({'event':'frozen','freeze_sha256':pin(NS/'FROZEN.json')['sha256'],
             'schedule':schedule,'exact_receipt':pin(exact_receipt)})
        for number,(label,fixture,role,flag) in enumerate(schedule):
            choose = new_binding if label.startswith('P') or label.endswith('P') else BASE_BINDING
            target = ROOT/('controls' if flag is not None else 'arms')/label
            argv = [sys.executable,'-IB','-X','utf8',str(NS/'harness/replay.py'),
                    '--binding',str(choose),'--fixture',fixture,'--output',str(target)]
            if flag is not None:
                argv.append(flag)
            started = time.perf_counter_ns()
            add({'event':'start','label':label,'fixture':fixture,'role':role,'binding':pin(choose),
                 'argv':argv,'started_ns':started})
            result = run(argv,cwd=REPO)
            stop = time.perf_counter_ns()
            summary = target/'SUMMARY.json'
            add({'event':'exit','label':label,'exit_code':result.returncode,'finished_ns':stop,
                 'wall_ns':stop-started,'summary':pin(summary) if summary.is_file() else None})
            if result.returncode or not summary.is_file() or read(summary).get('passed') is not True:
                add({'event':'blocked','label':label,'unrun':[item[0] for item in schedule[number+1:]]})
                print(label,'replay did not close with all evidence',flush=True)
                return 1
        add({'event':'complete','finished_ns':time.perf_counter_ns(),'new_Blender':0,'new_models':0})
    return 0


def archive():
    verified_freeze()
    checker = run_path(str(V/'perf050_dense_micro_surface_holdout_recovery_001/archive_evidence.py'))
    inspect = checker['check_named_bytes']
    binding_path = NS/'install/PRODUCT_RUN_BINDING.json'
    build_root = ROOT/'candidate_install'
    kept = {build_root/'PIP_STDOUT.bin',build_root/'PIP_STDERR.bin'}
    if binding_path.is_file():
        kept.add(Path(read(binding_path)['wheel_path']))
    kept.update(build_root.glob('*.whl'))
    index = {}
    target = NS/'ORIGINAL_RUNTIME.zip'
    with ZipFile(target,'x',compression=ZIP_DEFLATED,compresslevel=6) as bundle:
        for path in sorted(p for p in ROOT.rglob('*') if p.is_file() and (build_root not in p.parents or p in kept)):
            name = 'runtime/'+path.relative_to(ROOT).as_posix()
            raw = path.read_bytes()
            inspect(name,raw)
            bundle.writestr(name,raw)
            index[name] = digest(raw)
    with ZipFile(target) as bundle:
        require(len(bundle.namelist())==len(index) and set(bundle.namelist())==index.keys()
                and all(digest(bundle.read(name))==row for name,row in index.items()),'packed_raw_bytes_changed')
    write(NS/'RAW_INDEX.json',{'freeze_sha256':pin(NS/'FROZEN.json')['sha256'],
         'archive':{'name':target.name,**digest(target.read_bytes())},'member_count':len(index),'members':index})
    print('Sealed',len(index),'members',target.stat().st_size,target.name,pin(target)['sha256'],flush=True)


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
