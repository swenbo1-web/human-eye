# 支撑平面只读纠偏候选

新函数 `solve_support_plane_candidate(scene, request, *, expected_feature_signature=None)` 消费世界米制快照，提出最多一次零旋转平移，既不读写Blender，也不创建执行段。旧 `solve_clearance_candidate` 的世界轴箱体合同保持。

```python
from human_eye_plugin.support_plane_candidate import solve_support_plane_candidate

result = solve_support_plane_candidate(scene, {
    "focal_id": current_focal_id,
    "reference_id": current_reference_id,
    "reference_triangle_index": selected_original_triangle_index,
    "direction_world": [0.0, 0.0, 1.0],
    "target_clearance_m": 0.001,
    "clearance_tolerance_m": 1e-7,
    "max_step_translation_m": 0.01,
    "max_total_translation_m": 0.04,
})
```

对象与面索引必须属于输入快照；没有固定通用的“第2面”。参考面是调用者明确选择的原始有向三角面。函数不会拟合包围盒面、补凸包或自动切换到相邻三角／凹槽内壁。方向必须是三个有限非布尔数字，非零有限长度，由SDK归一化；允许计算结果沿相反方向纠偏。两个限额约束本次候选欧氏长度，max_total只是本次上限，不意味着已实现累计执行账本。接口没有max_steps或max_duration。

## 距离与候选证明

两个网格须通过精确原始半空间凸性、闭合有向单壳拓扑、单连通面邻接和正体积检查。每对网格分别最多64顶点/128三角面，整个输入最多2048顶点/4096三角面；另保留原有几何工作准入门。Fraction输入分子／分母位长上限512，中间精确运算由这些输入及网格上限有界，不能把512解释为所有中间量的位数。

使用已表示binary64坐标的精确有理数叉积、点积和重心符号。参考全部点须处于所选面的内半空间，焦点最低支持点须严格在外侧，且至少一个最低支持顶点的正交垂足位于该原始有限三角闭域。边和顶点上的见证可合法；面外一个ULP也不会被目标公差抹平。距离下界因此有原始表面上的可达见证。

令该单位法线为n、当前间隙g、归一化方向d，理论纯平移满足g(t)=g+t(n·d)。充分非平行时求t=(目标-g)/(n·d)，再按限幅裁剪。近平行阈值为abs(n·d)<1e-8；目标0在本阶段明确unsupported，另留专门接触合同。

理论值不代替候选验证。函数对返回平移生成虚拟binary64顶点与pivot，重新检查精确凸性／半空间／垂足和支持顶点集合，并用原严格几何内核分别核对当前与候选距离。一致性容差由局部几何ULP推导，硬上限1e-10米，独立于用户目标公差和巨大的世界原点。每个虚拟顶点的浮点位移也受硬预算限制；舍入超限最多8轮保守收缩，无法改善则停止。

`candidate_clearance_m`和`actual_max_vertex_translation_m`描述虚拟候选的浮点几何，不是Blender真实提交或回读。候选端特征切换、垂足越界、无法数值认证或严格内核未知均不会返回可用候选。goal_satisfied表示输入局部几何已在调用者公差内，零候选；不认证完整用户任务。

## 结果与限制

- `current_certificate`／`candidate_certificate`：所选原始面、最低支持顶点集合、见证、精确重心权重及浮点间隙。对外见证点是有理几何的浮点展示，不声称其坐标没有舍入。
- `current_strict_geometry`／`candidate_strict_geometry`：既有严格内核结果，不能与独立物理真值混同。
- `directional_derivative`、`predicted_plane_clearance_m`：理论线性模型；实际候选间隙另列。
- `feature_signature`：绑定参考完整几何和面索引、焦点拓扑和最低支持顶点、方向。它不绑定焦点形状、对象实例或外部编辑，不能充当跨步执行门。
- `candidate`仅在通过上述检查且虚拟残差确有减少时给出。invalid request仍抛ValueError；超出几何支持域为unsupported，资源／严格内核未知为unknown，数值无进展为precision_floor，特征改变为feature_changed。

所有结果的execution_authority、whole_scene_collision_certified、swept_path_certified及task_success_certified恒为false。第三个障碍、宿主精度／实例／版本和连续路径不由局部距离证书解决。任意多轴旋转后的近共面折面可能因实际浮点坐标并非严格凸而被拒绝；本阶段不通过放宽谓词来提高支持率。
