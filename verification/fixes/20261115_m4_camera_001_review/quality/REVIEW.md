# M4-TARGET-CAMERA-RELIABILITY-001 实际入口与图像独立复核

复核者 `/root/camera001_actual_quality`，自身 AL assignment `8fea6a43-b503-4ff2-a57d-bb7d95d2243f`、父任务 `a7a6442d-90bc-4559-8dc2-726fd4a5885f` revision1/write720，开始时 current=true。固定作者最终提交4f8c41f8，产品691f7b78。

**结论：六个实际槽、七帧的本轮独立质量核查通过，未发现新的产品事实或图像绑定缺陷。极值是显式数值不足，不是完整观察能力恢复。** 自编检查器最终147/147、读取129个文件pin；不是147个独立场景或新产品调用。0新产品入口、Blender、raster、模型；不执行作者checker，不导入产品或重新渲染。

## 本轮实际证据链

1. 读取六槽原始stdio RX，对上实际main response、公开JSON及随后ping、task aabb回读、ping。实际native wire的resource/local vertices、矩阵和scale独立展开，逐值等于保存的main/readback capture；两个角色不互相替代。
2. 对五个成功main，独立重建完整几何身份、网格次序身份、相机身份、实际camera_plan摘要和带完整相机的host binding。公开full虽然省略camera_specification，原始host capture提供了同次实际矩阵，重算仍与公开binding匹配。
3. 七帧的实际stdio公开回执均包含producer NPZ SHA及PNG SHA，均与原文件、runtime归档逐字节相同。MCP实际image block与PNG相同，PNG解码RGB与NPZ color逐像素相同。这关闭的是当前七帧的生产回执内容绑定；未补写旧001缺失的producer摘要。
4. 独立重建source face offsets、target patch分母、owner/patch身份、frame identity及公开image_ref。所有前景raw triangle ID对应正确对象及patch，深度为有限正值，背景depth为+inf/triangle=-1。
5. 从实际数组独立按相邻像素的RGB欧氏距离阈值重计边界、表面、bounds与row-major anchor，核对前向性、readability和complete witness。没有用作者scorer输出代替这些计数。

## 三类输入的实际结果

| 槽 | 帧数与关键独立结果 | 判定 |
|---|---|---|
| OLD extreme | 1 SCENE；70582表面/1060边界，背向；LEFT最终矩阵出画 | unknown/无完整见证正确，原数值漏覆盖存在 |
| NEW extreme | 主回复numeric_insufficient、isError=true；无成功主捕获/帧/pose/见证；随后ping和独立task回读成功 | 异常明确且服务仍可读，能力未恢复 |
| OLD/NEW origin | 每版SCENE+LEFT；LEFT188325表面/1736边界，bounds[23,53,487,457]，anchor[255,255] | 实际完整可读见证保持，covered=1 |
| OLD/NEW peripheral | 每版1 SCENE；91559表面/1127边界，背向；LEFT仍被Near正面积遮挡 | covered=0/null witness保持 |

原点两版与peripheral两版的实际有序捕获几何、六视图分类、NPZ全部数组、producer NPZ SHA、frame identity及独立像素统计均相同。目标三角法向由实际顶点独立验证，均为−X。原点仅一个矩形、无其他遮挡物，实际LEFT矩阵逐点精确投影全部在视锥内。

peripheral目标289点/512三角，单位YZ格子、无重复源面、面积1。Near仍为x=d的同一三角形，d=8589935/2147483648。从目标沿LEFT方向(-1,0,1)到Near得到y+z≤d，严格遮挡面积为 `73786983304225/9223372036854775808`。实际first_blocker的三角摘要与面积匹配。此负例保持，不能算观察完整。

NEW extreme的“主捕获0”指未交付成功的main capture，不声称宿主此前没有读取目标或做拟合计算。其后独立回读取得几何，不能回填为失败主请求的camera/来源见证。实际extreme world与冻结输入相同，原点world严格等于同一量化后world减共同原点。

## 文案勘误：实机出画方向

作者REPORT称实机旧版“LEFT最大y为1.2560179652388406”，应写为**最大绝对值**，或明确两个端点：

- 最小y：`-1.2560179652388406`；
- 最大y：`0.32631888776602064`。

精确Fraction值保存在RESULT的`OLD_extreme: actual exact matrix clipping`条目。实机实际是负侧出画，仍是同类数值问题。原tight-bounds纯反例的正侧最大y=1.4452000066471393保持。两者world相同、span相同；实际向外directory bounds比tight bounds宽，从而eye/depth发生变化。此次检查分别使用各自实际输出矩阵，没有把两个数值混为一次执行。

独立checker首版沿文案只检查max y>1，因此在OLD_extreme断言失败；首版`review_first_attempt.py`保留。只修为双侧[-1,1]检查后离线140项通过，随后补实际三角法向/面积检查，最终147项通过。没有改作者原文、原始证据或重跑产品。

## 限制与作者记录区别

本报告检查保存的六槽实际回包、当前producer绑定数组及精确几何关系，没有独立重新栅格化每个深度赢家，也没有新建Blender进程。字节一致性不证明整个生命周期绝无短暂修改；进程退出、完整成本、源码/wheel/安装由其他复核分工处理。

作者384输入回放、六输入pure及96/567项审计不计入本轮147项。147是保存证据断言，不是性能样本。作者微测和单槽耗时不在此报告重判。

产物：`review.py`、`RESULT.json`及首版失败脚本均在本目录。所有文件修改仅本独立目录，没有改作者工作区、安装、原资产或Git。
