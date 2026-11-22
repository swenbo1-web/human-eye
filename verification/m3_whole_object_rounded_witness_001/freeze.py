"""Freeze the actual replay/score inputs before the one candidate build."""
from hashlib import sha256
import json
from pathlib import Path
from subprocess import check_output

NS=Path(__file__).resolve().parent
V=NS.parent
RUN=Path('D:/he_m3_whole_object_rounded_witness_001')
BASE=V/'m3_whole_object_witness_triangle_001/install/PRODUCT_RUN_BINDING.json'
PLAN='76c217f2f62af12dbd338a720d62fbda0dfe5b8f:docs/M3_WHOLE_OBJECT_ROUNDED_WITNESS_001_PLAN.md'
PARENT='5c77f71a04e580e1e1810d4d72ff6a955cb27a0c'
PRODUCT='ae14344ea3aa654c710f2329bd4aa4423f7af9c4'
ASSET=Path('D:/he_m4_cross_scale_live_task_001/fixture/main.blend')
SOURCE=ASSET.with_name('READBACK_AFTER_RELOAD.json')
BVH=Path('D:/he_m4_cross_scale_assembly_transfer_001/slots/P1/TERMINAL_SOURCE.json')
KERNEL_A=Path('D:/he_m3_whole_object_rounded_witness_001_KERNEL_A.json')


def pin(path):
    path=Path(path).resolve(strict=True)
    data=path.read_bytes()
    return {'path':str(path),'bytes':len(data),'sha256':sha256(data).hexdigest()}


def verify_candidate_identity():
    git=lambda *args:check_output(['git','-C',str(V.parent),*args])
    expected=['human_eye_plugin/live_spatial_mcp.py','human_eye_plugin/surface_proximity.py','human_eye_plugin/task_query.py']
    if (git('rev-list','--parents','-n','1',PRODUCT).decode().split()!=[PRODUCT,PARENT]
            or git('diff','--name-only',PARENT,PRODUCT).decode().splitlines()!=expected):
        raise ValueError('candidate is not exactly the frozen three-file child')
    if (NS/'PLAN.md').read_bytes()!=git('show',PLAN):
        raise ValueError('frozen plan text changed')
    return expected


def freeze():
    changed=verify_candidate_identity()
    expected_raw={
       ASSET:'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce',
       SOURCE:'836219a6cd00f81dc658b0277c4dfa82cfafba8d094570ec797dbc5eb8e12dee',
       BVH:'d0d2294f5e5fe006d2f3f23deaf34290dba696b39424585b7cd5e4494d8ffa90',
    }
    if any(pin(path)['sha256']!=value for path,value in expected_raw.items()):
        raise ValueError('fixed actual Blender source changed')
    if (RUN/'candidate_install').exists():
        raise ValueError('admission must precede the only build')
    checks=NS/'checks'
    harness=NS/'harness'
    required=[checks/f for f in ('fixtures.py','geometry.py','evidence.py','matrix.py','kernel_batch.py',
                                  'numeric_controls.py','preflight.py','CHECKER_PREFLIGHT.json')]
    required += [harness/f for f in ('fixtures.py','run.py','worker.py','PREFLIGHT.json')]
    if not all(path.is_file() for path in required):
        raise ValueError('independent checker or actual replay setup missing')
    for p in [checks/'CHECKER_PREFLIGHT.json',harness/'PREFLIGHT.json']:
        if json.loads(p.read_bytes()).get('passed') is not True:
            raise ValueError('actual checker preflight did not pass',str(p))
    old=json.loads(BASE.read_bytes())
    if old['preparation_git']!=PARENT or len(old['source_manifest'])!=143:
        raise ValueError('fixed baseline identity changed')
    wheel=pin(old['wheel_path'])
    if wheel['sha256']!=old['wheel_sha256']:
        raise ValueError('fixed baseline wheel changed')
    baseline_sources=[]
    for item in old['source_manifest']:
        p=Path(old['install_root'])/item['path']
        if pin(p)['sha256']!=item['sha256']:
            raise ValueError('fixed baseline installed source changed',item['path'])
        baseline_sources.append(p)
    path=RUN/'KERNEL_BASELINE.json'
    with path.open('xb') as f:
        f.write(KERNEL_A.read_bytes())
    sources=[BASE,Path(wheel['path']),*baseline_sources,ASSET,SOURCE,BVH,path,
             Path(__file__),NS/'PLAN.md',NS/'build_install.py',NS/'timings.py',*required,
             V/'m4_source_region_display_001/harness/reused/stdio_checks.py',
             V/'m4_live_source_region_task_003/harness/reused/verified_bootstrap.py',
             V/'m3_whole_object_witness_triangle_consumption_001/RAW_INDEX.json',
             V/'m3_whole_object_witness_triangle_consumption_001/ORIGINAL_RUNTIME.zip',
             V/'m3_whole_object_witness_triangle_001/RAW_INDEX.json',
             V/'m3_whole_object_witness_triangle_001/ORIGINAL_RUNTIME.zip']
    specs={'plan':PLAN,'authorizes_one_build_after_freeze':True,
           'baseline_git':PARENT,'candidate_git':PRODUCT,'changed_runtime_sources':changed,
           'source_inputs':[pin(p) for p in sorted(set(sources))],
           'four_arms':['baseline_standard','baseline_evidence','candidate_standard','candidate_evidence'],
           'registered_replays':7,'phases':['cold','hot'],
           'recall_baseline_strict':202,'recall_candidate_strict':202,'recall_candidate_exact':8,
           'linear_body_limit':2304,'BVH_body_limit':3072,'ordinary_body_limit':2048,
           'optional_certificate_limit':1024,'new_Blender':0,'models':0,'new_rasters':0,
           'replacements':0,'asset_rebuilds':0,'additional_fees':0}
    with (NS/'FROZEN.json').open('x',encoding='utf8',newline='\n') as out:
        out.write(json.dumps(specs,ensure_ascii=False,indent=2)+'\n')
    print(pin(NS/'FROZEN.json'))


if __name__=='__main__':
    freeze()
