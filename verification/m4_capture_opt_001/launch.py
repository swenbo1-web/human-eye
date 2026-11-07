"""Freeze and launch a source-verified QA client, never import product here."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
FOLDER = Path(__file__).resolve().parent
PRODUCT = '2ef16a5e5b316453fff343ab8d2ff36b7b7c82113580137094f18896f1509664'
NATIVE = Path('D:/hefe/verification/fixes/20261106_perf010_r2/installed/verification/visual004_native.py')
NATIVE_SHA = '5bc1152aeafab89220c93edeec51cbe32ace458cc07d3e7d0507b6412b816fb3'
BASELINE = Path('D:/hefe/verification/fixes/20261107_m4_acquisition/review_qa_001/baseline_A')
CASES = ['peripheral','all_overlap','equal_ties','zero','rotated_nonuniform','large_offset_units',
         'isolated_vertex','degenerate','unsupported_modifier','far_second_degenerate','loose_first_vertex']
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,data): Path(path).write_bytes((json.dumps(data,indent=2)+'\n').encode())


def main():
    start_ns = time.perf_counter_ns();start_utc = datetime.now(timezone.utc)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['entry-check','run'])
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    assert out.is_relative_to(FOLDER) and not out.exists()
    if args.mode == 'run':
        cutoff = datetime(2026,11,7,12,25,tzinfo=timezone.utc)
        assert (cutoff-start_utc).total_seconds() >= 900+60+180, 'insufficient_real_batch_and_seal_margin'
    out.mkdir()
    source = json.loads((FOLDER/'B_IDENTITY.json').read_bytes())
    assert source['source_sha256'] == PRODUCT and len(source['files']) == 131
    for row in source['files']: assert sha(ROOT/row['path']) == row['sha256']
    assert sha(NATIVE) == NATIVE_SHA
    assert sha(BASELINE/'human_eye_plugin/blender_host.py') == 'ba83c5455f0e2a9a3e67443f04f4519fa064eabd6af108a6b94d3537783baa22'
    qa_sources = [FOLDER/name for name in ('launch.py','owned_driver.py','PREREGISTRATION.md','test_preflight.py','test_nine_pairs.py','B_IDENTITY.json')]
    plan = {'root':str(ROOT),'out':str(out),'product_sha256':PRODUCT,'product_manifest':source['files'],
        'qa_control_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'driver':str(FOLDER/'owned_driver.py'),'oracle_run':str(ROOT/'verification/m4_capture_qa_001/run_01'),
        'qa_sources':[{'path':str(p),'sha256':sha(p)} for p in qa_sources],
        'native_helper':str(NATIVE),'native_helper_sha256':NATIVE_SHA,'baseline_root':str(BASELINE),
        'blender':'D:/Tools/blender5.2/blender.exe','start_ns':start_ns,'deadline_ns':start_ns+900_000_000_000,
        'cases':CASES,'entry_check_only':args.mode=='entry-check','window':'M2-M4-CAPTURE-OPT-001-ONLY'}
    oracle = ROOT/'verification/m4_capture_qa_001/run_01'
    plan['oracle_frozen_assets_sha256'] = sha(oracle/'FROZEN_ASSETS.json')
    plan['oracle_source_sha256'] = '776485105a0616b9aa19b4a7385e6fd01a15ef32bf535d9487444855b1a193e5'
    plan['oracle_full_raw'] = [{'case':case,'path':str(oracle/('case_%02d_'%i+case)/'full_RAW.json'),
        'sha256':sha(oracle/('case_%02d_'%i+case)/'full_RAW.json')} for i,case in enumerate(CASES)]
    plan['blender_sha256'] = sha(plan['blender'])
    save(out/'FROZEN_PLAN.json',plan)
    plan_path = out/'FROZEN_PLAN.json'
    boot = '\n'.join([
        'import hashlib,json,sys,types', 'from pathlib import Path',
        '_path=Path('+repr(str(plan_path))+')', '_raw=_path.read_bytes()',
        'assert hashlib.sha256(_raw).hexdigest()=='+repr(sha(plan_path)), '_plan=json.loads(_raw)',
        'for _row in _plan["qa_sources"]: assert hashlib.sha256(Path(_row["path"]).read_bytes()).hexdigest()==_row["sha256"]',
        '_root=Path(_plan["root"])', '_name="human_eye_plugin/verified_source_loader.py"',
        '_pin=next(r["sha256"] for r in _plan["product_manifest"] if r["path"]==_name)',
        '_helper_path=_root/_name', '_blob=_helper_path.read_bytes()',
        'assert hashlib.sha256(_blob).hexdigest()==_pin',
        '_helper=types.ModuleType("_m4_verified_bootstrap");_helper.__file__=str(_helper_path)',
        'sys.modules[_helper.__name__]=_helper',
        'exec(compile(_blob,str(_helper_path),"exec",dont_inherit=True),_helper.__dict__)',
        'VERIFIED_GUARD=_helper.install(_root,_plan["product_manifest"],bootstrap_module=_helper)',
        '_driver=Path(_plan["driver"]);_driver_blob=_driver.read_bytes()',
        'assert hashlib.sha256(_driver_blob).hexdigest()==next(r["sha256"] for r in _plan["qa_sources"] if r["path"]==str(_driver))',
        'sys.argv=["pinned-owned-QA",str(_path)]',
        'exec(compile(_driver_blob,str(_driver),"exec",dont_inherit=True),globals())'])
    command = [sys.executable,'-I','-B','-c',boot]
    save(out/'COMMAND.json',{'argv':command,'cwd':str(ROOT),'start_utc':start_utc.isoformat()})
    process = None;failure = None
    try:
        with (out/'controller_stdout.txt').open('xb') as stdout,(out/'controller_stderr.txt').open('xb') as stderr:
            process = subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),shell=False)
            process.wait(timeout=45 if args.mode=='entry-check' else max(.001,(plan['deadline_ns']-time.perf_counter_ns())/1e9+60))
    except BaseException as exc:
        failure={'type':type(exc).__name__,'message':str(exc)}
    finally:
        if process is not None and process.poll() is None: process.kill();process.wait(timeout=5)
        drift = [r['path'] for r in source['files'] if sha(ROOT/r['path']) != r['sha256']]
        save(out/'COMMAND_RECEIPT.json',{'start_utc':start_utc.isoformat(),'end_utc':datetime.now(timezone.utc).isoformat(),
            'whole_command_ns':time.perf_counter_ns()-start_ns,'exit_code':None if process is None else process.poll(),
            'process_reaped':process is not None and process.poll() is not None,'launcher_error':failure,
            'product_source_drift':drift,'product_source_sha256':PRODUCT,'mode':args.mode})
    print(str(out))
    if failure or process is None or process.returncode != 0 or drift: raise SystemExit(1)


if __name__ == '__main__': main()
