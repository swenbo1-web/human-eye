# 可独立安装的主动观察纯核心验收

## 本批结果

选定的细分矩形发现、optimized 连续覆盖判断、实际帧可读性、CoverageState 和短事实已经进入两个正常产品模块。默认使用选定二维候选，默认执行移除了逐面工作字典、位长扫描和细粒度计数。诊断模式只增加阶段时钟与汇总规模。

源码和安装后默认 API 都通过固定数据、历史帧回放和状态失效验收。独立 wheel 已安装到仓库外，四项定向单元测试通过。实际新图共6张，普通两图与像素不足四图按预期完成反馈闭环。正式五配对满足事先冻结的工程准则。

完整入口的产品/原候选配对比中位为 **0.9775590096**，对应下降约 **2.24%**。五次累计由 **2431.6817 ms** 降至 **2389.3582 ms**，下降约 **1.74%**。第一对回退约 **0.68%**，全部保留。有限序列包含移除计数后的变化和未变阶段的波动，统计显著性及纯算术因果分解仍待证据。先前模型任务收益具有独立的任务与计时分母。

本批跨作者本地证据审计通过，管理员独立验收待进行。当前交付为隔离安装候选。宿主和 MCP 的下一条只读连接合同在 `NEXT_HOST_CONTRACT.md`，产品默认激活等待管理员复核。

## 版本与实际安装

- 基线 Git 为 `b638c499c049604902415965f500f50a9947d34f`。
- 初始准备 Git 为 `372102917dd1caf003cccb5ac77697bc42f3de06`。
- 安装布局修复准备 Git 为 `778090eb27a318a815648daccb94d2c3f7c14eb3`。
- 原冻结 SHA256 为 `507661a5372f4b679e2e85e7b76a2941ed0c51fba5894ce00ab9226823e551c1`，1233项来源。
- R2 冻结 SHA256 为 `032fdbfeea0dab167fcf03230306eed98b47c196832d536edbf884fa1fc1d7eb`，1596项来源。
- 新几何/状态模块 SHA256 为 `b99871b94ef74b9e92d422b09fabe4e32024a2a099a3e77d4248b94ff588f652`。
- 新图像模块 SHA256 为 `f64de2f4fb7be152198c5ff3c0ac101021ee1cf81601f823587a8cf3a49cdf34`。
- wheel 为 `human_eye_spatial_plugin-9.7.2+m4.active.observation.core.r1-py3-none-any.whl`，1143492字节，SHA256 `27f649e96728f84b72638ccce49575f21d71c15cbc3824a6c3f1b6e30d6c93d8`。
- 产品来源摘要为 `29c3f2a1a312d2d5eda1d688619846ae4137832576f9ff3ddf078c42d1a866c3`，140个产品源码纳入正常来源清单。

使用既有 wheel 构建器从明确源码清单构建，重复构建字节一致，wheel RECORD 全量校验。实际解释器为 `D:/he_core_001/venv/Scripts/python.exe`，工作目录为 `D:/he_core_001/run`。最终产品专用目录为 `D:/he_core_001/product`，独立依赖位于该 venv 的 site-packages，通过 venv 内正常 `.pth` 发现产品。

已安装的140个产品源码与准备源码、wheel 和首次失败安装快照逐字节一致。源代码中的运行入口采用静态产品导入和显式参数，移除了实验目录加载、FunctionType 重绑和固定旧安装路径注入。

## 默认 API 与数据流

```python
from human_eye_plugin.active_observation import prepare_scene
from human_eye_plugin.active_observation_images import ActiveObservationImages

session = prepare_scene(scene, cameras)
images = ActiveObservationImages(session, output_directory)
while session.next_view() is not None:
    frame = images.render_next()
    images.observe_frame(frame)
facts = session.short_facts()
```

完整世界几何只规范化一次。发现与覆盖索引共享同一已解析表示，图像适配也直接从该表示建立真实完整细分网格。规范四角与 front 用于 ROI 和可读性，实际遮挡三角形持续参与公共 RGB/depth/owner 光栅。

预测完整可见掩码与实际已覆盖状态分开保存。观察入口核 PNG 的真实 RGB、NPZ 与内存数组一致性、共同 depth/owner、来源和相机身份及16表面像素/4对比边界像素/RGB24口径后，再提交 CoverageState。重复查询复用状态与图像，同来源 rebind 保留可复用图像，来源或相机改变使旧覆盖失效。

短事实包含对象名称、ROI、当前状态与 unknown 原因、实际视角、图像引用及像素标量。完整 triangle_indices 位于内部几何和帧记录。源参数与调用方责任详见 `API_CONTRACT.md`。

## 固定差异与回放验收

原始两三角形、4分段规则、4分段重排交替、16分段规则、16分段重排交替五表示，分别比较 default 与 diagnostics。ROI、front、全部实际面索引、排序、36项分类和 unknown 范围与固定旧 selected candidate 相同。正交旋转与带孔控制在两模式下也逐值对照。

源代码资格和安装后资格各完成10条主表示、4条控制、4条历史观察链及1条重复/场景/相机失效组合。每次资格读取8个已封存历史帧，明确计为离线回放。观察轨迹与像素事实对旧原件逐值核对。4个定向 unittest 方法均通过，使用合成临时 PNG/NPZ 和 mocked raster。

