"""One-shot restricted compute worker for the common perf-counter branch."""
from pathlib import Path
import json,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from verification.model_trial.compute import RestrictedCompute,ComputeLimits,ComputeError

def clock_descriptor():
    info=time.get_clock_info('perf_counter')
    return {key:getattr(info,key) for key in ('implementation','monotonic','adjustable','resolution')}

def main():
    try:
        raw=sys.stdin.buffer.read(32*1024*1024+1)
        if len(raw)>32*1024*1024:raise ComputeError('compute input exceeds32MiB')
        request=json.loads(raw)
        if type(request) is not dict or set(request)!={'code','scene','limits','deadline_perf_counter','clock'}:
            raise ComputeError('invalid trusted common compute envelope')
        if request['clock']!=clock_descriptor() or request['clock'].get('monotonic') is not True:
            raise ComputeError('common compute clock descriptor differs')
        cap=request['deadline_perf_counter']
        if type(cap) not in (int,float) or time.perf_counter()>=cap:
            raise ComputeError('compute original deadline exhausted before worker')
        value=RestrictedCompute(ComputeLimits(**request['limits']),clock=time.perf_counter).run(
            request['code'],request['scene'],deadline=cap)
        if time.perf_counter()>=cap:raise ComputeError('late common compute result withheld')
        response={'ok':True,'value':value}
    except ComputeError as exc:response={'ok':False,'detail':str(exc)}
    except BaseException as exc:response={'ok':False,'detail':'common compute rejected: '+type(exc).__name__}
    sys.stdout.write(json.dumps(response,ensure_ascii=False,allow_nan=False,separators=(',',':')))
    sys.stdout.flush()

if __name__=='__main__':main()
