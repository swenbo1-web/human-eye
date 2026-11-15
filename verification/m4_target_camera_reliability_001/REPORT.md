# M4 目标相机数值可靠性修复

2026-11-15，批次 M4-TARGET-CAMERA-RELIABILITY-001。

## 本批判定

一个候选已完成隔离安装和固定旧新六槽资格，交管理员独立验收。极端大坐标、小尺寸目标取得显式 `numeric_insufficient`，实际完整观察能力仍待后续坐标表达方案解决。原点控制保持完整、可读见证，原遮挡控制保持准确 unknown。

旧批 A 的 `not_realized`、旧 A01 runtime exit 的 unknown 和历史清理策略拒绝继续保留。历史 F 性能复核另由管理员完成，提交 `162c29e6`，该复核维持 F 未准入，并确认历史恢复 E 已完成。本批以当前 M4 基线和自己的证据交付。

## 版本与最小改动

| 项目 | 固定值 |
| --- | --- |
| 基线 Git | `03eb4e2971891dfe0160972cbcf974e3dcf1a21c` |
| 候选产品 Git | `691f7b78ed89ccf30df47847fc1e99ad51a1dc64` |
| 分支 | `codex/m4-target-camera-reliability-001` |
| 141 源聚合 SHA256 | `9f2c5ca150f968841b64f4d4eda89313069453853c877ba21b6a262999e29a61` |
| wheel SHA256 | `0956bdeeebcbd5be47f79b0c34f6e3e1dca391b1b88cb4e985c2cb233433dd56` |
| 版本 | `9.7.2+m4.target.camera.reliability.r1` |
| 隔离安装 | `D:/he_m4_camera_001/candidate/product` |
| 冻结输入 SHA256 | `c10f7231091db360bf1fdb962ad916fba731df7cd94dfa3c5f5ff88e6cff4004` |
| 来源冻结 SHA256 | `bad3ad09e7614af541e8b95ba0c16eb498c6729f21af4c49d31993ca45094948` |

产品改动集中在两个文件。

- `blender_host.py` 的 `_observation_target_cameras` 复用共同中心相对顶点及每视图 XY 投影。依据最终实际 view/projection 系数，对相对计算、中心点积、全局 raster 点积及平移作向外误差包络。保留原 span，在无法保证 XY 包含目标时返回专用错误。
- `live_spatial_mcp.py` 的 `_error_result` 精确识别本地或远端对应错误，公开为 unknown 和 numeric_insufficient。保留 `isError`、错误正文、执行状态及禁止自动重试语义。因主捕获尚未完成，主回复只包含实际已知信息。

renderer、覆盖容差、遮挡判定、全场采集、缓存及默认部署均沿当前基线。候选安装和旧 A 安装分别保留。

## 数值验收

冻结输入先于生产修改，包括 binary32 可达极值、相同量化几何减共同原点、既有目标拟合及旋转控制、普通平移矩形和细长矩形。独立 oracle 对最终矩阵逐点使用 Fraction，并另算两阶段 binary64 求值的 Γ6 包络和多种求值顺序。生产路径使用普通浮点运算。

- 源码和隔离安装各 6 个固定输入通过。极值 1 个明确数值不足，其余 5 个可靠拟合。实际进入矩形核心并成功的控制为原点、普通平移和细长矩形 3 个，另外 2 个旧控制承担相机拟合检查。
- 原 384 输入离线网格原样重放。旧版接受 384 个，其中精确 XY 裁剪 14 个，独立求值包络无法保证 XYZ 的有 67 个。两项分别计数。
- 新版可靠拟合 273 个，明确数值不足 111 个，接受结果中的精确 XY 裁剪、独立 XYZ 包络失败和意外错误均为 0。
- 普通坐标量级 0、1e6、1e8 的既有控制保持接受。保守退出集中在大坐标、小尺寸组合，111 个退出构成本候选的能力范围代价。

该有限网格的结果用于本公式回归。极值从错误几何出画原因转为数值不足后，完整观察仍未恢复。

## 真实产品入口

三个固定资产各执行旧新两版，每版均依次调用主 active_observation、ping、只读 task aabb 回读、ping。主入口使用 `response_detail=full`，保存原始回执中的 producer NPZ SHA 和 frame identity。相机姿态由同一实际宿主捕获绑定，公开 full 序列化器当前省略 `binding.camera_specification`。

两版主请求和 Blender timeout 均为 30 秒，持有宿主保留原 600 秒生命周期期限。启动、采集、传输、分析、公开回执和退出成本各有原始时界。

资产保留原始 local、矩阵、面和实际量化尺寸。极值与原点的相同几何关系由资产构建回读验证。外部旧 peripheral 资产逐字节复制，保持其真实遮挡。

| 固定输入 | 旧版实际结果 | 新版实际结果 | 旧/新 raster |
| --- | --- | --- | --- |
| 极端坐标 | LEFT outside_frustum，covered=0 | numeric_insufficient，主捕获 0，图片 0 | 1 / 0 |
| 共同原点控制 | LEFT complete，covered=1，完整可读见证 | LEFT complete，covered=1，完整可读见证 | 2 / 2 |
| peripheral 遮挡 | LEFT positive_area_occlusion，covered=0 | 同一真实遮挡，covered=0 | 1 / 1 |

