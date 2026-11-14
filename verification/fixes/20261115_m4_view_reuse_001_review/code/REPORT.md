# M4-VIEW-REUSE-001 源码与正确性独立复核

复核固定交付 `a9dd9490d1817630e090975362591ce232d881ae`，对比 `6e1e65c6eba0545ef7d3a4280e914b76c99a3f38`。源码位于隔离作者树 `C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe`。本项结论：**在已声明的产品帧交付及固定捕获重放消费域中，未发现阻塞接受的源码缺陷。** 成本取舍、完整来源与512安装记录由根的其他复核合并判断。

本轮只读源码、已有结果和保存数组；新增产品、模型、Blender、raster调用均为0。自写 `review_saved_owners.py` 使用NumPy读取既有NPZ并独立查表，没有导入作者产品、scorer或验收脚本。95项检查全部通过。输入路径/长度/SHA见 `INPUTS.json`；详细结果见 `RESULT.json`。

## 实现范围与正确性

1. 三份产品变更与计划一致：`active_observation_images.py` 建立和保存双owner、校验/回读与引用；`active_observation_host.py` 将owner/frame身份纳入host ref；`live_spatial_mcp.py` 在既有full/debug帧白名单保留元数据。光栅内核未改，未新增缓存服务。
2. 首次第四缓冲传入全局递增源三角形ID。原获胜条件只由几何、深度和遍历顺序决定，ID仅随同一mask写入；新的ID不反过来影响像素。`_validated_patch_buffers` 先确认raw/object前景一致及每对象offset区间，再前向查 `face_patch_ids`。背景raw/patch均为-1；未支持源面保留raw但patch=-1。等深首赢、裁剪扇与源面顺序沿原内核保留，未增加二次几何求解。
3. 新NPZ确有五个像素缓冲和owner元数据。`observe_frame` 检查文件SHA、映射及帧能力，验证raw/object/patch对应关系；显式 `include_buffers=True` 返回真实回读的只读数组。旧三/四缓冲继续在原支持范围读取，缺raw声明能力false。原2/3/4-tuple raster API未改。
4. 复用实际发生在新版本消费适配器：产品已成功构造的真实NPZ进入既有buffers/by_ref/by_view，默认render_views优先查已登记帧。native首次构造亦登记；同批重复names使用第一个结果，包括fresh批内重复。只有fresh或确实缺失/绑定不符/缺raw能力才构造。
5. `_register` 先完成文件、SHA、数组metadata和binding准备，然后发布ref、view alias和共享数组字典。构造号不同的fresh不覆写旧文件；old ref保留原数组，view alias指向最新成功帧。保存失败发生在发布前时，原好帧仍存在；已发生的raster保持计入attempt。构造后回执/附图失败不回滚已构造成本。
6. 命中键使用会话冻结source IDs、对象/face-array顺序与引用、完整小相机规格及owner generation，没有每次全场景哈希。源代际、mesh删除/替换/顺序变化要求新会话；pose/projection变化可miss构造；非512尺寸明确拒绝。这个消费夹具只承诺六相机512域，不是通用live scene缓存实现。

## 独立保存数据和最终修正

本轮检查六份64px已存帧（五个focused情形加发布恢复帧）的PNG/NPZ SHA、shared shape、int32 raw、前景/背景、正深度、原面range、object offsets、raw→patch及owner元数据。独立确认：单patch含八种raw winners，三对象场景的unsupported原面2仍有raw，等深及裁剪情形记录raw0获胜。这是当前保存数据一致性验证，没有新渲染，也不能把它写成重新独立求得所有像素winner。

作者首轮19次真实raster矩阵对应images源码SHA `22414d9e74e39c012988a638d50f72e43551a447d4ee747cef8a99ee3947b113`，最终为 `c66ac2ae5ac0c147990763973fc6bc13cbf4162f7ba4770cceb0fe858cebe697`。本轮独立撤回最终缺image_ref分支的代码修改，逐字节恢复首轮SHA；其余映射、raster、校验和保存代码完全相同。这允许明确区分“原矩阵验证未变路径”与“最终修正另验”，不冒称19次均在最终字节上运行。

最终 `no_ref_after_02/RESULT.json` 确实绑定c66；其补充在原saved bytes上完成、零raster，31相关mock通过。根复核独立按canonical JSON SHA公式计算legacy与dual fallback，分别匹配实际回执且二者不同。旧公式保留，新公式包括owner schema/mapping和frame identity。首轮补充MagicMock signature错误属于验收脚本错误，作者保留了after_01失败，不据此说最终产品失败。

作者五个focused raw oracle与旧patch oracle共用未改的raster内核，仅输入ID与验证路径独立。因此其独立性证明的是“ID正确保留且旧四数组不变”，不是第二套独立光栅实现。128px项是失效验证，没有128px真实像素oracle；512真实消费来自后续安装验收。

## 公开可达性、缓存和内存边界

根提出一个值得检查的内部顺序：若先修改Owner内部poses再首次active，产品ReplayHost仍读原capture，而产品注册binding取当前内部poses。当前公开工具没有这个修改入口：bridge向Python namespace提供的是geometry/cameras的deepcopy，实际渲染session使用自己的冻结对象；原生题面明确source read-only。直接改私有Owner poses属于本轮harness的受控失效注入，不能扩写成已支持live动态来源。故不以这一私有状态组合阻塞本固定域；以后若开放通用动态接线，产品frame.pose必须随来源同步，不能直接照搬此fixture的冻结假设。

`observe_capture` 中的ActiveObservationImages和像素buffers是函数局部，返回前剔除buffers，仅返回可序列化帧metadata。服务缓存的正常返回不是永久保留这些局部像素数组；新adapter从NPZ加载并保留整帧才形成新的可见常驻数组。因此新增约17.3MiB可见payload不能只解释为3MiB raw，也不能凭这条代码就称有另一份三帧永久重复缓存。临时读回、压缩、分配器与RSS峰值仍需单列未测。

当前旧ref保留及六次构造额度使这个fixture的保留量有界。多视图共用ref/view alias指向同数组，没有因每次命中复制整帧。无需为本候选另加淘汰框架、全量重复校验或新权限层。若今后扩大成长时间、多代际、多分辨率常驻服务，再以实际任务增长记录决定缓存生命周期；本轮不提前扩域。

## 验收结论

源码、现存数组和最终fallback修正之间的证据链成立；原失败与兼容范围应继续保留。本项建议进入根的完整候选判定，不因本轮已覆盖路径重跑模型或19-raster矩阵。复用节省是本地服务/构造路径收益，不能直接替代完整模型任务收益；先按既定成本与内存取舍收口。
