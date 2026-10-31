"""Trusted one-shot worker for the restricted mathematical interpreter."""
from pathlib import Path
import dataclasses,json,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from verification.model_trial.compute import RestrictedCompute,ComputeLimits,ComputeError

def main():
    try:
        raw=sys.stdin.buffer.read(32*1024*1024+1)
        if len(raw)>32*1024*1024: raise ComputeError('compute input exceeds32MiB')
        request=json.loads(raw)
        if set(request)!={'code','scene','limits','deadline_monotonic'}:
            raise ComputeError('invalid trusted compute envelope')
        cap=request['deadline_monotonic']
        if time.monotonic()>=cap: raise ComputeError('compute deadline exhausted before worker')
        result=RestrictedCompute(ComputeLimits(**request['limits'])).run(
            request['code'],request['scene'],deadline=cap)
        if time.monotonic()>=cap: raise ComputeError('late compute result withheld')
        response={'ok':True,'value':result}
    except ComputeError as exc:
        response={'ok':False,'detail':str(exc)}
    except BaseException as exc:
        response={'ok':False,'detail':'compute worker rejected: '+type(exc).__name__}
    sys.stdout.write(json.dumps(response,ensure_ascii=False,allow_nan=False,separators=(',',':')))
    sys.stdout.flush()

if __name__=='__main__': main()
