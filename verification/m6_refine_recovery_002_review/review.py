"""Independent retry allocation tests using the actual fixed API functions."""
import ast
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import numpy as np

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'_m6rr2/batch'
ROOT=HERE/'private/controls'


def read(path):return json.loads(Path(path).read_bytes())


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes((json.dumps(value,indent=2)+'\n').encode())


def identity(path):
    path=Path(path)
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def control(name,source,legacy=False,sparse=False,counter=None,real=False):
    root=ROOT/name;directory=root/'private/sessions/s';directory.mkdir(parents=True,exist_ok=False)
    blend=directory/'saved.blend'
    old=HERE.parent/'_m6rf1/batch/private/sessions/v1_s01_facts/versions/001'
    if real:shutil.copyfile(old/'model.blend',blend)
    else:blend.write_bytes(b'read-only saved-state fixture')
    state=dict(version=7,pending=None,operations=[dict(operation_id='already_saved')],current_blend=str(blend))
    if counter is not None:state['next_readback_attempt']=counter
    state_file=directory/'session.json';write(state_file,state)
    saved_sha=identity(blend)['sha256']
    label1='q'+hashlib.sha256(b's:1').hexdigest()[:16]
    if legacy:(root/'private/jobs'/label1).mkdir(parents=True)
    if sparse:(directory/'readbacks/003').mkdir(parents=True)
    attempts=[]
    fail_first=not legacy and not sparse and counter is None
    def reader(d,current,saved,label,output):
        attempts.append(dict(label=label,output=str(output),persisted_attempt=read(state_file).get('next_readback_attempt')))
        (root/'private/jobs'/label).mkdir(parents=True,exist_ok=False)
        if fail_first and len(attempts)==1:raise RuntimeError('injected before reader output')
        output.mkdir(parents=True)
        target=output/'readback.npz'
        if real:
            command=['D:/Tools/blender5.2/blender.exe','--factory-startup','--disable-autoexec','--background',str(saved),
                     '--threads','1','--python-exit-code','23','--python',str(HERE.parent/'m6_refine_001_review/blender_reader.py'),
                     '--','--object-name','0135bbc4-c6c7-4003-a402-6f2e0283497d','--output',str(target)]
            process=subprocess.run(command,capture_output=True)
            (root/'Blender.stdout').write_bytes(process.stdout);(root/'Blender.stderr').write_bytes(process.stderr)
            assert process.returncode==0
            with np.load(target) as actual,np.load(old/'independent00/readback.npz') as expected:
                for key in ('vertices_local','faces','poly_offsets','poly_vertices','matrix_world'):
                    np.testing.assert_array_equal(actual[key],expected[key])
        else:target.write_bytes(b'independent readback control fixture')
        return {},dict(status='read_coordinates_matched' if real else 'control_reader_return')
    tree=ast.parse(source.read_text(encoding='utf-8'))
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='save_readback')
    namespace=dict(Path=Path,hashlib=hashlib,HERE=root,session_lock=lambda d:nullcontext(),state_path=lambda d:d/'session.json',
                   read=read,write=write,read_actual=reader,identity=identity,short_quality=lambda q:q)
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),namespace)
    errors=[];returns=[]
    for attempt in range(2 if fail_first else 1):
        try:returns.append(namespace['save_readback'](directory))
        except (RuntimeError,FileExistsError,ValueError) as exc:errors.append(type(exc).__name__)
    after=read(state_file)
    assert {k:v for k,v in after.items() if k!='next_readback_attempt'}=={k:v for k,v in state.items() if k!='next_readback_attempt'}
    assert identity(blend)['sha256']==saved_sha
    return dict(name=name,errors=errors,returns=len(returns),attempts=attempts,final_counter=after.get('next_readback_attempt'),
                saved_state_unchanged=True,fresh_Blender_reads=int(real and bool(returns)))


def main():
    started=time.perf_counter()
    old=BASE/'private/source/session_api_before.py';new=BASE/'private/source/session_api_after.py'
    rows=[control('old_pre_output',old),control('new_pre_output',new),control('new_legacy_job',new,legacy=True),
          control('new_sparse',new,sparse=True,counter=3),control('new_bad_counter',new,counter=True),
          control('new_real_reader',new,real=True)]
    assert rows[0]['errors']==['RuntimeError','FileExistsError'] and rows[0]['returns']==0
    assert rows[1]['errors']==['RuntimeError'] and rows[1]['returns']==1 and rows[1]['final_counter']==3
    assert rows[2]['returns']==1 and rows[2]['final_counter']==3
    assert rows[3]['returns']==1 and rows[3]['final_counter']==5
    assert rows[4]['errors']==['ValueError'] and rows[4]['returns']==0
    assert rows[5]['returns']==1 and rows[5]['fresh_Blender_reads']==1
    result=dict(status='passed',control_cases=6,fresh_Blender_reads=1,results=rows,
                substituted_components=['reader for five fixture controls','lock context','quality summary'],
                actual_API_function=True,real_reader_export_matches_prior_saved_geometry=True,
                new_consumers=0,new_training=0,wall_s=time.perf_counter()-started)
    (HERE/'RESULTS.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result))


if __name__=='__main__':main()
