# M6-SHAPE-DATA-001 来源文本审查

2026-11-14。根任务 `760eca87-1bd3-4335-9771-b1d8b67f517f`。合同固定于 `d88cf18d1a6cf564c907d980ccf0ef159a954e9f`。本文件记录四个指定角色目录内的来源文本、文件散列及可确认的派生关系。几何精确摘要、归一化近重复与求值网格映射由主线程另行登记。

## 范围与结论

审查首先使用 `rg --files` 盘点 `D:/codex data/2026-10-02/fps-blender-models/{Yanyite,Richie,Chipow,Yunhex}`，随后读取各角色处理记录、导入诊断、交付和保护报告，以及辨认对象和图像关联所需的处理脚本。来源检索覆盖这四个目录内的相关文本元数据，跳过与来源关系无关的工具运行时副本和视图性能实验。审查活动包括文件读取、JSON 解析、文本检索和 SHA256 计算。

四个角色的上游底模关系均登记为 `unknown`。文本可以确认各角色导入后的历史修订链，以及 Chipow 与 Yunhex 的场景交接链。可得记录缺少原始生成任务、底模标识和输入图到网格的对应凭证。不同角色名、对象 UUID、贴图散列及拓扑计数仍无法排除共同底模经过重采样和外观修改的可能。

本批将四者及其全部 patch、正常控制、损坏副本和历史修订保守合为一个来源组，限定 `train/dev-only` 用途。该分组反映尚未解决的来源不确定性。后续分组 JSON 由主线程冻结，当前材料提供一个保守来源组，独立验证组和保留测试组均为零。

## 已确认的角色内派生关系

### Yanyite

`source/Yanyite_Imported.blend`、外观处理版、备份和工作快照均属于同一角色的修订链。导入诊断登记对象 `0135bbc4-c6c7-4003-a402-6f2e0283497d`，27304 顶点和 53264 三角。外观交付报告给出处理前后相同的顶点、loops、多边形、UV、角法线和世界矩阵摘要。该报告适用于其登记的历史交付版本。原文短摘如下。

> “只复制材质掩码并更换材质”
>
> “live最终顶点、拓扑、UV、自定义角法线、世界矩阵哈希与应用前完全一致”

记录同时写明“后根据用户补充的岩屹正面原画优化材质”，并登记原画从项目 `outputs/character-design/Yanyite/Yanyite_Front_v1.png` 复制为 `source/Yanyite_Design_Front.png`。本审查读取角色目录内的参考副本。该记录建立后期外观参考关联，原始网格生成所用图像仍未知。[处理记录](<D:/codex data/2026-10-02/fps-blender-models/Yanyite/处理记录.md:3>) [导入诊断](<D:/codex data/2026-10-02/fps-blender-models/Yanyite/work/readonly_check/readonly_report.json>) [历史外观交付报告](<D:/codex data/2026-10-02/fps-blender-models/Yanyite/work/art_pass/live_art_delivery_report.json>)

### Richie

原始导入、外观修订、Manny 参考姿态转换、肩部和腰胯修订均属于同一角色。历史原始对象名为 `tripo_node_87e6a005`。处理记录登记 25768 顶点、49785 三角，姿态转换保持拓扑，并改变坐标和法线。后续记录给出 235 个肩部几何点修改，以及 1597 个腰胯几何点修改。原文短摘如下。

> “顶点与法线因参考姿态转换而变化”
>
> “最终改动235个权重点、235个几何点”
>
> “共1597个几何点”

因此，早期外观报告中的零位移和几何保全事实须保留其版本范围。设计图 `source/Richie_Design_Front.png` 及原 JPEG 的关联由记录和已打包图像路径建立。文本未提供该设计图生成原网格的任务记录。[处理记录](<D:/codex data/2026-10-02/fps-blender-models/Richie/处理记录.md:25>) [原始几何诊断](<D:/codex data/2026-10-02/fps-blender-models/Richie/work/geometry_diagnostic_report.json>) [腰胯交付报告](<D:/codex data/2026-10-02/fps-blender-models/Richie/work/waist_pass/waist_delivery_report.json>) [历史正式文件复检](<D:/codex data/2026-10-02/fps-blender-models/Richie/work/final_import_check/final_readonly_report.json>)

