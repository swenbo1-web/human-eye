# M4-COMPLETE-WITNESS-CONSUMPTION-001 独立语义复核

固定作者交付 `8baad59ac6da01f14e1eb87c3e1f4f0687eb2b7d`。本项结论：案例确实区分readable与complete；当前产品事实正确；正式最终答案选择了正确完整见证。模型实际采用产品身份、完整见证索引和引用，同时进行了额外原生补核，不能记为纯产品直接消费。没有观察到产品错误被纠正。

冻结自动评分器在内容判断前因字段归属错误退出，原自动0/1与direct adoption=null继续保留。本报告是对同一原始材料的独立语义判断，不替换自动失败，也没有改评分程序或重跑消费者。

## 方法与实际范围

本轮子复核 `/root/witness001_semantics_review` 使用自己的 `review_semantics.py`。直接读取原始场景/相机、工具请求与响应、final及归档PNG/NPZ；以Fraction自行计算遮挡和入框，以NumPy/PIL独立读取现存像素并验证PNG与color一致。没有导入候选产品、作者oracle/scorer/normalizer或验收生成器。

132项明确检查、132通过、0失败。新增产品、模型、Blender、raster执行均为0。输入在 `INPUTS.json`，逐项结果和真实工具代码在 `RESULT.json`。归档的每个实际读取文件均与登记大小/SHA比对；本项没有代替其他复核进行全库身份审计。

## 独立几何和像素

源输入只有Panel_A、Panel_B两个矩形，每个由两个共边、同向、非退化三角形组成；四条外边构成矩形，两面法向均为+Z，四个源面全部有支持归属。A在z=0、xy=[-2,2]；B在z=3、x=[3,5]、y=[-5,-3]。

从相机的有理方向独立投影B到A平面：投影点为 `B_xy - 3 * direction_xy / direction_z`。SCENE方向(4,-4,3)产生[-1,1]平方，和A交集面积为4，A面积为16；其余五方向交集正面积均为0。按实际视图/投影矩阵把全部源角点送入齐次裁剪域，两面在全部六视图均完整入框且正深度。B高度在前，不会被后方A遮挡。这里没有使用产品的complete标记推导几何真值。

资格和正式各自实际保存SCENE、TOP两帧。每阶段独立绑定本槽帧账本和PNG/NPZ，重新合并raw 0–1为A、2–3为B，按不同surface及RGB平方差至少576的水平/垂直邻接标记双方端点，计唯一目标像素。

| 视图/目标 | 实际表面像素 | 实际对比边界像素 | readable | 几何complete |
|---|---:|---:|---|---|
| SCENE / A | 37,917 | 924 | 是 | 否 |
| SCENE / B | 12,639 | 0 | 否 | 是 |
| TOP / A | 70,756 | 1,060 | 是 | 是 |
| TOP / B | 17,689 | 528 | 是 | 是 |

两阶段8行公开pixel事实的数量、bounds、readable及anchor均与实际数组一致。A首条readable是像素行0，确实不完整；完整见证索引2正确指向TOP的A行。B完整可读见证索引3也正确。产品covered精确为两区域，remaining为0，unsupported源面为0。

资格与正式使用不同Owner PID，并各有2次构造账本。帧ref可能同值，因为同源、同序和同像素产生确定性身份；不能以ref相同推断借用了资格缓存，也不能只凭ref断言正式新构造。本项核的是正式自己的帧文件、实际attempt和独立Owner记录。

## 正式答案与实际采用

实际工具依次为active_observation、execute_python、execute_python，均成功。tool_02成功执行 `json.loads(last_observation_json)`；同时打印完整geometry/cameras，读取TOP已有缓存。tool_03把raw三角形归并为表面、全幅重算表面/边界像素、查询anchor与相邻RGB、计算源面法向。缓存请求为一次、new_raster_attempts=0，正式总构造仍2。

final明确引用当前source binding、两个ROI身份、两对象的正确中心/范围和源面；有限池明确列出六相机，声明两面均有TOP完整可读见证、剩余0、unsupported0，并限制结论范围。目标A实际引用：

- TOP与当前完整图像ref，公开 `complete_witness_pixel_index=2`。
- 70,756表面像素、1,060边界像素；owned bounds为(23,23)至(288,288)。
- 实际owned pixel(155,155)：object 0、raw triangle 1、RGB(164,173,187)。
- 边界点(23,155)与背景(22,155)的实际色差262.232721…，final四舍五入262.23正确。
- 全部角点入框、+Z正向、两面TOP投影XY范围分离，所以无正面积遮挡；此解释与独立几何核验一致。

模型没有把首帧SCENE的readable误作完整见证，也没有拼接部分帧。最终完整覆盖声明不止目标A一句答对，A/B、源面、位置和有限池余项均成立。

## 是否存在必须补原生证据的缺口

题面所需内容在第一次公开brief-v4中已经齐备：

| 题面需要 | 已公开事实 |
|---|---|
| 当前身份及来源 | binding、objects、regions的ROI与object index |
| 世界位置、方向和范围 | center、half-edge u/v、front direction、location conventions |
| 完整见证帧 | complete_witness_pixel_index、pixels的image index、images的view/ref |
| 可读像素与实际owned点 | surface/boundary counts、RGB阈值规则、visible_pixel_anchor |
| 全部集合与有限池限制 | covered indices、inspection counts/view_names、support计数、scope |

没有识别出题面要求但产品事实缺失、必须通过本次原生全幅重算才能补齐的字段。具体源face索引、额外RGB相邻点、数值色差及独立法向是消费者自选的更详细证据；source-bound record可以由已有来源绑定和ROI/对象身份组成，不要求重新发现源三角形。

因此，应记录“最终正确、当前产品事实确实采用、额外原生补核存在、纯直接消费未通过”。不能把补核说成纠正产品错误，也不能由这些动作推断模型内部心理上的“不信任”。本轮没有运行消融或第二消费者，不能量化省掉这些补核后的时间/token差值。

这是一个两矩形的定向语义反例，不是复杂场景性能样本。它关闭了本例readable/complete混淆的最终答案核验，但不证明任意复杂资产、所有模型或无需补核的消费流程已经完成。后续自动评分修复应对同一保存材料执行并保留原失败，无需重新调用模型。