新进程在仓库外由正常已安装 API 执行，使用复制的几何、相机和明确历史帧。已安装新模块及 NumPy/PIL 的实际路径、字节与版本被记录。原受控 source loader 在导入前绑定140源，实际加载的新模块获得执行见证。Python open访问记录显示运行阶段的仓库、旧安装及管理员答案读取为0。原候选的两个源码副本仅在正式基准的 setup 阶段读取。

## 六张实际新图

| 相机池 | 新实际视角 | 覆盖增量 | 最终覆盖 | 有限池未覆盖 |
|---|---|---|---|---|
| 普通 | SCENE → BACK | 2 / 3 | 5 | Obj_006 |
| BACK64反馈控制 | SCENE → BACK64 → LEFT → TOP | 2 / 0 / 2 / 1 | 5 | Obj_006 |

每个光栅前先持久化全局意图。全批6个实际意图、6个成功帧，硬帽8。BACK64数值来自已验跨度64倍控制，只变更视角名称以明确引用。其像素不足造成0新增，状态随后继续选择 LEFT 和 TOP。

新图的 PNG、NPZ、数组元数据、引用与收据均保留。36条新像素事实由独立整数对比及 owner 端点回算，PNG、共同深度和来源绑定同时复核。两阶段合计16次逻辑历史帧回放，对应8个历史帧文件。旧帧数据与新观察的分母分别记载。

## 唯一五配对完整入口检查

在同一解释器与依赖内，原已选 candidate 与已安装产品默认 API 交替运行。每次从新读几何/相机文件、哈希和 JSON 开始，计入规范化、发现与完整索引返回。模块导入、源码校验、安装和结果序列化在外层单列，正式基准渲染为0。10条原值全部保留。

| 配对 | 顺序 | 原候选完整入口 ms | 产品默认完整入口 ms | 产品/原候选 |
|---|---|---|---|---|
| 1 | 原/产品 | 482.7624 | 486.0511 | 1.006812 |
| 2 | 产品/原 | 485.3668 | 472.5442 | 0.973582 |
| 3 | 原/产品 | 487.3448 | 476.4083 | 0.977559 |
| 4 | 产品/原 | 490.2624 | 478.5994 | 0.976211 |
| 5 | 原/产品 | 485.9453 | 475.7552 | 0.979030 |

同质量、完整配对比中位≤1和产品总耗时≤原候选的准则均满足。当前候选只有静态产品组合及默认审计开销删除，数学、裁剪、排序和像素标准沿用固定实现。

## 失败与修复原件

首次安装来源检查在 setup 失败，报 `verified_source_preloaded_module:numpy.version`。原因是受控 source root 覆盖整个 site-packages，原守卫将其中第三方模块也纳入内部源码执行见证要求。该失败发生在算法、实际光栅和正式计时开始前。

保留原失败 RESULT、ACCESS、绑定及140个失败安装源码。临时安装中的产品包、七个根模块和 distribution metadata 移到外部失败快照，逐项核对绝对目标范围。随后按正常 pip --target 安装到产品专用 root，依赖留在自己的 venv，`.pth` 提供正常包发现。R2 worker 仅把 NumPy/PIL 的两处路径断言绑定到独立 dependency_root，既有守卫及140个产品源码保持相同字节。修复后四个安装阶段均正常退出。

后验 API 审查发现宿主合同中一处类名错误，已由 BlenderReadonlyHost 更正为真实的 BlenderSceneHost。原冻结文档保存在 `review/document_correction/`，修正说明记录原 SHA 与最终 SHA。此文档是冻结清单唯一有原件归档的事后变更，运行源码与结果版本没有变化。独立审计的首次读回按冻结字段和 benchmark PROCESS 字段的错误假定停止过两次，随后按已登记文档例外及实际 quality-gate 链式绑定复核完成，原读回记录保存在 `review/FINAL_AUDIT_FIRST_READBACK.json`。包/API作者另有3项路径或字段判读修正，逐项保留在其审计记录。封存摘要另有一次将36行 pixel_rows 列表直接与整数比较的断言错误，修正与原件说明保存在 `review/FINAL_SEAL_READBACK_CORRECTION.json`。共6项后验审阅读取/判读修正，正式执行分母单独保留。

## 成本与后续接点

正式模型消费、Codex CLI consumer、Blender、Google和付费 API 调用为0。NumPy/PIL依赖静态复制1046个文件，共57693783字节，复制后逐字节哈希一致。准备、构建、首次安装、修复安装和各新进程的启动至退出时界均有记录，详细汇总见 `review/FINAL_COST_AUDIT.json`。五次外部 worker 从启动到退出合计15.6391168秒，包含失败。源资格、构建、修复和全部 worker 的不重叠已暴露窗口合计25.2250419秒。初始标记准备窗口为1594.3891315秒，含协作等待。新 PNG 共17983字节、NPZ 共126081字节、六帧数组载荷共23592960字节。环境构建10.60秒、venv创建4.07秒和依赖复制6.53秒存在嵌套，成本表保留其关系。RSS、完整最终发布耗时及未暴露的阶段分解填 unknown。

下一条薄接线从既有 BlenderMCPHost.capture_scene / BlenderSceneHost 完整已求值采集进入，保留米制世界坐标、loop triangles、host document/session、capture revision、完整遮挡范围与对象实例顺序。摄像机池与图像反馈使用同一绑定，外层来源更新触发状态失效。精确矩形谓词在真实 binary64 资产上的域外结果须保留，容差拟合需要独立的能力依据。

完整交付清单为 `CONTENT_MANIFEST.json`。最终 Git、来源例外、wheel/install身份和各项结论在 `FINAL_AUDIT.json` 与管理员 READY 回报中对应。
