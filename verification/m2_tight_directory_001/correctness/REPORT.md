# M2 directory bounded correctness

固定产品为 fac9b4373575d653cc96f39f1dcb225300cd5977，137 源 canonical 为 6acb3ac7f014a590a279994f44be07c581af53a2da4dafae8dba9cd58eaea0bb。真实入口使用隔离 dir.r1 安装。

## 完成结果

`unit_02/RESULTS.json` 记录 16/16 方法通过，包括 12 个新增方法和 4 个已有 selected-task、ReadContext 与 compact-nearest 回归方法。137 物理源码快照通过原 verified-source guard，来源为 unregistered_runtime。所有 subprocess、socket 和 signal 哨兵均未触发。原工作树、快照及测试源码前后未变。

`entry_02/RESULTS.json` 记录 21 个真实普通 MCP 观察成功，包括 17 次 directory，以及 selected task、directory 后 full-delta 重同步、旧 overview 和 surface-nearest。每次目录独立读取当前实际 evaluated 顶点、矩阵、单位和时刻，由 Fraction 仿射计算核 bbox 与中心。新建场景包含旋转非对称四面体、凹 L 棱柱、含孤立顶点的网格。

13 个变更依次覆盖位姿、旋转、几何、单位、整数帧、subframe、重命名、同名替换、undo、redo、场景切换、删除和重新加载。另有关闭产品后重新连接。纯离线反例覆盖无通知回退、错误来源后恢复、过期、字节预算、空网格、非有限坐标，以及最小 subnormal、同号极大端点和异号中点。目录前后的完整 decoder 基底、资源 revision、动作 journal 和写入口隔离分别核验。

两次真实产品启动均取得实际 runtime PID 的 retained Windows handle，关闭后 exit0、handle_closed。owned Blender 亦正常 exit0，无强制关闭。新建 fixture 文件 SHA 前后相等的断言通过。此轮无模型消费者，全部时界排除于性能样本。

## 保留的首轮失败

`unit_01` 有 1 个失败和 10 个包含 subtest 的错误，影响 3 个方法。QA 错将冷暖 `cache_hit` 元数据作为恒等事实，并误认为内部 `_call_tool` 会封装异常。修正后只排除该明确元数据，保留 digest、对象、来源及代际严格比较。负例改由真实 JSONRPC handler 验证准确错误理由。旧测试源码按 SHA 保存在 `history/`。

`entry_01` 的 21 个功能观察均成功，但 QA 使用 `bpy.ops.wm.quit_blender()` 将退出排队至继承的阻塞 accept 循环之后，owned Blender 最终被强制关闭，因此该轮整体保持失败。原脚本、fixture 与结果均保留。新 QA quit 使用 `SystemExit(0)` 穿过只捕获 Exception 的原循环，背景脚本正常结束。`entry_02` 保留了 socket 空响应的 JSONDecodeError 和实际 Popen exit0，两者按原始状态记录。产品代码未因此修改。

## 口径边界

本批仅为有限正确性覆盖。actual MCP 工具目录原包已保存，未执行独立完整 JSON Schema 引擎。runtime 参数正负例有准确拒绝原因。真实同名替换同时改变几何，纯离线 fake-RNA 另核相同名称、不同实例的 identity 失效。两次功能 fixture、四次产品启动均计入 `SUMMARY.json`。

性能、模型收益、任意 modifier 和整段动画的结论仍由各自验收承担。原始结果、源码 SHA、功能记录和限制详见 `SUMMARY.json`。
