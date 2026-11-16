# 保存层验收器修订与实际结果

本次修订保留冻结的 `saved_frames.py`、R1、所有失败 stderr、原始 PNG/NPZ 和三次实际会话。产品、安装、任务、资产及实际请求均未改动。仅对同一批已关闭原件重新作保存层检查。

## 具体接线更正

初稿误要求全场 capture 必须显式包含顶层 capture_scope。实际全场捕获省略该可选字段，host_identity 明确为 complete_scene_meshes。产品 `active_observation_host.py` 第 145–151 行对该字段有同样的完整场景默认值。R1 只接受该定义的默认值，并继续要求 host_identity 与公开 binding 一致。

`live_service.py` 第 360–363 行在核心摘要计算后追加 runtime_source_sha256、source_status、disk_status 和 source_check_scope。R1 按真实先后顺序核核心摘要，并单独要求追加值分别对应冻结 B 源码、loaded_generation、disk_not_checked 和 bound_generation_identity。

R1 在全场倾斜面上遇到无损有理方向 `[0,"-1/3",1]`，直接 float 字符串转换失败。R2 先用 Fraction 解析，再计算正面朝向。该比例方向保持原值，几何 oracle 另从独立源面求单位法向。

R1 的逆相机射线检查没有拒绝窗外采样点。512 图的最后一行或列中心为 511.5，映射到 NDC 闭区间外。宽于画幅的遮挡体因此使 R1 多预测了恰好 1023 个前景像素，全部位于最后一行或列。R2 先核采样中心属于 NDC 闭区间，再做世界面交点。它仍逐像素核全部 511×511 合法内部中心。

`CORRECTION_CONTROLS.json` 记录两个对应反例。实际抽取的 R1 normal 表达式与原 R1 ray 函数均复现了原失败，R2 均通过。`INITIAL_TO_R1.patch` 与 `R1_TO_R2.patch` 保存精确差异。R2 的 8 项来源/边界控制和 5 项解析射线控制全部通过。

## 已关闭原件的当前验收

三份最终报告为 global_FRAMES_R2.json、local_open_FRAMES_R2.json 和 local_covered_FRAMES_R2.json，共 655 项检查。8 张实际图像共 2,097,152 个像素位置，前景 701,991 个。每张 PNG 与保存 RGB 数组及实际 MCP native image block 字节一致，所有对象、原始三角面和 patch owner 映射均与本帧当前源顺序绑定。

全场保留 9 对象、56 源面，实际构造 SCENE、BACK、LEFT、RIGHT、FRONT、TOP。开放水平目标每图仅 1 个像素，开放倾斜目标每图 1–2 个像素，均不足 readable 阈值。覆盖目标在这六张图里均为 0 像素。

局部开放目标保留 2 对象、10 源面，实际 SCENE 图中有 50,557 个目标表面像素及 926 个对比边界像素，readable 为 true。局部覆盖目标保留 3 对象、22 源面，实际 SCENE 图中目标像素为 0，其他五方向明确保持未运行。完整几何遮挡原因由独立有限方向 Fraction oracle 核验。

逆相机射线核验在全部实际前景像素上检查源面交点与最近深度。记录的三角边缘或近等深数值带共有 1,263 个像素，带内不宣称已证明精确浮点三角面 tie ownership。其对象/源面交点及无更近表面仍接受数值验算。未重新渲染图像，也未增加 Blender、MCP 或模型调用。

复核者曾参与产品接线，并编写本验收器。独立几何与生命周期审核由其他代理负责。当前证据说明这组固定任务存在全场像素不足及局部图可恢复的机会，自动选目标和模型实际收益仍需后续独立验证。
