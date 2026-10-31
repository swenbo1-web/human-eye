"""Run bounded mathematical work in an owned process that can be terminated."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import json,os,queue,subprocess,sys,threading,time
from .compute import ComputeLimits,ComputeError
from .deadline import EpisodeDeadline

def run_isolated_compute(code,scene,budget,limits=None):
    if type(budget) is not EpisodeDeadline or budget.clock is not time.monotonic:
        raise ValueError('isolated computation needs the shared real monotonic clock')
    limits=limits or ComputeLimits()
    budget.check()
    end=min(budget.expires_at,time.monotonic()+limits.seconds)
    payload=json.dumps({'code':code,'scene':scene,'limits':asdict(limits),
                        'deadline_monotonic':end},ensure_ascii=False,allow_nan=False).encode('utf-8')
    if len(payload)>32*1024*1024: raise ComputeError('compute input exceeds32MiB')
    budget.check()
    if time.monotonic()>=end: raise ComputeError('compute time exhausted preparing input')
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',PYTHONNOUSERSITE='1')
    for name in ('PYTHONPATH','PYTHONHOME','HUMAN_EYE_CONFIG'): env.pop(name,None)
    child=subprocess.Popen([sys.executable,'-I','-B','-X','utf8',str(Path(__file__).with_name('compute_worker.py'))],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    replies=queue.Queue(maxsize=1)
    def kill_owned():
        if child.poll() is None:
            try: child.kill()
            except OSError: pass
    def exchange():
        try: replies.put(('ok',child.communicate(payload)))
        except BaseException as exc: replies.put(('error',type(exc).__name__))
    unregister=None;timer=None;worker=None
    try:
        # Ownership starts at Popen publication, including registration/start
        # failures and a concurrent deadline.close between spawn and register.
        unregister=budget.add_expiry_callback(kill_owned)
        timer=threading.Timer(max(0.,end-time.monotonic()),kill_owned); timer.daemon=True; timer.start()
        worker=threading.Thread(target=exchange,name='trial-compute-owned-io',daemon=True)
        worker.start()
        wait=end-time.monotonic()
        if wait<=0: raise ComputeError('compute process deadline exceeded')
        try: kind,value=replies.get(timeout=wait)
        except queue.Empty: raise ComputeError('compute process deadline exceeded') from None
        budget.check()
        if time.monotonic()>=end: raise ComputeError('late compute result withheld')
        if kind!='ok' or child.returncode!=0: raise ComputeError('compute worker stopped without a result')
        out,err=value
        if len(out)>limits.output_bytes+4096: raise ComputeError('compute response exceeds output limit')
        try: response=json.loads(out)
        except (ValueError,UnicodeError): raise ComputeError('compute worker returned invalid data') from None
        if type(response) is not dict or response.get('ok') is not True:
            raise ComputeError(response.get('detail','compute worker rejected') if type(response) is dict else 'invalid compute result')
        budget.check()
        if time.monotonic()>=end: raise ComputeError('late compute result withheld after parsing')
        return response['value']
    finally:
        if timer is not None: timer.cancel()
        if unregister is not None: unregister()
        kill_owned()
        try: child.wait(timeout=1)
        except subprocess.TimeoutExpired: raise ComputeError('compute worker cleanup deadline exceeded') from None
        if worker is not None and worker.ident is not None:
            worker.join(timeout=1)
            if worker.is_alive(): raise ComputeError('compute worker I/O did not stop after termination')
        for stream in (child.stdin,child.stdout,child.stderr):
            if stream is not None: stream.close()
