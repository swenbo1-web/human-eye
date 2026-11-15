"""Write the fixed data research report from actual counts and measured costs."""

from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import read,write
from collect_costs import collect


def main():
    qa,sampling,current=read("DATA_QA.json"),read("SAMPLER_AUDIT.json"),read("CURRENT_GEOMETRY_QA.json")
    costs=collect()
    write("COSTS.json",costs)
    low=lambda key:min(row[key] for row in current["cases"])
    high=lambda key:max(row[key] for row in current["cases"])
    concave=sum(row["natural_shape_counts"]["concave"] for row in qa["coverage"])
    covered=sum(row["ever_damaged_points"] for row in qa["coverage"])
    text=f'''# M6-PERCEPTION-DATA-001 数据交付

## 固定来源与分母

本批针对插件当前三维数据到区域感知的离线研究，交付同部位正常/合成凹陷配对、当前几何重建器及均衡状态抽样器。冻结提交为 `1d690ec2540be2ea86dc80037b2125ba63792919`，合同提交为 `9191dd8df4999ead991254a5eb4100f1c9944b0b`。

实际取得 MIT 六个 poses 包，保留原字节、README、OBJ 注释及 SHA256。horse/camel 与 face/head 两个派生组用于开发，cat/lion 整组用于验证。6 个网格身份、3 个已知派生组、12 个姿态均来自同一研究集合。每源 reference 加自然排序首个其他姿态，12 个姿态均有坐标差异。horse reference 扩展名是 `.pose`，实际为 OBJ 语法。归属与原几何问题依据原作者说明保存。[原作者数据页](https://people.csail.mit.edu/sumner/research/deftransfer/data.html) [原论文](https://people.csail.mit.edu/sumner/research/deftransfer/Sumner2004DTF.pdf)

24 个 ROI 均为 384 点，96 个损坏中心，576 个凹陷加 24 个正常观察，共 600 个唯一观察。开发400、验证200。单次固定矩阵完整执行，来源、姿态、中心和强度均无补选。正常观察物理存储24份，配对表576行。

503 个凹陷通过固定有效性定义，73 个失败保留在总分母。54 个真实支持点少于6，19 个出现相对原三角的局部翻面，共30个翻面实例。新增退化面0、方向未判定凹陷0、新增不可用顶点法向0。失败观察均排除出凹陷训练成员。开发可用338对，验证165对。horse派生组173、face派生组165、cat派生组165。

全部24个ROI可用，最少3个不同有效中心。每个ROI四中心和六组合都保留实际结果。对照、范围、真实位移标签和完整当前几何重建共7037项数值检查通过，全部12姿态的两个ROI交集为0。完整检查见 `DATA_QA.json`、`QA_CHECKS.json` 和 `FINAL_QA.json`。

## 方向与监督

cat/lion 两姿态的闭合且一致绕向组件用中心化有向体积确认外向。horse、camel、face、head 保留开放或非流形问题，用生成前固定的三轴真实网格视图确认可见外表锚点，再沿共享边恰两面且相反绕向的面片传播方向。camel 的其他小面片保留未锚定身份，全部实际损坏影响面均落在已确认面片。源 OBJ vn 与几何法向的局部反向计数原样保留，位移使用面积加权几何法向。

开放网格方向属于人工几何解释依据。全局三角自交尚未验证，局部翻面采用新旧三角叉积点积检查。12组固定正常/凹陷局部对照与12组来源三轴图均已实看，`cat_pose1_roi0_c0_r1_a2` 代表图保留其翻面失败。部分箭头标签延伸出裁剪边界，实际坐标、法向与位移检查独立留痕。原图位于 `private/views/`。

正常天然凹陷保持合成任务阴性。9216个ROI点行中有{concave}个按邻点均值偏移诊断为天然凹部，{covered}个点行在至少一次矩阵中发生真实位移。该统计按姿态与ROI计数，包含同一网格跨姿态重复观察。完整源点的全尝试/可用损坏频次位于 `private/qa/`，中心归一化空间分布和ROI交并见 `DATA_QA.json`。

每姿态原完整网格仅保存一份解析数组，原始字节作为来源证据另存。每观察保存局部当前位置及源点映射。`data_io.read_current` 重建完整当前几何，仅返回 vertices、faces、region_source_ids、mesh_id、pose_id。正常坐标、真实delta、位移模长、mask单独放在 `private/supervision/`，通过独立监督入口读取。编码器和候选选择器前向均为0。

## 抽样与尺度审计

单次 PCG64 seed1729 模拟保存1200×1024行。每步512个配对事件，按开发派生组、网格、姿态、有效ROI和有效损坏组合逐层均匀，再均匀抽F源点。每配对同时输出正常与受损两行，源点映射相同，随机交换两状态顺序。正常614400行、受损614400行，逐步和全局均为50/50，验证进入0。

独立保存索引检查核对全部1228800行的配对端点与SPLIT归属，中心曝光改用网格/姿态/ROI/源点的完整身份。逐层条件曝光、期望概率、实测来源曝光和正常逻辑重复权重见 `SAMPLER_AUDIT.json` 与 `SAMPLER_VERIFY.json`。开发正常物理观察16份，逻辑曝光614400次。正标签期望比例为{sampling['expected_positive_label_fraction']:.8f}，实际为{sampling['actual_positive_label_fraction']:.8f}。未来pos_weight与归一化尚未拟合。

`DATASET_INDEX` 原尺度字段使用冻结PLAN规定的未扰动姿态bbox与中心。另以完整受损当前几何、当前中心和官方 `0.05*bbox_diagonal` 重新统计576行，记录于 `CURRENT_GEOMETRY_QA.json`。当前半径/编码器半径范围为{low('radius_over_current_encoder_radius'):.6f}–{high('radius_over_current_encoder_radius'):.6f}，深度比为{low('depth_over_current_encoder_radius'):.6f}–{high('depth_over_current_encoder_radius'):.6f}，邻域中真实受损点比例为{low('current_encoder_neighborhood_damaged_fraction'):.6f}–{high('current_encoder_neighborhood_damaged_fraction'):.6f}。这些是几何尺度诊断，模型前向为0。

## 执行与成本

六包HTTP正文合计{costs['archive_HTTP_body_bytes']}字节，约{costs['archive_HTTP_body_bytes']/1024**2:.3f} MiB。另保存来源页8827字节。数值阶段受监控墙钟合计{costs['numerical_monitored_wall_s']:.3f}秒，计入临时只读命令墙钟上界后为{costs['numerical_budget_accounting_upper_s']:.3f}秒，上限1800秒。全部监控阶段树CPU合计{costs['monitored_tree_CPU_s']:.3f}秒，最大实测同时树RSS为{costs['max_sampled_simultaneous_tree_RSS_bytes']}字节。单线程、非独占正确性运行，进程发现间隔50ms，完整测量口径见 `COSTS.json`。

本批磁盘快照约{costs['new_disk_bytes_snapshot']/1024**2:.2f} MiB，上限2GiB。封存清单还记录最终各文件字节与SHA256。联网/解析阶段经历两次失败，先是reference扩展名识别，再是codec拼写；旧脚本、错误和原报告均保留，已下载的horse与来源页直接复用。矩阵执行一次，抽样模拟一次。随后代码审查补充通用方向回退、缺额登记与抽样身份守卫，原已执行生成器与抽样器保存在 `private/recovery/`，本批数据值与抽样索引均保持原执行结果。

训练0、模型前向0、修复输出0、Blender动作0、产品改动0、付费调用0。任务登记后的总墙钟、编写/读取/视图检查及工具等待的残余墙钟单列，初始化读取与短暂未发现进程的CPU仍未测。全部写入限于本批目录。

## 使用与出口

`acquire.py` 获取并解析六包，`freeze_plan.py` 生成固定来源/划分/PLAN，`generate.py` 运行单矩阵，`data_io.py` 提供重建入口，`sampler.py` 提供后续抽样API，`simulate.py` 保存固定索引，`qa.py`、`verify_sampling.py`、`current_qa.py` 执行审计。已有输出的生成与抽样入口会保留现有证据并拒绝覆盖。工作树运行时版本和只读依赖路径见 `RUNTIME.json`。

在当前工作树中可直接检查一个完整当前观察。

```powershell
& 'verification/m6_shape_train_001/private/venv/Scripts/python.exe' -I -B -X utf8 'verification/m6_perception_data_001/data_io.py' face_reference_roi0_c0_r1_a2
```

加 `--output` 可导出仅含当前几何、拓扑与F映射的NPZ。后续调用 `PairedStateSampler(dataset, seed=1729).sample_step()` 返回1024行的配对索引。获取与生成的重新执行需使用独立的空输出证据目录和匹配的只读运行时依赖，并保留该次独立运行记录。

本批数据工程验收通过，泛化质量仍待后续验证。该来源只覆盖动物及面部/头部，预训练重合未知，独立最终测试集缺失，商用资产及网格再分发授权尚未确认。唯一下一建议是独立复核通过后，再另冻合同，对同一冻结编码器和同一头进行一次配对状态监督优化，并保留旧权重在相同新验证数据上的对照。本批固定提交后回报一次并结束等待复核。
'''
    (HERE/"REPORT.md").write_text(text,encoding="utf8",newline="\n")


if __name__=="__main__":
    main()
