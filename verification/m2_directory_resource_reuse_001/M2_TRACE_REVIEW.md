# M2 既有真实宿主轨迹资格复核

本轮结论为 `not_actionable`，自然任务命中数为 0。仅覆盖旧 M2 归档，其他 M4 轨迹由根及其他复核人覆盖。

## 固定来源

计划 SHA 为 `19c991d42ac17d0b8e38cfe7286c2c4c28fc4dd554c2e25c29fd52cc41d2cf21`，固定起点为 `8f2a739e789b777358d84a168154bc7c50b929e5`。审查前固定旧 M2 全部 4702 个文件，共 83,146,547 字节，清单摘要为 `160bb51671b16075298f228affb18b9b334c6e3144cdb0cb8e75a2c65363e254`。分析后逐文件复核一致。完整相对路径、字节数和 SHA 均在 JSON 中。

## 分母与实际顺序

- 共 42 个真实 Blender 任务宿主，其中正式测量 36 个、测前检查 3 个、MCP 正确性 2 个、typed worker 1 个。
- 测量保存 321 条业务记录，逐条对应实际 WORKER_EVENTS 与原始 WIRE 请求。321 份代码 SHA 均一致，含清理的宿主事件及 WIRE 请求各为 360 条。
- 测量正式 27 个目录类会话各执行 cold 加 10 warm，另有 9 个目录类读取得 selected task 的会话。旧路用 overview，原生路执行独立目录代码，新产品路用 directory。
- 全部归档共 368 条业务读取，另有 1 条 typed shutdown。显式产品目录共 139 条，其中缓存命中 98 条、未命中 41 条。
- 新产品目录测量有 12 个宿主，首次业务请求均为目录，原始宿主事件显示此前驻留资源数全为 0。后续 selected task 后没有追加目录。

## 可疑序列的排除依据

`entry_01` 与 `entry_02` 的真实顺序均为 directory cold → directory warm → selected task → full overview → directory after full。最后一次目录明确 `cache_hit=true`，其 instance、epoch、revision 与前面的目录保持一致。两次分别处于独立 Blender 宿主。`entry_01` 的最终清理失败仍保留在分母和报告中。

typed 顺序为 directory cold → directory hot → capture task → directory after selected → full capture → shutdown。任务后的目录与 hot 保存文件逐字节相同，目录状态保持一致，明确命中缓存。

两次 MCP 正确性中另有 26 条人工场景变更后的目录读取。原请求由固定 QA 脚本产生，涉及姿态、几何、单位、帧、命名、替换、撤销、重做、场景和重载。当前矩阵 oracle 可读，旧资源 stamp/pose 快照缺失，逐对象兼容性为 unknown。它们没有构成自然资源先取、随后首次目录的任务证据。

## 排除范围与限制

资产构建另有 1 个实际 Blender 进程，执行任务目录请求为 0。离线 fake bpy、固定输入算术、对旧回执再分析和安装快照均单列。CAPTURE_REPLAY 的计入数为 0。

42 个宿主均来自脚本化工程测量或正确性验收。共享 host 或 document 身份不足以证明资源 stamp 与 pose 匹配。MCP 功能档只保留公开调用与当前 evaluated oracle，内部未记录调用和资源兼容性保留 unknown。

本次新增 Blender 启动、模型、raster、evaluator、产品导入、产品修改、旧树写入和安装改动均为 0。按计划可结束这部分资格，不据此生成产品候选或性能矩阵。

## 复核关联

复核人此前编写 M1 定向测试、A 归一化和运行复核，本次审查脚本也由复核人编写。旧 M2 产品与轨迹生产脚本由其他实施人产生，本报告交根独立复核。

错误数为 0。具体输入绑定、完整逐 case 顺序、原始请求路径、宿主 PID、缓存状态、计数与 unknown 均在 JSON 中。
