# M4-ACTIVE-COVERAGE-003 静态准入清单

依据计划 SHA256 `bf8506eea83482f4fc31e81c098102eda5b1b9986ef46ba86474c0196874d0a7`。本清单先核源码，真实资格由根统一启动。审查方执行 probe、engine、算法资格、渲染和基准的次数均为 0。

## 启动与来源

- 唯一 child 可执行文件为计划固定的直接 base Python，启动前核路径和 SHA256。
- 保留 `-I -B -X utf8`，bootstrap 显式加入原 venv site-packages，并经同一入口进入 probe 或正式 runtime。
- 明确冻结 base exe、bootstrap、launch、probe、资格器、控制器、runtime、validator、输入与既有产品源码。控制器解释器单独记录。
- 正常 probe 与正式 runtime 使用同一依赖绑定逻辑，记录实际 NumPy/PIL 路径、版本、初始化文件摘要、固定产品来源及真实 prefix。
- 固定 run 标识、输出目录与 Popen PID 严格绑定实际 child，旧 002 的 PID 谱系保持 unknown。

## 四个一次性无图资格

- 独占资格预留在首个 child 启动前落盘。每项仅一次实际调用，失败和未运行保留原分母。
- normal 真实导入同依赖，完整回读并核 PID、run、目录、来源和正常退出。
- nonzero 产生确定性异常，原始退出状态和 stderr 保留，资格器将预期失败作为该 probe 的成功条件。
- timeout 先收取且核验当前 child 握手，再在登记时界内确认其等待，超时通过原 Popen 句柄 kill 并有界 wait，记录真实退出。
- receipt_failure 先执行一次独占无害 marker 动作，再故意缺失或损坏回执。实际 marker 计数和回执拒绝均须成立，流程不自动补跑。
- 所有路径共用同一 launch/bootstrap/依赖与句柄回收逻辑，不使用裸 PID 杀进程。清理或生命周期状态未知即停止。
- probe 不读取 geometry/camera，不调用几何 index 或 raster。四项真实均合格后才允许正式批。
- 资格前源码固定。资格与正式批逐字复用已资格源码，不在两者间修实现。

## 正式接线与成本

- 保留 002 几何、像素、发布和回读语义。child 只读允许的旧源码，旧图像与答案仅允许 parent 在 child 完成后作原封后验对照。
- 6 对主槽与 2 个控制槽预先固定，AB/BA 交替，失败立即停止余槽，无替补。
- 正式每槽通过同一直接 base 启动。计时自 Popen 前开始，退出、所有原件读取和校验后结束。
- 正式路径不执行 probe 选择逻辑。共同来源核验及准入门明确归入 parent/setup 或每槽成本，资格成本单列。
- B 主流程需要第三张图时于实际 render 之前拒绝。主最多 48 次，控制最多 12 次，新批合计最多 60 次，连同旧 002 六次累计最多 66 次。未知次数保留 unknown 与已知下界。
- BACK64 控制保留实际像素不足历史和后续真实增量，最终像素不足仅计仍未覆盖区域。
- 严格完成与内容回读分别记录。全部配对完整且来源正确后才计算完整主槽 B/A 比值中位数，未运行不估算。

## 静态收口

待作者停更后一次核对最终 launch、bootstrap、probe、qualification、runtime、validator、runner 与冻结清单及资格到正式门。最终静态结论另存，真实资格和正式结果随后仅依既存原件复核。