记录中的“采用风持同源的 Manny 参考”明确指向骨架参考文件及其骨名称、父级和参考矩阵。该条证据建立与风持的骨架参考关联，四个角色的形状底模关系仍未知。参考文件位于本次指定四目录之外，本审查使用角色处理记录中的路径说明。[骨架参考记录](<D:/codex data/2026-10-02/fps-blender-models/Richie/处理记录.md:28>)

### Chipow

原始导入、外观修订、额头清色、眼部材质调整和正式归档属于同一角色。导入报告登记主对象 `ebdce536-9931-43c0-bae3-30889edaf621`，28368 顶点、54636 三角。后期添加的 `Chipow_HairWisps_RootStrands` 是该角色派生内容，记录为 7461 点、13802 三角，并以原角色为 parent。原文短摘如下。

> “保留原场景Cube/Camera/Light和同一角色对象，只新增独立细发束mesh”
>
> “原角色网格未替换”

该新增对象与主角色共享来源组。`source/Chipow_Design_Front.png` 被登记为用户提供的外观参考。原 JPEG 的散列与导入报告 `image_packed_sha256` 一致，为 `f426c5aa052f0773bb3ba8bda958bbdd8eabb8eb057ae9e8c7bd11012aab6975`。[处理记录](<D:/codex data/2026-10-02/fps-blender-models/Chipow/处理记录.md:33>) [导入报告](<D:/codex data/2026-10-02/fps-blender-models/Chipow/work/readonly_check/import_report.json>)

### Yunhex 与 Chipow 的交接场景关系

Chipow 归档时记录现场新增对象 `6cf51555-9352-4a3c-ac37-8f872f25da97`，26819 点，当时身份尚未核定。归档报告登记 `incoming_identity_not_assumed=true`，完整现场保留在项目交接场景中。随后 Yunhex 的处理脚本明确选取同一 `6cf51555-9352-4a3c-ac37-8f872f25da97` 对象。Yunhex 原始保护文件名为 `source/Yunhex_Imported_Session.blend`。相关原文如下。

> “原始保护现场：`source/Yunhex_Imported_Session.blend`，包含导入时已有的完整场景。”
>
> “炽破已从此独立工作副本移除，其正式归档与原交接场景保留。”

这建立了共享交接现场到 Yunhex 独立工作副本的关系。Chipow 主对象与 Yunhex 处理对象的 UUID 不同，二者的上游形状派生关系仍未知。交接场景文件路径只作为角色目录内记录的证据，本审查读取范围维持在指定四目录内。[Chipow归档记录](<D:/codex data/2026-10-02/fps-blender-models/Chipow/work/archive_pass/archive_report.json>) [Yunhex处理记录](<D:/codex data/2026-10-02/fps-blender-models/Yunhex/处理记录.md:5>) [Yunhex首轮处理脚本](<D:/codex data/2026-10-02/fps-blender-models/Yunhex/work/face_alignment/apply_face_controls.py:6>)

Yunhex 被撤回的开眼、眼表面候选与当前自然化眼部版本属于同一资产修订链。当前文本报告登记 `Yunhex_NaturalEyeSupport`，权重约 0.65，225 个支持顶点，最大求值向外补足约 `0.0006424701423384249` 模型单位。主线程的当前保存帧求值快照及其稳定映射是本批后续取样依据，相关几何映射另行记录。[当前眼部报告](<D:/codex data/2026-10-02/fps-blender-models/Yunhex/work/eye_natural_pass/natural_eye_report.json>)

`work/face_alignment/reference_face.png` 与 `textures/Yunhex_EyeReference_Source.png` 实测字节相同。脚本第 65～67 行建立复制和图像加载关系，原文为 `shutil.copy2(FACE/'reference_face.png',source_texture)`。文本中曾用 image_gen 制作的虹膜纹理属于被撤回眼部候选。当前参考图映射和这些局部纹理的处理记录均未提供原始角色网格的生成来源。[自然化脚本](<D:/codex data/2026-10-02/fps-blender-models/Yunhex/work/eye_natural_pass/apply_natural_eye_reference.py:65>) [眼部修订历史](<D:/codex data/2026-10-02/fps-blender-models/Yunhex/处理记录.md:17>)

