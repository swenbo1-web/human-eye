# Transport 首版回归

当前 27 个测试通过。其中 10 个新增测试核对 region_task 数字归一化、非法输入、缓存条件与来源变化、跨 scope 的同名 SCENE、图片块下标、完整图像构造档案、错误源与见证拒绝、图片后处理失败以及整对象量测补充。核心与服务组合使用受控合成 raster 输出，默认 brief 和显式 full 均经过实际产品投影及 PNG 编码路径。

原始 45 项旧测试组合有 7 项失败，原报告与完整 stdout 保存在 R0_LEGACY_RAW_CHECKS。7 项都要求已经升级前的 brief-v2 或 brief-v3。相同旧测试在固定的旧 B 隔离安装上运行 35 项，重现相同 7 项失败，完整结果保存在 BASELINE_LEGACY_CHECKS。旧测试文件保持原字节。当前通过组合采用仍适用的查询、brief 及已经接受的 legacy_v2 服务测试。后者已包含同捕获图片缓存、图片后处理失败后的缓存复用、六图上限与旧图片边界。

测试计数通过 Python profile 记录生产 attention_raster 调用、受控 core raster 函数调用以及 PIL Image.save。所有执行均没有启动 Blender 或模型。合成 PNG 写入及生产编码路径确实执行，其次数见 R0_CHECKS.json。core 独立测试覆盖取消、原期限与局部拟合数值不足后的已构造计数。

公开 region_task 数字为有限 int 或 float，排除 bool。整值 float 归为 int，其余保留 JSON 数值表示。几何比较使用十进制 repr 对应的 Fraction。面积范围与有向单位法向条件包含等号。region_task 使用全场捕获，objects 与之同时传入会被明确拒绝。无 region_task 的对象选择、task_query 及 whole_objects 量测沿现有路径。

新 brief 的图片表按 scope_id、camera_identity、frame_identity 和 image_ref 定位，native_content_block_index 对应所选图片实际交付顺序。full 保留所有 constructed_frames 与各 scope 的完整来源、相机、事实和帧引用。未选入六图交付上限的本地见证保留 selected_for_delivery=false 和空图片块下标。
