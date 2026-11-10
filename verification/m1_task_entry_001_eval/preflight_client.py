"""Explicit no-model probe through the same original thin stdio client.

This helper owns only that thin client, never the actor, product or Blender.
Importing it launches nothing. The root supplies requests and the existing
actor endpoint, and separately verifies facts and closes the actor/worker.
"""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ATTACH_PATH=HERE.parent/'native_plugin_complex_003/reused/stdio_attach.py'
MAX_FRAME=24*1024*1024


def encoded(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf8')+b'\n'


def save(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf8',newline='\n')


def _windows_runtime_proof(process,runtime_pid,deadline_ns):
    """One read-only bounded Toolhelp snapshot before sending any stdin."""
    proof={'confirmed':None,'status':'unknown','method':'Windows Toolhelp + process creation times',
        'launcher_pid':process.pid,'runtime_pid':runtime_pid,'max_parent_edges':4,
        'observed_ns':time.perf_counter_ns(),'parent_chain':[],'snapshot_process_count':None,
        'before_stdin':True,'error':None}
    handle=None;kernel=None
    try:
        if os.name!='nt':raise RuntimeError('Windows_process_proof_unavailable')
        if type(runtime_pid) is not int or runtime_pid<=0:raise ValueError('invalid_runtime_pid')
        if time.perf_counter_ns()>=deadline_ns:raise TimeoutError('original_chain_deadline')
        if process.poll() is not None:raise RuntimeError('launcher_exited_before_runtime_proof')
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        class Entry(ctypes.Structure):
            _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),
                ('th32ProcessID',wintypes.DWORD),('th32DefaultHeapID',ctypes.c_size_t),
                ('th32ModuleID',wintypes.DWORD),('cntThreads',wintypes.DWORD),
                ('th32ParentProcessID',wintypes.DWORD),('pcPriClassBase',wintypes.LONG),
                ('dwFlags',wintypes.DWORD),('szExeFile',wintypes.WCHAR*260)]
        kernel.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
        for name in ('Process32FirstW','Process32NextW'):
            fn=getattr(kernel,name);fn.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)];fn.restype=wintypes.BOOL
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
        kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
        kernel.GetProcessTimes.restype=wintypes.BOOL
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        kernel.WaitForSingleObject.restype=wintypes.DWORD
        def birth(proc_handle):
            stamps=[wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(proc_handle,*[ctypes.byref(v) for v in stamps]):
                raise ctypes.WinError(ctypes.get_last_error())
            return (stamps[0].dwHighDateTime<<32)|stamps[0].dwLowDateTime
        # Popen retains its actual launcher process handle, so its creation
        # time is not inferred by reopening a potentially reused numeric PID.
        launcher_birth=birth(int(process._handle))
        proof['launcher_created_filetime']=launcher_birth
        handle=kernel.OpenProcess(0x00101000,False,runtime_pid)  # synchronize + query limited
        if not handle:raise ctypes.WinError(ctypes.get_last_error())
        runtime_birth=birth(handle);proof['runtime_created_filetime']=runtime_birth
        if kernel.WaitForSingleObject(handle,0)!=258:raise RuntimeError('runtime_not_alive_at_proof')
        snapshot=kernel.CreateToolhelp32Snapshot(2,0)
        if snapshot in (None,ctypes.c_void_p(-1).value):raise ctypes.WinError(ctypes.get_last_error())
        rows={}
        try:
            entry=Entry();entry.dwSize=ctypes.sizeof(Entry)
            if not kernel.Process32FirstW(snapshot,ctypes.byref(entry)):raise ctypes.WinError(ctypes.get_last_error())
            while True:
                rows[int(entry.th32ProcessID)]={'pid':int(entry.th32ProcessID),
                    'parent_pid':int(entry.th32ParentProcessID),'exe':str(entry.szExeFile)}
                if len(rows)>32768:raise ValueError('bounded_process_snapshot_limit')
                if time.perf_counter_ns()>=deadline_ns:raise TimeoutError('original_chain_deadline')
                if not kernel.Process32NextW(snapshot,ctypes.byref(entry)):
                    error=ctypes.get_last_error()
                    if error!=18:raise ctypes.WinError(error)
                    break
        finally:kernel.CloseHandle(snapshot)
        proof['snapshot_process_count']=len(rows)
        pid=runtime_pid;child_birth=runtime_birth;seen=set()
        for depth in range(5):
            if pid in seen:raise ValueError('process_parent_cycle')
            seen.add(pid);row=rows.get(pid)
            if row is None:raise RuntimeError('process_absent_from_snapshot')
            row=dict(row,created_filetime=child_birth);proof['parent_chain'].append(row)
            if pid==process.pid:
                if child_birth!=launcher_birth:raise RuntimeError('launcher_creation_binding_mismatch')
                if process.poll() is not None:raise RuntimeError('launcher_exited_during_runtime_proof')
                if kernel.WaitForSingleObject(handle,0)!=258:raise RuntimeError('runtime_exited_during_proof')
                proof.update(confirmed=True,status='confirmed',parent_edges=depth,proved_ns=time.perf_counter_ns())
                return proof,handle
            if depth==4:raise RuntimeError('runtime_outside_bounded_launcher_ancestry')
            parent=row['parent_pid']
            if parent==process.pid:parent_birth=launcher_birth
            else:
                ancestor=kernel.OpenProcess(0x1000,False,parent)
                if not ancestor:raise ctypes.WinError(ctypes.get_last_error())
                try:parent_birth=birth(ancestor)
                finally:kernel.CloseHandle(ancestor)
            if parent_birth>child_birth:raise RuntimeError('parent_creation_after_child_PID_reuse')
            pid=parent;child_birth=parent_birth
    except BaseException as exc:
        proof['error']={'type':type(exc).__name__,'message':str(exc)}
        if handle and kernel is not None:kernel.CloseHandle(handle)
        return proof,None


def _runtime_exit(handle):
    """Observe the retained runtime handle; absence of a PID is not proof."""
    row={'confirmed':None,'exited':None,'exit_code':None,'method':'retained Windows runtime handle',
        'observed_ns':time.perf_counter_ns(),'handle_closed':None}
    if handle is None:
        row['reason']='runtime_ownership_or_handle_unavailable';return row
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
    try:
        state=kernel.WaitForSingleObject(handle,0)
        if state==0:
            code=wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle,ctypes.byref(code)):raise ctypes.WinError(ctypes.get_last_error())
            row.update(confirmed=True,exited=True,exit_code=int(code.value))
        elif state==258:row.update(confirmed=False,exited=False,reason='runtime_still_running')
        else:raise ctypes.WinError(ctypes.get_last_error())
    except BaseException as exc:row['error']=repr(exc)
    finally:row['handle_closed']=bool(kernel.CloseHandle(handle))
    return row