## 共同处理流程与未知关系

三份历史元数据保留以下 Tripo 图像或转换标识。

| 角色 | 文本中可复核的标识 | 证据 |
|---|---|---|
| Yanyite | `tripo_image_f503a439_0`，`tripo_convert_f503a439-c097-43d8-aed5-9e10bcf8607f.fbm` | [导入诊断](<D:/codex data/2026-10-02/fps-blender-models/Yanyite/work/readonly_check/readonly_report.json>) |
| Richie | `tripo_node_87e6a005`，`tripo_image_87e6a005_0` | [原始几何诊断](<D:/codex data/2026-10-02/fps-blender-models/Richie/work/geometry_diagnostic_report.json>)、[历史正式文件复检](<D:/codex data/2026-10-02/fps-blender-models/Richie/work/final_import_check/final_readonly_report.json>) |
| Chipow | `tripo_image_61b933e7_0` | [眼部原节点记录](<D:/codex data/2026-10-02/fps-blender-models/Chipow/work/eye_hair_pass/eye_candidate/eye_baseline_nodes.json:29>) |

这些标识支持共同 Tripo 处理流程关联。模型生成任务的唯一标识、生成配置、原始输入网格、共同底模及跨角色派生链仍未知。对象名、材质名或 UV 名中的不同标识不能完成来源独立性核验。

文本中可见的镜像和缩放操作均具有局部语境，包括眼部贴图方向、角色内部左右对应以及 Richie 参考姿态转换。四者之间的整体镜像、统一缩放或共同底模关系没有可闭合的来源记录。主线程继续进行精确摘要和刚体、尺度及镜像归一化近重复核查，文本结论保持 `unknown`。

## 当前正式文件与历史 SHA 的版本范围

当前正式文件的 SHA256 由本审查直接读取，与主线程 `SOURCE_MANIFEST.json` 的 `sources[*].original.sha256` 和 `sources[*].source_after.sha256` 一致。四者当前文件的读取前后 SHA 均相同。历史交付 SHA 与当前文件的差异应作为版本追踪缺口保留，该差异不影响本次当前文件读取前后散列保全成立。[当前来源清单](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/SOURCE_MANIFEST.json>)

| 当前正式文件 | 当前实测 SHA256 | 可得历史记录 |
|---|---|---|
| [Yanyite_Appearance.blend](<D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend>) | `614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d` | 处理记录和历史外观报告登记 `831fb35a74c979aa58303a79273f2832ec9e68d85e9f198b673ab60cf55f45d0` |
| [Richie_Appearance.blend](<D:/codex data/2026-10-02/fps-blender-models/Richie/outputs/Richie_Appearance.blend>) | `3e6d3a477c516e625515c327f6d4365da6821835206a5d8ce51779bdaba7aba0` | 处理记录和历史正式复检登记 `37a39cfacfc2507314393e0cc770a7aa79fe12f866a03a8a54689877d5dab097` |
| [Chipow_Appearance.blend](<D:/codex data/2026-10-02/fps-blender-models/Chipow/outputs/Chipow_Appearance.blend>) | `52c11defc6892f339a691cfdede924455e813f2fb414d4092758a50e35462f2d` | 与归档记录一致 |
| [Yunhex_Appearance.blend](<D:/codex data/2026-10-02/fps-blender-models/Yunhex/outputs/Yunhex_Appearance.blend>) | `f25116e94a56018afa97f2f3bd12307934b4103d972526a329f5ca3c36d48b3f` | 处理记录中未登记该正式文件完整 SHA |

Yanyite 与 Richie 的历史报告适用其登记的历史版本。当前二进制与历史记录之间具体变更尚未由这些文本闭合，当前文件的几何事实由本批导出摘要承担。Yanyite 本批沿用已冻结导出，其 raw 与 evaluated 数组相同。其他角色采用主线程登记的保存帧求值快照及对应映射。

## 来源文件和图像散列

