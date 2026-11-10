# LRC-PREP-001：零启动失败交接与索引范围修正

状态：**FIX_READY**。正式 GO 仍未发，模型、产品、CLI、Blender 调用均为 0。

## 修复范围

固定旧准备提交 `169b0be061e91b126f46313478690564ccb2bd60` 的打包器要求至少一个正 consumer PID。真实驱动可以已经登记 STARTED、进入首格并保存 terminal RUN_RESULT，却在输入/actor/初始快照或 CLI Popen 阶段失败而没有正 PID。原件虽然存在，旧打包器无法交付该失败与后八格 not_run。

当前打包器只为“无记录正 PID”的情况新增窄验证：当前 cycle 的 GO 授权、PLAN SHA 和 max9，STARTED 的同摘要/上限/真实时钟，以及首格失败终止记录的计数、停止原因、时钟和错误自洽。consumer=None 使用首格错误；已返回的失败 consumer 使用其 errors，允许 PID 为 null 或缺省、外层 errors 为空、finish 保留原状态。没有推断“未记录 PID”等于证明无人启动，没有将 unknown、失败或尾格改成成功。

GO/STARTED 原始字节沿既有 private/control、SHA 和末尾防变化检查保存。正 PID 路径以及所有原答案/语义投影函数保持不变。没有增加新的执行框架或权限入口。

## 保全和验收

`original_169b0be0/` 保存11份固定旧脚本/控制/报告，根复现及失败 JSON 按原字节复制到本修复目录，没有重跑根旧模型或产品。最小实现差异见 PACK_FIX.diff，现有完整 SOURCE.diff 和 SOURCE_REUSE 摘要已更新。

新验收只运行合成数据，旧231项原断言函数按归档源码编译后用于新打包器，明确记录新输出路径、固定 pack SHA 和原输入基路径的运行时覆盖。新增三种首格失败，以及缺失/错误启动依据、未终止、无失败证据或不一致时序/计数的拒绝。模拟 GO、PID、cells 只存在于带标记的独占短 QA 根；完整原件 ZIP、成员 SHA 和真实路径保全到 tests，真实批次没有 GO/cells。所有失败和辅助元数据脚本错误均保留，不覆盖为绿色结果。

`tests/RESULTS.json`：原231项全部通过，加79项新分支/归档/哨兵检查，合计310项；新增31个案例为3种合法失败＋28种精确拒绝，错误0。subprocess/socket尝试0。`OUTPUTS_02.zip` 逐成员核对618份原始材料，短临时根原件也保留；不把原231的重复执行称为新增独立场景。

固定 pack SHA：`3b960695d5308ac64c5512191d7c0dc4e854a72b5fa07b97ccb5dfe0c0b3c365`。测试 wrapper SHA：`5f68f70d98b7af7fd60b5c5dd4f7255ccab1717847ad257a017b67cb8148bbcd`。完整合成输出 ZIP SHA：`9a983c2fea8ad303a7756b1a556466b1d309fc59e6ba5762d30ebf84eef8dc80`。

首次新 wrapper 因归档源码的 __file__ 祖先改变而读错旧图片路径，在新打包门槛前失败；修正仅显式覆盖原输入基路径，原231函数和 pack 未改。实现摘要的首次静态脚本误用 AST 属性，修正只涉及元数据读取；没有执行产品。

## 索引范围

原固定提交实际有692份批次文件：680份原索引＋3份根自引用记录＋9份被 basename 排除的嵌套 FREEZE。独立 Git blob 核查确认九份均完整存在，精确路径、字节和 SHA 在 INDEX_SCOPE_REVIEW.json；没有原件丢失。

封存规则现在仅排除根级 ARTIFACT_INDEX、FREEZE、PREP_READY、FIX_READY 四份自引用文件及本地字节码缓存，所有嵌套同名元数据均纳入索引。最终数量按“索引文件数＋四份根记录＝本次提交批次文件数”核对，不再把683当作原提交总数。旧索引、冻结记录与旧 ready 同时归档纳入新索引。

本轮没有重做安装/来源矩阵，没有修改产品、共同输入、匿名 ID/顺序、评分语义、收益合同、actor/transport、时界、工具预算、默认配置、共享 GUI 或原资产。只更新必要脚本摘要和封存元数据；既有 pyc 留在本地，未尝试删除。AL仍未绑定host5，未借句柄写任务。

修复完成后回报管理员 FIX_READY 并停止，等待独立复核；不得沿用旧六格或尚未签发的本轮九格 GO。
