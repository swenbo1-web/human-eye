"""Shared isolated math for A2/C2, preserving the original perf-counter window."""
from dataclasses import asdict
from pathlib import Path
import json,os,queue,subprocess,sys,threading,time
from .compute import ComputeLimits,ComputeError
from .deadline import EpisodeDeadline

def run_common_compute(code,scene,budget,limits=None):
    if (type(budget) is not EpisodeDeadline or budget.clock is not time.perf_counter
            or not budget.watchdog_active):
        raise ValueError('common computation needs the original perf-counter watchdog')
    limits=limits or ComputeLimits();budget.check()
    end=min(budget.expires_at,time.perf_counter()+limits.seconds)
    info=time.get_clock_info('perf_counter')
    descriptor={key:getattr(info,key) for key in ('implementation','monotonic','adjustable','resolution')}
    payload=json.dumps({'code':code,'scene':scene,'limits':asdict(limits),
        'deadline_perf_counter':end,'clock':descriptor},ensure_ascii=False,allow_nan=False).encode('utf8')
    if len(payload)>32*1024*1024:raise ComputeError('compute input exceeds32MiB')
    budget.check()
    if time.perf_counter()>=end:raise ComputeError('compute time exhausted preparing input')
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',PYTHONNOUSERSITE='1')
    for key in ('PYTHONPATH','PYTHONHOME','HUMAN_EYE_CONFIG'):env.pop(key,None)
    child=subprocess.Popen([sys.executable,'-I','-B','-X','utf8',str(Path(__file__).with_name('common_compute_worker.py'))],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    replies=queue.Queue(maxsize=1);worker=None;timer=None;unregister=None
    def stop():
        if child.poll() is None:
            try:child.kill()
            except OSError:pass
    def exchange():
        try:replies.put(('ok',child.communicate(payload)))
        except BaseException as exc:replies.put(('error',type(exc).__name__))
    try:
        unregister=budget.add_expiry_callback(stop)
        timer=threading.Timer(max(0.,end-time.perf_counter()),stop);timer.daemon=True;timer.start()
        worker=threading.Thread(target=exchange,name='common-compute-owned-io',daemon=True);worker.start()
        wait=end-time.perf_counter()
        if wait<=0:raise ComputeError('common compute deadline exceeded before send')
        try:kind,value=replies.get(timeout=wait)
        except queue.Empty:raise ComputeError('common compute process deadline exceeded') from None
        budget.check()
        if time.perf_counter()>=end:raise ComputeError('late common compute result withheld')
        if kind!='ok' or child.returncode!=0:raise ComputeError('common compute worker stopped without result')
        out,err=value
        if len(out)>limits.output_bytes+4096:raise ComputeError('common compute response exceeds limit')
        try:response=json.loads(out)
        except (ValueError,UnicodeError):raise ComputeError('invalid common compute return') from None
        if type(response) is not dict or response.get('ok') is not True:
            raise ComputeError(response.get('detail','common compute rejected') if type(response) is dict else 'invalid common compute result')
        budget.check()
        if time.perf_counter()>=end:raise ComputeError('late parsed common compute result withheld')
        return response['value']
    finally:
        if timer is not None:timer.cancel()
        if unregister is not None:unregister()
        stop()
        try:child.wait(timeout=1.)
        except subprocess.TimeoutExpired:raise ComputeError('common compute cleanup deadline exceeded') from None
        if worker is not None and worker.ident is not None:
            worker.join(timeout=1.)
            if worker.is_alive():raise ComputeError('common compute I/O cleanup incomplete')
        for stream in (child.stdin,child.stdout,child.stderr):
            if stream is not None:stream.close()
