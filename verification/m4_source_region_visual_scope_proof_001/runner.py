"""Run installed offline frame proofs on the frozen sources without live acquisitions."""

import argparse
from pathlib import Path
import subprocess
import sys
import traceback
from zipfile import ZipFile
from runpy import run_path
import json

sys.path.insert(0,str(Path(__file__).resolve().parent))
import proof


def verify_install():
    here=proof.HERE
    accepted=here.parent/'m1_m2_source_region_scoped_measurement_001/install/PRODUCT_RUN_BINDING.json'
    commit='2b3c8c2811c018ab8eda5e7c21b2bc51a442fa10'
    planned='5118b228d8a2a2addfb4ba17213da7b39bba21d3:docs/M4_SOURCE_REGION_VISUAL_SCOPE_PROOF_001_PLAN.md'
    repo=here.parents[1]
    stored=subprocess.check_output(('git','show',commit+':'+accepted.relative_to(repo).as_posix()),cwd=repo)
    proof.need(stored==accepted.read_bytes(),'accepted_runtime_manifest_changed')
    plan=subprocess.check_output(('git','show',planned),cwd=repo)
    if not (here/'PLAN.md').is_file():
        with (here/'PLAN.md').open('xb') as stream:
            stream.write(plan)
    proof.need(plan==(here/'PLAN.md').read_bytes(),'frozen_plan_bytes_changed')
    binding=json.loads(stored)
    product='ba79e2f1ca79f4651a3acaef90988fef9a1a9fc6'
    proof.need(binding['preparation_git']==product and Path(binding['install_root'])==proof.INSTALL
               and len(binding['source_manifest'])==143,'wrong_original_ba79_install_or_file_count')
    wheel=Path(binding['wheel_path'])
    proof.need(proof.pin(wheel)['sha256']==binding['wheel_sha256'],'accepted_wheel_digest_changed')
    names=[row['path'] for row in binding['source_manifest']]
    utility=here.parent/'m4_cross_scale_local_first_view_001/install/build_install.py'
    files=run_path(str(utility))['git_blobs'](product,names)
    with ZipFile(wheel) as pack:
        proof.need(pack.testzip() is None
                   and sorted(n for n in pack.namelist() if n.endswith('.py'))==sorted(names),
                   'accepted_wheel_runtime_listing_or_CRC_changed')
        for row in binding['source_manifest']:
            path=row['path']
            v=(proof.INSTALL/path).read_bytes()
            proof.need(files[path]==v==pack.read(path) and proof.sha256(v).hexdigest()==row['sha256'],
                       'git_wheel_installed_byte_mismatch/'+path)
    for name,module in list(sys.modules.items()):
        if name.startswith('human_eye_plugin') and getattr(module,'__file__',None) is not None:
            proof.need(Path(module.__file__).is_relative_to(proof.INSTALL),'loaded_runtime_outside_installed_product')
    return {'git':product,'manifest':proof.pin(accepted),'wheel':proof.pin(wheel),
            'attached_product_source_sha256':binding['source_sha256'],'verified_sources':len(names),'new_builds':0,
            'new_installs':0}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',choices=('main','yanyite'),required=True)
    p.add_argument('--run',default='cases')
    args=p.parse_args()
    proof.need(args.run.replace('-','').isalnum(),'owned_run_segment_required')
    proof.need(sys.flags.isolated and sys.dont_write_bytecode,'requires_fixed_isolated_python')
    out=proof.ROOT/args.run/args.source
    out.mkdir(parents=True,exist_ok=False)
    install=verify_install()
    if args.source=='main':
        from sources import load_main
        cases=load_main()
    else:
        from auxiliary import load_aux
        cases=load_aux()
    receipts=[]
    for case in cases:
        label=case['label']
        case_dir=out/label
        case_dir.mkdir(parents=True,exist_ok=False)
        try:
            summary=proof.run_case(case,case_dir)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, IndexError, FloatingPointError, AssertionError) as exc:
            summary={'label':label,'passed':False,'error':str(exc),'type':type(exc).__name__,
                     'traceback':traceback.format_exc(),'source_proof':case['proof']}
        path=case_dir/'RESULT.json'
        proof.write(path,summary)
        receipts.append({'label':label,'passed':summary['passed'],'result':proof.pin(path)})
        if summary['passed']:
            t=summary['original_camera_tight_world']['counts']
            print(label,summary['actual_archived_frame']['view'],t['complete']['objects'],'->',t['common']['objects'],
                  summary['offline_case_window_ns'],flush=True)
        else:
            print(label,'failed',summary['error'],flush=True)
    proof.write(out/'RUN_RESULT.json',{'passed':all(row['passed'] for row in receipts),'product':install,
        'case_receipts':receipts,'live_blender':0,'models':0,'new_component_deployments':0,
        'actual_work_scope':'isolated installed renderer, original/persisted file read; no Blender/TCP or public response'})
    return int(not all(row['passed'] for row in receipts))


if __name__=='__main__':
    raise SystemExit(main())
