# RB-B 原生 Blender 采集

## 调用与生命周期

```python
from human_eye_fast.blender_resident_bridge import BlenderResidentBridge, MeshChange

bridge = BlenderResidentBridge()
graph = bpy.context.evaluated_depsgraph_get()
scale = bpy.context.scene.unit_settings.scale_length
first = bridge.capture("part-a", obj_a, graph, scale)
second = bridge.capture("part-b", obj_b, graph, scale)

# 在调用方修改对象后，取得本批当前 depsgraph，再捕获声明了变化的对象。
graph = bpy.context.evaluated_depsgraph_get()
current = bridge.capture(
    "part-a", obj_a, graph, scale,
    MeshChange.VERTICES | MeshChange.TRANSFORM | MeshChange.APPEARANCE,
)
```

首次传入 ID 时建立缓存。`get(id)` 读取已有描述符，`remove(id)` 删除单对象缓存，`clear()` 删除全批缓存，`len(bridge)` 返回当前缓存条数。调用方串行更新，按对象声明相对上次捕获的全部变化。`NONE` 直接返回缓存，`VERTICES` 刷新全部局部及世界顶点，`TRANSFORM` 刷新矩阵及世界顶点，`UNITS` 用保留的原生 float32 顶点和当前矩阵重新换算。`APPEARANCE` 更新外观。`TOPOLOGY` 重建本对象全部缓存，并应用本次捕获的顶点、变换、单位和外观。四边形和 n-gon 变形可能改变最终三角剖分，即使顶点数和面数不变，也需声明 `TOPOLOGY`。

返回 RB-A `ResidentMesh`。`local_m`、`world_m` 为 `(N, 3)` float64，`world_from_local` 为 `(4, 4)` float64，`triangles` 为 `(T, 3)` int32。米制变换保留原线性部分，平移乘 `scale_length`。稳定拓扑保留这四个数组视图的身份。数组由采集器持有并以只读视图借出，更新时可能原位变化。调用方需要跨次捕获保留快照时自行复制。重建、删除和清空后，仍被调用方持有的旧数组由 NumPy 保持有效。

`appearance` 为 `BlenderAppearance`。`object_color` 为对象 RGBA，`material_slots` 为按槽顺序排列的 `(槽名, diffuse RGBA)` 或空槽 `None`，`polygon_material_indices` 为逐多边形 int32 索引，`triangle_polygon_indices` 为逐三角 int32 多边形索引。三角材质可用 `appearance.polygon_material_indices[appearance.triangle_polygon_indices]` 取得。范围限于求值后的 Mesh 组件及上述外观元数据。

