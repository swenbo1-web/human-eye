"""Own exactly one background asset-build process and preserve its receipt."""

import hashlib
import json
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    output = HERE/'build_01'
    output.mkdir(exist_ok=False)
    paths = [Path(__file__), HERE/'build_asset.py', ROOT/'verification/scale_diag_001/fixtures/G508.blend',
        ROOT/'verification/scale_diag_001/fixtures/G508.json', ROOT/'verification/scale_diag_001/oracle.py',
        ROOT/'verification/scale_diag_001/ORACLE.json']
    sha = lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    pins = {str(p):sha(p) for p in paths}
    command = ['D:/Tools/blender5.2/blender.exe','--factory-startup','--disable-autoexec','--background',
        '--python',str(HERE/'build_asset.py')]
    started = time.perf_counter_ns()
    forced = False
    with (output/'stdout.bin').open('xb') as stdout, (output/'stderr.bin').open('xb') as stderr:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            forced=True
            process.kill()
            process.wait(timeout=10)
    unchanged = all(sha(Path(path)) == expected for path,expected in pins.items())
    result = {'passed':process.returncode==0 and not forced and unchanged and (HERE/'DERIVED_MANIFEST.json').exists(),
        'argv':command,'pid':process.pid,'exit_code':process.returncode,'reaped':process.poll() is not None,
        'forced':forced,'started_ns':started,'ended_ns':time.perf_counter_ns(),'input_sha256':pins,
        'inputs_unchanged':unchanged,'owned_build_Blender_sessions':1,'product_calls':0,'model_consumers':0}
    with (output/'RESULTS.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
