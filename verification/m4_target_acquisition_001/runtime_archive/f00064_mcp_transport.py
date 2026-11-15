"""Finite newline JSON-RPC framing shared by the persistent stdio entries.

Input limits do not cap native image responses or replace task/report budgets.
A response is encoded completely before its first write; dispatch is never retried.
"""
from __future__ import annotations
import json,math

MAX_INPUT_BYTES=256*1024
MAX_CONTAINER_DEPTH=32
MAX_ID_CHARACTERS=128
MAX_ID_INTEGER=2**53-1


class RPCInputError(ValueError):
    def __init__(self,code,message):
        self.code=code;self.message=message;super().__init__(message)


def rpc_error(request_id,code,message,**data):
    result={'jsonrpc':'2.0','id':request_id,'error':{'code':code,'message':message}}
    if data:result['error']['data']=data
    return result


def unicode_scalar_text(value):
    return type(value) is str and not any(0xD800<=ord(c)<=0xDFFF for c in value)


def valid_id(value):
    return value is None or (type(value) is int and abs(value)<=MAX_ID_INTEGER) or (
        unicode_scalar_text(value) and len(value)<=MAX_ID_CHARACTERS)


def _tree(value,*,input_value,allow_nonfinite=False):
    # Iterative traversal also rejects in-process cycles/depth without recursing.
    stack=[(value,0)];nodes=0;limit=MAX_CONTAINER_DEPTH if input_value else 128
    while stack:
        item,depth=stack.pop();nodes+=1
        if input_value and nodes>MAX_INPUT_BYTES:raise RPCInputError(-32600,'Input value budget')
        if type(item) in (dict,list):
            depth+=1
            if depth>limit:raise RPCInputError(-32600,'JSON depth budget')
            if type(item) is dict:
                for key,child in item.items():
                    if not unicode_scalar_text(key):raise RPCInputError(-32600,'Invalid Unicode object key')
                    stack.append((child,depth))
            else:stack.extend((child,depth) for child in item)
        elif type(item) is str:
            if not unicode_scalar_text(item):raise RPCInputError(-32600,'Invalid Unicode string')
        elif type(item) is float:
            if not allow_nonfinite and not math.isfinite(item):raise RPCInputError(-32700,'Nonfinite JSON number')
        elif item is not None and type(item) not in (int,bool):raise RPCInputError(-32600,'Invalid JSON value')


def validate_request(value,*,allow_nonfinite=False):
    _tree(value,input_value=True,allow_nonfinite=allow_nonfinite)
    if (type(value) is not dict or value.get('jsonrpc')!='2.0'
            or not unicode_scalar_text(value.get('method')) or not 0<len(value['method'])<=256
            or ('id' in value and not valid_id(value['id']))):
        raise RPCInputError(-32600,'Invalid Request')
    # In-process callers receive the same aggregate bound as a decoded frame.
    try:encoded=json.dumps(value,ensure_ascii=False,allow_nan=allow_nonfinite,separators=(',',':')).encode('utf8')
    except (ValueError,TypeError,OverflowError,RecursionError,UnicodeError) as exc:raise RPCInputError(-32600,'Invalid Request') from exc
    if len(encoded)>MAX_INPUT_BYTES:raise RPCInputError(-32600,'Input byte budget')
    return value


def _depth(raw):
    depth=0;quoted=False;escaped=False
    for c in raw:
        if quoted:
            if escaped:escaped=False
            elif c=='\\':escaped=True
            elif c=='"':quoted=False
        elif c=='"':quoted=True
        elif c in '[{':
            depth+=1
            if depth>MAX_CONTAINER_DEPTH:raise RPCInputError(-32700,'JSON depth budget')
        elif c in ']}':depth-=1


def _pairs(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError('Duplicate JSON object key')
        result[key]=value
    return result


def parse_request(raw):
    try:
        if type(raw) is bytes:
            if len(raw)>MAX_INPUT_BYTES:raise RPCInputError(-32700,'Input byte budget')
            text=raw.decode('utf8','strict')
        elif type(raw) is str:
            if len(raw.encode('utf8','strict'))>MAX_INPUT_BYTES:raise RPCInputError(-32700,'Input byte budget')
            text=raw
        else:raise RPCInputError(-32700,'Invalid input frame')
        _depth(text)
        value=json.loads(text,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)),object_pairs_hook=_pairs)
    except RPCInputError:raise
    except (ValueError,TypeError,OverflowError,RecursionError,UnicodeError) as exc:raise RPCInputError(-32700,'Parse error') from exc
    return validate_request(value)


def requests(incoming):
    """Drain only an oversized frame; never treat its tail as a new request."""
    source=getattr(incoming,'buffer',incoming)
    while True:
        try:raw=source.readline(MAX_INPUT_BYTES+1)
        except (OSError,ValueError):return
        if not raw:return
        newline=b'\n' if type(raw) is bytes else '\n'
        if len(raw)>MAX_INPUT_BYTES:
            while not raw.endswith(newline):
                try:raw=source.readline(MAX_INPUT_BYTES+1)
                except (OSError,ValueError):return
                if not raw:break
            yield None,rpc_error(None,-32700,'Input byte budget');continue
        if not raw.strip():continue
        try:value=parse_request(raw)
        except RPCInputError as exc:yield None,rpc_error(None,exc.code,exc.message)
        else:yield value,None


def internal_error(request):
    request_id=request.get('id') if type(request) is dict and valid_id(request.get('id')) else None
    may_have_run=type(request) is dict and request.get('method')=='tools/call'
    return rpc_error(request_id,-32603,'Request response unavailable',
        tool_outcome='unknown' if may_have_run else 'not_applicable',automatic_retry=False)


def encode_response(response,request=None,*,error_fields=None):
    try:
        _tree(response,input_value=False)
        # ASCII escapes avoid relying on the shell/stream locale; image data is
        # unchanged. No input-size cap is applied to output image/report bytes.
        return json.dumps(response,ensure_ascii=True,allow_nan=False)+'\n'
    except (ValueError,TypeError,OverflowError,RecursionError,UnicodeError):
        failure=internal_error(request)
        if error_fields is not None:failure['error']['data'].update(error_fields())
        return json.dumps(failure,ensure_ascii=True,allow_nan=False)+'\n'


def write_encoded(outgoing,encoded):
    try:
        written=outgoing.write(encoded)
        if written is not None and written!=len(encoded):return False
        outgoing.flush()
    except (OSError,ValueError):return False
    return True


def serve(incoming,outgoing,handler):
    for request,error in requests(incoming):
        response=error
        if response is None:
            try:response=handler(request)
            except Exception:response=None if 'id' not in request else internal_error(request)
        if response is not None and not write_encoded(outgoing,encode_response(response,request)):return
