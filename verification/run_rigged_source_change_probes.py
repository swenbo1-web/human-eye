"""Explicit QA actor changes sources BETWEEN read-only captures, never a product command."""
import argparse,importlib.util,json,os,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]


def worker_wrapper():
    import bpy
    from mathutils import Matrix
    mode=os.environ['HE_B3_CHANGE_MODE'];output=Path(os.environ['HE_B3_CHANGE_OUTPUT']);base=sys.stdout;changed=[False]
    def mutate():
        if mode=='future_key':
            action=bpy.data.actions['Anim_0'];curves=[f for layer in action.layers for strip in layer.strips for bag in strip.channelbags for f in bag.fcurves]
            curve=next(f for f in curves if f.data_path.endswith('.location') and f.array_index==0)
            key=curve.keyframe_points[-1];old=list(key.co);assert key.co.x>bpy.context.scene.frame_current+1
            key.co.y+=.125;detail=dict(path=curve.data_path,index=curve.array_index,before=old,after=list(key.co),RNA_setters=1)
        elif mode=='parent_inverse':
            obj=bpy.context.scene.objects['Cylinder'];inverse=obj.matrix_parent_inverse.copy();basis=obj.matrix_basis.copy();world=obj.matrix_world.copy()
            obj.matrix_parent_inverse=inverse@Matrix.Translation((.125,0.,0.));obj.matrix_basis=Matrix.Translation((-.125,0.,0.))@basis
            detail=dict(object=obj.name,before_inverse=[list(v) for v in inverse],after_inverse=[list(v) for v in obj.matrix_parent_inverse],
                before_basis=[list(v) for v in basis],after_basis=[list(v) for v in obj.matrix_basis],prior_world=[list(v) for v in world],RNA_setters=2)
        else:raise ValueError('unknown_test_actor_mode')
        bpy.context.view_layer.update()
        with (output/'TEST_ACTOR.json').open('x',encoding='utf8') as f:json.dump(dict(mode=mode,test_actor_only=True,
            no_geometry_coordinates_assigned=True,no_file_saved=True,shared_GUI=False,detail=detail),f,indent=2)
    def intercept(value):
        if isinstance(value,bytes):value=value.decode('utf8')
        if value.startswith('B3_SOURCE_PROBE:') and not changed[0] and json.loads(value.split(':',1)[1]).get('kind')=='snapshot':
            changed[0]=True;mutate()
    class Buffer:
        def write(self,value):
            count=base.buffer.write(value);intercept(value);return count
        def flush(self):return base.buffer.flush()
        def __getattr__(self,name):return getattr(base.buffer,name)
    class Output:
        buffer=Buffer()
        def write(self,value):
            count=base.write(value)
            intercept(value)
            return count
        def flush(self):return base.flush()
        def __getattr__(self,name):return getattr(base,name)
    sys.stdout=Output()
    path=ROOT/'verification/rigged_source_capture_probe.py';spec=importlib.util.spec_from_file_location('_explicit_b3_test_actor_target',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    parser=argparse.ArgumentParser();parser.add_argument('--worker',action='store_true');parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--profile-sha256',required=True);parser.add_argument('--deadline-ns',type=int,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);module.worker(args)


def parent(args):
    import contextlib,io
    import numpy as np
    from types import SimpleNamespace
    from unittest.mock import patch
    sys.path.insert(0,str(ROOT))
    from verification import rigged_source_capture_probe as capture
    from verification.rigged_source_qualification import qualify
    assert args.output.is_absolute() and args.output.resolve()==args.output and args.output.is_relative_to(ROOT/'verification/fixes')
    args.output.mkdir(exist_ok=False);rows=[];original=capture.subprocess.Popen
    for mode in ('future_key','parent_inverse'):
        folder=args.output/mode
        def spawn(command,**kwargs):
            cmd=list(command);assert '--worker' in cmd;cmd[cmd.index('--python')+1]=str(Path(__file__).resolve())
            kwargs['env']=dict(os.environ,HE_B3_CHANGE_MODE=mode,HE_B3_CHANGE_OUTPUT=str(folder));return original(cmd,**kwargs)
        log=io.StringIO();started=time.perf_counter_ns()
        options=SimpleNamespace(output=folder,scene=args.scene,blender=Path('D:/Tools/blender5.2/blender.exe'),mesh_name='Cylinder',rig_name='Armature',
            frame_number=1,subframe=0.,qualify=True)
        with patch.object(capture.subprocess,'Popen',side_effect=spawn),contextlib.redirect_stdout(log):code=capture.controller(options)
        (folder/'CONTROLLER_STDOUT.txt').write_text(log.getvalue(),encoding='utf8')
        failure=json.loads((folder/'FAILURE.json').read_bytes());assert code==1 and failure['reason']=='b3_probe_repeated_source_changed'
        assert not (folder/'REPORT.json').exists();a=json.loads((folder/'READ_01.json').read_bytes());b=json.loads((folder/'READ_02.json').read_bytes())
        assert a['source_sha256']!=b['source_sha256']
        fresh=qualify(b,deadline_ns=time.perf_counter_ns()+5_000_000_000)
        stale=qualify(b,deadline_ns=time.perf_counter_ns()+5_000_000_000,expected_source_sha256=a['source_sha256'])
        assert fresh['status']=='qualified' and stale['status']=='rejected' and stale['reasons']==['b3_stale_source'],(mode,fresh,stale)
        av=np.asarray(a['evaluated']['vertices']);bv=np.asarray(b['evaluated']['vertices']);difference=float(np.max(np.abs(av-bv)))
        assert difference<=2e-5
        assert capture.sha(args.scene)==a['profile']['scene_sha256'] if 'profile' in a else capture.sha(args.scene)==json.loads((folder/'PROFILE.json').read_bytes())['scene_sha256']
        row=dict(case=mode,expected_controller_refusal=failure['reason'],expected_qualifier_refusal=stale['reasons'],fresh_source_qualified=True,
            evaluated_coordinates_identical=a['evaluated']['vertices']==b['evaluated']['vertices'],max_evaluated_coordinate_difference=difference,
            old_source_sha256=a['source_sha256'],new_source_sha256=b['source_sha256'],test_actor=json.loads((folder/'TEST_ACTOR.json').read_bytes()),
            original_file_unchanged=True,product_setters=0,product_saved=False,complete_fault_probe_wall_ns=time.perf_counter_ns()-started,
            replay_note='fresh/stale post-run checks are historical packet verification, not a renewed live observation')
        with (folder/'QA.json').open('x',encoding='utf8') as f:json.dump(row,f,indent=2)
        rows.append(row);print(json.dumps(dict(case=mode,passed=True,max_evaluated_coordinate_difference=difference)),flush=True)
    with (args.output/'RESULT.json').open('x',encoding='utf8') as f:json.dump(dict(cases=rows,total=2,passed=True,
        test_actor_mutates_inputs=True,reader_geometry_setters=0,reader_saved=False,shared_GUI=False),f,indent=2)


if __name__=='__main__':
    if os.environ.get('HE_B3_CHANGE_MODE') and '--worker' in sys.argv:worker_wrapper()
    else:
        parser=argparse.ArgumentParser();parser.add_argument('--scene',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parent(parser.parse_args())
