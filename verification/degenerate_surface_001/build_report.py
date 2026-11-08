"""Assemble the bounded algorithm/QA evidence without running a product."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
load = lambda path: json.loads((OUT / path).read_bytes())


def main():
    freeze = load('CANDIDATE_FREEZE.json')
    offline = load('offline_01/RESULTS.json')
    identity = load('offline_01/EXECUTION_IDENTITY.json')
    qa = load('qa_01/RESULTS.json')
    plan = load('qa_01/PLAN.json')
    outer = load('qa_invocation_01/RESULT.json')
    close = load('qa_01/rpc_close/METER.json')
    assert offline['passed'] and qa['passed'] and outer['process_reaped']
    sections = []
    for filename in ('GEOMETRY_AUDIT.md', 'QA_AUDIT.md', 'SOURCE_REVIEW.md'):
        text = (OUT / filename).read_text(encoding='utf8')
        lines = text.splitlines()
        if lines and lines[0].startswith('# '):
            lines[0] = '#' + lines[0]
        sections.append('\n'.join(lines))
    group_rows = '\n'.join(f"| {name} | {group['tests']} | {group['failures']} | {group['errors']} | {group['skipped']} |"
                           for name, group in offline['groups'].items())
    call_rows = '\n'.join(f"| {row['label']} | {row['elapsed_ns']/1e9:.7f} | {row['physical_RPC_delta']} |"
                          for row in qa['public_calls'])
    report = f"""# DEGENERATE-SURFACE-001

原 T04 的退化焦点现在得到 complete 表面距离：0.004000000189989805 米，唯一最近对象 M4_Near，四个目标均有效、零未决。名称观察和返回 focal.id 的旧入口观察语义相同。只交付一个候选：{freeze['candidate_commit']}；131 源 canonical SHA256 {freeze['source_sha256']}。最终证据提交及索引/报告哈希在一次完成回传中固定。

## 实现与边界

每个原三顶点面的闭凸包按精确零法向保留为三角形、线段或点。三点共线时取真实字典序两端，重复顶点不会生成零长边。网格仍是原各面集合的并集，不计算全局凸包。点线/点面/线线继续复用原精确特征，线穿面内部用原重心判据的齐次整数形式判定；有理交点在 witness 阶段构造。点点有独立见证描述符，零距离方向保持 not_applicable。有效距离与见证/方向可发布性继续分开。

产品只改 surface_proximity.py 和 task_query.py 的两类缓存算法版本。METHOD 为 exact_binary64_triangle_surface_hulls_v3；普通缓存 task-surface-proximity-exact-aabb-v3，精确排名缓存 task-surface-proximity-exact-world-rank-v2。旧退化 unknown 缓存不能命中，普通/精确排名仍分离。MAX_FACES=4096、MAX_TRIANGLE_PAIRS=16384、MAX_BITS=4096、发布容差、AABB 严格剪枝、world 精确排名和并列规则不变。坏索引、非有限、位宽/规模超限、取消与原期限仍保留其拒绝或传播语义。

普通三角形复用原 5-tuple、3 顶点/3 边，新增维数布尔门控及变长端点索引（每面三次 len(points)）；普通单面对计数仍为 intersection/point-face/point-edge/edge-edge=1/6/18/9。这些常量级检查也是实际工作。点/线段记录保留 1/2 顶点与 0/1 非零边；点点没有点面/点边/边边工作。只在退化段与面组合构造齐次临时量，没有新增模块、服务或缓存层。临时堆字节、CPU 周期与完整模型收益未测，不把静态结构计数当作这些测量。SAT、实体判定、动作/写权限、名称入口、参数/字段/说明均未改。

## 离线数学、链路与回归

首遍也是唯一一遍离线执行：{offline['tests_run']}/83 方法通过，零失败、错误或跳过。新增定向组严格为 12 个方法，其余是与改动有关的既有回归；旧退化 unknown 断言按合同更新，partial/unknown 另用真实有限位宽超限输入保留。旧运行原件未覆盖。

| 组 | 方法 | 失败 | 错误 | 跳过 |
|---|---:|---:|---:|---:|
{group_rows}

独立 oracle 用 Fraction 枚举各面非空支持集并以 KKT 高斯消元求约束驻点，另核明确解析平方距离；不调用产品特征生成答案。覆盖点/线/面组合、顶点全排列、真实凸包端点、端点都在面外的内部穿面、共面/平行/重叠、原 T04、实际 binary64 平移旋转、极近非零、预算与取消、全部并列、严格排除、两类缓存及见证精度。tests/TEST_PLAN.md 固定全部 12 组变体。

