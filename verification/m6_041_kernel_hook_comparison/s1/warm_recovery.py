"""One recovery of G60 warm scan requests absent from the first diagnostic."""
import sys,pathlib,types,hashlib,traceback,time,ast
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import s1,audit,warm_diagnostic as original
def main():
    plan=s1.read(original.PLAN); out=ROOT/'warm_scan_recovery';out.mkdir(exist_ok=False)
    need= s1.need; initial=ROOT/'warm_diagnostic'
    need(sum(1 for k in initial.joinpath('cells').glob('G60_*/CELL.json'))==14,"all original G60 services ended")
    for p in initial.joinpath('cells').glob('G60_*/CELL.json'):
        q=s1.read(p);need([r['label'] for r in q['rows']]==['first_nearest','warm_nearest','first_scan_after_nearest'],"unexpected original inventory")
        need(q['close']['method']=='eof' and q['close']['exit_code']==0,"original client recovery boundary")
    source=(ROOT/'warm_diagnostic.py').read_text(encoding='utf8')
    lhs='"nearest" if "nearest" in key else "scan"';rhs='"nearest" if req["arguments"]["query"]["mode"]=="surface_nearest" else "scan"'
    lhs2='(11 if "nearest" in key else 66)';rhs2='(11 if req["arguments"]["query"]["mode"]=="surface_nearest" else 66)'
    need(source.count(lhs)==source.count(lhs2)==1,"unique exact amendment")
    corrected=source.replace(lhs,rhs).replace(lhs2,rhs2)
    path=out/'CORRECTED_DRIVER.py'
    with path.open('x',encoding='utf8',newline='\n') as f:f.write(corrected)
    runner=types.ModuleType('warm_diagnostic_after_query_mode_repair');runner.__file__=str(ROOT/'warm_diagnostic.py')
    exec(compile(corrected,str(path),'exec'),runner.__dict__)
    runner.FOLDER=out
    s1.dump(out/'PLAN.json',{"parent":s1.pin(original.PLAN),"original":s1.pin(ROOT/'warm_diagnostic.py'),"driver":s1.pin(path),"recovery":s1.pin(pathlib.Path(__file__)),
        "schedule":[r for r in plan['schedule'] if r[0]=='G60'],"reason":"Historical lookup mistakenly dispatched by substring in display label first_scan_after_nearest. Use actual query.mode in both prior-geometry and expected-work assertions.",
        "use":"Only originally absent warm_scan enters the 7 paired primary observations; additional prefill/nearest measurements are recovery cost only. No replacement of recorded originals. No reruns after this recovery."})
    g,svc=s1.api(); prior=s1.read(s1.PLAN);h=None;res=[];receipt={'start_ns':time.perf_counter_ns()}
    try:
        h=g.Owned(out/'native',plan['asset_pins']['G60'],prior['support'],s1.read(initial/'WINDOW.json'))
        before=s1.loadsnap(h,'BEFORE',out);need(s1.check_input('G60',before,svc),"original native geometry")
        for asset,group,arm in plan['schedule']:
            if asset=='G60':res.append(runner.loop_cell(asset,group,arm,h,before,svc,plan))
        after=s1.loadsnap(h,'AFTER',out);need(s1.geokey(before)==s1.geokey(after),"no geometry change")
        receipt['geometry_preserved']=True
    except BaseException:receipt['error']=traceback.format_exc()
    finally:
        if h:
            try:receipt['close']=h.close()
            except BaseException:receipt['close_error']=traceback.format_exc()
        receipt['end_ns']=time.perf_counter_ns();s1.dump(out/'HOST.json',receipt)
    print('recovery',len(res),sum(x['valid'] for x in res),receipt.get('close',{}).get('status'),flush=True)
if __name__=='__main__':main()

