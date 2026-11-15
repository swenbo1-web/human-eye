# A 实际产品复核

本次复核 `passed_checked_scope=True`，读取已关闭的 A_peripheral_02 原件，新增产品观察、Blender、raster、模型调用和产品import均为0。四份目标接线源码与A冻结、Git来源表及隔离安装逐字节一致。复核人是这四份文件的产品作者，独立质量审核另有已绑定报告。

实际公共请求以单元素 objects 指定 M4_Far_00，返回 brief-v5。目标为索引13、512个完整原始三角形，源面闭区间为[0,511]。其余13个对象仅参与遮挡，支持/不支持目标计数均为0，未成为unknown目标。A保留全部14对象、3474顶点与6146三角形。

目标在x=1平面、法向−X。根据实际目标三角形和六方向独立核对，SCENE/RIGHT背向，TOP/FRONT/BACK边缘朝向，LEFT为唯一正面。Near原三角形在x=d，d=8589935/2147483648。LEFT射线映射给出目标遮挡区域y≥0、z≥0、y+z≤d，其正面积为73786983304225/9223372036854775808。该面积及Near源三角形摘要与实际audit一致。实际LEFT视锥包含目标，六个complete均为false。

实际仅构造SCENE。已保存PNG与MCP图片块逐字节一致，RGB与当前NPZ一致，对象/源三角赢家及target patch映射一致。91559个目标可见像素、bounds和anchor从当前数组复算一致。SCENE的front_facing/readable保持false。1127个对比边界像素由独立质量报告交叉核对，本脚本没有重新计算该指标。

观察API的complete与目标unknown同时保留，covered=0、完整见证为空、finite_pool_exhausted符合当前证据。固定主输入没有达到完整可读见证目标。按预登记出口维持not_realized。输入冻结前没有确认存在无挡完整视图的规划不足保留，B和正式性能矩阵未运行。

实际公开文本7088 UTF8字节，PNG3223字节，原MCP RX为12139字节。写入文本的LF审计为12138字节，原wire结尾CRLF解释该1字节差异。根REPORT和DECISION中相关产品、目标、字节及scope措辞与本次已检查范围一致，未发现需要修改的声明。

限制为单个固定输入和一次成功A观察。LEFT没有构造图片，本复核没有独立reraster。当前NPZ可核，brief未交付生成时完整frame和NPZ摘要回执。工程收益、B收益、模型消费及更多场景仍未测。具体输入SHA、逐项检查和异常见PRODUCT_A_REVIEW.json。
