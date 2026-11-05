# CF 第二阶段实现与验收

协议固定为 `CF_ACCEPTANCE_PROTOCOL.md` SHA256 `740662fe75aa1108cd0fc580024fa3ffb813b16677b1300274ad05c111dbdb43`。CF 使用已验收的 RB、BC、TD、VG 和 AO。VG 接线由主干先行交付。S 按协议单独留待验收。

## 运行路径

`human_eye_fast/cerebellar_flash.py` 提供线性及二次读出、精确最近邻排序和两个独立经验环。V 将当前见证及索引遮挡几何转换为 16×5 摘要，再经 VG 回调提交完整规范索引排列。F 使用 VG 原生默认路径，R 查询 V 经验库，L 只使用训练得到的权重。V 在线反馈只给实际呈现方向加可用标签。A 从当前网格、见证和已知有限动作提取 23 维，复用同一次局部见证三角对距离，输出米制残差校正。两个头分别在真实反馈到达后更新。环的写入序号决定覆盖位置及检索同分顺序。

冻结基线保留为独立核对代码。生产几何特征位于 `human_eye_fast/_cf_features.py`，无需导入夹具、验证模块或评估记录。基准中的 C 只处理命令分组，G 只对当前见证三角施加有限动作，学习臂的 PCA、分桶及其余特征只计入学习臂。所有 A 主样本的标签均来自 `BlenderControl` 实际执行及动作后的原生 RB/BC 回读。

## 执行与证据

从仓库根目录执行以下命令。正式输出目录需要是新的路径。

```powershell
$cfPy = 'D:\human eye\venv\Scripts\python.exe'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
& $cfPy -B -m unittest verification.test_cerebellar_flash verification.test_cf_training -v
& $cfPy -B verification/benchmark_cerebellar_flash.py --phase smoke --out artifacts/cf/stage2_smoke_003
& $cfPy -B verification/benchmark_cerebellar_flash.py --phase all --out artifacts/cf/formal_001
```

阶段分别保存 `source.zip`、`source.json`、输入白名单与摘要、实际输入记录、原生进程日志及输出身份。独立 Blender 后台进程串行运行。Pillow 在 venv 子进程读取实际 PNG 并复核紧凑的底图像素、相机及独立裁剪网格证据。正式目录按 seed 保存训练/验证标签、四配置、验证渲染、封存文件、独立留出 PNG、原生逐射线和动作记录、诊断、计时及生命周期。训练 worker 只收两个训练数组文件。全部 seed 封存后，驱动程序才物化 evaluation 和 diagnostic。

视角训练标签保留逐候选真实 PNG，学习分数的安全正例同时要求像素合格与原生停止。真实全失败时保留 F 的原始顺序与回退语义，R/L 的同分顺序按冻结协议。留出三臂均独立测其真实输出。只有全部观察臂均无成功时，封闭评分器才枚举各方向判断该几何是否存在可见解。真值与核验结果都留在评分目录。

正式计时的 F/R/L 同时涵盖真实 VG/AO 和 A 的动作前后采集、图像、读回与 Outcome。R/L 向独立影子对象写入反馈，L 同时更新权重。评估模型及库保持冻结，计时后以 PNG 摘要、帧、目标、见证与计数核对所复放的 V 反馈。另用单独部署对象跑两步 prequential，记录实际 PNG 独立评分、真值、真实更新和下一次查询。容量、常驻字节、额外分配与进程 RSS 在独立便携进程中采集。

阶段二第一轮烟测中，25×25 审计网格未能稳定检出 CF 小内腔模型的错误剖切。保持原两例 CF 正烟测，剖切负例改用已有 VG 验收的第 20 号闭合壳体，保证错误面在网格上可观察。复跑通过实际错切、漏切、错帧、错对象、篡改射线及擦除见证等负例。首轮源码和原始失败日志位于 `artifacts/cf/stage2_smoke_001`，通过的复跑位于 `stage2_smoke_002`。

正式运行在三个 seed 封存后进入留出。首个 seed 20261105 已写完 60 条 A 主记录和每个 V 臂的 60 条主记录，随后首个零间隙控制触发 Pillow worker 的 NumPy 布尔值序列化错误。原始日志、媒体、记录、快照和输入摘要保留在 `formal_001/20261105/evaluation`。修正零间隙布尔值的传输类型后，`--phase complete-evaluation` 先按已归档的摘要读取并核对原主记录，继承其数值与图像，再仅完成控制、诊断、独立在线步骤以及后两个 seed 的首次留出。首个 seed 的续做证据位于 `evaluation-completion`。三个主评估配置、模型和训练库仍使用续做前已封存的原件。续做后依次执行 `--phase performance`、`--phase memory` 和 `--phase report`。

## 正式结果

实施端报告 `artifacts/cf/formal_001/summary.json` 的结论为 **PASS**，所有 L 部署门均满足。每个 seed 每头 60 个留出 group。V 的 F、R、L 每臂每 seed 都有 60 幅公开 PNG 通过。整链参考动作预测器按 validation 冻结为 G。A 质量门每 seed 按 C/G 的更低留出 MAE 独立计算。

| Seed | V 射线中位 F / R / L | L/F | A 最强基线 → L MAE（mm） | A 比值 | L/F p95 整链 / V / A |
| --- | ---: | ---: | ---: | ---: | ---: |
| 20261105 | 24 / 19.5 / 13 | 0.542 | G 0.506899 → 0.169300 | 0.334 | 1.014 / 1.008 / 1.021 |
| 79463 | 25 / 14 / 13 | 0.520 | G 0.551885 → 0.256948 | 0.466 | 1.027 / 1.042 / 1.008 |
| 310519 | 23 / 14 / 13 | 0.565 | C 0.981212 → 0.368290 | 0.375 | 1.021 / 1.020 / 0.989 |

R 的 seed 20261105 射线比为 0.8125，高于 0.75 门。R 的另两个 seed 满足射线与像素门。V 零权重消融逐 seed 射线比均为 1.000；打乱监督消融为 0.542、2.300、1.152，其中首 seed 与训练臂同中位数。A 打乱监督的 MAE 在每个 seed 都高于 L。10,000 次按 seed 分层的配对 bootstrap 得到 L pooled V 射线比 0.542，95% 区间 [0.520, 0.591]，A MAE 比 0.382，区间 [0.291, 0.513]。整链 pooled p95 为 56.940→58.186 ms，比值 1.022，区间 [1.006, 1.031]。

72 个原生控制、21 个封存动作诊断、6 个独立顺序反馈步骤、每 seed 9 个 V 和 5 个 A 负例均通过。两经验环的 0/1/4096/4097 条压力、覆盖、会话隔离及释放通过。14 项便携单测和最终原生烟测通过，最终烟测证据在 `artifacts/cf/stage2_smoke_003`。GPU 环境为 RTX 3060、OpenGL 和 Blender 5.2.3 LTS，三次正式性能进程依序独占窗口。

逐组射线、真实 PNG、A 前后 AO、原生 Outcome、相机/剖切证据、选择快照、完整计时原样本、训练来源和冷/热内存见正式目录。主干独立复核及后续 CF 阶段待主干接手。S 尚待单独验收。
