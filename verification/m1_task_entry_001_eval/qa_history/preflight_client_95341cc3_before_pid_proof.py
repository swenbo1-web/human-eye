"""Explicit no-model probe through the same original thin stdio client.

This helper owns only that thin client, never the actor, product or Blender.
Importing it launches nothing. The root supplies requests and the existing
actor endpoint, and separately verifies facts and closes the actor/worker.
"""
import argparse
import json
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
        'thin_pid':None,'exit_code':None,'process_reaped':False,'error':None,'responses':[],
        'client_exit_receipts':[],'backend_close_requested':False,'model_calls':0,'automatic_retries':0}
    process=None;stdout=stderr=b'';communicated=False
    try:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            cwd=output,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        result['thin_pid']=process.pid
        remaining=(value['chain_deadline_ns']-time.perf_counter_ns())/1e9
        if remaining<=0:raise TimeoutError('original_chain_deadline')
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
                    row['confirmed']=bool(a and a.get('pid')==result['thin_pid'] and b.get('pid')==a.get('pid')
                        and b.get('instance_nonce')==a.get('instance_nonce') and b.get('started_ns')==a.get('started_ns')
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
            and result['exit_code']==0 and result['process_reaped'] and result['reply_ids_match']
            and result['client_exit_confirmed'] and result['within_original_deadline'])
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
