"""Run the actual scorer CLI cold, recording executed dependencies and write boundaries."""

import hashlib
import json
import os
from pathlib import Path
import re
from runpy import run_path
import shlex
import sys
import time


HERE = Path(__file__).resolve().parent
RUN = Path('D:/he_m4_rail_source_region_product_native_001').resolve()
WRITE_BITS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as source:
        return {'path':str(path),'bytes':path.stat().st_size,'sha256':hashlib.file_digest(source,'sha256').hexdigest()}


def run():
    if not sys.flags.isolated or not sys.dont_write_bytecode or len(sys.argv)<4:
        raise ValueError('isolated_original_scoring_entry_required')
    entry, receipt = (Path(arg).resolve() for arg in sys.argv[1:3])
    if (entry.parent != HERE or entry.name not in ('score.py','baseline.py','controls.py')
            or not receipt.is_relative_to(RUN) or receipt.exists()):
        raise ValueError('current_scoring_entry_and_new_receipt_required')
    sys.path.insert(0, str(HERE))
    arguments = [str(entry), *sys.argv[3:]]
    executed, subprocesses = set(), []

    def writable(value):
        return isinstance(value,int) or Path(os.fsdecode(value)).resolve().is_relative_to(RUN)

    def guard(event,args):
        if event == 'exec':
            path = args[0].co_filename
            if path.endswith(('.py','.pyw','.pyd')):
                executed.add(path)
        elif event == 'open' and args[2] & WRITE_BITS:
            if not writable(args[0]):
                raise PermissionError('historical_scoring_inputs_are_read_only')
        elif event in ('os.remove','os.rmdir','os.mkdir','os.chmod','os.utime','os.truncate'):
            if not writable(args[0]):
                raise PermissionError('historical_scoring_inputs_are_read_only')
        elif event in ('os.rename','os.link','os.symlink'):
            if not all(writable(value) for value in args[:2]):
                raise PermissionError('historical_scoring_inputs_are_read_only')
        elif event == 'subprocess.Popen':
            executable, command, cwd, _ = args
            if not isinstance(command,str):
                raise PermissionError('scoring_may_only_launch_retained_read_only_git_reads')
            program,*options = [word.strip('"') for word in shlex.split(command,posix=False)]
            work = Path(cwd or Path.cwd())
            if len(options) >= 2 and options[0] == '-C':
                work = Path(options[1])
                options = options[2:]
            if (Path(executable or program).name.lower() not in ('git','git.exe')
                    or Path(program).name.lower() not in ('git','git.exe')
                    or work.resolve() != HERE.parents[1]
                    or len(options) != 2 or options[0] != 'show'
                    or not re.fullmatch(r'[0-9a-f]{7,40}:verification/[\w./-]+',options[1])):
                raise PermissionError('scoring_may_only_launch_retained_read_only_git_reads')
            subprocesses.append({'executable':executable,'command':command,'repository':str(work.resolve())})
        elif event in ('socket.connect','socket.bind','os.system','os.spawn','os.exec','os.posix_spawn','os.startfile'):
            raise PermissionError('scoring_has_no_live_or_network_operations')

    start = time.perf_counter_ns()
    sys.addaudithook(guard)
    status = 0
    failure = None
    try:
        sys.argv = arguments
        run_path(str(entry),run_name='__main__')
    except SystemExit as error:
        status = error.code if type(error.code) is int else 0 if error.code is None else 1
    except Exception as error:
        status = 1
        failure = {'type':type(error).__name__,'message':str(error)}
    finally:
        end = time.perf_counter_ns()
        files = {Path(__file__).resolve(),Path(sys.executable).resolve(),entry}
        files.update(Path(path).resolve() for path in executed if Path(path).is_file())
        files.update(Path(path).resolve() for module in tuple(sys.modules.values())
                     if isinstance(path:=getattr(module,'__file__',None),str) and Path(path).is_file())
        with receipt.open('x',encoding='utf-8',newline='\n') as stream:
            json.dump({'entry':str(entry),'argv':arguments,'pid':os.getpid(),'parent_pid':os.getppid(),
                       'working_directory':str(Path.cwd()),'started_ns':start,'closed_ns':end,
                       'elapsed_ns':end-start,'entry_return_code':status,'entry_exception':failure,
                       'read_only_git_processes':subprocesses,'source_pins':[pin(path) for path in sorted(files)],
                       'new_Blender':0,'new_models':0,'new_rasters':0},stream,ensure_ascii=False,indent=2,
                      sort_keys=True,allow_nan=False)
            stream.write('\n')
    return status


if __name__ == '__main__':
    raise SystemExit(run())
