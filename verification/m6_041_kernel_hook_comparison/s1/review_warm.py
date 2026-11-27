"""Read-only recomputation from the frozen diagnostic cells, then write a separate review."""
import hashlib,json,statistics,sys
from pathlib import Path
D=Path(__file__).resolve().parent/'warm_diagnostic'
REC=D.parent/'warm_scan_recovery'
sys.path.insert(0,str(D.parent))
import s1,audit
def read(p):return json.loads(p.read_bytes())
def sign(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write(p,v): 
    with p.open('x',encoding='utf8',newline='\n') as f:f.write(v)
def fmtlist(seq):return ', '.join(f'{v:.2f}' for v in seq)
def main():
    plan=read(D/'PLAN.json');res=read(D/'RESULTS.json');records={};checks=[];limits=0
    total=0; extra=0; cost=[]; failed=[]
    for location,scheme in ((D,plan['schedule']),(REC,[r for r in plan['schedule'] if r[0]=='G60'])):
      for name,n,arm in scheme:
        folder=location/'cells'/(name+'_'+str(n)+'_'+arm);cell=read(folder/'CELL.json')
        labels=[r['label'] for r in cell['rows']]
        if name=='G60' and location==D:
            checks.append(not cell['valid'] and labels==['first_nearest','warm_nearest','first_scan_after_nearest'] and len(cell['errors'])==1 and 'G60 exact prior geometry' in cell['errors'][0])
            failed.append(str(folder))
        else:
            checks.append(cell['valid'] and labels==[r[0] for r in plan['steps'][name]])
        checks.append(cell['group']==n and cell['arm']==arm)
        startup=read(folder/'client/STARTUP.json');close=read(folder/'client/CLOSE.json')
        checks.append(startup['actual_pid']==startup['startup_trace']['pid'] and startup['startup_trace']['identity_check']['actual']['source_sha256']==plan['arm_sources'][arm]['source_sha256'] and close['exit_code']==0 and close['method']=='eof')
        for r in cell['rows']:
            total+=1
            req=read(folder/'client'/(r['timing']['id']+'.TX.bin'));wire=read(folder/'client'/(r['timing']['id']+'.RX.bin'))
            val=wire['result'].get('structuredContent')
            if val is None:val=json.loads(wire['result']['content'][0]['text'])
            checks.append(req['params']==plan['requests'][name][r['label']] and r['trace']['source']==plan['arm_sources'][arm]['source_sha256'] and sign(val)==sign(r['value']))
            absolute=req['params']['arguments']['query']['mode']
            if name=='G60':
                ref=s1.read(s1.INPUTS['G60_040_'+{'surface_scan':'scan','surface_nearest':'nearest'}[absolute]])
                checks.append(audit.geometric(val)==audit.geometric(ref))
                work=r['trace']['work'][0]; warm=r['label'].startswith('warm')
                checks.append(work['result_cache_hit']==warm and work['kernel_calls']==(0 if warm else 66 if absolute=='surface_scan' else 11))
            if location==D or r['label']=='warm_scan':
                key=(name,n,arm,r['label']);checks.append(key not in records);records[key]=r
            else:extra+=1
            cost.append(dict(directory=str(folder),group=n,arm=arm,label=r['label'],retained=location==D or r['label']=='warm_scan',response_ms=r['response_ms'],OS_before=r['OS_before'],OS_after=r['OS_after'],tx=r['timing']['tx_bytes'],rx=r['timing']['rx_bytes']))
        limits+=sum(c['tool_error'] or bool(c['rpc_error']) for c in cell['rows'])
    outcome={}
    for name,seq in plan['steps'].items():
        for k,_,_ in seq:
            base=[];r3=[];diff=[];rel=[];equiv=[]
            for n in range(1,8):
                a=records[name,n,'032',k];b=records[name,n,'r3',k]
                x=a['response_ms'];y=b['response_ms'];base.append(x);r3.append(y);diff.append(y-x);rel.append(100*(y/x-1))
                def norm(r):
                    v=dict(r['value']);v.pop('trace_id',None)
                    if 'binding' in v:
                        v['binding']=dict(v['binding']);v['binding'].pop('runtime_source_sha256')
                    return v
                equiv.append(sign(norm(a))==sign(norm(b)))
            med=statistics.median
            result={"baseline_ms":base,"r3_ms":r3,"delta_ms":diff,"relative_pct":rel,"pair_equivalent":equiv,"median_baseline_ms":med(base),'median_r3_ms':med(r3),
                 'paired_median_delta_ms':med(diff),'paired_median_relative_pct':med(rel),'material_regression':med(diff)>5 and med(rel)>5 if k.startswith('warm') else None}
            ref=res['scores'][name+'_'+k]
            checks.append(all(equiv))
            if name=='Yanyite':
                checks.append(all(equiv)==ref['all_seven_matched'])
                if all(equiv):checks.append(abs(ref['median_delta_ms']-med(diff))<1e-8 and abs(ref['median_relative']*100-med(rel))<1e-8 and ref['material_regression']==result['material_regression'])
            outcome[name+'_'+k]=result
    for x in [*res['hosts'],read(REC/'HOST.json')]:checks.append(x['geometry_preserved'] and x['close']['status']=='pass' and x['close']['released_port']['owned_listener'] is False)
    z=dict(all_pass=all(checks),checks=len(checks),errors=sum(not x for x in checks),product_errors=limits,complete_responses=len(records),total_business_responses=total,extra_recovery_prefills=extra,original_partial=failed,all_query_costs=cost,outcome=outcome)
    write(D/'INDEPENDENT_REVIEW.json',json.dumps(z,indent=2,allow_nan=False)+'\n')
    lines=['# S1 七组暖读取诊断','',f'每个资产七组交错配对。最初两个真实普通 Blender GUI 共启动 28 个独立 stdio。G60 的 14 个首轮服务均在第三个正确响应后，因校验程序按标签末尾 nearest 选择了不对应的历史结果而退出，保留原三个响应。按实际 query.mode 离线复核。为取得各槽尚未发出的 warm scan，另起一台相同资产的普通 GUI 和 14 个服务，严格按原次序重建相同三个前置读取后，只采用新取得的 warm scan；其余 {extra} 个额外响应另列成本。共 {total} 个业务响应，固定比较中 {len(records)} 个，3 台 GUI 和 42 个服务正常回收。逐份原始输入、返回、安装身份、缓存工作和进程退出核验共 {len(checks)} 项，失败 {z["errors"]} 项。该诊断是观察到 S1 单次耗时后追加的固定样本，原始主矩阵及失败另行保留。','',
           '| 连续相同输入 | 032 中位 ms | R3 中位 ms | 配对差中位 ms | 配对相对差中位 | 双门实质退化 |','|---|---:|---:|---:|---:|---|']
    for key,val in outcome.items():
        gate=val['material_regression']
        lines.append(f"| {key} | {val['median_baseline_ms']:.2f} | {val['median_r3_ms']:.2f} | {val['paired_median_delta_ms']:+.2f} | {val['paired_median_relative_pct']:+.2f}% | {('是' if gate else '否') if gate is not None else '首读单列'} |")
    lines.extend(['','判据逐工作负载按 7 个配对的 R3−032 毫秒与 R3/032−1 分别取中位数，严格同时超过 +5ms 和 +5% 才触发。G60 暖 nearest 和暖 scan 要求相应实际结果缓存命中且 0 新内核求解。Yanyite 暖读取指同一进程中第二次同一高盒源码测量，未假设未公开的结果缓存。','',
        '## 暖读取的全部配对毫秒','',
        '| 暖请求 | 组序 | 032 | R3 | R3−032 | 相对变化 % |','|---|---:|---:|---:|---:|---:|'])
    for key,v in outcome.items():
        if v['material_regression'] is None:continue
        for n in range(7):lines.append(f"| {key} | {n+1} | {v['baseline_ms'][n]:.2f} | {v['r3_ms'][n]:.2f} | {v['delta_ms'][n]:+.2f} | {v['relative_pct'][n]:+.2f} |")
    lines.extend(['','每组先后顺序交替，从 032→R3 开始。组间保持普通 GUI、操作系统文件缓存与资产不变，两臂分别新建 stdio/状态。跨查询首次 scan 在同服务首次 nearest 之后。所有首次读取和配对明细、请求时的逐进程 CPU/工作集及进程启动/退出见 [RESULTS.json](RESULTS.json)、[独立复算](INDEPENDENT_REVIEW.json) 和 cells 原件。'])
    write(D/'REPORT.md','\n'.join(lines)+'\n')
    print(z['all_pass'],len(records),[(k,round(v['paired_median_delta_ms'],4),round(v['paired_median_relative_pct'],3),v['material_regression']) for k,v in outcome.items()])
if __name__=='__main__':main()

