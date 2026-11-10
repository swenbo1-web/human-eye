"""Render the measured ledger, retaining unknowns and incomplete cells."""
from pathlib import Path
import json,statistics
HERE=Path(__file__).resolve().parent
def load(p):return json.loads(Path(p).read_bytes())
s=load(HERE/'SUMMARY.json');l=load(HERE/'LEDGER.json');q=load(HERE/'QUALITY_REVIEW.json')
assert q['audit_valid'] and s['quality']['N']['complete_correct']==36 and s['quality']['P']['complete_correct']==30
def f(v):return '未发/不可用' if v is None else '%.3f'%v
text='''# SCALE-DIAG-001：固定基线的几何、发现与连续状态诊断

2026-11-10。管理员合同为 `D:/hefe/docs/HUMAN_EYE_SCALE_AND_EXPERT_NEXT_STAGE.md`（管理员计划提交 `4364f869c7cde0c40d3bea5b5fbfbee91214f7ee`）。本批只诊断本地引擎，不改变产品代码、算法、准入、期限或正式安装，不运行大模型消费者或训练。

## 判定

当前不能宣称大型复杂任务的收益。固定任务分母为78，Native N完成且正确36/39，已安装插件 P 为30/39。两路所有已报告为成功的数值/名次/所问实体字段均与独立答案相符。P有6个几何准入unknown、3个192对象查询期限耗尽；N最高几何档冷查询超时，随后两个暖格因会话中毒未发出，仍留在分母。**计划78格，实际76次逻辑请求，两个未发格没有补跑或改成冷启动。**

主要瓶颈是M3的逐对精确表面距离遍历，以及在精算前按总组合数拒绝输入。完成的发现/连续变化非缓存查询中，`geometry.nearest_pair_loop`占完整入口约96.2%–98.7%。M2整场景失效会放大这种成本：仅改名也重新计算47对；单个移动/局部编辑同样重算47对。目录、连接、解码均已单独保留，不能把其含义不明的残差解释成某个宿主内部阶段。

## 固定实现和场景

- 产品基线 `d01d49bc0ec82583b24a8faf22e622e6f6ea8c5d`；137个实际安装源，canonical `a50e34c9169e9384047b29fa8bda8a072f96681f64610334ccec367d8597589b`。复用 `.plugin_ab_runtime/B` 已有venv/wheel，生产来源类型为installed_distribution；逐链身份和实际文件核验见QUALITY_REVIEW。
- 五个静态快照：G60_D12、G508、G4092、D48、D192。G-low/D-low共用一份场景，但各自独立cold链。每条静态链一次冷读、两次暖读；每路T固定三轮。Native和P均独立拥有缓存，各T轮从相同冻结初态开始。
- 真实齿槽挤出网格增长为每个相关对象60/508/4092三角形（32/256/2048顶点），并非平面细分。G场景12对象；D为12/48/192对象，相关几何固定为60三角形，所有候选在目标附近、均表面分离，包含AABB重叠。许多候选互相交错，本批是距离/发现规模诊断，不是可制造装配或任意穿插检出资格。
- G显式给Target/Peer_000，分别评分surface距离和closed-solid关系。D/T只给Target，使用完整目录的全局最近**无符号表面**入口，不使用最多3候选的关系工具冒充全局发现。没有预选oracle候选名单。
- 最近peer有切向x/z偏移，避免vertex-only算法碰巧通过。T7为初读、原样复读、改peer名、移动competitor、其局部顶点编辑、删除competitor、重载冻结初态。T3/T4最近变为约1.000016303毫米；其他状态约3.000005905毫米。T4的competitor不再具备该oracle闭体域资格，但本题仅问无符号距离，未冒充闭体成功。
- Native是普通bpy/NumPy、完整三角距离、保守AABB/BVH及持久几何/对象对缓存；先判边穿面，再覆盖点面与边边，不能等同LLM已自行产生该代码。Native闭体判定仅服务已独立验证的双层挤出域，失败时unknown。当前T依靠固定协调事件失效，不能宣称通用自动dirty支持。
- 两路沿用30秒请求预算、570秒独立worker期限。Native与P的socket方式和来源核验固定开销并不完全相同，暖读时应结合分段判断；没有测量并扣减包装器成本。

## 独立答案与来源绑定

`oracle.py`不导入产品或Native实现。对最终实际binary64 worldmesh，以精确有理支持面给全表面下界、实际三角形非负重心见证给上界；遍历全部候选，严格下/上界比较证明唯一最近者。12份静态/连续状态快照共599个候选对均独立有证，最大区间宽度约4.53e-8米，低于冻结1e-6米精度。G三档目标对另有封闭简单挤出资格及实际世界舍入后的分片仿射单射证书；独立审查未发现阻断问题。

`QUALITY_REVIEW.json`与作者ledger独立评分一致：28个冻结文件、18个初态、42个T状态及receipt严格全字段相等；实际安装源核验通过。未放宽为无向三角集。oracle `absolute_error_bound_m`半宽字段可能低报中点舍入的半ulp；保留已冻结原件，**评分只使用外向L/U，计算max(abs(result-L),abs(result-U))，不使用该半宽。**成功格最坏L/U误差约8.94e-17米。本批未对该已知微小展示字段另改版本重采样。

## 静态全部结果

单位毫秒。cold入口包括实际代码/采集/通信/解码/求解/结果JSON编码；setup另列，并计入cold完整成本。暖栏列两次全部值，没有p95/长尾验收。unknown/expired的耗时只表示退出成本。

|格|路径|正确完成|cold入口|cold setup|cold合计|两次warm|状态|
|---|---|---:|---:|---:|---:|---|---|
'''
for row in s['static']:
    warm=row['warm_ms'];values=' / '.join(f(v) for v in warm['all']) if warm else '未发 / 未发'
    total=None if row['cold_entry_ms'] is None else row['cold_entry_ms']+(row['cold_setup_ms'] or 0)
    text+='|%s|%s|%s|%s|%s|%s|%s|%s|\n'%(row['cell'],row['group'],row['correct'],f(row['cold_entry_ms']),f(row['cold_setup_ms']),f(total),values,', '.join(row['outcomes']))
