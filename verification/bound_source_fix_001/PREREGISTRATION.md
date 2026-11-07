# BOUND-SOURCE-FIX-001 唯一候选验收

从d6fdf2a出发，只改blender_host新acquisition路径。一个helper按去向一次：所有对象全三角面结构/角索引校验，在任何原生展开之前完成；excluded随后用每对象临时bytearray去重验证引用坐标有限；retained坐标复用原_capture。没有mesh.validate/minmax重算/新缓存/schema/版本常量变更。全局数量门限和原期限复用，正常退化面仍属M3资格。

原16定向测试、旧M4/九点对、host/selected回归及新增工作计数通过后，固定源码/测试/五脚本/原资产/binary/helper再启动。旧fake缺RNA布局的原失败及一次未覆盖generated-wire模块的适配失败保留；只在新测试runner补缺失fake接口，产品绝不添加回退。真实只一个NativeSession，原far_second_degenerate私有副本，五状态RPC+close共6RPC，最多每状态一次capture，0重试/第二session/builder/性能/消费者/API/安装。600秒+60清理，完整turn14:00Z（北京时间22:00）截止。

五状态均从同一原件几何开始且finally恢复，不保存blend：

1. 原baseline：成功，far仍严格排除，2对象展开；一次build信息。
2. 后续点3=(.25,.25,.25)，正常mesh.update/view_layer.update：成功，far保留，3对象展开。
3. 同一far后续被引用顶点NaN：正常RNA构造，预期受控 `acquisition_nonfinite_referenced_vertex:<far id>`；不成功发布排除。
4. 同一far loop3索引13（6顶点）：预期 `acquisition_invalid_triangle_indices:<far id>`，不原生展开。
5. 完全相同的坏索引数据仍放在原far对象，但本次明确选择它作为 `focal_id`，检验其真正focal角色（名字不决定角色）；预期同类受控索引错误。原名M4_Focal只有一面，无需为测试新建面、替换mesh或重建资产。

正常API拒绝/归一化如实记，不换方法；宿主/传输未知则清理不重放。捕获前后native oracle完整坐标/索引为QA真值；NaN明确标签化比较，不用NaN!=NaN误判漂移。完整oracle不是生产gate。实际compile字节、TX/RX、动作/恢复、Popen.wait及初末指纹保留。

额外工作由离线真实helper的属性读取及bytearray分配计数给出，不把原首面见证或原_capture读数算作新增：有效两面excluded查6角+6唯一引用坐标，retained查6角+0坐标；400共享面查1200角但只读3坐标；最大500000顶点marker payload不超过500000B。不得宣传成速度收益；真实作业墙钟也不是正式性能对照。
