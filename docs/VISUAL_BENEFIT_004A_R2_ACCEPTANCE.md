# VISUAL-BENEFIT-004A-R2 启动握手与失败清理

本批关闭 READY 发布竞态，只改验证设施及对应文档、测试和计划。产品 129 源仍为 `6a5375fb5d5577e8de05c043db7523263cf96ad8386ee524a04beb25feb9f382`，基线 `afd851ec5c142e08addd596f6622122e081cac09`。**正式消费者为 0，004B 未启动；没有模型任务收益结论。**

## 原故障及修复

固定旧源码的 `OLD_FAILURES.json` 在改动前记录真实方法与受控首次写入屏障：原 save 创建 READY 路径后暂停写入，真实 NativeSession.start 立即解析空 JSON 失败；原 launcher 已 kill/wait 自己的假进程各一次。完整 READY 对照成功。原 broker client 同样会解析到已出现但未完成的 BROKER_READY。此为受控反例，不是现实发生率，不把测试活线程说成真实 launcher 进程泄漏。

新增定向 `publish_ready` 只接受 READY.json/BROKER_READY.json：自有唯一 sibling staging 完整写入、flush/fsync、字节与 JSON 读回后，通过不覆盖既有目标的单次链接发布；失败不改走 replace 或复用已有文件，只清理本次持有的 stage。原 save 及其他持久化策略未重写。写入、发布、读回、清理后的期限均检查；文件系统不支持链接则失败，不承诺所有文件系统均支持。

NativeSession.start 将完整读取、字段/endpoint/PID/helper/指纹、源/copy/binary、SESSION 保存后的复核纳入 min(原期限,原30秒)。坏数据、错误身份/来源和过期立即拒绝，无解析重试、固定延迟掩盖、重启或续期。失败保留 START_FAILURE，自己的已启动进程被终止并回收；遗留 SESSION 不能重新打开。

worker 的线程启动、socket 和发布失败均进入 finally，停止并 join 自己的 watchdog，不取消运行中的原期限保护。测试初始化在解析与 session 构造前登记自身监听地址并登记 cleanup，确保对应 setup 故障也能关闭 worker；不吞掉原失败。

broker 使用同一发布接口。client 将 BROKER_READY 与 SESSION、现有 BROKER_STATE 中 owner PID、worker PID、条件、来源、helper 和原期限绑定；完整读取、来源校验及 response JSON 解码后再检查期限。普通调用不能借 READY 延期；只有已绑定 close 使用既有七秒清理控制窗口，不延长任务或 worker 生命周期。

## 确定性与回归

最终 **240/240 普通、240/240 `-O`**，记录 `ALL_TESTS_001_NORMAL.txt` / `ALL_TESTS_001_OPTIMIZED.txt`。原七模块 204 个测试方法全部保留，新增 36 项：native 3、session 6、readiness 27。

新回归用临时文件、Event 屏障和假 Popen，验证两个信号发布前不可见、完整发布后继续、并发 first-create、重复/损坏既有目标、写入/fsync/readback/link/自有 stage 清理错误、永久坏 JSON、错误身份/来源、原期限及初始化失败后的线程回收。负例核对预期原因，不靠重复运行碰运气或降低拒绝标准。R1 的公共语义、完整域、v2 绑定、六题/顺序/预算保持。

## 最小真实校准及协调脚本失败

使用同一既有 calibration.blend，没有新造资产或请求图片。初次协调脚本错误把 Windows venv 启动器 Popen PID 等同于实际 broker PID，在任何读取前误拒两侧，随后其失败清理杀了启动器。实际 broker 后续已不存在，worker 在原期限后也已不存在；原退出码及原 Popen 回收没有证据，记 unknown。精确 CIM、原日志和 `POST_FAILURE_STATUS.json` 保留，不把该次计为通过，也没有续期、恢复或补读原 actors。

修正仅发生在另一份独立协调脚本：直接 base Python 启动并显式保留原 venv 包路径；实测 numpy 2.3.5、Pillow 12.3.0。新脚本及新 attempt 单独封存，不覆盖旧失败。纠正后每侧各一次启动、一次只读、一次 close：

| 条件 | 调用 | broker / worker PID | 关闭与保护 |
| --- | --- | --- | --- |
| N | 普通 bpy 读取 | 35548 / 11716 | 双退出0，原 worker Popen 回收；源文件、copy、初始 PNG 和几何指纹不变 |
| P | 真实产品 observe，include_image=false | 33356 / 30140 | 双退出0，原 worker Popen 回收；相同保护及原期限保持 |

有效结果在 `qualification/minimal_calibration_r2/RESULT.json`。两侧各 public_calls=1、read+close 两个事件，完整外部耗时分别约 1.824/2.643 秒，整批约 4.580 秒；这些是有限校准成本，不是正式任务收益。两次资格尝试的启动和失败材料均保留，不能只报第二次成本或称原失败窗口通过。

## 封存与边界

本批有效计划在新 R2 目录 `final_protocol/FORMAL_PLAN.json`，引用旧 004A 资产根；17 份 helper/test/README 源码 pin 随候选更新。六个公共语义补充与 R1 相同，原问题/真值/PNG 不变。旧 004A/R1 evidence 与 seals 不覆盖；旧源码分别以原 Git 提交核对。

没有修改 human_eye_plugin、产品阈值、默认安装、GUI、用户资产、语义合同或算法域；没有 Google/key/付费/学习库/清理重试/push，Git 审核快照保持原固定提交。本次没有模型消费或新的图片交付验收，原 V03/V06 配对拒绝、P native 灰色材质等产品限制保持。文件系统适用性、外部强杀/崩溃后的通用子进程管理和现实故障率不作泛化保证。

完成后交回复核并核对发送回执；不自行启动 004B 或扩展其他模块。