以下全部 SHA256 来自本次直接读取。设计图和纹理文件的散列用于追踪具体文件及复制关系。

| 文件 | SHA256 |
|---|---|
| [Yanyite原始导入](<D:/codex data/2026-10-02/fps-blender-models/Yanyite/source/Yanyite_Imported.blend>) | `ebeff481fe72046ab291b754343d33d24b7caeee013ebc3a2d0ea3722723ded4` |
| [Yanyite设计图](<D:/codex data/2026-10-02/fps-blender-models/Yanyite/source/Yanyite_Design_Front.png>) | `5a261d83fee2c4a49dc59f6d1fb1ba5090b91ad301902986d089541d103caba6` |
| [Yanyite原JPEG](<D:/codex data/2026-10-02/fps-blender-models/Yanyite/source/Yanyite_BaseColor_Original.jpg>) | `1f86cd2ccb1fc073bf2309b78031b8d27c5dec742ade891727b4e6e841fc3988` |
| [Richie原始导入](<D:/codex data/2026-10-02/fps-blender-models/Richie/source/Richie_Imported.blend>) | `5cc6ae54289581b0b34ce09eb672ad710852e6e729f90c08eed89b4eca9ea457` |
| [Richie设计图](<D:/codex data/2026-10-02/fps-blender-models/Richie/source/Richie_Design_Front.png>) | `df1f755ed6fb296ed17890b941750afe2a177551d83bb69304ca7bfc8dc27849` |
| [Richie原JPEG](<D:/codex data/2026-10-02/fps-blender-models/Richie/source/Richie_BaseColor_Original.jpg>) | `ab71205042083945056e5171f7a4f3a3de13c4a2eec3e04fc3b96966eef0193f` |
| [Chipow原始导入](<D:/codex data/2026-10-02/fps-blender-models/Chipow/source/Chipow_Imported.blend>) | `e80f9767b4f1968e8dc0eb57080bc4f4dd9d3877d14053fd958feb503c3a2977` |
| [Chipow设计图](<D:/codex data/2026-10-02/fps-blender-models/Chipow/source/Chipow_Design_Front.png>) | `e1a8b098ab718c2918142b17f2c42dcf184c66ff7d0fc548faf17205a3af51ae` |
| [Chipow原JPEG](<D:/codex data/2026-10-02/fps-blender-models/Chipow/source/Chipow_BaseColor_Original.jpg>) | `f426c5aa052f0773bb3ba8bda958bbdd8eabb8eb057ae9e8c7bd11012aab6975` |
| [Yunhex原始保护现场](<D:/codex data/2026-10-02/fps-blender-models/Yunhex/source/Yunhex_Imported_Session.blend>) | `b17c315d3f2dbb509c2db3ecfc766beea7d8fb599fcc1219e8f5fe52e2114e04` |
| [Yunhex面部参考](<D:/codex data/2026-10-02/fps-blender-models/Yunhex/work/face_alignment/reference_face.png>) | `2b41f885cb70097daf086add3a32c17ac0b65333eb9155d3c67c326e9b201575` |
| [Yunhex眼部参考副本](<D:/codex data/2026-10-02/fps-blender-models/Yunhex/textures/Yunhex_EyeReference_Source.png>) | `2b41f885cb70097daf086add3a32c17ac0b65333eb9155d3c67c326e9b201575` |

## 文本证据散列