读取求值对象的 `data`，在捕获调用内复制所需数据。Blender 更新依赖图时可使先前的 evaluated 数据引用失效，因此缓存只保存自有数组及普通 Python 外观值。调用方在开始捕获前使同批 depsgraph 处于当前状态。后台性能计时包含这次求值。 [Blender 5.2 Depsgraph API](https://docs.blender.org/api/5.2/bpy.types.Depsgraph.html)

坐标从 `position` 属性批量读入自有 float32 缓冲，float64 乘法同时做类型转换和单位转换。材质索引从 `material_index` 属性读取，属性缺省时逐面索引为零。有效全三角网格按 `.corner_vert` 顺序读取连接，每三条 corner 对应一个三角面并生成面索引。混合面、四边形和 n-gon 读取 Blender 的 `loop_triangles` 和 `loop_triangle_polygons`。全三角分支仅在建立或重建拓扑时判定。 [Blender 5.2 属性说明](https://docs.blender.org/manual/en/5.2/modeling/geometry_nodes/attributes_reference.html) [实测版本的 Blender 三角剖分源码](https://github.com/blender/blender/blob/e13b728c6880/source/blender/blenkernel/intern/mesh_tessellate.cc)

## 作者验证

测试和测量按照 [RB-B 冻结协议](RB_B_ACCEPTANCE_PROTOCOL.md) 执行。

```powershell
# 在仓库根目录执行。复验时指定独立 --seed 和 --output。
$blender = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
& $blender --background --factory-startup --python-exit-code 1 `
    --python verification/test_blender_resident_bridge.py
& 'D:\human eye\venv\Scripts\python.exe' -B verification/benchmark_blender_resident_bridge.py `
    --blender $blender --seed 31871 --output artifacts/rb_b/author.json
```

基准启动三个串行的独立 Blender 后台进程。每进程每档有两对象、五次预热和三十一次交错样本，两条路径交换先后顺序，且在每条路径开始前对称恢复预状态并初始化常驻缓存。每步从 Blender 属性写入后开始计时，包含本步各自的依赖图求值和两对象的输出准备。直接基线通过 `to_mesh()`、标准顶点/面/三角集合的 `foreach_get`、`to_mesh_clear()` 实现相同字段，使用预分配常驻坐标和变换缓冲。稳定拓扑不重读索引，无变化不复制数组。原始样本含每步耗时、完整八步和、先后顺序、相位、复制量及独立的拓扑增减样本。

环境为 Blender 5.2.3 LTS（`e13b728c6880`）、内置 Python 3.13.13、NumPy 2.3.4，Windows 主机 Intel Core i7-10700 @ 2.90 GHz、16 逻辑 CPU。启动器将 OpenBLAS、MKL、BLIS、OpenMP 和 Accelerate 的线程环境变量设为 `1`。Blender 原生依赖图线程由其后台进程配置管理。

冻结协议提交 `954f572d56e44aa3f178d2135bd050606ca402b6`。实测文件 SHA-256 如下。

| 文件 | SHA-256 |
| --- | --- |
| `human_eye_fast/blender_resident_bridge.py` | `f2cbeb79218e68b1506423392f77878e489fc797b001e187249b659c0aaf124d` |
| `verification/test_blender_resident_bridge.py` | `97a678bc4c564b39a9239ad654aa21c707bdaf78331f6be09e064666d0266ddb` |
| `verification/benchmark_blender_resident_bridge.py` | `6ed2dbccafc4a93bd14c01cfb6437a6a85dbb26feeddfd31521c05d9651591e3` |

### 完整八步的数组写入量

下表按两对象合计，`100×100` 每对象为 10,000 顶点、19,602 三角，`300×300` 为 90,000 顶点、178,802 三角。表内为可观察的逻辑写入字节，和物理内存总线流量有区别。每步明细及拓扑增减的复制量见原始 JSON。

| 写入项 | 100×100 字节 | 300×300 字节 |
| --- | ---: | ---: |
| RNA → 自有 float32 坐标暂存 | 840,000 | 7,560,000 |
| 类型与单位转换 → 自有 float64 局部数组 | 2,160,000 | 19,440,000 |
| 世界数组写入，含矩阵乘法及原位加平移各一次 | 5,280,000 | 47,520,000 |
| 矩阵写入，含平移单位换算 | 1,216 | 1,216 |
| RNA → 自有三角连接 | 470,448 | 4,291,248 |
| 三角到多边形映射，基线 RNA 读取、候选生成 | 156,816 | 1,430,416 |
| RNA → 逐多边形材质索引 | 470,448 | 4,291,248 |

两条路径的转换均读取 `1,080,000 / 9,720,000` 字节的 float32 坐标。每条路径还写入六个对象级外观描述符及其槽数据。基线每个完整序列创建并释放九次额外 Blender 临时网格，候选为零。Blender 内部共享缓冲、分配与复制字节量及 Python 元数据堆大小未测。速度收益包含批量属性读取和全三角路径省去的剖分及三角映射读取成本。

### 作者结果

五项 Blender Object Mode 测试全部通过。基准在计时前使用逐元素读取 `to_mesh()` 的独立 oracle 核对两档、两个相位及全部八步。两路径相对同一 Blender float32 求值，局部数组和米制矩阵逐元素相等，世界坐标最大绝对误差为 `8.88e-16 m`。三角及外观分类字段精确相等。与未量化解析输入相比，100×100 和 300×300 两档的局部坐标最大绝对误差分别为 `1.140e-7 m`、`1.141e-7 m`，世界坐标分别为 `2.694e-7 m`、`3.260e-7 m`，混合量纲的矩阵元素最大绝对差为 `7.379e-8`、`9.178e-8`。

| 网格 | 统计量 | 基线 ms | 候选 ms | 候选 / 基线 | 冻结门值 |
| --- | --- | ---: | ---: | ---: | ---: |
| 100×100 | 进程 0 中位数 | 39.017 | 19.724 | 0.506 | ≤0.80 |
| 100×100 | 进程 1 中位数 | 36.307 | 18.436 | 0.508 | ≤0.80 |
| 100×100 | 进程 2 中位数 | 35.000 | 18.127 | 0.518 | ≤0.80 |
| 100×100 | 93 样本合并 p95 | 42.466 | 21.318 | 0.502 | ≤1.20 |
| 300×300 | 进程 0 中位数 | 241.871 | 99.023 | 0.409 | ≤0.80 |
| 300×300 | 进程 1 中位数 | 256.328 | 104.227 | 0.407 | ≤0.80 |
| 300×300 | 进程 2 中位数 | 238.314 | 98.351 | 0.413 | ≤0.80 |
| 300×300 | 93 样本合并 p95 | 277.384 | 115.555 | 0.417 | ≤1.20 |

拓扑增减另列合并中位数（基线 → 候选）。100×100 增加 `20.665 → 10.664 ms`、减少 `19.019 → 10.199 ms`。300×300 增加 `137.717 → 59.193 ms`、减少 `136.448 → 58.932 ms`。

作者正式验收一次通过。`artifacts/rb_b/author.json` 汇总并内嵌全部样本，`author.process-0.json`、`author.process-1.json`、`author.process-2.json` 为各进程原始输出，`author-verify.json` 为仅正确性的预跑。100×100 单独的变换和单位步骤中位数分别为 `0.578 → 0.665 ms`、`0.771 → 0.825 ms`，冻结门针对完整序列。性能结果适用上述有效全三角网格，四边形等非三角网格覆盖正确性。Edit Mode、其他 Blender 版本和整链性能待验。RB-B 放行由主对话对最终版本换种子独立复验后决定。
