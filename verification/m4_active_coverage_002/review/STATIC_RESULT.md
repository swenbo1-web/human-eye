# 主动覆盖002最终静态准入

结论为静态准入通过，当前源码接线没有剩余阻塞。此结论依据文件与合同阅读，正式资格和性能由唯一预登记批次的原始结果验证。

## 已完成核对

- 001优化几何、CoverageState和固定光栅按原SHA复用。根已接受的二十二首次三角见证及二十定向例沿用，本轮没有重跑几何资格。
- worker仅从新输入读取完整geometry、camera及固定依赖，旧证据审计在动态导入前安装。旧001的PNG/NPZ/READABILITY/oracle读路径受到阻止，动态链只调用已审纯几何及光栅函数。
- 每次被选视角单独生成共同depth/owner新帧，实际像素资格进入receipt后更新covered。主B第三图需求在第三次raster之前记录资格失败。重复已观察回执及结束状态不产生新图。
- 历史shortfall按观察保留，最终shortfall与state.unresolved求交。控制B还验证BACK不足区域在后续new_roi_ids实际回补，最后仅保留候选池几何不可见区域。recovered集合字段表示历史不足而终态已覆盖，B的时间先后关系由额外step条件验证。
- 两arm共用PNG和NPZ策略，数组dtype_str等五字段产消一致。parent纯回读对新PNG/NPZ/TRACE和像素计数核验，旧帧的内容比较放在child退出之后。
- 十二主槽AB/BA交替及两个独立控制槽预登记，BATCH_STARTED独占执行。worker最多六视角，主B最多两次真实调用；配合固定槽位形成主48、控制最多12、总60上限。失败与未知计数不被补成有效样本。
- 主时界从Popen之前到进程退出及完整回读验证之后。整批协调、源码核验及进度单列。控制器bootstrap未测范围明确保留。
- fixed BACK64控制的其余五相机逐字段保持，BACK的projection前两行恰为原值除64，span/half_span/m_per_pixel同步乘64。方向、center/eye、view、near/far及512尺寸保持对应。

## 准备期调整

旧帧预读范围、控制器窗口、unknown计数、dtype_str产消字段及控制恢复条件的静态发现和修正均保留在 `PREPARATION_ADJUSTMENTS.md`。未执行子进程预试、render或额外资格样本。

## 本次读取的定稿源码

| 文件 | SHA256 |
| --- | --- |
| runtime.py | `40a5dfc0abfee1b8cd46efd96e3670e64cf2a0dadcbb5585a75bbb5e4c0436e6` |
| runner.py | `9ae321f697dc3b53ddc39eec26d607db355ab1f58825632e4ac8600bb0aaf2bd` |
| validate.py | `1cfd1b8940b5271beb4e9164c12320c20f945c1e1919c57feae0076ba2d19a01` |
| PREREGISTRATION.json | `90cbada570a6f936f4e715666d35ba4151fe86225070b75e13cddee38ab8fcc8` |
| 控制camera | `1468391bba3910f5c107fd38974f4ef984a6d346dfd5444804ce8b9f3a2692d2` |

后续仅依据这次唯一批次原件静态复核，保留失败、未运行、准备消耗和未测项，不追加样本。
