# 同九格成本解封私有来源绑定复核

2026-11-13。离线复核通过。新增模型、Blender、产品 API 调用均为零。

本次完成 5169 项断言，读取 932 个不同输入文件，含两份管理员原件副本和一份复核器失败历史。源证据按固定交付提交核字节，管理员 seal 与成本合同绑定到独立管理员提交。

准备提交 `3a1ba86c5fce2fe125671cc68a84b14031d318cb`，正式交付 `f5cfcf5e4768b1b6c31127b5d4a6c1227b8d7907`，管理员封存 `1f1a23dda3413721d6c71bd1db95f3a40a7c4977`。

## 质量与私有映射

根 seal 保留原件。九份最终答案内容均为 complete_correct，匹配 639/639 个事实。严格执行为七份 complete_correct、两份 execution_failure。N2 与 O2 的 reconnect/response decoding 错误保留，随后 turn.completed、CLI exit0、final 文件存在的事实同时保留。

N、O 各有两格有效完整正确，C 有三格。C/N 与 C/O 均未满足双方各 3/3 的正式质量前提。内容正确口径可用于同九格描述性成本，正式准入仍受冻结执行合同约束。

| 格 | 私有匿名 ID | 内容 | 严格执行 | 加载版本 | 完整墙钟 ns |
|---|---|---|---|---|---:|
| N1 | answer_89dab9e90194dcbf | complete_correct | completed | 原生工具 | 96570260800 |
| O1 | answer_4a4a77418ce1424c | complete_correct | completed | 9.7.2+m4.surface.scan.opt1.r1 | 98544892300 |
| C1 | answer_9297e204cfb1d7f7 | complete_correct | completed | 9.7.2+m4.surface.scan.compact.r1 | 44479883800 |
| O2 | answer_4c4c0fa03baa1ee8 | complete_correct | failed | 9.7.2+m4.surface.scan.opt1.r1 | 103047564900 |
| C2 | answer_dccb27e1bc47c94f | complete_correct | completed | 9.7.2+m4.surface.scan.compact.r1 | 42838333200 |
| N2 | answer_3990a6a4bf660eee | complete_correct | failed | 原生工具 | 107343994400 |
| C3 | answer_9ee63c86af8ff66d | complete_correct | completed | 9.7.2+m4.surface.scan.compact.r1 | 39486958600 |
| N3 | answer_bb2c246d257d7867 | complete_correct | completed | 原生工具 | 100080051100 |
| O3 | answer_11a4c8ec025d6a16 | complete_correct | completed | 9.7.2+m4.surface.scan.opt1.r1 | 106579204500 |

## 原始来源与公开投影

私有预建 MAP 与固定九格、根 seal、九 final、CLI 最后一条公开消息、原输出文件、两套匿名公开答案逐字节对应。九原始 ZIP 的 807 项原件分别与磁盘、私有 provenance SHA 对应。27 次业务尝试与 54 条消费者开始/结束事件逐项连接到原始请求、完整返回、公开投影和原行 SHA。

r2 的 42 文件 canonical 与 ZIP 均匹配根 seal。行政修正仅删除两处错误信封 perf_ns，恢复原值后 INDEX 原字节完全一致，其他 41 文件保持一致。原始匿名 ZIP 与初始 canonical 分别保留。

## 实际进程与时界

九个独立实际 CLI thread、九个独立 Blender worker、六个独立产品 runtime 分别核验。每格实际 CLI 隔离设置、请求模型与 effort、MCP 配置、tools/list 声明、读取 schema、产品 source pin、安装版本、父链与创建时间对应。初始 QA、四次元数据握手、runtime 证明、消费者业务的先后关系一致。旧 O 绑定旧扫描 OPT1。

18 个初末完整快照与实际 worker stdout、snapshot 脚本、receipt 和冻结基准逐项一致，包含全部顶点、面、矩阵及单位。每格完整计时覆盖输入检查前到最终业务回执关闭及 owned 清理结束，prefix 与计时回执发布分别核算。九格均在原 570 秒时限内，下一格开始晚于前格计时回执发布结束。

同字节复用既有 source/wheel/install 验收与两份旧复核记录，本次重点新增历史实际运行来源、配置与事件的对应。

## 保留的边界

九个 thin-client EXIT 回执均为 unknown，owned 消费者、owner、Blender 与适用产品 runtime 的关闭分别得到记录确认。provider 实际解析型号与 effort、实际渲染或截断后的模型输入、fsync 级落盘、请求总数及真实账单仍未测。终态快照及 render/file 保护保持其记录范围，无法排除所有已恢复的瞬时操作。历史 process 记录无法重放过去进程内存。

Agent Learning 本轮绑定仍为 context_bound=false、host_epoch=5、rebind_required=true。未借用其他会话句柄。

离线复核器开发时出现四次自身读法失败，涉及 Windows 路径排序、schema 字典编码顺序、TOML 解析及基准额外字段。均已修正并保留在 CHECK_HISTORY.json，原件无改动。

## 可重复执行

使用依赖 Python 加 `-I -B -X utf8` 执行同目录 verify_binding.py 可只读重核。加 `--write-report` 只写本目录派生 BINDING_RESULT.json 与 REPORT.md。完整断言和输入 SHA 清单见 JSON。
