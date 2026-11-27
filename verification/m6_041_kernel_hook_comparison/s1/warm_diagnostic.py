"""Seven paired blocks of unchanged G60 queries and Yanyite source-region reads."""
from __future__ import annotations
import argparse, json, pathlib, statistics, sys, time, traceback
from itertools import groupby

ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import s1
from finish_yanyite import after_flush
import audit
NOW=time.perf_counter_ns
FOLDER=ROOT/'warm_diagnostic'
PLAN=FOLDER/'PLAN.json'
ORDERS=[["032","r3"] if i%2==0 else ["r3","032"] for i in range(7)]
STEPS={
    "G60":[("first_nearest","G60_nearest","nearest"),("warm_nearest","G60_nearest","nearest"),
           ("first_scan_after_nearest","G60_scan","scan"),("warm_scan","G60_scan","scan")],
    "Yanyite":[("first_high","Yanyite","high"),("warm_high","Yanyite","high")]}
def freeze():
    FOLDER.mkdir(exist_ok=False)
    source=s1.read(s1.PLAN)
    val={"status":"frozen_before_diagnostic","reason":"Owner requested these additional denominators after seeing S1 single-slot results. Earlier S1 gates and attempts stay in their original denominators.",
         "arm_sources":source["arms"],"asset_pins":{k:source["assets"][k] for k in STEPS},"parent":s1.pin(s1.PLAN),
         "schedule":[[asset,n,a] for asset in STEPS for n,order in enumerate(ORDERS,1) for a in order],
         "steps":STEPS,"requests":{asset:{key:source['requests'][scenario][q] for key,scenario,q in rows} for asset,rows in STEPS.items()},
         "state":"Each asset owns one standard GUI document and unchanged native copy throughout its seven paired blocks. Every group/arm uses a new externally pinned service, new state, new audit and original 30s bound. Initial service reads are measured separately; warm = immediately repeated identical request, no GUI edits. Host cache naturally persists across arms; G60 scan first follows nearest. Source-region warm means repeated exact box; no undocumented cache hit assumed.",
         "comparison":"Per workload compare paired medians of R3-032 ms and R3/032-1. Material regression only if both are strictly greater than +5ms and +0.05. Also retain individual paired deltas/ratios, first reads, invalid slots and cleanup. Do not infer tail quantiles.",
         "source":{str(p):s1.pin(p) for p in (pathlib.Path(__file__),ROOT/'s1.py',ROOT/'finish_yanyite.py',ROOT/'audit.py')}}
    s1.dump(PLAN,val);print(s1.pin(PLAN))
def loop_cell(asset,group,arm,host,start_geometry,svc,plan):
    folder=FOLDER/'cells'/(asset+'_'+str(group)+'_'+arm);folder.mkdir(parents=True)
    client=None;items=[];errors=[];cl=None;entered=NOW()
    try:
        client=svc.Client(folder/'client',host,asset,plan["arm_sources"][arm]);client.open(asset);ready=NOW()
        for key,scenario,q in STEPS[asset]:
            req=plan["requests"][asset][key]
            before={k:svc.transport.counters(pid) for k,pid in [('host',host.pid),('product',client.server_pid)]}
            row=client.observe(req);end=NOW()
            after={k:svc.transport.counters(pid) for k,pid in [('host',host.pid),('product',client.server_pid)]}
            info=after_flush(client,row);body=row['result']
            item={"label":key,"response_ms":(end-row["timing"]["started_ns"])/1e6,"timing":row['timing'],
                "tool_error":row['tool_error'],"rpc_error":row['rpc_error'],"value":body,"trace":info,"OS_before":before,"OS_after":after}
            items.append(item)
            s1.dump(folder/(key+".json"),item)
            s1.need(not row['tool_error'] and not row['rpc_error'],"completed read")
            if asset=="G60":
                truth=s1.read(s1.INPUTS["G60_040_"+("nearest" if "nearest" in key else "scan")])
                s1.need(audit.geometric(body)==audit.geometric(truth),"G60 exact prior geometry")
                work=info['work'][0]
                s1.need((work['result_cache_hit'] and work['kernel_calls']==0) if key.startswith("warm") else
                         (not work['result_cache_hit'] and work['kernel_calls']==(11 if "nearest" in key else 66)),"cold or warm actual work")
            else:
                truth=s1.read(s1.INPUTS["Yanyite"])["regions"]["high"]
                s1.need(body['status']=='complete' and body['source_triangle_a']==min(truth['source_witness_triangle_ids']) and
                        body['source_triangle_b']==min(truth['cube_witness_triangle_ids']) and body['distance_m']==truth['distance_m'] and
                        body['point_a_m']==truth['source_point_world_m'] and body['point_b_m']==truth['reference_point_world_m'],"Yanyite independent oracle")
        s1.need(all(audit.geometric(items[i]['value'])==audit.geometric(items[i+1]['value']) for i in range(0,len(items),2)),"same-source warm output")
    except BaseException:
        errors.append(traceback.format_exc())
    finally:
        if client is not None:
            try:
                rc=client.close();cl=s1.read(folder/'client/CLOSE.json')
                s1.need(rc==0 and cl['method']=='eof' and not client.reader.is_alive(),"owned EOF close")
            except BaseException:errors.append(traceback.format_exc())
    result={"group":group,"arm":arm,"asset":asset,"start_ns":entered,"ready_ns":locals().get('ready'),"end_ns":NOW(),
        "rows":items,"errors":errors,"close":cl,"valid":not errors and len(items)==len(STEPS[asset]),"host_pid":host.pid}
    s1.dump(folder/"CELL.json",result)
    print(asset,group,arm,'ok' if result['valid'] else errors,flush=True)
    return result
