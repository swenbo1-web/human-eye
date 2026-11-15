# 相机数值不足的错误映射

本改动范围为 live_spatial_mcp.py 的 LiveSpatialMCPServer._error_result。输入数值用例冻结后才编辑该函数。

宿主沿既有失败包发出 BlenderHostError，message 精确为 `active_observation_target_camera_numeric_insufficient`，mutation_uncertain 为布尔 false。连接器沿原逻辑生成 HostRemoteError。

映射仅接受完整的三个远端错误字段，校验 dict 的精确键集合、type/message 精确值以及 mutation_uncertain 的布尔身份。本地同一 BlenderHostError 类的精确实例和同一 token 也可映射。普通 ValueError、派生类、字符串前后缀、缺少或多出的字段、不同宿主错误类、true 和整数0均沿原错误出口。

匹配后，公开文本 status 为 unknown，reason 保留宿主机器代码，observation_status 为 numeric_insufficient，observation_mode 为 active_observation。error、tool_outcome=unknown、automatic_retry=false、MCP isError=true 及原请求执行字段保持现有合同。捕获没有完成时不生成来源绑定、区域、完整见证或图片事实。

现有目标与完整模式的成功结果、实际遮挡 unknown、outside_frustum 分类和图像构造流程由原入口产生。本映射由相机精度专用宿主错误触发。

纯检查将直接调用实际 _error_result 并读取返回的JSON文本。16个固定案例列在 ERROR_MAPPING_TEST_PLAN.json。检查status、reason、原错误文本、MCP错误标志、单文本块、无伪造facts/binding以及原请求字段。它们是错误合同反例，场景数仍按相机和真实输入分别记录。

本任务的实际Blender、相机、raster和公共入口资格由根代理统一执行。子代理的AL仍未绑定，登记pending。旧A01退出unknown与缓存清理拒绝的历史沿原记录保留。
