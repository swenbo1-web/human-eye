"""Report the original public capability receipt; no new product call."""
from pathlib import Path
import hashlib
import json

OUT = Path(__file__).resolve().parent
load = lambda name: json.loads((OUT / name).read_bytes())


def main():
    r = load('qa_01/RESULTS.json'); p = load('qa_01/PLAN.json')
    outer = load('qa_invocation_01/RESULT.json'); source = load('SOURCE_FREEZE.json')
    assert r['passed'] and r['capability_gap_observed']
    assert r['product_attempts'] == 1 and r['total_RPC_attempts'] == 2
    first = r['public_calls'][0]; public = first['public_value']
    schedule = '\n'.join(f"| {x['state']} | {x['candidate']} | {x['status']} | {x.get('reason','')} |" for x in r['schedule'])
    originals = '\n'.join(f"| {Path(x['source_path']).name} | {x['sha256']} |" for x in source['originals'])
    static = (OUT / 'SUPPORT_MATRIX.md').read_text(encoding='utf8').replace('# COMPLEX-REENTRY-001 static public support map', '## 静态支持矩阵', 1)
    audit = (OUT / 'ENTRY_AUDIT.md').read_text(encoding='utf8')
    if audit.startswith('# '): audit = '#' + audit
    report = f"""# COMPLEX-REENTRY-001

已确认当前公开实体关系的必要能力缺口。本轮原初始 Object_01/Object_03 请求来源、对象及当前几何绑定正确，事实 solid_relation 返回 status=unknown、value=null、reason=unsupported_solid_geometry；顶层 task_query 为 {public['status']}，MCP isError={first['public_isError']}。这不是参数或传输错误，也没有完成原装配题。按停止规则立即关闭；其余八项未运行，没有重复三状态拒绝或新模型消费。

固定基线 a4465a388b73ce144035d9139afb48f61519163a；产品 0ad59befeee43c2fad752e3bad2ee69f87af3136；131 源 canonical 82dbf9b3a68e0c21d085ac8289ca0e504da567b4cce7300ce697d602c2e4f0c6。产品源码变化0、新候选0、模型消费者/答案0。SOURCE_FREEZE、准备 FREEZE、原帧/脚本和执行守卫保留实际字节关系。

## 原题、实际入口与分母

使用原提交8ab8f0bea915475ebeb557d3e5f62544a7ba174a的assembly题面和原scene/patch/snapshot字节，没有重建资产。scene只复制到私有目录；QA patch配置已固定但未应用、未保存原文件。原完整场景是4网格72点132三角面；本次只采集所选Object_01/Object_03两网格56点108面，目录candidate_count4不能替代三个候选的完整实体关系覆盖。

| 原件 | SHA256 |
|---|---|
{originals}

首次公开参数：

```json
{json.dumps(first['arguments'], ensure_ascii=False, indent=2)}
```

实际1/9公开观察、1/1私有NativeSession、2/16物理RPC（所选capture背后的execute1＋owner close1）。初始化、initialized通知和tools/list是另外三个stdio帧，未产生产品capture。原600秒会话期限不重置，单请求20秒、host/native10秒保持。独立审计核对原始socket的Object_01/Object_03名字/ID、原local→matrix→world坐标、oriented三角面、scene fingerprint/revision、source/runtime82db及selected2-of4。公开unknown有这些当前绑定，不借surface距离0代替穿插。

| 状态 | 候选 | 本轮状态 | 原因 |
|---|---|---|---|
{schedule}

未运行项包括其他两基线候选、unchanged/changed所有观察、原生readback和四点patch。它们不算本轮通过，也不使用旧九次拒绝填分母。完整原题答案质量、P/N模型消费、三态缓存连续性及模型收益均未运行。单次captured selected geometry并不证明全场实体诊断能力或驻留优化。

## 能力出口

当前公开task确有solid_relation，先走认证凸shell/凸组件SAT，再走world-axis orthogonal fallback。原目标是连通带孔凹闭体；当前凸支路拒绝连通凹shell，不将其替成全局凸包。原绑定world坐标每轴48平面，超过orthogonal的16上限，面也不是world轴恒定面。这些细条件来自固定源码和实际绑定快照的静态核对；公开回执只给通用unsupported_solid_geometry，没有伪称取得内部instrumented细因。

最小下一项建议仅是原题需要的该类连通、带孔、非正交凹闭体与探针之间的只读实体关系支持设计，交根深审。本批不实现新判据、不求原题未要求的全局最小脱离向量，不扩到动作、写权限或其他域。surface_proximity可以提供独立无符号量，但不能补上未知实体关系。本批未额外调用它。未知measurement不缓存是静态代码事实；本轮只有一次请求，未实测重复命中。

## 适配失败、时间与资源

准备首遍错误记录在prepare_failures：控制器只接受STATE的granted前缀，而根已签发的同token状态为active_dispatched。随后父代理误调用外层脚本，它因缺PLAN在Popen之前停止；空目录及记录保留。两步均0会话/0RPC。只使用一次允许的适配修正，显式接受active_dispatched，同时继续核固定WINDOW、token/owner/caps/source/expiry，并改为prepare成功后才启动。旧控制器a93b01ac…和实际冻结控制器54c4835b…都保留。此后只实际启动一个会话，没有现场重试或未知动作重发。

复制/源码预检内部 {source['copy_precheck_elapsed_ns']/1e9:.7f}s；首个prepare失败工具.2103767s、未启动外层失败工具.1815351s；成功prepare内部 {p['prepare_elapsed_ns']/1e9:.7f}s（工具外层6.1391343s）。真实QA完整外层 {outer['wall_ns']/1e9:.7f}s，从 {outer['started_utc']} 至 {outer['ended_utc']}；controller {r['whole_controller_ns']/1e9:.7f}s、Native启动 {r['native_startup_ns']/1e9:.7f}s、公开observe包装 {first['elapsed_ns']/1e9:.7f}s。stdio生命周期 {r['stdio_cleanup']['elapsed_ns']/1e9:.7f}s、Native close {r['native_cleanup']['elapsed_ns']/1e9:.7f}s；这些边界嵌套，不能相加或把准备/测量开销当免费。

字节：product socket TX/RX {r['boundary_totals']['product_TX_bytes']}/{r['boundary_totals']['product_RX_bytes']} B；close {r['boundary_totals']['control_TX_bytes']}/{r['boundary_totals']['control_RX_bytes']} B；完整stdio {r['boundary_totals']['stdio_TX_bytes']}/{r['boundary_totals']['stdio_RX_bytes']} B。逻辑LF执行及CRLF磁盘脚本/stdout分别核对。58个已加载模块guard和全部execution/namespace witness成立，generation compatible；第三方/test依赖不扩大为产品guard。

外层Popen4984、stdio19412、Native10896各owner exit0/reap；controller self29812只有记录，没有直接owner-wait或新增OS查询，不补造stopped。worker事件completed/unknown保留，另有closed response；poisoned=false，qa_patch_applied=false，原期限与初末fingerprint相同、原资产/helper字节匹配。已知owner与末态文件检查不证明未知后代、瞬时回滚或Python沙箱。没有额外信号/进程查询。

MANAGEMENT_START/CLOCK记录从13:33:28Z到封存的完整实施elapsed下界，包含静态映射、适配失败、准备、嵌套QA与并行审计；最终终审/提交/回传尾段由完成聊天metadata补全，45分钟实施期限和600秒会话期限分别保留。作者/子审token、费用、CPU/heap未测；没有新模型用量或收益测量。

独立审计详见 ENTRY_AUDIT.md/json（52/52检查，54份原件稳定）；公开支持矩阵及代码行/静态条件详见 SUPPORT_MATRIX.md/json。

## 封存

EVIDENCE_INDEX直接覆盖本批源快照、固定输入、控制器/适配失败、原始MCP/socket/worker/owner证据、审计与报告；排除索引自身和直接bytecode/cache。旧保护标记、旧运行和原作者资产保持。最终提交的所有索引成员会逐字节核Git blob；仅新增本批目录。STATE由根维护；Google/API/key/503、原资产、共享GUI/default9876、正式配置和竞争分支保持原边界。本批完成回传后结束，不自启下一轮。
"""
    (OUT / 'REPORT.md').write_text(report, encoding='utf8', newline='\n')
    print(json.dumps(dict(report_sha256=hashlib.sha256((OUT / 'REPORT.md').read_bytes()).hexdigest())))


if __name__ == '__main__': main()
