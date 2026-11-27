# M6-049 实验与独立验收

**最终版 `9.7.2+k049final` 通过 032 现有 BVH 几何查询的替代验收。** BVH 用空间范围把三角形分组，用于找最近点、测量距离和扫描近邻。候选独立安装，在求解前根据面数和原计算额度选择 R3 或内置 032。本实验保留现有桌面 Hook（接收提示和工具事件的入口）。实际发布、安装和桌面自动触发验证另行管理。[独立验收报告](../../docs/M6_R3_FINAL_REPLACEMENT_049_REVIEW.md) · [实施者报告](REPORT.md) · [事前验收标准](../../docs/M6_R3_FINAL_REPLACEMENT_049_TASK.md)

| 输入或任务 | 032 与最终版的实测结果 |
| --- | --- |
| 两件各 129 面的压力例 | 两版都用 1,918 次精确比较算出 9.568319 毫米，均为两侧各自编号 128 的面。修复前的 R3 在 16,384 次后仍然未知。另一份同面数的历史输入按 032 原规则保留未知 |
| G60，12 个物体，找最近并扫描 5 毫米内的对象对 | 4.280 秒 → 0.751 秒。六组完整业务全部更快，配对降幅中位 82.49%。计入进程启动和退出后缩短 67.60% |
| B02，24 件装配，找最近并扫描 2 毫米内的对象对 | 2.109 秒 → 0.585 秒，六组全部更快，配对降幅中位 71.33%。732 次求解中 18 次用内置 032 |
| Yanyite 人物，同一局部区域第二次读取 | 12 组的配对中位慢 1.23 毫秒（3.07%）。实际移动参照物 15.625 毫米后，两处区域都按新位置给出距离 |
| D48，从 47 个对象中找最近 | 首次 4.182 秒 → 0.662 秒。直接命中缓存的一次重复查询为 30.94 → 43.13 毫秒 |
| G508，非凸模型 | 找最近 4.520 秒 → 4.553 秒，11 次都走内置 032。扫描 10.654 秒 → 8.635 秒。041 轮原 R3 在同一资产的单次观察约为 0.567 秒和 0.997 秒，显示出保守选路的性能代价 |

百分比先按同组算再取中位。D48 和 G508 是单次观察。84 个固定输入相对 032 均保留原结果，83 个算出距离，1 个按同一原因返回未知。共享接触、错误输入、既有预算限制和局部编辑失效的结果见独立复核。G60 第一组缺少业务结束后的宿主快照，该组原业务回包、计时和进程退出均保留。全进程组同时峰值内存和更换桌面 Hook 后的自动派发均未测。[84 例逐项结果](public/CASE_RESULTS.json) · [独立复核数据](../m6_r3_final_replacement_049_review/RESULTS.json) · [逐组取时记录](public/TIMINGS.json)

## 核对与复现

在仓库根目录运行下列命令。第一条只读取随分支发布的数据，重算 G60、B02 的六组配对结果及 Yanyite 的暖读变化。第二条可选，在临时目录重建候选并将经过摘要核验的 wheel 写入指定目录，要求 Python 3.11 以上和 Git。本次已用 Windows 上的 Python 3.12 验证。构建只需要本仓库的 Git 对象，原模型、Blender 和原实验机数据均无需参与这个步骤。

```text
python -I -B verification/m6_r3_final_replacement_049/replay_public.py
python -I -B verification/m6_r3_final_replacement_049/replay_public.py --wheel-dir ./dist-049
```

正常完整克隆包含全部来源。只取了本实验分支的浅克隆，重建前还需执行 `git fetch origin codex/m3-bvh-deep-optimization codex/b32g-hook-release-closure-001-product codex/m3-bvh-work-credit-032-product`，这三个来源的固定提交分别为 `119327bb`、`31792523`、`6c93f237`。候选含 145 份 Python 源文件；受测 wheel 的 SHA-256 为 `308dd624cb4916b28bbe2decae87ac0a80d05dfad793da5afecebc65ac698964`。[候选源清单](candidate/PINS.json) · [局部遍历补丁](../m6_r3_region_attribution_043/candidate/C.patch) · [最终选路补丁](candidate/F.patch)

## 实验记录

本分支接续已发布的 041。042–048 保留了定位过程和未通过的方案；049 的实施与复核材料分别取自固定本地提交 `a5323d6d` 和 `430b4edf`。报告、实验脚本及复核数据保留原始提交字节。原始报告里的 Windows 绝对路径用于回查实验机；模型、私有安装、现场线包和实际配置留在原存档。此处提供额外的可移植核对入口和原件摘要。[041 对照](../m6_041_kernel_hook_comparison/REPORT.md) · [本次发布目录与来源](public/PUBLICATION.json) · [3,210 份原件的文件清单](public/RAW_FILE_INDEX.json)

| 轮次 | 复核问题 |
| --- | --- |
| [042](../../docs/M6_FORMAL_ENTRY_AND_WARM_REGION_042_REVIEW.md)、[043](../../docs/M6_R3_REGION_REPLACEMENT_043_REVIEW.md) | 区分普通 Blender 局部耗时与桌面 Hook 行为，定位 Yanyite 局部查询的慢点 |
| [044](../../docs/M6_R3_FRESH_BUDGET_044_REVIEW.md)、[045](../../docs/M6_R3_REPLACEMENT_ENTRY_045_REVIEW.md) | 在原预算上比较 125×125 与 129×129，记录 032 可答而 R3 未知的反例 |
| [046](../../docs/M6_R3_PREVIOUS_WITNESS_046_REVIEW.md)、[047](../../docs/M6_R3_COVERAGE_DOMAIN_047_REVIEW.md) | 保留未获额外剪枝的尝试，建立面数与工作量的上界，说明适用范围 |
| [048](../../docs/M6_R3_WITNESS_PARITY_048_REVIEW.md)、[049](../../docs/M6_R3_FINAL_REPLACEMENT_049_REVIEW.md) | 核对距离、最近点和原始面，再用同一最终安装验收覆盖及完整成本 |