原点和 peripheral 的对应 frame identity、producer arrays SHA 在两版中一致。遮挡的独立严格正面积为 `73786983304225/9223372036854775808`。成功工具回执的顶层 complete 表示调用完成，区域完整性以 inspection、region 和实际见证为准。

固定 tight-bounds 纯反例的 LEFT 最大 y 为 `1.4452000066471393`，实机旧版最终矩阵为 `1.2560179652388406`。两者均实际出画。实机 world 与冻结 world 相同，实际目录的向外世界边界改变了相机 eye/depth，span 保持一致，纯反例数值与实机数值分别保存。

新版极值主调用仍返回 error 内容块，正文精确给出 unknown。随后 ping 和 task 回读均成功。该后续回读仅承担独立来源核对，单列 READBACK_CAPTURE。它具有自己的请求、计时和角色。

六槽均持有 MCP runtime 和 Blender 进程退出证据，exit code 为 0。源文件及终端几何指纹保持一致。保护范围为实际文件/终端检查及执行代码审查，无法据此排除所有可能恢复原值的瞬时修改。

## 成本和范围

冻结 helper 微测只执行一次。每尺寸 7 个旧新配对块，每块 512 次，每版每尺寸预热 16 次，合计计时 14,336 次、预热 64 次。原始块和离群值保留。

| helper 输入 | 旧 median | 新 median | 配对块比值中位 |
| --- | --- | --- | --- |
| 4 顶点 | 114.328µs | 121.034µs | 1.058653，增加约 5.87% |
| 289 顶点 | 2153.864µs | 1320.858µs | 0.613360，减少约 38.66% |

4 点固定开销增加约 6.706µs。289 点收益来自复用重复相对计算和投影。完整任务的实际窗口另行保留。

| 固定输入 | 主请求 RTT 旧/新 ms | 完整会话旧/新 ms |
| --- | --- | --- |
| 极端坐标 | 198.5008 / 145.4195 | 2266.3591 / 2240.6310 |
| 共同原点 | 339.5054 / 315.9316 | 2471.4940 / 2297.2753 |
| peripheral | 993.2967 / 905.4573 | 3301.3959 / 2885.1837 |

以上每个输入每版仅一次资格运行，存在启动和运行顺序影响。极值两版工作量也已改变。这些值完整记录开销，尚不足以形成端到端速度、尾延迟或模型任务收益结论。完整会话包括启动、协议初始化、主请求、回读、ping 和进程关闭，独立事后校验另列。

实际使用 7 次 owned Blender 启动，其中资产准备 1 次、产品资格 6 次，raster 尝试总数 7。上界为 10 次启动和 36 次 raster。所有预算 claim/settlement、原始 wire、脚本、生产回执、PNG/NPZ 和退出证据逐字节归档。实验模型和付费实验 API 调用均为 0，协调与复核模型成本尚未计量。

## 复核、失败及交付边界

独立分工为数值与图像、产品与隔离纯检查、宿主来源与成本。数值代理也编写了独立 oracle，产品代理参与最小错误映射，接线代理编写了 harness。这些关联在本批明确披露，最终准入仍交管理员执行。

目标公共纯断言 29 项、旧 full-scene 17 项、缓存/来源/预测 16 项及精确错误分流 16 例分别保留。29 项涵盖入口/绑定/分母/摘要合同，其相机场景数见冻结 6 输入和实际 3 资产。

隔离纯检查首轮发现 fixture 插入 checkout 路径后 hook 模块取到同字节源码副本，首轮失败结果保留。修正仅涉及本批 runner 的普通预加载顺序，R1 结果及实际执行来源另列。实际数值审计首轮对 unknown 回执缺失可选 `producer_frames` 字段的假设导致 KeyError，原 checker 和事件保留，修正后仅重算已关闭材料。

AL 当前 `context_bound=false`、`rebind_required=true`、host epoch 5。本聊天任务登记仍待当前宿主绑定，task 写入 0 次。

选择性采集 B、扩展相机池、默认安装激活、正式性能矩阵、全场模型收益和新付费调用均留给后续经审核的计划。本批达到的出口为有限数值可靠性修复候选已就绪。

## 证据入口

- [数值源码](CANDIDATE_NUMERIC_SOURCE_01.json)与[数值隔离安装](CANDIDATE_NUMERIC_INSTALLED_01.json)
- [384 输入重放](PRIOR_384_REPLAY_01.json)与[固定 helper 微测](MICRO_CAMERA_01.json)
- [实际相机与图像复核](ACTUAL_CAMERA_REVIEW.json)
- [产品与隔离检查复核](FINAL_PRODUCT_REVIEW.json)
- [宿主来源、退出及成本复核](RUNTIME_REVIEW.json)
- [原始运行归档映射](RUNTIME_ARCHIVE.json)
- [最终审计](FINAL_AUDIT.json)与[完整内容清单](CONTENT_MANIFEST.json)
