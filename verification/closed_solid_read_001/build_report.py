"""Summarize frozen implementation, analytic evidence and original QA."""
from pathlib import Path
import hashlib
import json

OUT = Path(__file__).resolve().parent
load = lambda name: json.loads((OUT / name).read_bytes())


def main():
    source = load('SOURCE_FREEZE.json'); r = load('qa_01/RESULTS.json')
    p = load('qa_01/PLAN.json'); outer = load('qa_invocation_01/RESULT.json')
    closure = load('REGRESSION_CLOSURE.json')
    assert r['passed'] and r['original_contract_complete'] and r['original_contract_checks_passed']
    rows=[]
    for call in r['public_calls']:
        facts=call['public_value']['facts']
        relation=facts['closed_solid_relation']['value']; gap=facts['surface_proximity']['value']['distance_m']
        rows.append(f"| {call['state']} | {call['candidate']} | {relation} | {gap} | {call['elapsed_ns']/1e9:.7f} |")
    report=f"""# CLOSED-SOLID-READ-001

一个通用只读候选已完成原复杂装配三态核查。固定产品候选 {source['candidate_commit']}，131源 canonical SHA256 {source['source_sha256']}，基线4ca1fdb2882ae31da2fd3ec49ac77e1710c69a3e。初始与未变：仅Object_03穿插、最近分离件Object_02；原四点更新后Object_02/03穿插、最近分离件Object_04。九项公开事实和三项集合/最近件聚合均符合原独立Decimal80真值及非零误差界。这是工程能力与当前执行证据，不是模型收益或默认部署验收。

## 实现与支持边界

通过原M1 task添加 closed_solid_relation，输出字符串separated/touching/penetrating，penetrating明确指表示坐标下正体积内部交集，relation_tolerance_m=0。旧solid_relation仍为1e-9m容差，geometry_safety、动作/SAT、写权限和负距离语义未变。没有伪造负穿透深度或全局MTV，没有圆环、对象名、世界轴或fixture答案特判，没有新产品模块/服务/场景缓存层。

surface_geometry复用精确整数/Fraction及BVH；每壳闭合边方向、连通性、顶点link、非零体积及self-BVH自交先验证，之后才给跨壳早停证书。严格三角面内部横截或严格包含证明正体积；边界不交时双向精确射线奇偶判断包含/分离；实际接触加全局反侧support plane证明touching。八个确定射线方向均退化、重合/部分mesh-edge边界无法证明时明确unknown。全局反转面方向支持；不一致winding、开口/非流形、孤立点、多壳、自交和退化面拒绝。输入有效性与几何数值位宽不确定分开。

预算保持有限：顶点总4096、面总4096、原face-product16384、4096bit；self/cross精确pair测试合计16384、ray测试16384、accounted work262144。取消/期限异常传播，不伪装为几何unknown。CORE_DESIGN.md给证书理由及保守退化政策；CODE_REVIEW.md/json为独立只读检查，未执行额外kernel。

原surface_proximity只加私有同query preparation hook，旧数值公式不变。冷双事实共享一次admission和float→整数frame；tuple不进入公开结果/持久cache。新关系沿现有完整当前几何pair_measurement缓存，独立algorithm_version=task-closed-solid-exact-v1；失败/unknown不缓存。live_service只补new-only实际计算的engine_invoked审计条件。普通旧事实不调用新核、不产生共享字典。新geometry scope在正常工具/结果metadata明确，不另加教程或输出坐标域。

## 验证分母与保留的失败

首遍127方法＝新16、原exact-BVH16、task/P1类30、selected13、surface41、pruning/cache11：125通过，2个旧桥接测试被无网络保护拦下（socket创建前），并触发记录器finally断言，首遍EXECUTION_IDENTITY/RESULTS/执行ZIP没有生成，保持缺失而不补造。原engine、六组unittest日志、stdout/stderr、执行runner字节及失败说明均保留。已有极值fixture的一条renderer bbox overflow RuntimeWarning也在原stderr。

产品字节未改。修记录器后只重复新16方法：16/16通过，原verified loader guard和131源执行证明完整。再只重测两个旧桥接失败项：严格127.0.0.1、最多2连接、禁止新进程；2/2通过，无Blender或消费者。最终127个不同方法都取得通过，累计145次执行＝143通过＋2历史失败；新定向16组两次共32全部通过。未把首失败改写为通过，也未重复已通过的旧矩阵。三个阶段真实原件与REGRESSION_CLOSURE.json分别记录。

解析反例独立于产品核：孔内空域与材料包含、正表面间隙包含、双方无顶点内含的穿越、面/边/点相切、重合保守unknown、平移旋转/交换/全反winding、非法/自交、极近正间隙与正体积、位宽/工作/取消。新fact独立dispatch、旧容差合同、shared preparation、成功cache与unknown不缓存均经真实service/fake-host链验证。原三态使用未修改snapshot和TRUTH，距离既满足原answer_rule，也位于其distance_interval_m；不把约.01/.04当精确真值。每个分析子例的单独reason/调用数未全部导出，方法日志、断言和固定执行测试字节保留，不从方法数推全部kernel调用数。

首遍外层4.1367343s；第二遍2.6764499s（内部2.5045259s）；两项loopback第三遍.7179982s。它们是完整方法执行边界，包含wrapper/loader，不能只报最后通过的一次。第二、三阶段guard true且源码摘要相同；首遍快照亦逐字节相同，缺失的首终态证明不回填。

## 唯一实际QA与三态成本

候选Git/新digest冻结后唯一1私有NativeSession，原600秒期限不重置；原scene、原四点patch和快照按固定SHA复制，不保存回原文件。公开观察9/9；实际场景物理RPC14＝9capture＋3独立native readback＋1既有QA patch＋close。另有上述2个loopback模拟请求，独立列账；按全部实验TCP请求保守合计16，未超过窗口16，实际Blender仍14。模型消费者/答案0，没有第二候选、重开worker或消费对照。

| 状态 | 候选 | closed_solid_relation | unsigned surface distance m | observe包装s |
|---|---|---|---:|---:|
{chr(10).join(rows)}

分离距离Object02=.010000049869218474、Object04=.039999960660935814，落在接受的非零区间。初始/未变最近分离02，changed仅04分离且最近。独立readback确认initial=unchanged；仅目标local四点改变，四个对象world AABB全部不变，几何revision/fingerprint仍正确更新。零surface距离本身不用于判穿插。

| 状态 | 三observe包装s | acquisition socket s | closed pair包装s | closed kernel次数/缓存命中 | surface次数/缓存命中 |
|---|---:|---:|---:|---|---|
| initial | 2.2453568 | .0890950 | .7006153 | 3/0 | 3/0 |
| unchanged | .1370247 | .0838506 | .0006088 | 0/3 | 0/3 |
| changed | 2.1725649 | .0878370 | .6812376 | 3/0 | 3/0 |

这些是嵌套本地wall观测，不相加、不减wait/计量开销、不当模型收益。三态共9次fresh selected capture＝18网格/504点/972面，未证明host驻留。每个冷/变化pair仍各验证108面56点（同一focal跨pair重新验证）；surface分支标shared_preparation并记0额外admission/frame。没有借缓存命中掩去捕获。实际classifier与surface各6次，work仅accounted predicate/candidate/BVH/ray量，不代表全部算术、heap或CPU。

准备内部 {p['prepare_elapsed_ns']/1e9:.7f}s（工具外层5.7706494s）；完整QA外层 {outer['wall_ns']/1e9:.7f}s，{outer['started_utc']}至{outer['ended_utc']}；controller {r['whole_controller_ns']/1e9:.7f}s、Native启动 {r['native_startup_ns']/1e9:.7f}s、stdio生命周期 {r['stdio_cleanup']['elapsed_ns']/1e9:.7f}s、Native close {r['native_cleanup']['elapsed_ns']/1e9:.7f}s。profile记录.0001248s是已有计量字段，不能视为全部仪器开销或扣掉后宣称提速。MANAGEMENT_START/CLOCK给从14:17:55Z至封存的实施elapsed下界，含并行审计与嵌套工作；最终终审/提交/回传尾段由完成聊天metadata补全，完整预算90分钟，窗口到16:07不扩大该实施期限。作者/子审token、费用与CPU/heap未测。

control TX/RX={r['boundary_totals']['control_TX_bytes']}/{r['boundary_totals']['control_RX_bytes']}B，product socket={r['boundary_totals']['product_TX_bytes']}/{r['boundary_totals']['product_RX_bytes']}B，stdio={r['boundary_totals']['stdio_TX_bytes']}/{r['boundary_totals']['stdio_RX_bytes']}B；边界重叠，不当token。161项独立原件检查全通过，161份QA/outer文件稳定；所有9公开事实和3聚合由独立旧truth核对，不调用产品作oracle。58模块guard、全execution/namespace witness、generation与新1545digest匹配。

owner：outer6828、stdio16496、Native19568各exit0/reap；self controller30724没有directwait/新增OS查询，不捏造其stopped。worker12completed、1qa_patch_applied和close unknown保留。poisoned=false，qa_patch_applied=true；final=accepted新fingerprint0e30606d…，initial307f2bb7…保持作为原值，符合授权四点更新；不误报初末几何相同。源、原资产/helper/patch字节保持。末态owner/file证据不证明未知后代、瞬时回滚或Python沙箱。

## 交付范围

五产品文件、两份新定向测试/计划构成唯一候选；原geometry_safety、spatial_sniffer、query_policy、blender_host/MCP host、scene_cache字节与基线相同。SOURCE_PROOF、CODE_REVIEW、CORE_DESIGN、ENTRY_AUDIT及原始输出分别封存。EVIDENCE_INDEX覆盖五产品源和本批文件，排除自身与直接bytecode/cache；全部Git blob在提交前后核对。24个旧保护标记、旧拒绝/失败和原作者资产不改。

本批结束等待根深审，不自动启动模型消费者或下一优化。STATE由根管理；Google/API/key/503、正式部署、共享GUI/default9876和竞争分支保持原边界。
"""
    (OUT/'REPORT.md').write_text(report,encoding='utf8',newline='\n')
    print(json.dumps(dict(report_sha256=hashlib.sha256((OUT/'REPORT.md').read_bytes()).hexdigest())))


if __name__=='__main__':main()
