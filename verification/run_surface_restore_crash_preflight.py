"""Real owned Blender process hard exits; parent performs only journal reads."""
import argparse,hashlib,importlib.util,json,os,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2)


def main(args):
    args.output.mkdir(exist_ok=False)
    spec=importlib.util.spec_from_file_location('_restore_crash_entry',args.entry);entry=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=entry;spec.loader.exec_module(entry);proof=entry.validate_binding(expected_python=sys.executable)
    sys.path.insert(0,proof['module_root']);identity,_=entry.verify_imported_runtime(proof)
    from human_eye_plugin.surface_restore import RestoreJournal
    harness=Path(__file__).with_name('run_surface_kernel_preflight.py');rows=[]
    for phase in ('preparing','after_setter','after_final'):
        for repeat in range(2):
            root=args.output/(phase+str(repeat));out=args.output/(root.name+'.stdout');err=args.output/(root.name+'.stderr')
            with out.open('xb') as stdout,err.open('xb') as stderr:
                # This exact Popen handle owns the child, not a later PID lookup.
                child=subprocess.Popen([str(args.blender),'--factory-startup','--disable-autoexec','--background','--python',str(harness),'--',
                    '--output',str(root),'--core-root',proof['module_root'],'--crash-phase',phase],stdout=stdout,stderr=stderr,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                try:code=child.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    child.kill();child.wait();raise AssertionError('owned crash child timed out; forced cleanup is not a pass')
            assert code==37,(phase,code,out.read_text(encoding='utf8',errors='replace'))
            journal=root/'flat_success';before=hashlib.sha256((journal/'slot-00/RECORD.json').read_bytes()).hexdigest()
            recovered=RestoreJournal.inspect(journal);fresh=RestoreJournal(journal);poisoned=fresh.poisoned;fresh.close()
            assert hashlib.sha256((journal/'slot-00/RECORD.json').read_bytes()).hexdigest()==before
            assert recovered['restart_can_dispatch'] is False
            if phase!='after_final':assert recovered['unknown'] and poisoned and recovered['rows'][0]['setter_count'] is None
            if phase=='after_setter':
                physical=json.loads((root/'PHYSICAL_WRITE.json').read_text(encoding='utf8'))
                assert physical['actual_RNA_setter_count']==1 and physical['protected_vertices_unchanged']
            if phase=='after_final':
                physical=json.loads((root/'PHYSICAL_FINAL.json').read_text(encoding='utf8'))
                assert physical['actual_RNA_setter_count']==1 and physical['source_after']==physical['reference_raw']
                assert not recovered['unknown'] and recovered['rows'][0]['setter_count']==1 and not physical['client_received_result']
            rows.append(dict(phase=phase,repeat=repeat,child_exit=code,forced_cleanup=False,recovered=recovered,
                same_process_handle_waited=True,record_unchanged_by_recovery=True))
            print(json.dumps(dict(phase=phase,repeat=repeat,recovered_unknown=recovered['unknown'])),flush=True)
    save(args.output/'RESULT.json',dict(runtime_source=identity['source_sha256'],rows=rows,all_passed=True,user_GUI_accessed=False,formal_model_calls=0))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--entry',type=Path,required=True);p.add_argument('--blender',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);main(p.parse_args())
