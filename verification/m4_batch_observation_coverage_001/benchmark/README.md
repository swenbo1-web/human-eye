# 固定离线测量

根协调者使用当前 Python 执行一次 controller。manifest 指定 base 的 bundle、主请求及三份变体的原件路径、SHA 和字节数。

```text
python -I -B -X utf8 benchmark/run_measurements.py --manifest validation/MANIFEST.json --output benchmark/run_01
```

命令中的相对路径以当前工作目录为基准。在 batch 目录下执行时，可直接使用以上写法。输出目录采用新名称。

四个 fixture 分别使用 draft、final、native 三个新 worker，顺序逐 fixture 轮换。controller 串行等待每个 worker 退出。每个 worker 先加载固定实现和解析输入，然后预热一次，保留 21 个原始纳秒样本，再独立进行一次 tracemalloc 测量。worker 通过固定 SHA 和标准库 import 检查加载投影源码。

每个计时样本覆盖 directory、selected_observation 两个函数，以及两份 `ensure_ascii=False`、紧凑分隔符、`allow_nan=False` 的 UTF-8 JSON 编码和末尾 LF。主请求已经固定。输入加载、世界坐标准备及已有关系计算在此计量范围之外。

每个 worker 保存两份完整响应、全部原始计时与字节数、实现和输入 SHA、进程退出记录，以及两种内存记录。tracemalloc 记录额外一次组合投影和编码的 Python 增量峰值。OS 指标来自新 worker 自启动至内存查询时的生命周期峰值，包含输入、导入、预热、计时样本和 tracemalloc；查询后的文件发布另有范围说明。

OS 查询仅从原 `verification/measure_nonplanar_cancellation.py` 中提取 process_memory 函数 AST。原文件 SHA 固定为 `85ea9434505ed72a407375b05a9ecd9a936c09ecf6143045cb6057169fd0cd02`，提取函数的 AST SHA 写入每份结果。controller 的 subprocess 导入位于 controller 函数内。worker 使用本地数据、标准库和该 OS 查询函数。

controller 核对 final 与 native 两个响应的逐值相等，并记录实际字节是否相等。draft 与 final 的目录差异限定为 center，选定响应逐值一致。RESULTS.json 保留执行顺序、冻结文件摘要和比较结果，各 worker 目录保留全部原始样本。已有关系是双方共同的输入。本轮结果用于离线投影与接口覆盖分析，实际宿主采集和缓存计数留待入口验收。

实现代理只完成静态 AST 与不执行 compile 检查。实际十二个 worker 由根协调者统一启动。
