# 002 来源、连续执行与原期限独立复核

固定实施交付 `a798caf982e2d7eefe0bf52b739b9bef88526be4`，准备提交 `11ae08e791c300c58ae935f4f632a22b3d7f3342`，根合同 `79ed3bff7c87d4ac68e2b2bf382de05d41b731c6`。本轮只离线读原件、Git 对象、ZIP 与已固定源码，新增产品 / Blender / 模型 / API 运行均为 0；未执行作者 checker。

独立结果：来源与执行 372 项、补充期限与预算 49 项，最终均通过。这是核验断言数，不是实验样本数。实际执行分母为 6 集、每集 3 轮，共 18 轮；6 个不同 UUID、12 次显式 resume，执行记录 18 completed、0 failed、0 not_run。答案是否正确、实际记忆收益和成本结论由根另行审核，本报告不作评分或解封组别与费用。

## 本轮实核

- 310 内容文件加 DELIVERY_MANIFEST，完整匹配固定交付的 Git blob、文件集合、长度及 SHA256；准备 172 内容加 PREPARATION，425 外部依赖的现存字节匹配固定记录。旧 001、interface fix、FIX1/FIX2 与产品目录未改，不重跑旧矩阵。
- 原准备 `012daa93cd2b67164ac2dc4ed04089d395ef2ed1` 有 168 内容文件，现仍可逐项从该 Git 提交读取并匹配原 SHA。准备期修正准确等于两处 `git show` 改成 `git cat-file blob`。原失败回执的 formal_started=false、new calls=0 保留；这些是留存记录，不是本轮重新启动验证。
- 最终 driver 在独占 formal reservation 前验证固定准备，实际每集 ACTUAL_WIRING 和执行前后 SOURCE_GUARD 对应已审 interface wrapper、绑定到原函数 globals 的 transport/archive，以及原 legacy.pack。直接核了最终源码连线和原始归档，不将作者 passed 字段作为独立证明。
- 89 个公开文件与匿名 ZIP 逐字一致，ZIP SHA256 为 `21198b498acbbe0eb3ef68e399b468629094b325eb8cdd75eef532755b068610`。6 份原始 ZIP 共 1589 成员同时绑定原短路径文件、成员清单和私有来源清单。18 个公开 final、PUBLIC_FINAL、consumer final、模型最终事件对应；CLI 原文另行逐字对应。所有公开工具事件、owner 业务投影、错误字段和行政字段移除记录均独立复算。
- 每集三轮使用同一实际 UUID、shared work、owner/backend 身份；不同集 UUID 不同。六次注册 EDIT 在 REPEAT 完成与 EDIT 轮开始之间发生，每集恰好一次；INITIAL/PRE_EDIT 全量几何等于固定 BASE，EDIT/FINAL/注册回读全量几何等于固定 EDIT。原资产字节保持。
- 六个 owner 与 Blender 的实际退出回执、适用产品 runtime 的退出、18 轮 CLI/reaping/readers 分别对应。**18 个 thin EXIT 缺失仍为 unknown**，没有用 CLI 或 owner 退出推断 thin 正常退出。
- 使用原 FINAL_TIMING、绝对 deadline、actor/endpoint/session/worker/continuity 记录直接核算：6 集完整业务边界和 18 轮 consumer 写闭边界均未超原期限；原时界在各层相同，未续期。外层 timing publication 也在期限内。6 集累计 32 业务、128 非关闭 host 请求、1 MiB 编码响应上限均未越；所有业务 code 及实际 host SCRIPT 的原逻辑字节、hash 和 256 KiB 上限通过。只发布通过/失败，不发布组别或实际耗时/字节成本。

## 限制与保留项

本轮证明来源、实际续接、当前 EDIT 读回与执行预算，不能推出模型利用了历史上下文，也不能单靠正确答案证明当前工具事实被消费。18 个 thin EXIT 未知保留；已知 QA 在持久 Python namespace 中覆盖 `_j` 的限制保留，shared GUI 前后未测。时界到缓冲写入并 close，fsync 未测；consumer FINAL_TIMING 自身发布不在其记录的 consumer 写闭边界内，不能声称覆盖无记录的最后一字节持久化。

作者的早期准备故障、旧失败批次均保留。本审两次主脚本字段/分母误读、一次补充脚本字段误读也保留，详见 SELF_ISSUES.md 和 ATTEMPT 文件；纠正后未修改原件。没有发现新增来源污染、未知 EDIT 或当前终态阻塞，可供根完成质量封存，再按原合同解封同批成本。

自身 AL handle `eedb2e6559c7410dbf9007536acc04f1` 仍为历史 write611/current=false；已读取当前父 write630，只按父当前离线任务工作，未借父句柄登记。`INPUT_HASHES_PRIVATE.json`、`BUDGET_INPUT_HASHES_PRIVATE.json` 包含实际来源路径，应在根质量 seal 前留作私有。成本证明文件仅作交付完整性盲哈希，未统计或对外返回数值 usage/组别成本。