def probe(python,endpoint,output,messages):
    """Launch the original client once, send unchanged messages, then stdin EOF.

    The original endpoint deadline still applies. Tool errors are retained as
    replies, not replayed or promoted to successful fact assertions.
    """
    endpoint=Path(endpoint).resolve();output=Path(output).resolve()
    value=json.loads(endpoint.read_bytes())
    if type(messages) is not list or not messages or any(type(row) is not dict for row in messages):
        raise ValueError('explicit_JSON_RPC_message_list_required')
    frames=[encoded(row) for row in messages]
    if any(len(frame)>MAX_FRAME for frame in frames):raise ValueError('MCP_frame_limit')
    left=(value['chain_deadline_ns']-time.perf_counter_ns())/1e9
    if left<=0:raise TimeoutError('original_chain_deadline')
    output.mkdir(parents=True,exist_ok=False)
    audit=output/'attachments'
    command=[str(python),'-I','-B',str(ATTACH_PATH),'--endpoint',str(endpoint),'--kind','native','--audit',str(audit)]
    wire=b''.join(frames);(output/'TX.bin').write_bytes(wire)
    save(output/'REQUESTS.json',messages)
    result={'command':command,'started_ns':time.perf_counter_ns(),'original_chain_deadline_ns':value['chain_deadline_ns'],
        'launcher_pid':None,'runtime_pid':None,'thin_pid':None,'thin_pid_scope':'actual runtime from STARTED',
        'exit_code':None,'process_reaped':False,'launcher_reaped':False,'launcher_exit_code':None,
        'error':None,'responses':[],'client_exit_receipts':[],'runtime_provenance':None,
        'backend_close_requested':False,'model_calls':0,'automatic_retries':0}
    process=None;runtime_handle=None;stdout=stderr=b'';communicated=False
    try:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            cwd=output,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        result['launcher_pid']=process.pid
        startup_deadline=min(value['chain_deadline_ns'],time.perf_counter_ns()+30*10**9)
        # The thin client publishes STARTED before reading stdin. Do not send
        # even initialize until its runtime is bound to our owned launcher.
        while True:
            if time.perf_counter_ns()>=startup_deadline:raise TimeoutError('thin_STARTED_deadline')
            folders=list(audit.glob('bridge_*'))
            if len(folders)>1:raise ValueError('multiple_thin_instances_before_stdin')
            if folders and (folders[0]/'STARTED.json').exists():
                try:started=json.loads((folders[0]/'STARTED.json').read_bytes())
                except (OSError,ValueError):started=None
                if started is not None:break
            if process.poll() is not None:raise RuntimeError('launcher_exited_before_STARTED')
            time.sleep(.01)
        result['runtime_pid']=started.get('pid');result['thin_pid']=result['runtime_pid']
        result['startup_receipt']=started
        proof,runtime_handle=_windows_runtime_proof(process,result['runtime_pid'],value['chain_deadline_ns'])
        result['runtime_provenance']=proof;save(output/'RUNTIME_PROVENANCE.json',proof)
        if proof['confirmed'] is not True:raise RuntimeError('thin_runtime_ownership_unknown_no_stdin_sent')
        remaining=(value['chain_deadline_ns']-time.perf_counter_ns())/1e9
        if remaining<=0:raise TimeoutError('original_chain_deadline')
        result['stdin_send_started_ns']=time.perf_counter_ns()
        stdout,stderr=process.communicate(wire,timeout=remaining);communicated=True
    except BaseException as exc:
        result['error']={'type':type(exc).__name__,'message':str(exc)}
    finally:
        if process is not None:
            if process.poll() is None:process.kill()
            if not communicated:
                try:stdout,stderr=process.communicate(timeout=5)
                except BaseException as exc:result['cleanup_error']=repr(exc)
            process.wait(timeout=5)
            result['exit_code']=process.poll();result['process_reaped']=process.poll() is not None
            result['launcher_exit_code']=process.poll();result['launcher_reaped']=process.poll() is not None
        result['runtime_exit']=_runtime_exit(runtime_handle)
        (output/'RX.bin').write_bytes(stdout);(output/'stderr.bin').write_bytes(stderr)
        result['attempted_send_bytes']=len(wire);result['sent_bytes']=len(wire) if communicated else None
        result['stdin_delivery']='complete' if communicated else 'unknown';result['received_bytes']=len(stdout)
        try:
            result['responses']=[json.loads(line) for line in stdout.splitlines() if line]
            expected=[row['id'] for row in messages if 'id' in row]
            actual=[row.get('id') for row in result['responses']]
            result['reply_ids_match']=actual==expected
            result['tool_response_bytes']=sum(len(line)+1 for line in stdout.splitlines() if line
                and json.loads(line).get('id') in {row['id'] for row in messages if 'id' in row and row.get('method')=='tools/call'})
        except (ValueError,TypeError,KeyError) as exc:
            result['parse_error']=repr(exc);result['reply_ids_match']=False
        for folder in sorted(audit.glob('bridge_*')):
            started=folder/'STARTED.json';ended=folder/'EXIT.json'
            row={'directory':str(folder),'started':None,'exit':None,'confirmed':None}
            try:
                row['started']=json.loads(started.read_bytes()) if started.exists() else None
                row['exit']=json.loads(ended.read_bytes()) if ended.exists() else None
                if row['exit'] is not None:
                    a,b=row['started'],row['exit']
                    row['confirmed']=bool(a and a.get('pid')==result['runtime_pid'] and b.get('pid')==a.get('pid')
                        and b.get('instance_nonce')==a.get('instance_nonce') and b.get('started_ns')==a.get('started_ns')
                        and a==result.get('startup_receipt')
                        and b.get('normal_exit') is True and b.get('backend_close_requested') is False
                        and type(b.get('ended_ns')) is int and b['ended_ns']>=a['started_ns'])
            except (OSError,ValueError,TypeError,KeyError) as exc:
                row['error']=repr(exc);row['confirmed']=False
            result['client_exit_receipts'].append(row)
        result['client_exit_confirmed']=bool(len(result['client_exit_receipts'])==1
            and result['client_exit_receipts'][0]['confirmed'] is True)
        result['finished_ns']=time.perf_counter_ns()
        result['within_original_deadline']=result['finished_ns']<value['chain_deadline_ns']
        result['confirmed']=bool(not result['error'] and not result.get('cleanup_error') and not result.get('parse_error')
            and result['launcher_exit_code']==0 and result['launcher_reaped'] and result['reply_ids_match']
            and result['client_exit_confirmed'] and result['within_original_deadline']
            and result.get('runtime_provenance',{}).get('confirmed') is True
            and result['runtime_exit']['confirmed'] is True and result['runtime_exit']['exit_code']==0
            and result['runtime_exit']['handle_closed'] is True)
        save(output/'RESULT.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python',required=True,type=Path)
    parser.add_argument('--endpoint',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--requests',required=True,type=Path)
    args=parser.parse_args()
    result=probe(args.python,args.endpoint,args.output,json.loads(args.requests.read_bytes()))
    print(json.dumps({'confirmed':result['confirmed'],'model_calls':0,'output':str(args.output)},ensure_ascii=False))
    raise SystemExit(0 if result['confirmed'] else 1)
