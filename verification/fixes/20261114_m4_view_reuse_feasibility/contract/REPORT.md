# M4 重复视图复用：最小契约只读复核

复核身份：`/root/m4_reuse_contract_feasibility`，Agent Learning 句柄 `fa4efe7d812d4ea9ac401169bad1adbc`。
范围：只读源码；未启动产品、Blender、模型或 raster，未修改正在封存的六槽输入、安装或源码。本报告是实现可行性，不是实现通过证明。

## 结论

好处理，但需要修真实产品帧交付和消费入口两处。产品已有帧缓存，缺的是把已构造帧交给消费者的统一入口。仅修改提示词，或者只把验收脚本的重复次数改成缓存命中，不能算修复。

建议唯一后续候选：**首次构造保留精确 triangle_ids 和现有 patch_owners；同源同视图请求默认复用，显式 fresh=True 才重建。** 不引入新缓存框架，不改变 raster 内核，不在每个请求重算全场景 hash。新版本合同另存；当前六槽的 every request is fresh 合同与历史失败保留。

## 已有机制与缺口

| 层 | 现状 | 最小落点 |
|---|---|---|
| `active_observation_images.py:263,300` | `_synchronize` 按 scene/candidate、对象顺序、patch mapping 和相机判断；`render_view` 先查 `_frames[view_name]`，命中直接返回 | 保持此缓存。首次 raster 的第四数组使用全局 source triangle IDs，再查已有 face→patch 表生成 patch_owners；两个数组均保存、加载、校验并交付 |
| `read_context.py:42,82` / `live_service.py:1389` | generation 是 capture instance/epoch/revision，selection 含 entry/token/source_binding；完整观察结果已缓存，命中 work 新构造为0。没有可靠 capture token 时不跨请求命中 | 沿用。现有复用不会免除本来已有的 host capture；本批不扩大到采集缓存重构 |
| `active_observation_host.py:294–336` | 调用真实 `images.render_view`，生成 host-bound image ref；序列化排除内存 buffers，但保留 NPZ及身份 | 将 raw triangle_ids 纳入 NPZ 和元数据，保持对象/三角形顺序明确。产品成功构造后的真实帧通过既有数组文件传递 |
| `native_tools.py:327–410` | `_register` 只填 by_ref/by_view；product帧已注册但消费者 buffers 未填。native `render_views` 无条件 `_charged_raster`，public_frame 总写 cached=False | 新版适配器接通已登记产品帧到 buffers；render_views 先按身份与能力命中，显式 fresh 绕过。产品缓存命中无需再次调用产品或 raster |
| `bridge.py:38–87,226` | 公共工具文档强制每次fresh；Python wrappers也未提供fresh参数；read_images已有同ref重交付 | 更新新版本 schema、Python wrapper、返回字段三者；旧冻结文件不改 |

产品源码本轮读取内容与候选 `99fa034ee6074a9b674c1bb05b3328b91e9d93fe` 这些文件没有 diff；读取时作者 HEAD 为 `3689ab0726fb05f1dd45e7f8fd628c3081d6835a`。验收适配器是在候选后新增，不能称它们都属于99fa提交；实际字节见 INPUTS.json。

## 新版最小接口合同

1. `render_views(names, include_images=False, fresh=False)`：先查现有 by_view。完整同键帧返回相同 image_ref、同数据、cached=True；不产生 raster intent、PNG/NPZ重写或伪造构造次数。fresh=True 走现有构造路径，返回 cached=False。混合请求逐项报告命中/构造，保持输入顺序。
2. product `active_observation` 注册帧时一次加载 NPZ，按产品现有验证逻辑保留 `color/depth/owners/triangle_ids/patch_owners`。优先抽取现有读取/校验小函数供 observe_frame 和适配器共同调用，避免第二套 validator。公开 buffers 仍是只读数组。新增字段的 validator 不能悄悄丢弃 raw owner。
3. `buffers[view]` 可保留“本视图最新帧”兼容入口，同时按不可变 frame ref提供同数组别名；public buffer_handle使用该ref。显式fresh后旧ref仍指向旧帧，不能把旧ref偷偷重定向新数组。image_ref是图像身份、构造attempt_id是尝试身份；fresh重建同字节可以图像身份相同，但新尝试必须单独记账。若buffer语义变化导致图像相同，frame/buffer ref必须包含语义版本，不能只用PNG hash。
4. 命中键只用已有可信身份：当前 session/owner + source generation/binding + scene/mesh order identity + candidate/pose/size + owner schema/version（raw triangle与patch分开）+ patch mapping identity。固定 replay 从已核验manifest/pose建立一次；live来源使用既有generation。不得仅按SCENE名字、文件路径或PNG像素相同复用。相机参数、size、物体替换/顺序、场景切换/撤销重连、mapping改变都必须失效。
5. 旧产品NPZ缺 raw triangle_ids 时，不能将 patch_owners 改名充数。新默认调用需要raw能力而旧帧不具备时明确记录 capability miss，构造一次完整帧，后续命中；历史帧仍可读图。已有patch值不能唯一反解raw source triangle。
6. 边界：这是**真实产品帧交付+当前消费者接线修复**。当前产品没有通用公开 render_views MCP 工具；不宣称已让所有外部/Blender原生渲染自动复用。无需为本批增加新MCP服务或live缓存框架。若后续正式工具采用该合同，应接产品帧身份和保存读取入口，不能另造一套相互不通的缓存。

## 计费与最小验收

raster构造、数据交付、MCP图片块编码必须分账。cache hit仅省实际raster/PNG构造；`include_images=True`或read_images仍可能读取PNG并再次base64编码、发出图片、消耗模型输入。每次真实编码继续record_constructed；编码后超时、序列化/发出失败不得退款。fresh调用和实际失败构造照旧占用构造额度。缓存命中不应因“无新raster额度”而禁止只读交付，但仍服从原请求/图片交付预算；不增加重型权限层。

必须在新固定版本跑以下定向测试，不再启动一轮优化循环：

- 产品先构造SCENE，消费者重复SCENE两次：新增raster=0，ref与RGB/depth/object/raw triangle/patch逐元素一致；不只断言cached字段。
- 原生先构造SCENE再重复：两组同合同，同样只有首次构造；fresh=True增加1次且旧ref未被重定向。
- `[SCENE, LEFT]` 一命中一未命中，以及同请求重复SCENE：只构造缺失项；不得每列表元素重建。
- source generation、camera/view/projection/size、object order、patch mapping、owner schema分别变更：旧帧不命中。宿主无version token保留原无跨请求缓存行为。
- product raw→patch查表与旧产品patch全像素一致；与独立原生同输入raw owner一致。选一个patch含多个三角形的样本，证明不是patch假装raw。
- 一次命中无图片，一次命中交付图片，一次交付后处理失败：raster不增加，图片构造/编码按实际增加，失败保留已消耗成本。
- 先定向功能验收并独立复核，再最多一个既有消费任务确认能直接读现有SCENE buffers。报告实际新增raw保留内存/压缩文件成本及端到端时间；不把静态可行性或省一次0.246s包装成完整任务必然显著提速。

实现后验收必须显示真实产品 NPZ 已携带 raw owner、消费者读取的是这些字节；只改 verification 的 public_frame/counters 不算通过。原六槽结果继续按原合同评分并封存。