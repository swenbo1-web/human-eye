"""Scoped recovery of audit visibility after the two successful Yanyite high requests."""
import json,sys,time,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import s1
original=s1.brief_trace
def after_flush(client,row):
    started=time.perf_counter_ns()
    while True:
        try:
            audit=original(client,row)
        except (json.JSONDecodeError,ValueError) as exc:
            if (not isinstance(exc,json.JSONDecodeError) and str(exc)!="one trace per request") or time.perf_counter_ns()-started>2_000_000_000:
                raise
            time.sleep(.01)
            continue
        return dict(audit,post_response_verify_and_wait_ns=time.perf_counter_ns()-started)
if __name__=="__main__":
    s1.brief_trace=after_flush
    s1.SLOTS=s1.ROOT/'slots_recovery_02'
    source=s1.read(s1.PLAN)
    plan={"scenarios":[["Yanyite","032"],["Yanyite","r3"]],"timing":"whole stdio through response decode recorded before tracing; poll only after response for audit visibility","parent":s1.pin(s1.PLAN),"driver":s1.pin(Path(__file__)),"earlier_highs":[s1.pin(s1.ROOT/'slots_recovery_01'/('Yanyite_'+a)/'SLOT.json') for a in ('032','r3')]}
    s1.dump(s1.ROOT/'YANYITE_RECOVERY.json',plan)
    for scenario,arm in plan["scenarios"]:s1.execute(scenario,arm,s1.read(s1.ROOT/'WINDOW.json'))

