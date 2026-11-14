# M4 可消费观察001：独立消费者质量与轨迹复核

结论：本槽原任务质量1/1成立，当前产品事实与公开JSON字符串确被实际使用；冻结的直接消费效率条件仍失败，因为实际又构造一次SCENE。不能把后者扩大成“重新发现整个场景、重算全部六相机遮挡”。模型此次只按已有产品区域核对源三角形归属，并核对SCENE一幅图的像素。

固定作者交付 `a7632563fa8631176816100ff4bef778bdbce318`，原件 `D:/he_consume_001/formal/P1/`。本子审计不修改作者文件，不运行产品、作者评分器、模型、Blender或光栅。根另核Git/安装/全部来源。

## 独立方法和结果

自写离线脚本 `audit.py` 对32份实际输入记录SHA，3720项检查全部通过。检查包括七项原始CLI事件与owner请求/响应对应、正式final与turn.completed、138区域/414像素行和SERVICE_RESULT、三张产品图与一张原生图的NPZ/PNG/CLI内容、完整覆盖表、未知理由及三项定位。

每视角完整几何参考来自上一批根已用有理几何独立复算过的P3表：先核此前记录的该文件SHA，再核当前scene/camera逐字节同源。没有把当前作者NORMALIZED或TRUTH当成答案，也没有声称本轮重算了整个几何场景。对四份当前实际缓冲重新计算表面像素、RGB距离平方至少576的横竖异区域边界两端去重计数、可见范围和owned anchor，逐项核对当前输出。没有重新生成光栅，不能仅靠同帧一致性证明上游渲染算法所有情况正确。

138个产品区域以世界中心、法向和四角映射到同源几何参考，再对应源三角形集合。集合无重复，覆盖3336个源三角形；triangle48为唯一域外余量。当前产品face_patch_ids与这一映射一致。115个covered均有当次实际图、几何完整且像素过门限的见证；23个未观察分别是22个无正面候选、1个所有正面候选均有正面积遮挡。

最终答明确引用实际工具事实完整覆盖账；tool7的138行源面与见证表逐行和当前产品/原几何相符。域外triangle48及有限相机池范围都未被吞掉。所有已观察行采用的视图在本场景确为几何完整。

|最终位置答案|独立证据|
|---|---|
|SCENE `[109,247]`|当前像素归属region72，原三角形35；中心 `[0.15625,-0.15625,0.11865234375]`，朝+Z，宽高均0.0703125米，354/73像素。原产品anchor已恰为该点；final却引用新生成image-04。|
|原点朝+Z|SCENE正向但0像素；BACK当前完整见证 `[419,224]`，468/84像素，产品image_ref相同；LEFT也可读。|
|指定底面朝−Z|region107保留no_front_facing_candidate；同源六相机方向均从正Z方向观察，final只限定注册池，未声称池外不可观察。|

最终使用BACK而非LEFT并不是质量缺陷。确定见证只要当前完整可读即可，不应让评分器硬编码一个视角。

## 实际消费方式

1. tool1真实调用active_observation，收到v4与当前三图。
2. tool2明确执行 `obs=json.loads(last_observation_json)`，打印公开JSON结构、图像引用和相机元数据。
3. tool3从该对象建立regions/pixels字典，直接查询两个指定世界位置和23个remaining理由。
4. tool4请求 `render_views(names=['SCENE'],include_images=true)`，实际返回cached=false的新image-04。
5. tool5把原几何的Fraction字符串直接转float，产生一次ValueError。tool6使用Fraction恢复，按产品已经给出的138个区域的center/u/v/front匹配所有源三角形，并读取SCENE点击的原triangle ID。
6. tool7把SCENE原triangle IDs按这个映射合并，核对整幅像素/边界统计，输出完整138行覆盖和源面表；随后有正式final与正常turn.completed。

公开进度说明的目的为“verify the queried pixel and retain source-face evidence”。这与实际请求和代码一致。它不是没有采用产品，也不是再次做区域发现或六池遮挡求解；无需推断模型内部“不信任”。

tool7自行选取首个readable作为表内见证，没有直接使用complete_witness_pixel_index；本场景所有161条readable实际也完整，所以表没有因此误判。该行为不能证明模型在其它场景一定理解readable与complete的区别，产品级契约审查由根另行汇合。

## 同字符串复用的证明边界

bridge在成功sendall后将该次公有结果 `content[0]['text']` 的不可变字符串直接赋给namespace。下一观察开始或失败会清空。实际tool2解析成功，tool3/6/7使用的字段和值与公有结果一致；owner与CLI公有内容逐字节相同。

没有独立对运行时namespace完整字符串做dump/hash，所以没有额外观测点直接证明其所有字节。当前证明来自固定赋值路径、成功发送与真实字段消费，不能扩大到provider内部输入字节、截断或token内容。没有理由为此再跑一个真实会话。

## 效率失败及下一步判断

重复SCENE的pose和PNG与产品首帧相同；将原native triangle IDs通过已核源面映射转换后，所有支持区域pixel owner相同。首次首包已经给出点击点的owned anchor及世界事实，重复渲染按原预登记criterion3必须记fail。原任务质量pass与效率机制fail应继续分开。

但该失败不等于上一槽整体重算退化。本次新增计算是一次SCENE、一次已有区域引导的源面匹配及一幅像素核验。是否继续优化应结合完整任务成本，而不是为了“重复为零”无限重跑同题。

若下一项选择实际帧复用，应注意当前native工具承诺winning raw-triangle-ID，而产品缓冲使用patch-owner。不能把两种ID直接替换后宣称native缓存命中。可以改进已有公开事实的查询/引用，或在明确契约下读取已有当前帧；不必以新增几何算法或强制禁止原生工具来制造成功。根应根据边际收益选择一个有限修复或转入公平任务收益对照。本结果本身不能给出产品相对原生的因果时间收益。

## 审计自身假失败

第一次离线审计有两项假失败，原 `audit_first.py`、`RESULTS_first.json`、`CHECKS_first.json` 均保留。其一把native背景sentinel −2与product背景−1直接比较；差异只出现在252939个背景像素，统一负值语义后支持区域完全相同。其二硬编码了未知原因标签的另一种拼写，真实标签是 `positive_area_occlusion_all_front_views`，与独立几何正面积遮挡证据一致。修正只涉及本审计器，不改变产品、原件、质量分母或既定效率失败。

最终RESULTS SHA256：`04d4e788519ddc127f13a500b96f549f4d6b266e7f63becf212aff81328495ea`。所有实际输入摘要与检查明细分别在RESULTS、CHECKS中；新增产品、模型、Blender、raster及benchmark执行数均为0。