def run():
    p=s1.read(PLAN);s1.need(all(s1.pin(k)==v for k,v in p['source'].items()),"diagnostic runner drift")
    prior=s1.read(s1.PLAN);s1.need(s1.pin(s1.PLAN)==p['parent'] and s1.source_plan()==p['arm_sources'],"external pins")
    w=s1.read(FOLDER/'WINDOW.json');g,svc=s1.api()
    hosts=[];cells=[]
    for asset,rows in groupby(p['schedule'],key=lambda r:r[0]):
        directory=FOLDER/asset;directory.mkdir();host=None;receipt={};receipt['start_ns']=NOW()
        try:
            host=g.Owned(directory/'native',p['asset_pins'][asset],prior['support'],w)
            before=s1.loadsnap(host,'BEFORE',directory)
            s1.need(s1.check_input(asset,before,svc),"bound frozen asset")
            for _,group,arm in rows:
                cells.append(loop_cell(asset,group,arm,host,before,svc,p))
            after=s1.loadsnap(host,'AFTER',directory)
            s1.need(s1.geokey(before)==s1.geokey(after),"unchanged source")
            receipt['geometry_preserved']=True
        except BaseException:receipt['error']=traceback.format_exc()
        finally:
            if host:
                try:receipt['close']=host.close()
                except BaseException:receipt['close_error']=traceback.format_exc()
            receipt['end_ns']=NOW();s1.dump(directory/'HOST.json',receipt);hosts.append(receipt)
    analyze(p,cells,hosts)
def analyze(p,cells,hosts):
    indexes={(c['asset'],c['group'],c['arm']):c for c in cells}
    scores={}
    for asset,seq in STEPS.items():
        for i,(label,_,_) in enumerate(seq):
            rows=[]
            for group in range(1,8):
                a=indexes.get((asset,group,'032'),{});b=indexes.get((asset,group,'r3'),{})
                if not a.get('valid') or not b.get('valid'):
                    rows.append({"group":group,"valid":False});continue
                aa,bb=a['rows'][i],b['rows'][i]
                same=audit.digest(audit.norm(aa['value'],aa['trace']['source']))==audit.digest(audit.norm(bb['value'],bb['trace']['source']))
                t1,t2=aa['response_ms'],bb['response_ms']
                rows.append(dict(group=group,valid=same,order=ORDERS[group-1],baseline_ms=t1,r3_ms=t2,
                                 delta_ms=t2-t1,relative=t2/t1-1))
            valid=all(r['valid'] for r in rows)
            m=statistics.median
            v={"rows":rows,"all_seven_matched":valid,"diagnostic_primary":label.startswith('warm')}
            if valid:
                d=m(r['delta_ms'] for r in rows);pdelta=m(r['relative'] for r in rows)
                v.update(median_delta_ms=d,median_relative=pdelta,baseline_median_ms=m(r['baseline_ms'] for r in rows),
                    r3_median_ms=m(r['r3_ms'] for r in rows),material_regression=(d>5 and pdelta>.05) if label.startswith('warm') else None)
            scores[asset+'_'+label]=v
    s1.dump(FOLDER/'RESULTS.json',dict(status='complete' if len(cells)==28 and all(c['valid'] for c in cells) and all(h.get('geometry_preserved') and h.get('close',{}).get('status')=='pass' for h in hosts) else 'incomplete',
                  plans=s1.pin(PLAN),cells=len(cells),actual_responses=sum(len(c['rows']) for c in cells),hosts=hosts,scores=scores))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('freeze','run'));a=p.parse_args()
    if a.action=='freeze':freeze()
    else:run()