text+='''
G508每对面组合258064超过16384；G4092组合16744464且总面8184超过4096。产品两档surface均为`surface_geometry_work_limit`，solid均为`closed_solid_geometry_work_limit`，没有进入距离精算。G4092总顶点恰好4096，未误写成vertex_budget拒绝。N高档30秒超时只说明此实现/预算内未完成，未得到其精算全部计数，不能写成零工作。

## 连续状态全部步骤

两路T均21/21正确。下表为三轮入口中位毫秒；每步三次全部值和范围在SUMMARY/LEDGER中。内核调用数三轮一致。

|步骤|N中位ms|P中位ms|N/P精算对象对调用|
|---|---:|---:|---|
'''
steps=['0 初读','1 原样复读','2 改名','3 移动竞争件','4 局部网格编辑','5 删除竞争件','6 重载初态']
for i,name in enumerate(steps):
    a=next(r for r in s['T_steps'] if r['group']=='N' and r['step']==i);b=next(r for r in s['T_steps'] if r['group']=='P' and r['step']==i)
    text+='|%s|%s|%s|%s / %s|\n'%(name,f(a['entry_ms']['median']),f(b['entry_ms']['median']),a['kernel_calls'][0],b['kernel_calls'][0])
text+='\n整链含初始化、同等管理变化、必要fullmesh读取、原始证据发布、重载与退出：N三次为 '+', '.join('%.6f秒'%(v/1000) for v in s['T_full_chain_ms']['N']['all'])+'；P为 '+', '.join('%.6f秒'%(v/1000) for v in s['T_full_chain_ms']['P']['all'])+'。中位分别11.376622秒和116.729242秒，P约为N的10.26倍。这是同一个受限资产的三次重复，不能当三份资产覆盖或模型任务收益。\n'
text+='''
## 工作、字节、缓存与完整成本

逐格完整分段在LEDGER.json及原始MEASUREMENT文件中；跨度为inclusive，不能相加。

'''
extracts=[]
for key in ('D_low_P_0','D_mid_P_0','D_high_P_0','T_round_0_P_1','T_round_0_P_2','D_mid_N_0','D_high_N_0'):
    x=next(v for v in l['logical'] if v['key']==key)
    extracts.append({k:x.get(k) for k in ('key','entry_ms','response_bytes','ipc','capture_work','kernel_work','kernel_work_scope','native_work','native_stages','cache_array_bytes','cache_current','product_counts','product_stages','rss_before','rss_after')})
    if x['group']=='P':
        loop=x.get('product_stages',{}).get('geometry.nearest_pair_loop',{}).get('duration_ns',0)/1e6
        cap=x.get('product_stages',{}).get('host.capture_nearest_candidates',{}).get('duration_ns',0)/1e6
        text+='- `%s`：入口%.3fms，host capture %.3fms，nearest loop %.3fms；实际socket发送/接收%s/%s字节，最终MCP JSON%s字节。\n'%(key,x['entry_ms'],cap,loop,x['ipc'].get('socket_send_bytes'),x['ipc'].get('socket_recv_bytes'),x['response_bytes'])
    else:
        text+='- `%s`：目录展开/建索引%.3fms，距离%.3fms；建树%s份，真实triangle精算%s对，索引/数组记账%s字节。\n'%(key,x['native_stages']['directory_expand_index_ns']/1e6,x['native_stages']['distance_ns']/1e6,x['native_work']['index_builds'],x['native_work']['triangle_pairs'],x['cache_array_bytes'])
