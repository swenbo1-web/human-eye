# M4-ACTIVE-COVERAGE-002 停批独立复核

## 判定

保留本批严格失败和停止状态。首槽 `main_p01_A` 因 `child_process_or_output_binding` 被 controller 拒绝，余下 11 个主槽和 2 个控制槽均为 `not_run`。全批门限为 false，配对时间收益为 null。此次复核新增 engine 进程、render 和正式样本均为 0。

## 已有原件复核

`review_final.py` 只读取已发布原件，复用冻结 `validate.py` 进行文件、数组和当前 owner/RGB 像素计数回读。执行所得 21 项检查全部通过，151 份冻结输入源码字节均保持一致，200 个输入绝对路径和 SHA256 绑定在 `FINAL_REVIEW.json`。

- controller 记录首槽 `returncode=0`，worker 原件状态为 `completed`。
- TRACE 有 6 条持久化 render intent、6 条 render completion 和 6 条 frame completion。顺序为 SCENE、TOP、LEFT、RIGHT、FRONT、BACK。
- 6 份新 PNG、6 份新 NPZ 及帧元数据通过冻结 validator 的完整回读。PNG 合计 15,735 字节，NPZ 合计 136,752 字节，原始数组载荷合计 23,592,960 字节。
- worker 实际返回 36 行像素结果，回读器另核对 36 行当前 owner/RGB 结果。6 组原基线图像对照发生在 child 完成后的回读阶段。
- 最终覆盖 5 个区域，剩余 1 个区域等于有限相机池的几何不可覆盖集合。主场景像素不足历史和最终像素不足均为空。同版本重复查询新增 render 为 0，状态保持一致。
- worker 记录的旧证据读取和旧内容写入违规均为 0。

这些已有输出通过内容校验，controller 的进程身份绑定仍未成立。

## PID 来源边界

controller 的 Popen PID 为 `23456`，RESULT 和全部 TRACE 行的 worker PID 为 `20368`，输出目录一致。冻结 runner 先完成 `validate_run`，随后因 PID 不等触发绑定错误。因此内容校验通过与严格槽位失败同时成立。

本地 venv `Scripts/python.exe` 为 277,808 字节，PE 元数据 `OriginalFilename=py.exe`。`pyvenv.cfg` 指向另一个 107,312 字节的 base `python.exe`。本机标准库 `venv` 源码包含 Windows 使用 launcher 副本的分支。这些静态元数据与 launcher 启动实际解释器的解释相容。已读取文件及 SHA256 保存于 `LAUNCHER_METADATA.json`。

本批未记录操作系统父子进程链。无法仅据以上元数据证明 `20368` 是 `23456` 的后代，实际 PID 来源关系继续为 `unknown`。首槽保持 `failed`。

## 尚未取得的证据

B 自适应主流程和 BACK64 像素反馈控制均未执行。首 A 失败槽原始耗时为 1,075,954,200 纳秒，包含回读及身份绑定失败处理。该值保留在原成本记录中。缺少已验收 A/B 配对数据，整体耗时改善、减少调用带来的净收益及控制恢复效果均未获本批验证。

本轮保留原冻结源码、准备文件和全部正式槽位。后续处置需另行固定身份绑定合同并安排新批次。

## 原件绑定

`FINAL_REVIEW.json` 的 SHA256 为 `f9d6906ad0b1e9a4f5b303eae7ca0c4337eaf8a3b46a5dcc0f9f1c82198db71b`。首 worker `RESULT.json` 的 SHA256 为 `a651c026e791f955af93f508c1f5434aa6d26191dbbfd0ed4b1c4431386e797e`。