| 证据文件 | SHA256 |
|---|---|
| [Yanyite处理记录](<D:/codex data/2026-10-02/fps-blender-models/Yanyite/处理记录.md>) | `37f691e8a994dc83e98efdc14a9540185e0d8e5a2d5c13b83f9f7fffd32bb42d` |
| [Yanyite导入诊断](<D:/codex data/2026-10-02/fps-blender-models/Yanyite/work/readonly_check/readonly_report.json>) | `a710a610d237450e8572e3a2f471ecfc184c83669b6d569d6859811ecd960261` |
| [Yanyite原材质报告](<D:/codex data/2026-10-02/fps-blender-models/Yanyite/work/material_pass/source_material_report.json>) | `331c82b429b77fea85924132f6d47c79e5c16fa018483f9d8b18d9696e872f3d` |
| [Yanyite历史外观交付](<D:/codex data/2026-10-02/fps-blender-models/Yanyite/work/art_pass/live_art_delivery_report.json>) | `f5e7fcbb5eaf928fbf49f72b263f70c59ddd4961e05e653524368c4bf205a535` |
| [Richie处理记录](<D:/codex data/2026-10-02/fps-blender-models/Richie/处理记录.md>) | `91eb564a5e0657944bf22d18d10460b0bde7ecbef322e891cb199cf6c6478b64` |
| [Richie原始几何诊断](<D:/codex data/2026-10-02/fps-blender-models/Richie/work/geometry_diagnostic_report.json>) | `73307765f13ff0fb98584aa7ff38819477bcf51b6f906d4b5208557422f8ed46` |
| [Richie腰胯交付](<D:/codex data/2026-10-02/fps-blender-models/Richie/work/waist_pass/waist_delivery_report.json>) | `6a492dc4a540cbc9395043677ceb60c055df92ace74732d567679e94273b8379` |
| [Richie历史正式复检](<D:/codex data/2026-10-02/fps-blender-models/Richie/work/final_import_check/final_readonly_report.json>) | `ed20dd1c937b09d1f61512ba6784b448a0d4b0eccbb6d1190938b06337ab01a4` |
| [Chipow处理记录](<D:/codex data/2026-10-02/fps-blender-models/Chipow/处理记录.md>) | `6b298be29290bc3b13e00ccf316a787d73fe85fb0efadaac6a2f47a69c998abe` |
| [Chipow导入报告](<D:/codex data/2026-10-02/fps-blender-models/Chipow/work/readonly_check/import_report.json>) | `39f7efd779d80093fbb8ee5254563ecd4b7f381477c4eca82b81d6c41a4f5d60` |
| [Chipow归档记录](<D:/codex data/2026-10-02/fps-blender-models/Chipow/work/archive_pass/archive_report.json>) | `ce7a268e471c34931d78b7128a0cedee0cdf25b5427736de132f8b72fa8b28e5` |
| [Chipow眼部原节点](<D:/codex data/2026-10-02/fps-blender-models/Chipow/work/eye_hair_pass/eye_candidate/eye_baseline_nodes.json>) | `13a1c83f00b5c611d8553c3b743b74f4b9ebc02c7e708082e518cc034c2a1c2a` |
| [Yunhex处理记录](<D:/codex data/2026-10-02/fps-blender-models/Yunhex/处理记录.md>) | `8e0f31fe021bc5c406c7f169423091c4dab38d61ae60ec77799d954ba68e4603` |
| [Yunhex首轮交付](<D:/codex data/2026-10-02/fps-blender-models/Yunhex/work/face_alignment/live_apply_report.json>) | `5aa556c52ad8010b2cea75ec2fdce445269fd9f8eb5dea733854c76014764be2` |
| [Yunhex首轮处理脚本](<D:/codex data/2026-10-02/fps-blender-models/Yunhex/work/face_alignment/apply_face_controls.py>) | `d961f521fedcc83cfa6b15b77732c655d685e004c9686cb350e006d3addaeb7c` |
| [Yunhex当前眼部报告](<D:/codex data/2026-10-02/fps-blender-models/Yunhex/work/eye_natural_pass/natural_eye_report.json>) | `c2fa51fd09ae6280b23fcd2b7f5216a3174868b56f237f7712d687ba0e5aa074` |
| [Yunhex自然化脚本](<D:/codex data/2026-10-02/fps-blender-models/Yunhex/work/eye_natural_pass/apply_natural_eye_reference.py>) | `378da004c444dcc3597e57b2f826a935a297cb4aa5f7649976bc38dd2c4cdbcc` |

## 验收事实的归属

本审查核对文本、字段和文件散列。历史记录中“待用户观察”“待用户查看”“外观由用户验收”等内容保留其原有状态。Chipow 文本登记用户指定当前版为后续模型，该记录的适用范围为当时版本指定和归档。来源审查本身不增加用户艺术验收、动画验收或模型修复能力验收事实。
