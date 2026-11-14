# 唯一矩形遮挡案例

固定产品沿 VIEW-REUSE 已验收交付 a9dd9490d1817630e090975362591ce232d881ae，产品候选 d12c7ab248452ff253452007d0635f2d662f0191，141 源摘要 d8ad7003397d0c0611f54d128c0d0ad3433865b8d9f69b8b0519123752fe9f02。产品与旧封存保持只读。

本文件属于管理员准备材料。消费者仅获得当前源几何、当前相机及一般任务要求，以下预期视图、数量和解析结论不写入消费者题面或工具描述。

## 一次固定的输入

只有一个案例，全部位置采用世界米的 JSON 整数。

| 对象 | 有序四角 | 本对象原三角形 | 全局源三角形 |
| --- | --- | --- | --- |
| Panel_A | (-2,-2,0), (2,-2,0), (2,2,0), (-2,2,0) | [0,1,2], [0,2,3] | 0, 1 |
| Panel_B | (3,-5,3), (5,-5,3), (5,-3,3), (3,-3,3) | [0,1,2], [0,2,3] | 2, 3 |

两个对象均为单个 +Z 绕向矩形，分别保留自己的四个顶点。无非平面组件、无额外 modifier 或动态姿态，当前支持域可直接表达两者。目标通过正常对象名 Panel_A 指定，无预置 ROI 或完整见证视图。

`CAPTURE_REPLAY.json` 明确包含 synthetic replay provenance，来源为确定性整数网格。兼容字段 source=blender 供既有 host schema 使用，实际 Blender 捕获和进程数均为 0。没有将合成输入描述为真实用户资产。

## 独立解析关系

对法向 +Z 的 Panel_A，从观察方向 d=(dx,dy,dz) 看，位于 z=3 的 Panel_B 在 z=0 上的遮挡影子为原 xy 坐标减去 (3 dx/dz, 3 dy/dz)。各相机均有 dz>0，且所有几何已按同一完整场景相机规则拟合入框。

| 相机 | B 在 A 平面的影子 xy | 与 A 的正面积交集 |
| --- | --- | --- |
| SCENE，(4,-4,3) | [-1,1] × [-1,1] | 4 平方米 |
| TOP，(0,0,1) | [3,5] × [-5,-3] | 0 |
| LEFT，(-1,0,1) | [6,8] × [-5,-3] | 0 |
| RIGHT，(1,0,1) | [0,2] × [-5,-3] | 0 |
| FRONT，(0,-1,1) | [3,5] × [-2,0] | 0 |
| BACK，(0,1,1) | [3,5] × [-8,-6] | 0 |

A 面积为 16，SCENE 中中心面积 4 被正面积遮挡，剩余面积 12。其完整外轮廓与背景相邻，解析上保留较宽的可见边带。该视图的可读像素数和对比边界数必须由资格运行的真实 RGB/owner 核验，不能从几何完整性直接推断可读。

B 在 SCENE 中投影内含于 A，二者使用相同 +Z 法向和固定颜色，着色也相同。因此 B 在首帧可能没有达标的颜色对比边界，即使它在几何上完整。首轮提案曾推测 SCENE 会覆盖 B，独立复查指出这一可读性区别，当前设计撤回该推测，场景保持原字节。TOP 中两者投影分离，可读性仍由实际资格结果决定。

## 实际交付顺序的依据

静态审查既有 CoverageState.next_view，首个观察固定选择 SCENE。后续只在未观察视图中按尚未覆盖的几何完整区域数取最大值，并保留相机顺序打破并列。

A 在 SCENE 中未完整，余下五个视图均几何完整。B 在余下五个视图也几何完整。无论 B 首帧是否达可读门槛，TOP 都与其余四个未观察视图的几何增益并列，注册顺序最先为 TOP。因此预期实际序列从 SCENE 到 TOP。是否在这两帧终止必须由实际完整且可读 receipt 决定。

资格成功要求 A 第一条实际 readable 记录来自不完整视图，并且后续实际交付的另一帧同时完整、可读。若该区别没有出现，返回 not_realized 并结束本批，不调整本案例再次挑选。

## 相机与生成边界

`make_case.py` 未导入产品模块。它用 NumPy 复写已冻结的全场相机公式，保留原六方向、顺序、512 像素、5% 单侧 margin、同一包围盒中心、刚性 look-at 与正交投影。每个源顶点在六帧内的 NDC 和正深度在生成时直接校验。独立资格程序还需与真实产品返回的相机逐字段绑定。

相机公式静态来源为 active_observation_host.freeze_cameras、attention_rendering._attention_camera、scene_rendering._look_at 和 scene_rendering._projection。生成器没有执行区域发现、可见性求解、产品 observe、raster、Blender 或模型，也没有生成多个案例进行筛选。

输入生成只执行一次。

```powershell
& 'C:/Users/Administrator/.codex/worktrees/2c7d/hefe/verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe' -I -B -X utf8 'verification/m4_complete_witness_consumption_001/make_case.py'
```

| 输入 | SHA256 | 字节 |
| --- | --- | --- |
| SCENE_GEOMETRY_RATIONAL.json | 27ab4bf41ec446440432c01b0ebdd2173cd99b49db27bca2ee79a97c215daa0f | 926 |
| CAMERAS.json | 56d5b2b2bca93b430ee6f1f7129beb2269256d9e878f178583af0e99744993c9 | 18174 |
| CAPTURE_REPLAY.json | 9e0dc12badc43aa932e8782f9af0059ab000655aa0b5ff3b570f83e31333097e | 3976 |

两对象、八顶点、四源三角形，六相机且尺寸均为 512×512。资格运行及之后唯一消费者由根在准备闭包冻结后执行，产品资格最多 6 raster，正式最多 6 raster，当前生成阶段三者调用数均为 0。独立真值与像素核验由另一代理提供，预期结论不会注入产品 JSON 或模型上下文。
