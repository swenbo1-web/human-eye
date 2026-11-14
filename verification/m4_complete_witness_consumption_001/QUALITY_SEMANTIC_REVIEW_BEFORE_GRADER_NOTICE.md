# 正式 P1 质量与采用语义复核

本次最终任务答案通过独立语义复核，25 项保存证据检查通过。产品公开事实已实际读取，并用于当前来源、区域身份与完整见证索引。无原生重算的直接消费条件未通过，实际发生了原生像素与几何补核。

复核材料为本次 P1 的 PUBLIC_FINAL.txt、三次实际工具请求/响应及响应内 PNG。没有读取本批 TRUTH、私有资格结果、usage 或耗时汇总。复核者曾负责本案例输入设计，该角色予以披露。冻结评分器与独立像素/来源审查仍各自保留结果。

## 最终答案的实际依据

- 完整集合逐条列出 Panel_A 与 Panel_B 的当前 ROI，声明 remaining unknown 为 0、unsupported 为 0，并明确限制于六个已注册相机池。两条区域、两条 support 计数、来源对象和全部四个源三角形都在当前公开事实及原生几何输出中对应。
- Panel_A 中心 (0,0,0)、原三角形 0/1、世界矩形 x/y∈[-2,2]、z=0 与当前事实一致。Panel_B 的中心 (4,-4,3)、原三角形 0/1 及世界位置也由当前输出支持。
- 最终逐字引用 complete_witness_pixel_index=2。当前公开 regions 第0行的索引2解析到 pixels 第2行，其 image_index=1、region_index=0、front_facing/readable 均为 true，再解析到 images 第1行 TOP。
- 引用的当前 TOP ref 为 active-host-image:823c9ba62ce65a39b49823c87db8685b0e772edc4238d5dd1d70a1c9b804fe70。它同时出现在首产品响应及后续缓存查询，响应内 PNG 的实际 SHA 与公开 image_sha256 相同。
- Panel_A 的 70,756 surface pixels、1,060 unique boundary pixels 和 bounds[23,23,288,288] 与公开像素行及实际补核输出一致。Panel_B 的 17,689/528 也对应当前 TOP 像素行。
- 实际补核输出确认像素[155,155]的 object owner=0、global source triangle=1、RGB[164,173,187]。最终引用的边界点[23,155]及背景邻点[22,155]、RGB 与对比值262.23符合实际输出262.232721...的两位小数舍入。
- 当前第一条 readable 的 A 行实际为 SCENE 的 pixels[0]，37917/924。最终选择完整见证映射中的 pixels[2]/TOP，没有把第一条 readable 替作完整见证。最终未额外叙述 SCENE 的局部遮挡，题面也未要求追加该句。

## 采用与补核分开记录

tool01 是真实 active_observation(include_images=true)，返回当前 brief-v4、来源绑定、区域、完整见证索引及图像。

tool02 实际成功执行 json.loads(last_observation_json)，同时打印完整原生 geometry/cameras，并查询 TOP 缓存帧。返回 cached=true、new_raster_attempts=0，ref 仍是当前产品的 TOP ref。

tool03 读取该帧的 triangle_ids/RGB，将原始面0/1和2/3分别归并为表面，重新计算全幅水平/垂直邻接的对比边界与 surface/boundary counts，读取目标像素及颜色对，并计算源三角形法向。最终明确使用了这些独立验证结果。

因此本次属于产品事实采用加原生补核，最终答案正确，无原生重算的直接采用为 false。当前补核没有暴露产品事实错误或产生修正产品答案的记录。它也没有调用新的渲染函数，现有 TOP 帧复用记录与额外计算分别保留。此处只分类数据用途，没有统计耗时、usage 或任务收益。

## 记录与限制

完整逐主张出处、请求/响应/最终答案 SHA 和检查结果保存在 QUALITY_SEMANTIC_REVIEW.json，SHA 为 10ba581bcede645aec715ebea9545e3806e5b342cc6700fc4f28abd332b67015。最终答案没有引用本地 artifact，复核也未读取其它 scratch 文件填补答案。

图像核对绑定保存的实际工具响应内容，CLI 入口、来源与接收链由独立审查覆盖。本复核未启动产品、模型、raster、Blender 或测试。结论仅适用于本次固定案例与实际最终输出。
