# OPT1 桥接与配对验收独立复审

本次复审读取冻结产品 `c1cb2da32034e056a270384e691a2cde8dddbc0d` 的桥接实现，以及本轮工程脚本当前字节。未启动 Blender、产品调用、固定输入性能或消费者。内核作者身份与本次桥接、测量器的交叉复审身份分开记录。

## 桥接依赖

`SurfaceScanDependencies` 由 decoder 的私有工厂生成。它保存不可变对象元组和当前请求 packet 引用，getter 仅接受最近一次成功 decode 的同一 payload，并在成功取出后清 decoder 的引用。`matches_capture` 又核同一 packet、capture_state、scope、完整和局部 host identity、host source。服务在既有 packet 校验后取 getter，reducer 在使用前再次执行 matching。

依赖覆盖 runtime source、host source、decoder owner、host instance/epoch、document epoch、对象 incarnation、resource id/revision/admission、实际矩阵和单位尺度。相同 resource 版本重传时，新增扫描路径核对完整内容。live 集合修剪后再次进入使用新的 admission serial，plain 路径会清 decoder 资源状态。该机制使同名替换、resource 重建、epoch 和连接变更具有独立失效依据。

getter 消费后的 token 由请求栈临时持有。cache 提取当前 mesh 对象的短摘要，不保存 token 和 raw packet。decoder 仍复用原有 local resource 和 world pose 缓存。普通几何和 native evidence 路径继续走原键与原 delta 合同。

未发现新旧版本之间使该固定扫描错误 complete 的依赖缺口。继承的传输等待和隐藏来源异常限制按主计划保留。

## 旧承诺与质量

新 `qualification_binding` 从输入冻结提交读取 READY 与 SOURCE_OUTPUT_MANIFEST，要求当前文件字节一致，再核对原先承诺的九个 SHA 和全部资格文件。原 actor 的传递依赖也进入本轮文件绑定。

新 verifier 对全部 276 个唯一 pair 核分类和实测距离，对所有 bound exclusion 核严格阈值与独立真实距离下界，对公开匹配核完整集合、名字与 ID、独立最近距离、measured 见证状态、原表面归属及点距。它同时核 coverage 的完整性和守恒。每次请求后先执行质量检查，错误会停止后续产品请求并保留当前与未执行分母。

主序列 cold 前仅进行初始化、工具目录、ping、只读原生快照和进程证明。元数据阶段要求零 host RPC，QA 导出器读取 Blender 几何但不调用产品 measurement cache。两版本采用相同顺序。

## 配对与分母

`run_pairs.py` 固定 AB、BA、AB、BA、AB，逐版本 fresh owned Blender 与产品进程。`summarize.py` 独立按五组、两个版本、三个状态生成完整 30 格，缺失、重复、失败和意外状态均不能通过。实际开始时序还需吻合预定版本顺序。

各门使用以下原公式。

- EDIT 为五个 `new_i / old_i` 的中位数，门限 0.70。
- cold、repeat 为五个配对差值的中位数，允许量为 `max(0.05 * median(old_i), 2 ms)`。
- 三业务请求之和使用每组相加后新旧比值的中位数，要求严格小于 1。
- 生命周期使用每组完整序列新旧比值的中位数，门限 1.05。生命周期实际增加时，局部通过与净收益分开。

逐 pair 复用映射现已采用完整 EDIT 快照的 24 个对象 ID，未知 ID 会被拒绝。104 个未变 pair 要求命中并与 cold 的实际 measurement key 相等。10 个含移动对象的 pair 要求未命中，已有 cold key 时必须变化。主门另核新核数、每请求一个 host RPC、edit 零资源读取和 8 点世界变换，并核 B 的原 2 MiB、256-entry 容量。

## 时界与第二宿主

主客户端完整时界含 Peer 证据 I/O，服务器外层 trace 覆盖 wire encode 与 stdio write。序列时界覆盖启动、QA、业务、逐次质量检查、退出和源码复核，结束于最终 RESULTS 序列化和写盘前。后者在新 summary 说明中已明确，双方使用一致定义。单独记录的质量检查与复用映射耗时可追溯。

Process 定向使用明示的 QA-only stdin wrapper，按固定顺序截取两次快照和一次登记 pose edit，其余命令交给核过源码的原安装版 worker。正常产品命令为 capabilities、三次 capture_surface_scan 和 shutdown。该定向不计入主五组性能门，wrapper 身份和输入均进入原件。

## 复审结论

两项建议已在正式脚本冻结前落实，分别为从完整快照建立 pair 名字映射，以及明确最终 RESULTS 写盘的生命周期边界。当前源码和测量计划可进入冻结后的实际五组配对。真实机制、质量和成本结论仍以原始输出及独立复算为准。
