# 产品双 owner 实现与 focused 验证

实现起点为 `6e1e65c6eba0545ef7d3a4280e914b76c99a3f38`。所有写入位于 m4-view-reuse-001 隔离工作目录。本代理的真实 raster 总数为 19，模型和 Blender 调用均为 0。

## 产品改动

- `active_observation_images.py` 在既有映射阶段准备全局 int32 source triangle IDs，首 raster 的第四缓冲保存 raw winner，通过显式前景掩码查原 face_patch_ids 得到 patch winner。每个 raw winner 同时检查 object offsets 区间与 patch 一致性。
- 内存帧与真实 NPZ 保留 color、depth、owners、triangle_ids、patch_owners 五个缓冲。新 NPZ 为 13 个数组项，包含原 patch 映射和三个 owner 元数据标量。回读校验真实文件与当前映射，`observe_frame(..., include_buffers=True)` 显式返回已校验的五缓冲，默认结果继续可 JSON 序列化。
- 历史三缓冲和 patch-only 帧按既有支持范围读取，明确报告 triangle_ids 能力缺失。新帧引用绑定 owner schema、mapping identity 和构造身份。
- `active_observation_host.py` 的 host ref 使用不可变 frame_identity，并保留旧帧公式。`live_spatial_mcp.py` 的 full/debug 帧白名单保留新 owner 元数据。既有 brief-v4 图像、像素和事实表示测试通过。

## 首轮 focused 与相关单测

`product_checks_01/CASE_REGISTRY.json` 在首 raster 前写入。`RASTER_RECEIPTS.jsonl` 保留每次实际构造的开始、结束、角色与返回长度。

| 场景 | 产品 raster | 独立直接 raw-ID oracle | 旧 patch-ID oracle | 结果 |
| --- | --- | --- | --- | --- |
| 单 patch 八个源面 | 1 | 1 | 1 | 八种 raw winner，单一 patch |
| 三对象、近远与 unsupported 遮挡 | 1 | 1 | 1 | 三对象可见，unsupported raw 保留 |
| 同对象等深重合面 | 1 | 1 | 1 | 先出现的原始面获胜 |
| 裁剪三角扇 | 1 | 1 | 1 | 两个裁剪扇三角保持同一 raw ID |
| 全背景 | 1 | 1 | 1 | raw、patch、object 均为 -1，depth 为正无穷 |

五场景均对 RGB、depth、object owner 和 patch owner 与旧 patch-ID raster 做逐元素比较。raw oracle 的 IDs 直接从输入对象三角形数量及前向 offsets 建立，未使用产品 raw-ID 准备或 patch 反向查表。此 oracle 共用既有 raster 内核，独立性覆盖 ID 输入与所有权保留，内核像素算法本身的正确性仍依赖既有验证。

公共 2/3-tuple 真实调用各一次。发布失败后恢复实际调用两次，总计 19。注入故障发生于 raster 完成后的 NPZ 写入，第一次构造成本保留，缓存为空，下一次用新序号重新构造，随后复用完整帧。故障产生的 PNG 与零字节 NPZ 均作为测试原件保留。

同一产品帧连续读取三次保持同一 frame 和数组对象，仅发布一次 PNG/NPZ。真实 NPZ 重新加载后的五缓冲、metadata、readonly 属性与内存一致。source、camera、projection、128px 尺寸、face order/mapping 和多对象输入顺序变化均复用已生成帧检查失效与旧帧拒绝，新增 raster 为 0。

首轮通过 351 个脚本断言及 31/31 个相关单测。相关五模块全部使用 mock raster 或纯表示逻辑，真实 raster 为 0。单测完整输出位于 `product_checks_01/UNIT_OUTPUT.txt`。

## 缺省引用补充修复与保留失败

首轮 focused 未覆盖去掉 image_ref 的 saved frame。随后静态复查发现 dual 帧的 fallback 仍使用旧 patch-only 公式。同一真实 saved NPZ 的修前回放保存于 `no_ref_before_01/RESULT.json`，其中 dual 和 legacy fallback 实际碰撞。该文件的 passed 表示成功复现预期缺陷。

