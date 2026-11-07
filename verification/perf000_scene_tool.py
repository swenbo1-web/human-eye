"""Thin numeric-only direct tool; ownership and budgets stay in the R2 broker."""
from __future__ import annotations
import argparse,ast,json,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from verification.visual004_native import check,need,save,sha
from verification.visual004_session import client


def _error(value):
    sys.stderr.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n')


def _request(workspace,operation,arguments,include_image):
    started=time.perf_counter_ns();workspace=Path(workspace).resolve()
    need(workspace.is_dir(),'perf000_existing_workspace')
    request=dict(request_id='perf000-'+uuid.uuid4().hex,operation=operation,args=arguments)
    folder=workspace/'perf000_calls'/request['request_id'];folder.mkdir(parents=True,exist_ok=False)
    reply=None;error=None
    try:
        save(folder/'REQUEST.json',request)
        if include_image:raise ValueError('UNAVAILABLE: PERF-000 numeric audit has no image delivery; no image was shown.')
        # client performs the existing strict SESSION/broker/helper/source and
        # original-deadline binding. N never imports the product here; P's
        # actual product entry additionally enforces its candidate runtime pin.
        reply=client(workspace,request);save(folder/'REPLY.json',reply)
    except BaseException as exc:
        error=dict(type=type(exc).__name__,message=str(exc));save(folder/'ERROR.json',error);raise
    finally:
        audit=dict(operation=operation,started_ns=started,finished_ns=time.perf_counter_ns(),
            elapsed_ns=time.perf_counter_ns()-started,helper_sha256=sha(__file__),error=error,
            include_image_requested=bool(include_image),actual_image_delivery=False,automatic_retries=0,
            scope='thin coordinator bookkeeping; raw broker requests/replies retained; not model token usage')
        save(folder/'AUDIT.json',audit)
    try:check(reply['original_deadline_ns'])
    except Exception as exc:
        error=dict(type=type(exc).__name__,message=str(exc));save(folder/'ERROR.json',error)
        audit.update(error=error,delivery_rejected=True,finished_ns=time.perf_counter_ns(),elapsed_ns=time.perf_counter_ns()-started)
        save(folder/'AUDIT.json',audit,replace=True);raise
    return reply


def _deliver(reply,operation):
    if not reply.get('ok'):
        _error(reply.get('error',reply));return 1
    result=reply['result']
    if operation=='native_run':
        sys.stdout.write(result.get('stdout',''));sys.stderr.write(result.get('stderr',''))
        if result.get('script_error') is not None:_error(result['script_error'])
        return int(not reply.get('operation_succeeded',False))
    for text in result.get('mcp_text',[]):
        sys.stdout.write(text)
        if not text.endswith('\n'):sys.stdout.write('\n')
    if result.get('rpc_error') is not None:_error(result['rpc_error'])
    return int(not reply.get('operation_succeeded',False))


def native(workspace,code,*,include_image=False):
    """Print the actual native stdout/errors; retain its persistent namespace."""
    try:return _deliver(_request(workspace,'native_run',dict(code=code),include_image),'native_run')
    except Exception as exc:_error(dict(type=type(exc).__name__,message=str(exc)));return 1


def observe(workspace,*,focal_id=None,reference_id=None,query=None,task_instruction=None,response_detail=None,include_image=False):
    """Print actual P MCP text once, without selecting objects or solving."""
    arguments=dict(include_image=False)
    for name,value in dict(focal_id=focal_id,reference_id=reference_id,query=query,
        task_instruction=task_instruction,response_detail=response_detail).items():
        if value is not None:arguments[name]=value
    try:return _deliver(_request(workspace,'observe',dict(arguments=arguments),include_image),'observe')
    except Exception as exc:_error(dict(type=type(exc).__name__,message=str(exc)));return 1


def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='operation',required=True)
    ordinary=commands.add_parser('native');product=commands.add_parser('observe')
    for command in (ordinary,product):
        command.add_argument('--workspace',type=Path,required=True);command.add_argument('--image',action='store_true')
    code=ordinary.add_mutually_exclusive_group(required=True);code.add_argument('--code');code.add_argument('--script',type=Path)
    product.add_argument('--focal');product.add_argument('--reference');product.add_argument('--query-literal', help=(
        "Python dict literal. For mode='task', include only mode, objects and requested_facts. "
        "The text CLI automatically sets include_image=false outside query; do not put it inside task query. "
        "Legacy query modes remain supported."))
    product.add_argument('--instruction');product.add_argument('--detail',choices=('full','brief'))
    args=parser.parse_args(argv)
    try:
        if args.operation=='native':
            code=args.code if args.code is not None else args.script.read_text(encoding='utf-8-sig')
            return native(args.workspace,code,include_image=args.image)
        query=ast.literal_eval(args.query_literal) if args.query_literal is not None else None
        return observe(args.workspace,focal_id=args.focal,reference_id=args.reference,query=query,
            task_instruction=args.instruction,response_detail=args.detail,include_image=args.image)
    except Exception as exc:_error(dict(type=type(exc).__name__,message=str(exc)));return 1


if __name__=='__main__':raise SystemExit(main())