原 verified_source_loader 从冻结的 131 份相同源码安装，guard_verify_loaded={identity['guard_verify_loaded']}；已加载产品模块的执行/namespace witness 随 EXECUTION_IDENTITY 保存。测试 raw SHA→compile 文件名和 EXECUTED_BYTES.zip 同时封存，不以磁盘同名文件代替执行字节。原 T04 fake-RNA 链路冷请求 kernel_calls/cache_hits=4/0，重复为0/4；普通焦点并列变体仍有2有效/1严格排除。普通/rank 缓存各第一次计算、第二次命中，旧版本 seed 被隔离。

离线内部耗时 {offline['elapsed_ns']/1e9:.7f} 秒，外层 exec 观测 2.7327832 秒。两个既有 renderer bbox add overflow RuntimeWarning 在工具合并输出中保留为 OFFLINE_INVOCATION 观测，没有测试失败。首遍没有另捕获外层 stdout/stderr 原始文件，该边界明确未测；完整 unittest 文本、结果和执行 ZIP 均保留。未为取得干净日志重复执行。

{sections[0]}

## 唯一真实 QA 与完整成本

源码先提交固定后才执行真实 QA。原 controlled stdio、原已核验 helper 与私有 T04 副本；1 NativeSession、2 公开观察、1 owner close，共3物理 RPC。没有 profile setup、资产编辑/保存、额外观察、新模型消费者或外部 API。worker 600秒、单请求20秒、host/native10秒均沿用原框架。prepare 在候选冻结后执行一次，只做字节/身份/资产/窗口核对和准备。

QA prepare 内部 {plan['prepare_elapsed_ns']/1e9:.7f} 秒（工具外层5.7833808秒）；完整 QA 外层 {outer['wall_ns']/1e9:.7f} 秒，从 {outer['started_utc']} 至 {outer['ended_utc']}。controller 内部 {qa['whole_controller_ns']/1e9:.7f} 秒，Native 启动 {qa['native_startup_ns']/1e9:.7f} 秒，close 包装 {close['elapsed_ns']/1e9:.7f} 秒。以下单请求时间含在外层中，不相加、不扣除准备或测量开销，也不作冷暖模型收益推断。

| 公开调用 | 包装秒数 | 物理 RPC |
|---|---:|---:|
{call_rows}

原始字节边界：control TX/RX={qa['boundary_totals']['control_TX_completed_bytes']}/{qa['boundary_totals']['control_RX_bytes']} B；product socket TX/RX={qa['boundary_totals']['product_TX_completed_bytes']}/{qa['boundary_totals']['product_RX_bytes']} B；stdio 完整 TX/RX={qa['boundary_totals']['complete_stdio_TX_bytes']}/{qa['boundary_totals']['complete_stdio_RX_bytes']} B。这些边界重叠，不能相加成模型输入或服务费用。无新增模型消费者；作者/子审 token 和费用未测。MANAGEMENT_START/CLOCK 另记本回合从任务开始至封存的完整 elapsed 下界，包含嵌套实施、测试、Git、准备、QA及并行审计；最终提交/回传尾段由完成聊天 metadata 补全，较早回合不混入。

{sections[1]}

{sections[2]}

## 封存与未测事项

RAW_ORIGINALS.zip 与逐成员索引完整保留 offline_01、qa_01、qa_invocation_01，包括原始 bytecode；原目录不删移。PRESERVATION 固定14个旧标记及本批原始字节。EVIDENCE_INDEX 覆盖两产品源、三份必要旧测试及本批文件，排除索引自身和直接 bytecode/cache（其原始字节在 ZIP 内）。提交前后都核对磁盘、索引、Git blob和限定变更范围。原 RUN001–005、两个 M1 离线尝试及 raw QA 均保持。

本批没有 RUN006，也没有新模型消费收益结论。真实 QA 只覆盖原 T04 的名称/旧ID两观察，不扩大为所有退化网格或实际源类型验收。有限精确算术与原规模/期限拒绝仍有效。STATE/window 由根管理，本分支未写 STATE；Google付费、原资产、共享GUI/default9876、正式配置和竞争分支保持原边界。本批完成回传后停止，等待根深审。
"""
    (OUT / 'REPORT.md').write_text(report, encoding='utf8', newline='\n')
    print(json.dumps(dict(report_sha256=hashlib.sha256((OUT / 'REPORT.md').read_bytes()).hexdigest())))


if __name__ == '__main__':
    main()
