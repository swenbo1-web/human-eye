"""Own one short background Blender probe and always release its process."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
script=Path(__file__).with_name('real_probe.py')
if not script.is_file():raise FileNotFoundError(script)
executable=Path('D:/Tools/blender5.2/blender.exe')
command=[str(executable),'--factory-startup','--disable-autoexec','--background','--python-exit-code','12',
         '--python',str(script),'--',str(out),str(ROOT)]
with (out/'blender.log').open('w',encoding='utf8',newline='\n') as log:
    process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        (out/'process.json').write_text(json.dumps({'pid':process.pid,'command':command},indent=2),encoding='utf8',newline='\n')
        code=process.wait(timeout=45)
        result_path=out/'RESULT.json'
        result=json.loads(result_path.read_text(encoding='utf8')) if result_path.is_file() else {}
        if code or not result.get('passed'):
            raise RuntimeError('Blender source probe failed; see '+str(out/'blender.log'))
        print(json.dumps({'passed':True,'pid':process.pid,'returncode':code,'result':str(result_path)}))
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=5)
        (out/'process_exit.json').write_text(json.dumps({'pid':process.pid,'returncode':process.returncode,
            'closed':process.poll() is not None}),encoding='utf8',newline='\n')