最小修正仅在 raw 帧缺少 image_ref 时追加 OWNER_SCHEMA、owner_mapping_identity 与可用的 frame_identity，legacy 公式保持。`no_ref_after_02/RESULT.json` 证明同一 saved PNG/NPZ 字节下 dual fallback 已绑定 schema，legacy fallback 稳定。全过程新增 raster 为 0。

`no_ref_after_01` 保留一次补充验证器错误。raster 禁用 guard 的 MagicMock 隐藏了原函数 signature，使公共 API 静态单测出现 KeyError，30 项通过、1 项 error。修正 guard 保留原 signature 后，同一 saved bytes 和 31 个 mock 单测全部通过。产品 fallback 修复后的实际引用在该失败记录中也已正确。该次错误未引发产品、模型或 raster 调用。

19-raster 首轮绑定 images SHA `22414d9e74e39c012988a638d50f72e43551a447d4ee747cef8a99ee3947b113`。最终仅追加上述 fallback 修复，images SHA 为 `c66ac2ae5ac0c147990763973fc6bc13cbf4162f7ba4770cceb0fe858cebe697`。最终补充通过 31/31，首轮矩阵保留原版本绑定。最终隔离安装验证由另一代理执行。

## 命令与产物

均在新 worktree 根目录执行，使用现有固定 venv Python，带 `-I -B -X utf8`。

```powershell
& 'C:/Users/Administrator/.codex/worktrees/2c7d/hefe/verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe' -I -B -X utf8 'verification/m4_view_reuse_001/product_checks.py' --product-root 'C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe' --output 'C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe/verification/m4_view_reuse_001/product_checks_01'
& 'C:/Users/Administrator/.codex/worktrees/2c7d/hefe/verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe' -I -B -X utf8 'verification/m4_view_reuse_001/fallback_checks.py' --phase before --output 'C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe/verification/m4_view_reuse_001/no_ref_before_01'
& 'C:/Users/Administrator/.codex/worktrees/2c7d/hefe/verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe' -I -B -X utf8 'verification/m4_view_reuse_001/fallback_checks.py' --phase after --output 'C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe/verification/m4_view_reuse_001/no_ref_after_01'
& 'C:/Users/Administrator/.codex/worktrees/2c7d/hefe/verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe' -I -B -X utf8 'verification/m4_view_reuse_001/fallback_checks.py' --phase after --output 'C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe/verification/m4_view_reuse_001/no_ref_after_02'
```

按上述顺序，退出码分别为 0、0、1、0。第一条首轮结果为 pass，351 assertions、19 actual raster；最后一条为 pass，31 mock tests、0 actual raster。修前与首次修后运行时的 fallback_checks 比最终脚本少了保留 guard signature 的三行，该修改原因及原错误已保留于结果和日志。

| 文件 | SHA256 |
| --- | --- |
| product_checks_01/RESULT.json | 62c7c0a1ff2041cf809074acde1d10df4bde9926e88d16a78efe313fb0f59165 |
| product_checks_01/CASE_REGISTRY.json | d3b4e9f82e815bef87ef27b60b9f0db77b9c84d4f3e5676877499c473c692b44 |
| product_checks_01/RASTER_RECEIPTS.jsonl | fedc0d86c754392fbdfdbea990bbf82dea10191541e46a6468ed79e2a7b33f01 |
| no_ref_before_01/RESULT.json | 207a822805f4a604b7a9df3a81ac76519e26bc56d8a311b0cbd7c3c778f62753 |
| no_ref_after_01/RESULT.json | 1970a1c04efedf47432565fab2c4464940d264fb5763bf9e9a6cce0cde6c7999 |
| no_ref_after_02/RESULT.json | 4ad84ed0a44c64f47d166ca037515f1c67843f07c8dd1ae9d1206ca33927ad93 |

Focused 实际光栅尺寸为 64px，128px 只检验绑定失效。512px 真实安装、消费适配器复用与五配对成本由独立集成执行。此报告不包含完整模型任务收益或首次成本结论。旧封存、旧安装和旧 worktree 未写入。本代理已停止产品源码和验证脚本编辑。
