# PERF-030-002 固定 QA 入口

本文件补充原静态预登记，产品候选固定在 `326b64c74b2672fd620ddb9cac83bf47dd5355f2`。原七项 static_freeze 及 10 叶核／1 封闭构造／12 解析对象对继续按原字节核验。

当前完成的是静态 QA 编写。Python 编译、产品函数、NumPy 探针、单元测试与性能采样均未执行。静态审查不构成入口运行成功或候选正确性成绩。

## 三个新增 QA 文件

- `verification/perf030_002_run.py` 为标准库控制器，导出固定 Git 源、核验原冻结、启动两个持久 arm、执行唯一顺序并封存结果。
- `verification/perf030_002_worker.py` 从固定 bytes 安装原产品 SourceGuard，再从已冻结 QA bytes 导入验证辅助源，执行诊断、测试和样本请求。
- `verification/perf030_002_results.py` 仅使用标准库，对保存的完整 payload、准备账本、解析真值和正式统计作复核。

实际运行 freeze 为 `verification/fixes/perf030_002/run_freeze.json`。它引用原 static_freeze 的 SHA、候选产品提交、基线提交和后继 QA 提交，逐项列出实际 QA／输入的长度与 SHA。控制器从该 QA 提交导出字节，执行时核对自身脚本与冻结版本一致。

## 固定字节与输入路径

运行输出采用全新目录。两个 runtime snapshot 和一个 QA snapshot 都位于本线工作树内。产品各 130 个源文件从 E／326 提交导出，实际 loader bytes 核验后编译执行，原 guard 负责产品包及其延迟导入。

QA snapshot 保留原 `verification/...` 布局，包含根层 QA 源和完整原始 inputs.json。四项定向测试的 ROOT 因此指向该 QA snapshot，读取的是冻结副本。QA finder 只允许清单内 verification 模块，按已核验 bytes 编译。正式 worker 以隔离模式运行，其 cwd 为对应 runtime snapshot。活动工作树用于读取固定 Git 对象和初始 freeze。

QA 导入闭包包含 14 个脚本，另固定直接编译的 controller 和 results，共 16 个脚本。函数内的 `test_complex_scene_quality.fixture` 也在清单内，生成几何所需辅助源按相同机制冻结。原 static_freeze 里的其他文件作为原件核验数据列入。

启动、候选 tests_complete、finish 三个显式检查点保存源身份见证与模块来源，原 guard 内部检查另属其既有实现。异常短名产品模块作为身份失败记录。解释器、NumPy、PIL 版本与路径保存为信任外部依赖身份。

## 执行顺序

1. 校验 STATE 的 M3、PERF-030-002、实际授予 token 和 granted 状态，启动本轮 300 秒总截止。
2. 导出并核验 QA／两套 runtime，核对 E 源摘要、326 geometry SHA 及两个 runtime 唯一产品差异，逐一启动并等待 arm ready。
3. baseline 执行原两叶核及唯一封闭构造，candidate 执行十叶核及同一封闭构造。每 arm 另在原 30V/56F 对执行一次标量 PT 算子／数组归因。所有结果及未知保留。
4. candidate 执行四个冻结定向测试方法和七个原回归模块，预期共 159 个 unittest 方法。十个叶核在这里明确复测一次，因此 candidate 诊断十次、定向测试十次，baseline 原始诊断两次。该次数单列为验证成本。
5. 正确性门控通过后，执行原 case／block／mode／entry／repeat／arm 顺序的唯一 2,880 条序列。每条保存完整 measure 或完整 task 响应、诊断、各阶段成本和实际输入摘要。
6. 保存每 case／mode 的实际摘要、位移范围及缩放锚点，核对两 arm 输入相同，核对 2,160 次显式 prime，取最终源见证并退出 worker。
7. 回收 worker、统计完整或部分记录，分别给出正确性、非退化和 M3 20% 模块目标判定，封存错误与总成本。

公开封闭构造未能进入支持域时保留原因。candidate 私有 scalar 与独立 witness 检查设为必需项，缺失或异常使门控失败。baseline 旧错值是否实际复现单列，诊断协议完成与物理答案正确分别记录。

工作请求在第 295 秒停止，最后五秒用于回收和封存。一次性硬截止在第 300 秒杀死已登记 worker 并退出控制器。原始 JSONL 和 worker stdout 逐行 flush，超时保留部分记录。运行目录排他新建，命令不补样或自动重跑。

## 成本和成绩解释

控制器记录源提取、初始化、启动／ready、请求往返、stdout 发布、原始记录发布、清理和完整过程墙钟。worker 记录对象构造、真实输入修改、prime、内核及样本过程成本。包含关系明确，准备、内核和往返时间不能直接相加作为互斥成本。

task 内核仍含固定 helper 内 scene/query 构造。直接 measure 的 hot 仅复用同对象支持信息，有效 task hot 才使用请求级 pair cache。输入元数据在内核外生成，其成本计入样本过程和整个运行。控制器每 case／mode／arm 保存一份输入元数据，并逐条检查一致性。

正式序列复用已完成上述诊断的同两个 worker。候选另外执行 159 项测试，验证前置工作量在两 arm 间不同并单列。cold 的定义是该已加载进程中的新对象和新 pair cache。完整过程账本包含这些前置验证，结束计时文件记录此前所有 JSON 发布的编码／写入／flush 明细，其自身发布另标未计。

算子诊断使用包装器记录实际 einsum/cross 调用，tracemalloc current/peak 包含该诊断日志的分配。它不是累计 allocator 次数或进程 RSS，也不代替正式速度。累计分配、RSS、host、MCP 和真实 fingerprint 成本标为未测。

每 case 的 15 点中位、线性 p95、五个 block 配对收益及五个目标 case 聚合沿用原计划。预算拒绝保留为单独控制分母，异常不进入有效加速平均。完整 task 的所有保存字段作差分，包括 binding。静态数值比较阈值、非退化与 20% 模块门槛继续采用原预登记。

## 授窗后的命令形状

从本线工作树使用已有 Python 执行下列入口，token 取主线实际授予值，输出目录使用此前不存在的本批路径。

```powershell
& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' `
  'C:/Users/Administrator/.codex/worktrees/2c7d/hefe/verification/perf030_002_run.py' `
  --freeze 'C:/Users/Administrator/.codex/worktrees/2c7d/hefe/verification/fixes/perf030_002/run_freeze.json' `
  --output 'C:/Users/Administrator/.codex/worktrees/2c7d/hefe/verification/fixes/perf030_002/run_once' `
  --window-token '<主线实际授予的 token>'
```

当前 WINDOW_REQUEST 继续有效。静态 QA 固定提交及运行 freeze 封存后发送一次 READY，等待主线主动授窗。