dump=lambda p,v: p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
dump(HERE/'EXTRACTS.json',extracts)
text+='''
生产capture `source_*`/`expanded_*`描述采集逻辑规模，不能直接当成每次都新to_mesh或新三角化次数；decoder的world_transforms/transformed_vertices为现有可见工作计数。未新增宿主内部目录/求值/三角化计时，具体内部耗时保留未测。IPC exchange包含等待及外层解析；资源解码/world展开、场景normalize、内核、准入、exact准备已分段。超时内核的未返回工作计数未知，已返回子调用之和仅是下界。

Native cache_array_bytes仅含数组/树的nbytes，不含全部Python容器、对象对cache或临时对象；产品scene_cache.accounted_bytes仅是2MiB读缓存的序列化payload记账，不含ReadContext、decoder、宿主缓存。两者不能直接当总内存比较。RSS分别记录actor/Blender当前working set和进程生涯peak；N超时后host样本已处于退出状态，其约32KiB残留值不作为有效运行内存。未暴露的缓存内存或宿主细分均为未测。

76个实测逻辑请求=N37+P39（P capture_task9、capture_nearest_candidates30），初态fullmesh读取18、T额外fullmesh读取42、固定协调变化36、close尝试18，合计190次协调层尝试；worker日志有188个请求event，另两个是N超时未落event及其close未建立连接。实际receipt与日志分别保留，不把78逻辑格当78物理RPC。

本批token/模型费用N/A。脚本准备与复核的协调模型成本未暴露，单列未测，未将JSON字节换算token或费用。

## 唯一最小候选，交管理员选择

建议仅评估一个`SCALE-OPT-001`候选：**用现有层级几何能力实现保守下界的优先距离遍历，保留当前精确叶谓词，并按实际访问工作计预算**。它针对已实测占比96%–99%的热点及全组合预拒绝。仍需独立面的/顶点/字节/期限保障，不以单纯上调上限替代算法；G4092总面限及closed-solid资格不能因距离分支改善而自动放开。

下一批是否采用、如何收敛由管理员审核决定，本批没有实现这个优化。T的过宽缓存失效作为已测事实归因保留，不在本批同时加入第二项优化。原样暖读确实有收益，但不能据此宣称连续任务或全规模已达标。

## 封存、局限和回放

原始preflight目录与正式measurements分开；预检期间只修验证baseline/夹具API适配，没有更改产品或按结果换题。五个blend及12份worldmesh、FREEZE、独立oracle/replay、Native数学反例、代码、逐请求脚本/原始worker日志、全部测量、独立评分均保留。旧NATIVE-PLUGIN-COMPLEX-003只在未来叙述中归为“中等空间推理、低几何规模”，未改其封存原件。

这是旋转齿槽挤出族的规模诊断，不覆盖任意角色、凹陷裂缝的所有资产域、动画、模型自发规划、自动Hook或最终端到端模型收益。不向外推p95，不跨两种成功语义合并均值。Native有限域和更宽产品闭壳合同的差异已明示。

回放使用FREEZE固定来源/环境和原始fixture；不要在本封存目录重新采样覆盖measurements。只读重算可运行`analyze.py`、`quality_review.py`，独立几何证书复核入口为`oracle.py --replay`（以其CLI支持项为准）。实际产品安装未重装、原资产未修改，所有变化只在owned测试副本。

生命周期核对见CLEANUP.json；N超时worker被原owner终止并回收，close ACK/WORKER_CLOSED缺失按真实失败保留，不能写成18条都正常close。其他17条正常退出。当前学习runtime绑定context_bound=false/rebind_required=true，本批状态未借用其他聊天handle更新，待合法重绑同步，不影响管理员明确授权的实施工作。
'''
# Avoid suggesting an unsupported convenience CLI: actual independent replay is
# already self-contained in ORACLE_REPLAY, with script invocation preserved.
text=text.replace('独立几何证书复核入口为`oracle.py --replay`（以其CLI支持项为准）','独立几何证书重放结果及反例见ORACLE_REPLAY.json，生成命令以oracle.py的实际CLI为准')
(HERE/'README.md').write_text(text,encoding='utf8',newline='\n')
